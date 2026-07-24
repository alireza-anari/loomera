from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.accounts.forms import SalonManagerUpdateProfileForm


def _image_upload(
    *,
    name="manager.jpg",
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


def _animated_gif_upload(*, name="manager.gif", content_type="image/gif"):
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


class SalonManagerProfileImageSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _form(self, uploaded_file, manager_instance=None):
        manager_instance = manager_instance or self.make_salon_manager()

        return SalonManagerUpdateProfileForm(
            data={
                "name": manager_instance.user.name or "مدیر",
                "family": manager_instance.user.family or "تست",
                "email": manager_instance.user.email or "",
                "mobile_number": manager_instance.user.mobile_number,
                "address": manager_instance.address or "",
                "salon_number": str(manager_instance.salon_number or ""),
            },
            files={
                "image": uploaded_file,
            },
            instance=manager_instance.user,
            manager_instance=manager_instance,
        )

    def test_manager_profile_image_accepts_valid_jpeg(self):
        form = self._form(
            _image_upload(
                name="manager.jpg",
                size=(32, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_manager_profile_image_rejects_gif_extension(self):
        form = self._form(
            _animated_gif_upload(
                name="manager.gif",
                content_type="image/gif",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_manager_profile_image_rejects_gif_with_jpg_filename(self):
        form = self._form(
            _animated_gif_upload(
                name="manager.jpg",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_manager_profile_image_rejects_svg_extension(self):
        svg_file = SimpleUploadedFile(
            "manager.svg",
            b"<svg><script>alert(1)</script></svg>",
            content_type="image/svg+xml",
        )

        form = self._form(svg_file)

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_manager_profile_image_rejects_invalid_content_type(self):
        form = self._form(
            _image_upload(
                name="manager.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    @override_settings(CUSTOMER_PROFILE_IMAGE_MAX_DIMENSION=64)
    def test_manager_profile_image_rejects_too_large_dimension(self):
        form = self._form(
            _image_upload(
                name="manager.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    @override_settings(CUSTOMER_PROFILE_IMAGE_MAX_PIXELS=1000)
    def test_manager_profile_image_rejects_too_many_pixels(self):
        form = self._form(
            _image_upload(
                name="manager.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)
