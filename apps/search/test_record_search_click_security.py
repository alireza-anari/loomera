from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SEARCH_CLICK_POST_MAX_BYTES=512)
class RecordSearchClickSecurityTests(TestCase):
    def test_record_search_click_rejects_get_method(self):
        response = self.client.get(
            reverse("search:record_search_click"),
            {"salon_id": "1"},
        )

        self.assertEqual(response.status_code, 405)

    @override_settings(SEARCH_CLICK_POST_MAX_BYTES=32)
    def test_record_search_click_rejects_oversized_payload(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "query": "x" * 100,
            },
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

    def test_record_search_click_rejects_external_target_url(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "target_url": "https://evil.example/phish",
            },
            HTTP_HOST="127.0.0.1:8000",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_payload")

    def test_record_search_click_rejects_javascript_target_url(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "target_url": "javascript:alert(1)",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_payload")

    def test_record_search_click_accepts_relative_target_url_when_model_missing(self):
        response = self.client.post(
            reverse("search:record_search_click"),
            {
                "salon_id": "1",
                "target_url": "/salons/local-seed-salon-5/",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_record_search_click_does_not_expose_internal_exception(self):
        with patch(
            "django.apps.apps.get_model",
            side_effect=RuntimeError("sensitive database failure"),
        ):
            response = self.client.post(
                reverse("search:record_search_click"),
                {
                    "salon_id": "1",
                    "target_url": "/salons/local-seed-salon-5/",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["recorded"])
        self.assertEqual(payload["reason"], "recording_failed")
        self.assertNotIn("sensitive", str(payload))
