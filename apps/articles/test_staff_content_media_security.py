from __future__ import annotations

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from apps.articles.forms import (
    StaffContentSubmissionForm,
    validate_staff_content_media_upload,
)
from apps.articles.models import StaffContentSubmission
from apps.dashboards.content_views import StylistDashboardContentSubmissionForm


def _image_upload(
    *,
    name="content.jpg",
    size=(64, 64),
    image_format="JPEG",
    content_type="image/jpeg",
):
    buffer = BytesIO()
    image = Image.new("RGB", size, color=(240, 240, 240))
    image.save(buffer, format=image_format)
    buffer.seek(0)

    return SimpleUploadedFile(name, buffer.read(), content_type=content_type)


def _animated_gif_upload(*, name="content.gif", content_type="image/gif"):
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

    return SimpleUploadedFile(name, buffer.read(), content_type=content_type)


def _mp4_upload(
    *,
    name="content.mp4",
    content=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
    content_type="video/mp4",
):
    return SimpleUploadedFile(name, content, content_type=content_type)


class StaffContentMediaValidatorSecurityTests(TestCase):
    def assert_media_valid(self, uploaded_file):
        self.assertIs(
            validate_staff_content_media_upload(uploaded_file),
            uploaded_file,
        )

    def assert_media_invalid(self, uploaded_file):
        with self.assertRaises(ValidationError):
            validate_staff_content_media_upload(uploaded_file)

    def test_media_accepts_valid_jpeg(self):
        self.assert_media_valid(
            _image_upload(
                name="content.jpg",
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

    def test_media_accepts_valid_png(self):
        self.assert_media_valid(
            _image_upload(
                name="content.png",
                image_format="PNG",
                content_type="image/png",
            )
        )

    def test_media_accepts_valid_webp(self):
        self.assert_media_valid(
            _image_upload(
                name="content.webp",
                image_format="WEBP",
                content_type="image/webp",
            )
        )

    def test_media_accepts_valid_mp4(self):
        self.assert_media_valid(_mp4_upload())

    def test_media_rejects_gif_extension(self):
        self.assert_media_invalid(
            _animated_gif_upload(name="content.gif", content_type="image/gif")
        )

    def test_media_rejects_gif_with_jpg_filename(self):
        self.assert_media_invalid(
            _animated_gif_upload(name="content.jpg", content_type="image/jpeg")
        )

    def test_media_rejects_svg_extension(self):
        self.assert_media_invalid(
            SimpleUploadedFile(
                "content.svg",
                b"<svg><script>alert(1)</script></svg>",
                content_type="image/svg+xml",
            )
        )

    def test_media_rejects_invalid_content_type(self):
        self.assert_media_invalid(
            _image_upload(
                name="content.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

    def test_media_rejects_fake_mp4(self):
        self.assert_media_invalid(
            _mp4_upload(
                name="content.mp4",
                content=b"not a real mp4",
                content_type="video/mp4",
            )
        )

    def test_media_rejects_mp4_with_image_content_type(self):
        self.assert_media_invalid(
            _mp4_upload(
                name="content.mp4",
                content=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
                content_type="image/jpeg",
            )
        )

    @override_settings(STAFF_CONTENT_MEDIA_IMAGE_MAX_DIMENSION=64)
    def test_media_rejects_too_large_image_dimension(self):
        self.assert_media_invalid(
            _image_upload(
                name="content.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

    @override_settings(STAFF_CONTENT_MEDIA_IMAGE_MAX_PIXELS=1000)
    def test_media_rejects_too_many_image_pixels(self):
        self.assert_media_invalid(
            _image_upload(
                name="content.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

    @override_settings(STAFF_CONTENT_MEDIA_MAX_SIZE_BYTES=100)
    def test_media_rejects_too_large_file(self):
        self.assert_media_invalid(
            _image_upload(
                name="content.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )


class StaffContentMediaFormSecurityTests(TestCase):
    def _simple_form(self, uploaded_file):
        return StaffContentSubmissionForm(
            data={
                "submission_type": StaffContentSubmission.SubmissionType.STORY,
                "title": "استوری تست",
                "body": "کپشن تست",
                "contains_identifiable_client": "",
                "client_consent_status": "not_required",
                "professional_confirmed_responsibility": "on",
            },
            files={"media": uploaded_file},
        )

    def _dashboard_form(self, uploaded_file):
        return StylistDashboardContentSubmissionForm(
            data={
                "submission_type": StaffContentSubmission.SubmissionType.STORY,
                "title": "استوری تست",
                "body": "کپشن تست",
                "contains_identifiable_client": "",
                "client_consent_status": "not_required",
                "professional_confirmed_responsibility": "on",
            },
            files={"media": uploaded_file},
            submission_type=StaffContentSubmission.SubmissionType.STORY,
        )

    def assert_media_field_invalid(self, form):
        self.assertFalse(form.is_valid())
        self.assertIn("media", form.errors)

    def test_simple_form_rejects_gif_with_jpg_filename(self):
        form = self._simple_form(
            _animated_gif_upload(name="content.jpg", content_type="image/jpeg")
        )

        self.assert_media_field_invalid(form)

    def test_simple_form_accepts_valid_mp4(self):
        form = self._simple_form(_mp4_upload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_dashboard_form_rejects_gif_with_jpg_filename(self):
        form = self._dashboard_form(
            _animated_gif_upload(name="content.jpg", content_type="image/jpeg")
        )

        self.assert_media_field_invalid(form)

    def test_dashboard_form_accepts_valid_jpeg(self):
        form = self._dashboard_form(
            _image_upload(
                name="content.jpg",
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
