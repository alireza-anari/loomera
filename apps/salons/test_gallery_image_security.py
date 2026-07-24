from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from apps.salons.forms import SalonsGalleryForm


def _image_upload(
    *,
    name="salon.jpg",
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


def _animated_gif_upload(*, name="salon.gif", content_type="image/gif"):
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


class SalonGalleryImageSecurityTests(SimpleTestCase):
    def _form(self, uploaded_file):
        return SalonsGalleryForm(
            files={"salon_image": uploaded_file},
            data={},
        )

    def test_salon_gallery_accepts_valid_jpeg(self):
        form = self._form(
            _image_upload(
                name="salon.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_salon_gallery_rejects_gif_extension(self):
        form = self._form(
            _animated_gif_upload(
                name="salon.gif",
                content_type="image/gif",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)

    def test_salon_gallery_rejects_gif_with_jpg_filename(self):
        form = self._form(
            _animated_gif_upload(
                name="salon.jpg",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)

    def test_salon_gallery_rejects_svg_extension(self):
        svg_file = SimpleUploadedFile(
            "salon.svg",
            b"<svg><script>alert(1)</script></svg>",
            content_type="image/svg+xml",
        )

        form = self._form(svg_file)

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)

    def test_salon_gallery_rejects_invalid_content_type(self):
        form = self._form(
            _image_upload(
                name="salon.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)

    @override_settings(SALON_GALLERY_IMAGE_MAX_DIMENSION=64)
    def test_salon_gallery_rejects_too_large_dimension(self):
        form = self._form(
            _image_upload(
                name="salon.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)

    @override_settings(SALON_GALLERY_IMAGE_MAX_PIXELS=1000)
    def test_salon_gallery_rejects_too_many_pixels(self):
        form = self._form(
            _image_upload(
                name="salon.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)

    @override_settings(SALON_GALLERY_IMAGE_MAX_SIZE_BYTES=100)
    def test_salon_gallery_rejects_too_large_file_size(self):
        form = self._form(
            _image_upload(
                name="salon.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("salon_image", form.errors)
