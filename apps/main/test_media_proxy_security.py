from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class _NamedBytesIO(BytesIO):
    name = "media-file"


@override_settings(
    MEDIA_PROXY_IMAGE_EXTENSIONS={".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif"},
    MEDIA_PROXY_ALLOW_SVG=False,
    MEDIA_PROXY_MAX_PATH_LENGTH=512,
)
class MediaProxySecurityTests(SimpleTestCase):
    def test_media_proxy_rejects_internal_parent_traversal(self):
        with patch("apps.main.views.default_storage.open") as mocked_open:
            response = self.client.get(
                reverse("media_proxy"),
                {"path": "uploads/../../secret.jpg"},
            )

        self.assertEqual(response.status_code, 404)
        mocked_open.assert_not_called()

    def test_media_proxy_rejects_backslash_paths(self):
        with patch("apps.main.views.default_storage.open") as mocked_open:
            response = self.client.get(
                reverse("media_proxy"),
                {"path": r"uploads\..\secret.jpg"},
            )

        self.assertEqual(response.status_code, 404)
        mocked_open.assert_not_called()

    def test_media_proxy_rejects_too_long_path(self):
        long_path = "uploads/" + ("a" * 600) + ".jpg"

        with patch("apps.main.views.default_storage.open") as mocked_open:
            response = self.client.get(
                reverse("media_proxy"),
                {"path": long_path},
            )

        self.assertEqual(response.status_code, 404)
        mocked_open.assert_not_called()

    def test_media_proxy_rejects_svg_by_default(self):
        with patch("apps.main.views.default_storage.open") as mocked_open:
            response = self.client.get(
                reverse("media_proxy"),
                {"path": "uploads/logo.svg"},
            )

        self.assertEqual(response.status_code, 404)
        mocked_open.assert_not_called()

    def test_media_proxy_keeps_jpg_content_type_when_body_looks_like_svg(self):
        fake_file = _NamedBytesIO(b"<svg><script>alert(1)</script></svg>")

        with patch("apps.main.views.default_storage.open", return_value=fake_file):
            response = self.client.get(
                reverse("media_proxy"),
                {"path": "uploads/logo.jpg"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_media_proxy_accepts_safe_image_path(self):
        fake_file = _NamedBytesIO(b"\xff\xd8\xff test jpeg")

        with patch("apps.main.views.default_storage.open", return_value=fake_file) as mocked_open:
            response = self.client.get(
                reverse("media_proxy"),
                {"path": "uploads/salons/logo.jpg"},
            )

        self.assertEqual(response.status_code, 200)
        mocked_open.assert_called_once_with("uploads/salons/logo.jpg", "rb")