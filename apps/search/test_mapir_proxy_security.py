from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class _FakeHeaders:
    def __init__(self, content_type="image/png"):
        self.content_type = content_type

    def get_content_type(self):
        return self.content_type


class _FakeUpstreamResponse:
    def __init__(self, body, content_type="image/png"):
        self.body = body
        self.headers = _FakeHeaders(content_type)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            return self.body
        return self.body[:size]


@override_settings(MAPIR_API_KEY="test-key")
class MapirProxySecurityTests(SimpleTestCase):
    def test_map_tile_proxy_rejects_insecure_http_upstream(self):
        with override_settings(
            MAPIR_WMS_BASE_URL="http://map.ir/shiveh",
            MAPIR_ALLOWED_HOSTS={"map.ir"},
        ):
            response = self.client.get(reverse("search:map_tile_proxy", args=[1, 0, 0]))

        self.assertEqual(response.status_code, 503)

    def test_map_tile_proxy_rejects_unallowed_host(self):
        with override_settings(
            MAPIR_WMS_BASE_URL="https://127.0.0.1/internal",
            MAPIR_ALLOWED_HOSTS={"map.ir"},
        ):
            response = self.client.get(reverse("search:map_tile_proxy", args=[1, 0, 0]))

        self.assertEqual(response.status_code, 503)

    def test_reverse_geocode_proxy_rejects_unallowed_host(self):
        with override_settings(
            MAPIR_REVERSE_BASE_URL="https://localhost/reverse",
            MAPIR_ALLOWED_HOSTS={"map.ir"},
        ):
            response = self.client.get(
                reverse("search:reverse_geocode_proxy"),
                {"lat": "35.7", "lon": "51.4"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()["ok"])

    @patch("apps.search.views.urlopen")
    def test_map_tile_proxy_rejects_large_upstream_response(self, mocked_urlopen):
        mocked_urlopen.return_value = _FakeUpstreamResponse(b"x" * 10)

        with override_settings(
            MAPIR_WMS_BASE_URL="https://map.ir/shiveh",
            MAPIR_ALLOWED_HOSTS={"map.ir"},
            MAPIR_MAX_TILE_RESPONSE_BYTES=4,
            MAPIR_UPSTREAM_RETRY_COUNT=0,
        ):
            response = self.client.get(reverse("search:map_tile_proxy", args=[1, 0, 0]))

        self.assertEqual(response.status_code, 502)

    @patch("apps.search.views.urlopen")
    def test_reverse_geocode_proxy_rejects_large_upstream_response(self, mocked_urlopen):
        mocked_urlopen.return_value = _FakeUpstreamResponse(
            b'{"too_large": true}',
            content_type="application/json",
        )

        with override_settings(
            MAPIR_REVERSE_BASE_URL="https://map.ir/reverse/no",
            MAPIR_ALLOWED_HOSTS={"map.ir"},
            MAPIR_MAX_REVERSE_RESPONSE_BYTES=4,
            MAPIR_UPSTREAM_RETRY_COUNT=0,
        ):
            response = self.client.get(
                reverse("search:reverse_geocode_proxy"),
                {"lat": "35.7", "lon": "51.4"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()["ok"])