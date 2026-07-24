from django.test import TestCase, override_settings
from django.urls import reverse


class ApiV1FoundationTests(TestCase):
    def test_api_v1_health_returns_standard_success_response(self):
        response = self.client.get(reverse("api:v1:health"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/json"))

        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertEqual(payload["data"]["service"], "loomera-api")
        self.assertEqual(payload["meta"]["api_version"], "v1")

    def test_api_v1_meta_returns_public_non_sensitive_metadata(self):
        response = self.client.get(reverse("api:v1:meta"))

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertEqual(payload["data"]["api"]["base_path"], "/api/v1/")
        self.assertEqual(payload["data"]["localization"]["rtl"], True)

    @override_settings(
        SECRET_KEY="test-secret-key-should-not-leak",
        PAYMENT_PROVIDER="zibal",
        ZIBAL_MERCHANT="merchant-should-not-leak",
        BALE_BOT_TOKEN="bale-token-should-not-leak",
        BALE_WEBHOOK_SECRET="bale-secret-should-not-leak",
        AWS_ACCESS_KEY_ID="aws-access-key-should-not-leak",
        AWS_SECRET_ACCESS_KEY="aws-secret-key-should-not-leak",
        LOOMERA_PUBLIC_BUILD_ID="public-build-1",
    )
    def test_api_v1_meta_does_not_expose_secrets_or_private_runtime_settings(self):
        response = self.client.get(reverse("api:v1:meta"))

        self.assertEqual(response.status_code, 200)

        body = response.content.decode("utf-8")
        self.assertIn("public-build-1", body)

        forbidden_values = [
            "test-secret-key-should-not-leak",
            "merchant-should-not-leak",
            "bale-token-should-not-leak",
            "bale-secret-should-not-leak",
            "aws-access-key-should-not-leak",
            "aws-secret-key-should-not-leak",
        ]
        for value in forbidden_values:
            self.assertNotIn(value, body)

        forbidden_keys = [
            "SECRET_KEY",
            "ZIBAL_MERCHANT",
            "BALE_BOT_TOKEN",
            "BALE_WEBHOOK_SECRET",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "DEBUG",
            "ALLOWED_HOSTS",
            "CSRF_TRUSTED_ORIGINS",
            "DATABASES",
            "CACHES",
        ]
        for key in forbidden_keys:
            self.assertNotIn(key, body)

    def test_unknown_api_v1_path_returns_404(self):
        response = self.client.get("/api/v1/unknown/")

        self.assertEqual(response.status_code, 404)
