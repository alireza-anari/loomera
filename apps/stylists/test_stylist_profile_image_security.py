from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from apps.stylists.forms import StylistProfileForm


def _image_upload(
    *,
    name="stylist.jpg",
    size=(32, 32),
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


def _animated_gif_upload(*, name="stylist.gif", content_type="image/gif"):
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


class StylistProfileImageSecurityTests(TestCase):
    def _form(self, uploaded_file):
        return StylistProfileForm(
            data={
                "display_name": "متخصص تست",
                "resume_headline": "متخصص زیبایی",
                "resume_summary": "رزومه تست",
                "expert": "ناخن",
                "description": "توضیح تست",
                "started_working_year": "1400",
                "public_visibility": "public",
                "address": "",
                "linkedin_link": "",
                "insta_link": "",
                "telegram_link": "",
                "calendar_color": "",
            },
            files={
                "profile_image": uploaded_file,
            },
        )

    def test_stylist_profile_image_accepts_valid_jpeg(self):
        form = self._form(
            _image_upload(
                name="stylist.jpg",
                size=(32, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_stylist_profile_image_rejects_gif_extension(self):
        form = self._form(
            _animated_gif_upload(
                name="stylist.gif",
                content_type="image/gif",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)

    def test_stylist_profile_image_rejects_gif_with_jpg_filename(self):
        form = self._form(
            _animated_gif_upload(
                name="stylist.jpg",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)

    def test_stylist_profile_image_rejects_svg_extension(self):
        svg_file = SimpleUploadedFile(
            "stylist.svg",
            b"<svg><script>alert(1)</script></svg>",
            content_type="image/svg+xml",
        )

        form = self._form(svg_file)

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)

    def test_stylist_profile_image_rejects_invalid_content_type(self):
        form = self._form(
            _image_upload(
                name="stylist.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)

    @override_settings(STYLIST_PROFILE_IMAGE_MAX_DIMENSION=64)
    def test_stylist_profile_image_rejects_too_large_dimension(self):
        form = self._form(
            _image_upload(
                name="stylist.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)

    @override_settings(STYLIST_PROFILE_IMAGE_MAX_PIXELS=1000)
    def test_stylist_profile_image_rejects_too_many_pixels(self):
        form = self._form(
            _image_upload(
                name="stylist.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)

    @override_settings(STYLIST_PROFILE_IMAGE_MAX_SIZE_BYTES=100)
    def test_stylist_profile_image_rejects_too_large_file_size(self):
        form = self._form(
            _image_upload(
                name="stylist.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("profile_image", form.errors)
