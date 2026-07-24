from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import qrcode
from django.contrib.auth import get_user_model
from django.test import (
    RequestFactory,
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from qrcode.constants import ERROR_CORRECT_H

from apps.accounts.models import SalonManager
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_qr import (
    BOOKING_QUICK_LINK_QR_BORDER_MODULES,
    BOOKING_QUICK_LINK_QR_GLYPH,
    BOOKING_QUICK_LINK_QR_LOGO_RATIO,
    BOOKING_QUICK_LINK_QR_MIN_PIXELS,
    build_booking_quick_link_qr_filename,
    generate_booking_quick_link_qr,
)
from apps.salons.models import Salon
from apps.services.models import Services


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["loomera.test"],
)
class BookingQuickLinkQRServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09129995001",
            password="test-pass-123",
            name="مدیر",
            family="کیوآر",
        )

        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="Karino",
            salon_manager=cls.manager,
            is_active=True,
        )

        cls.service = Services.objects.create(
            service_name="خدمت QR",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )

        cls.salon.services.add(cls.service)

    def create_quick_link(self, **overrides):
        values = {
            "creator": self.manager_user,
            "salon": self.salon,
            "service": self.service,
            "mode": BookingQuickLink.Mode.SERVICE,
            "placement": (
                BookingQuickLink.Placement.TABLE_STAND
            ),
            "campaign_name": "کمپین QR",
            "is_permanent": True,
            "payload": {
                "mode": BookingQuickLink.Mode.SERVICE,
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": None,
                "date": "",
                "time": "",
                "summary": {},
            },
        }

        values.update(overrides)

        return BookingQuickLink.objects.create(
            **values
        )

    def build_request(self):
        return RequestFactory().get(
            "/",
            secure=True,
            HTTP_HOST="loomera.test",
        )

    def test_png_is_print_sized_and_has_white_background(self):
        quick_link = self.create_quick_link()

        generated = generate_booking_quick_link_qr(
            request=self.build_request(),
            quick_link=quick_link,
        )

        self.assertEqual(
            generated.content_type,
            "image/png",
        )

        self.assertTrue(
            generated.content.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )

        with Image.open(
            BytesIO(generated.content)
        ) as image:
            image.verify()

        with Image.open(
            BytesIO(generated.content)
        ) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreaterEqual(
                image.width,
                BOOKING_QUICK_LINK_QR_MIN_PIXELS,
            )
            self.assertEqual(
                image.width,
                image.height,
            )
            self.assertEqual(
                image.convert("RGB").getpixel((0, 0)),
                (255, 255, 255),
            )

        self.assertEqual(
            generated.width,
            generated.height,
        )

    def test_qr_uses_h_correction_and_four_module_border(self):
        quick_link = self.create_quick_link()

        with patch(
            "apps.orders.quick_link_qr.qrcode.QRCode",
            wraps=qrcode.QRCode,
        ) as qr_class:
            generated = generate_booking_quick_link_qr(
                request=self.build_request(),
                quick_link=quick_link,
            )

        qr_class.assert_called_once()

        kwargs = qr_class.call_args.kwargs

        self.assertEqual(
            kwargs["error_correction"],
            ERROR_CORRECT_H,
        )

        self.assertEqual(
            kwargs["border"],
            BOOKING_QUICK_LINK_QR_BORDER_MODULES,
        )

        self.assertEqual(
            generated.error_correction,
            ERROR_CORRECT_H,
        )

        self.assertEqual(
            generated.border_modules,
            4,
        )

    def test_qr_url_is_exact_public_booking_quick_link_url(self):
        quick_link = self.create_quick_link()
        request = self.build_request()

        generated = generate_booking_quick_link_qr(
            request=request,
            quick_link=quick_link,
        )

        expected_url = request.build_absolute_uri(
            reverse(
                "orders:quick_booking_entry",
                kwargs={
                    "token": str(quick_link.token)
                },
            )
        )

        self.assertEqual(
            generated.url,
            expected_url,
        )

    def test_official_glyph_is_composited_in_center(self):
        quick_link = self.create_quick_link()

        generated = generate_booking_quick_link_qr(
            request=self.build_request(),
            quick_link=quick_link,
        )

        self.assertEqual(
            generated.glyph_static_path,
            BOOKING_QUICK_LINK_QR_GLYPH,
        )

        self.assertLessEqual(
            generated.logo_width_ratio,
            BOOKING_QUICK_LINK_QR_LOGO_RATIO,
        )

        with Image.open(
            BytesIO(generated.content)
        ) as image:
            image = image.convert("RGB")

            radius = max(
                8,
                int(image.width * 0.04),
            )

            center_x = image.width // 2
            center_y = image.height // 2

            center_crop = image.crop(
                (
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                )
            )

            has_colored_glyph_pixel = any(
                (
                    abs(red - green) > 8
                    or abs(green - blue) > 8
                    or abs(red - blue) > 8
                )
                and (red, green, blue)
                not in {
                    (255, 255, 255),
                    (17, 17, 17),
                    (0, 0, 0),
                }
                for red, green, blue
                in center_crop.getdata()
            )

        self.assertTrue(
            has_colored_glyph_pixel,
            msg=(
                "No colored official Loomera glyph pixel "
                "was found in the QR center."
            ),
        )

    def test_readable_filename_contains_salon_placement_and_link_id(self):
        quick_link = self.create_quick_link()

        filename = build_booking_quick_link_qr_filename(
            quick_link
        )

        self.assertEqual(
            filename,
            (
                f"loomera-karino-stand-"
                f"link-{quick_link.pk}.png"
            ),
        )

    def test_generation_does_not_write_to_media_storage(self):
        quick_link = self.create_quick_link()

        with TemporaryDirectory() as media_root:
            with override_settings(
                MEDIA_ROOT=media_root
            ):
                generated = generate_booking_quick_link_qr(
                    request=self.build_request(),
                    quick_link=quick_link,
                )

                written_files = [
                    path
                    for path in Path(media_root).rglob("*")
                    if path.is_file()
                ]

        self.assertTrue(generated.content)
        self.assertEqual(written_files, [])

    def test_inactive_expired_and_fixed_time_warnings(self):
        inactive_link = self.create_quick_link(
            is_active=False,
        )

        inactive_result = generate_booking_quick_link_qr(
            request=self.build_request(),
            quick_link=inactive_link,
        )

        self.assertTrue(
            any(
                "غیرفعال" in warning
                for warning in inactive_result.warnings
            )
        )

        expired_link = self.create_quick_link(
            expires_at=(
                timezone.now()
                - timedelta(minutes=1)
            ),
        )

        expired_result = generate_booking_quick_link_qr(
            request=self.build_request(),
            quick_link=expired_link,
        )

        self.assertTrue(
            any(
                "پایان" in warning
                for warning in expired_result.warnings
            )
        )

        fixed_link = self.create_quick_link(
            mode=(
                BookingQuickLink.Mode
                .SERVICE_STYLIST_TIME
            ),
            payload={
                "mode": (
                    BookingQuickLink.Mode
                    .SERVICE_STYLIST_TIME
                ),
                "salon_id": self.salon.pk,
                "service_ids": [self.service.pk],
                "stylist_user_id": 1001,
                "date": "2026-08-01",
                "time": "10:00",
                "summary": {},
            },
        )

        fixed_result = generate_booking_quick_link_qr(
            request=self.build_request(),
            quick_link=fixed_link,
        )

        self.assertTrue(
            any(
                "چاپ دائمی" in warning
                for warning in fixed_result.warnings
            )
        )
