from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from tests_stage1_helpers import Stage1DomainFactoryMixin


def _animated_gif_upload():
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
        "avatar.gif",
        buffer.read(),
        content_type="image/gif",
    )


def _image_upload(
    *,
    name="avatar.jpg",
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


class CustomerProfileImageSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _url(self):
        return reverse("accounts:customer_update_profile_image")

    def test_customer_profile_image_requires_login(self):
        response = self.client.post(
            self._url(),
            {"image": _image_upload()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_customer_profile_image_rejects_get_method(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 405)

    def test_customer_profile_image_forbids_non_customer_user(self):
        manager = self.make_salon_manager()
        self.client.force_login(manager.user)

        response = self.client.post(
            self._url(),
            {"image": _image_upload()},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)

    def test_customer_profile_image_rejects_missing_file(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(),
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    def test_customer_profile_image_rejects_invalid_extension(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(),
            {
                "image": _image_upload(
                    name="avatar.gif",
                    image_format="PNG",
                    content_type="image/png",
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    def test_customer_profile_image_rejects_invalid_content_type(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(),
            {
                "image": _image_upload(
                    name="avatar.jpg",
                    image_format="JPEG",
                    content_type="text/plain",
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    @override_settings(CUSTOMER_PROFILE_IMAGE_MAX_DIMENSION=64)
    def test_customer_profile_image_rejects_too_large_dimension(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(),
            {
                "image": _image_upload(
                    name="avatar.jpg",
                    size=(128, 32),
                    image_format="JPEG",
                    content_type="image/jpeg",
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("ابعاد", response.json()["error"])

    @override_settings(CUSTOMER_PROFILE_IMAGE_MAX_PIXELS=1000)
    def test_customer_profile_image_rejects_too_many_pixels(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(),
            {
                "image": _image_upload(
                    name="avatar.jpg",
                    size=(40, 40),
                    image_format="JPEG",
                    content_type="image/jpeg",
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("پیکسل", response.json()["error"])

    def test_customer_profile_image_accepts_valid_jpeg(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            self._url(),
            {
                "image": _image_upload(
                    name="avatar.jpg",
                    size=(32, 32),
                    image_format="JPEG",
                    content_type="image/jpeg",
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["image_url"])

        customer.refresh_from_db()
        self.assertTrue(customer.profile_image)


def test_customer_profile_image_rejects_animated_gif(self):
    customer = self.make_customer()
    self.client.force_login(customer.user)

    response = self.client.post(
        self._url(),
        {"image": _animated_gif_upload()},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json()["status"], "error")
    self.assertIn("متحرک", response.json()["error"])

    customer.refresh_from_db()
    self.assertFalse(customer.profile_image)


def test_customer_profile_image_rejects_gif_with_jpg_filename(self):
    customer = self.make_customer()
    self.client.force_login(customer.user)

    gif_file = _animated_gif_upload()
    gif_file.name = "avatar.jpg"
    gif_file.content_type = "image/jpeg"

    response = self.client.post(
        self._url(),
        {"image": gif_file},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    self.assertEqual(response.status_code, 400)
    self.assertEqual(response.json()["status"], "error")

    customer.refresh_from_db()
    self.assertFalse(customer.profile_image)
