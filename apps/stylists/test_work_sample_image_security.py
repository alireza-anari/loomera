from __future__ import annotations

from io import BytesIO
from tests_stage1_helpers import Stage1DomainFactoryMixin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from apps.services.models import Services
from apps.stylists.forms import WorkSamplesForm


def _image_upload(
    *,
    name="sample.jpg",
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


def _animated_gif_upload(*, name="sample.gif", content_type="image/gif"):
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


class WorkSampleImageSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _form(self, uploaded_file):
        service = self.make_service()

        return WorkSamplesForm(
            data={
                "description": "نمونه‌کار تست",
                "service": str(service.pk),
            },
            files={
                "sample_image": uploaded_file,
            },
        )

    def test_work_sample_accepts_valid_jpeg(self):
        form = self._form(
            _image_upload(
                name="sample.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_work_sample_rejects_gif_extension(self):
        form = self._form(
            _animated_gif_upload(
                name="sample.gif",
                content_type="image/gif",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    def test_work_sample_rejects_gif_with_jpg_filename(self):
        form = self._form(
            _animated_gif_upload(
                name="sample.jpg",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    def test_work_sample_rejects_svg_extension(self):
        svg_file = SimpleUploadedFile(
            "sample.svg",
            b"<svg><script>alert(1)</script></svg>",
            content_type="image/svg+xml",
        )

        form = self._form(svg_file)

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    def test_work_sample_rejects_invalid_content_type(self):
        form = self._form(
            _image_upload(
                name="sample.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    @override_settings(WORK_SAMPLE_IMAGE_MAX_DIMENSION=64)
    def test_work_sample_rejects_too_large_dimension(self):
        form = self._form(
            _image_upload(
                name="sample.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    @override_settings(WORK_SAMPLE_IMAGE_MAX_PIXELS=1000)
    def test_work_sample_rejects_too_many_pixels(self):
        form = self._form(
            _image_upload(
                name="sample.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)

    @override_settings(WORK_SAMPLE_IMAGE_MAX_SIZE_BYTES=100)
    def test_work_sample_rejects_too_large_file_size(self):
        form = self._form(
            _image_upload(
                name="sample.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors)
