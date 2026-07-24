from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from unittest.mock import patch

from apps.main.views import _support_rate_limited
from apps.main.forms import SupportForm, SupportTicketReplyForm


def _image_upload(
    *,
    name="proof.jpg",
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


def _animated_gif_upload(*, name="proof.gif", content_type="image/gif"):
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
    name="proof.pdf",
    content=b"%PDF-1.4\n% Loomera test PDF\n",
    content_type="application/pdf",
):
    return SimpleUploadedFile(name, content, content_type=content_type)


class SupportAttachmentSecurityTests(TestCase):
    def _support_form(self, uploaded_file):
        return SupportForm(
            data={
                "issue_type": "other",
                "email": "customer@example.com",
                "full_name": "کاربر تست",
                "city": "تهران",
                "mobile": "09123456789",
                "description": "شرح درخواست تست",
            },
            files={"attachment": uploaded_file},
        )

    def _reply_form(self, uploaded_file):
        return SupportTicketReplyForm(
            data={"body": "پاسخ تست"},
            files={"attachment": uploaded_file},
        )

    def assert_attachment_invalid(self, form):
        self.assertFalse(form.is_valid())
        self.assertIn("attachment", form.errors)

    def test_support_attachment_accepts_valid_jpeg(self):
        form = self._support_form(
            _image_upload(
                name="proof.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_support_attachment_accepts_valid_png(self):
        form = self._support_form(
            _image_upload(
                name="proof.png",
                size=(64, 64),
                image_format="PNG",
                content_type="image/png",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_support_attachment_accepts_valid_pdf(self):
        form = self._support_form(_pdf_upload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_support_attachment_rejects_gif_extension(self):
        form = self._support_form(
            _animated_gif_upload(name="proof.gif", content_type="image/gif")
        )

        self.assert_attachment_invalid(form)

    def test_support_attachment_rejects_gif_with_jpg_filename(self):
        form = self._support_form(
            _animated_gif_upload(name="proof.jpg", content_type="image/jpeg")
        )

        self.assert_attachment_invalid(form)

    def test_support_attachment_rejects_svg_extension(self):
        svg_file = SimpleUploadedFile(
            "proof.svg",
            b"<svg><script>alert(1)</script></svg>",
            content_type="image/svg+xml",
        )

        form = self._support_form(svg_file)

        self.assert_attachment_invalid(form)

    def test_support_attachment_rejects_invalid_content_type(self):
        form = self._support_form(
            _image_upload(
                name="proof.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assert_attachment_invalid(form)

    def test_support_attachment_rejects_fake_pdf(self):
        form = self._support_form(
            _pdf_upload(
                name="proof.pdf",
                content=b"not a pdf",
                content_type="application/pdf",
            )
        )

        self.assert_attachment_invalid(form)

    def test_support_attachment_rejects_pdf_with_image_content_type(self):
        form = self._support_form(
            _pdf_upload(
                name="proof.pdf",
                content=b"%PDF-1.4\n",
                content_type="image/jpeg",
            )
        )

        self.assert_attachment_invalid(form)

    @override_settings(SUPPORT_ATTACHMENT_IMAGE_MAX_DIMENSION=64)
    def test_support_attachment_rejects_too_large_image_dimension(self):
        form = self._support_form(
            _image_upload(
                name="proof.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assert_attachment_invalid(form)

    @override_settings(SUPPORT_ATTACHMENT_IMAGE_MAX_PIXELS=1000)
    def test_support_attachment_rejects_too_many_image_pixels(self):
        form = self._support_form(
            _image_upload(
                name="proof.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assert_attachment_invalid(form)

    @override_settings(SUPPORT_ATTACHMENT_MAX_SIZE_BYTES=100)
    def test_support_attachment_rejects_too_large_file(self):
        form = self._support_form(
            _image_upload(
                name="proof.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assert_attachment_invalid(form)

    def test_reply_attachment_rejects_gif_with_jpg_filename(self):
        form = self._reply_form(
            _animated_gif_upload(name="reply.jpg", content_type="image/jpeg")
        )

        self.assert_attachment_invalid(form)

    def test_reply_attachment_accepts_valid_pdf(self):
        form = self._reply_form(_pdf_upload(name="reply.pdf"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_support_rate_limit_cache_unavailable_fails_open_by_default(self):
        request = self.client.post(
            "/main/contact/",
            {
                "issue_type": "other",
                "email": "customer@example.com",
                "full_name": "کاربر تست",
                "city": "تهران",
                "mobile": "09123456789",
                "description": "شرح درخواست تست",
            },
        ).wsgi_request

        with patch(
            "django.core.cache.cache.get", side_effect=ConnectionError("redis down")
        ):
            self.assertFalse(_support_rate_limited(request))

        @override_settings(LOOMERA_SUPPORT_TICKET_RATE_LIMIT_FAIL_CLOSED=True)
        def test_support_rate_limit_cache_unavailable_can_fail_closed(self):
            request = self.client.post(
                "/main/contact/",
                {
                    "issue_type": "other",
                    "email": "customer@example.com",
                    "full_name": "کاربر تست",
                    "city": "تهران",
                    "mobile": "09123456789",
                    "description": "شرح درخواست تست",
                },
            ).wsgi_request

            with patch(
                "django.core.cache.cache.get", side_effect=ConnectionError("redis down")
            ):
                self.assertTrue(_support_rate_limited(request))
