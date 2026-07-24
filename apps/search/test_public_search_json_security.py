from __future__ import annotations

import json

from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SEARCH_JSON_BODY_MAX_BYTES=64)
class PublicSearchJsonSecurityTests(TestCase):
    def test_loomera_search_rejects_oversized_json_body(self):
        response = self.client.post(
            reverse("search:loomera_search"),
            data=json.dumps({"q": "x" * 100}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

    def test_filter_salon_rejects_oversized_json_body(self):
        response = self.client.post(
            reverse("search:filter_salon"),
            data=json.dumps({"q": "x" * 100}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

    def test_loomera_search_rejects_json_array_payload(self):
        response = self.client.post(
            reverse("search:loomera_search"),
            data=json.dumps(["salon", "service"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON")

    def test_filter_salon_rejects_json_array_payload(self):
        response = self.client.post(
            reverse("search:filter_salon"),
            data=json.dumps(["salon", "service"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON معتبر نیست", response.json()["error"])

    def test_loomera_search_accepts_small_json_object(self):
        response = self.client.post(
            reverse("search:loomera_search"),
            data=json.dumps({"q": "مو"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("salons", response.json())

    def test_filter_salon_accepts_small_json_object(self):
        response = self.client.post(
            reverse("search:filter_salon"),
            data=json.dumps({"q": "مو"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("salons", response.json())