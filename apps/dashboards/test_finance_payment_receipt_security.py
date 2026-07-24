from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from PIL import Image

from apps.dashboards.finance_withdrawal_views import (
    validate_finance_payment_receipt_upload,
)
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin
from apps.payments.models import StylistWallet, StylistWalletWithdrawalRequest


def _image_upload(
    *,
    name="receipt.jpg",
    size=(64, 64),
    image_format="JPEG",
    content_type="image/jpeg",
):
    buffer = BytesIO()
    image = Image.new("RGB", size, color=(240, 240, 240))
    image.save(buffer, format=image_format)
    buffer.seek(0)

    return SimpleUploadedFile(
        name,
        buffer.read(),
        content_type=content_type,
    )


def _animated_gif_upload(*, name="receipt.gif", content_type="image/gif"):
    buffer = BytesIO()

    frame_one = Image.new("RGB", (32, 32), color=(255, 0, 0))
    frame_two = Image.new("RGB", (32, 32), color=(0, 255, 0))

    frame_one.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=[frame_two],
        duration=100,
        loop=0,
    )
    buffer.seek(0)

    return SimpleUploadedFile(
        name,
        buffer.read(),
        content_type=content_type,
    )


def _pdf_upload(
    *,
    name="receipt.pdf",
    content=b"%PDF-1.4\n% Loomera receipt test\n",
    content_type="application/pdf",
):
    return SimpleUploadedFile(name, content, content_type=content_type)


class FinancePaymentReceiptSecurityTests(TestCase):
    def assert_receipt_valid(self, uploaded_file):
        self.assertIs(
            validate_finance_payment_receipt_upload(uploaded_file),
            uploaded_file,
        )

    def assert_receipt_invalid(self, uploaded_file):
        with self.assertRaises(ValidationError):
            validate_finance_payment_receipt_upload(uploaded_file)

    def test_receipt_accepts_valid_jpeg(self):
        self.assert_receipt_valid(
            _image_upload(
                name="receipt.jpg",
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

    def test_receipt_accepts_valid_png(self):
        self.assert_receipt_valid(
            _image_upload(
                name="receipt.png",
                image_format="PNG",
                content_type="image/png",
            )
        )

    def test_receipt_accepts_valid_pdf(self):
        self.assert_receipt_valid(_pdf_upload())

    def test_receipt_rejects_gif_extension(self):
        self.assert_receipt_invalid(
            _animated_gif_upload(name="receipt.gif", content_type="image/gif")
        )

    def test_receipt_rejects_gif_with_jpg_filename(self):
        self.assert_receipt_invalid(
            _animated_gif_upload(name="receipt.jpg", content_type="image/jpeg")
        )

    def test_receipt_rejects_svg_extension(self):
        self.assert_receipt_invalid(
            SimpleUploadedFile(
                "receipt.svg",
                b"<svg><script>alert(1)</script></svg>",
                content_type="image/svg+xml",
            )
        )

    def test_receipt_rejects_invalid_content_type(self):
        self.assert_receipt_invalid(
            _image_upload(
                name="receipt.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

    def test_receipt_rejects_fake_pdf(self):
        self.assert_receipt_invalid(
            _pdf_upload(
                name="receipt.pdf",
                content=b"not a pdf",
                content_type="application/pdf",
            )
        )

    def test_receipt_rejects_pdf_with_image_content_type(self):
        self.assert_receipt_invalid(
            _pdf_upload(
                name="receipt.pdf",
                content=b"%PDF-1.4\n",
                content_type="image/jpeg",
            )
        )

    @override_settings(FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_DIMENSION=64)
    def test_receipt_rejects_too_large_image_dimension(self):
        self.assert_receipt_invalid(
            _image_upload(
                name="receipt.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

    @override_settings(FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_PIXELS=1000)
    def test_receipt_rejects_too_many_image_pixels(self):
        self.assert_receipt_invalid(
            _image_upload(
                name="receipt.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

    @override_settings(FINANCE_PAYMENT_RECEIPT_MAX_SIZE_BYTES=100)
    def test_receipt_rejects_too_large_file(self):
        self.assert_receipt_invalid(
            _image_upload(
                name="receipt.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )


class FinancePaymentReceiptViewSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _make_pending_withdrawal(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        stylist = self.make_stylist()
        salon.stylists.add(stylist)

        wallet, _ = StylistWallet.objects.get_or_create(stylist=stylist)

        withdrawal = StylistWalletWithdrawalRequest.objects.create(
            wallet=wallet,
            salon=salon,
            amount=100000,
            iban="IR" + "1" * 24,
            account_holder_name="متخصص تست",
            bank_name="بانک تست",
        )

        return manager, withdrawal

    def test_manager_approval_rejects_invalid_receipt_and_keeps_pending(self):
        manager, withdrawal = self._make_pending_withdrawal()
        self.client.force_login(manager.user)

        response = self.client.post(
            reverse("dashboards:finance_stylist_withdrawals"),
            data={
                "withdrawal_id": str(withdrawal.pk),
                "action": "approve",
                "note": "تست رسید نامعتبر",
                "payment_receipt": _animated_gif_upload(
                    name="receipt.jpg",
                    content_type="image/jpeg",
                ),
            },
        )

        self.assertEqual(response.status_code, 302)

        withdrawal.refresh_from_db()
        self.assertEqual(
            withdrawal.status, StylistWalletWithdrawalRequest.Status.PENDING
        )
        self.assertFalse(withdrawal.payment_receipt)

    def test_manager_approval_accepts_valid_pdf_receipt(self):
        manager, withdrawal = self._make_pending_withdrawal()
        self.client.force_login(manager.user)

        response = self.client.post(
            reverse("dashboards:finance_stylist_withdrawals"),
            data={
                "withdrawal_id": str(withdrawal.pk),
                "action": "approve",
                "note": "تست رسید معتبر",
                "payment_receipt": _pdf_upload(name="receipt.pdf"),
            },
        )

        self.assertEqual(response.status_code, 302)

        withdrawal.refresh_from_db()
        self.assertEqual(
            withdrawal.status, StylistWalletWithdrawalRequest.Status.APPROVED
        )
        self.assertTrue(withdrawal.payment_receipt)
