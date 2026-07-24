from django.test import TestCase, override_settings
from django.urls import reverse

from apps.api.v1.auth_serializers import normalize_iran_mobile, validate_mobile_for_auth
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ApiV1AuthFoundationTests(Stage1DomainFactoryMixin, TestCase):
    def test_auth_status_reports_current_session_without_private_user_data(self):
        user = self.make_customer(
            user_kwargs={
                "name": "کاربر",
                "family": "اپ",
                "mobile_number": "09120001111",
                "email": "private-auth@example.com",
            }
        ).user
        self.client.force_login(user)

        response = self.client.get(reverse("api:v1:auth_status"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["authenticated"], True)
        self.assertEqual(payload["data"]["user"]["id"], user.pk)
        self.assertEqual(payload["data"]["user"]["display_name"], "کاربر اپ")
        self.assertTrue(payload["data"]["session"]["active"])

        body = response.content.decode("utf-8")
        self.assertNotIn("09120001111", body)
        self.assertNotIn("private-auth@example.com", body)

    def test_auth_me_requires_authenticated_user(self):
        response = self.client.get(reverse("api:v1:auth_me"))

        self.assertIn(response.status_code, [401, 403])
        body = response.content.decode("utf-8")
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("DATABASES", body)

    def test_auth_me_returns_current_user_private_self_data_only(self):
        user = self.make_customer(
            user_kwargs={
                "name": "کاربر",
                "family": "اپ",
                "mobile_number": "09120002222",
                "email": "self-auth@example.com",
            }
        ).user
        self.client.force_login(user)

        response = self.client.get(reverse("api:v1:auth_me"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["authenticated"], True)
        self.assertEqual(payload["data"]["user"]["id"], user.pk)
        self.assertEqual(payload["data"]["user"]["display_name"], "کاربر اپ")
        self.assertEqual(payload["data"]["user"]["mobile_number"], "09120002222")
        self.assertEqual(payload["data"]["user"]["email"], "self-auth@example.com")
        self.assertTrue(payload["data"]["user"]["roles"]["is_customer"])

    @override_settings(
        LOOMERA_API_AUTH_OTP_LENGTH=5,
        LOOMERA_API_AUTH_OTP_TTL_SECONDS=180,
        LOOMERA_API_AUTH_OTP_RESEND_SECONDS=90,
        LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS=4,
        SECRET_KEY="auth-policy-secret-should-not-leak",
        SMS_API_KEY="sms-secret-should-not-leak",
        BALE_BOT_TOKEN="bale-secret-should-not-leak",
    )
    def test_auth_policy_is_public_and_does_not_leak_secrets(self):
        response = self.client.get(reverse("api:v1:auth_policy"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["method"], "mobile_otp")
        self.assertEqual(payload["data"]["otp"]["length"], 5)
        self.assertEqual(payload["data"]["otp"]["ttl_seconds"], 180)
        self.assertEqual(payload["data"]["otp"]["resend_seconds"], 90)
        self.assertEqual(payload["data"]["otp"]["max_verify_attempts"], 4)

        body = response.content.decode("utf-8")
        self.assertNotIn("auth-policy-secret-should-not-leak", body)
        self.assertNotIn("sms-secret-should-not-leak", body)
        self.assertNotIn("bale-secret-should-not-leak", body)
        self.assertNotIn("SECRET_KEY", body)
        self.assertNotIn("SMS_API_KEY", body)
        self.assertNotIn("BALE_BOT_TOKEN", body)

    def test_mobile_normalization_accepts_common_iran_formats(self):
        self.assertEqual(normalize_iran_mobile("+989121234567"), "09121234567")
        self.assertEqual(normalize_iran_mobile("00989121234567"), "09121234567")
        self.assertEqual(normalize_iran_mobile("989121234567"), "09121234567")
        self.assertEqual(normalize_iran_mobile("0912-123-4567"), "09121234567")
        self.assertEqual(normalize_iran_mobile("0912 123 4567"), "09121234567")

    def test_mobile_validation_rejects_invalid_values(self):
        valid, mobile, error = validate_mobile_for_auth("09121234567")
        self.assertTrue(valid)
        self.assertEqual(mobile, "09121234567")
        self.assertEqual(error, "")

        invalid_cases = [
            "",
            "9121234567",
            "08121234567",
            "0912123456",
            "091212345678",
            "not-a-phone",
        ]

        for value in invalid_cases:
            valid, mobile, error = validate_mobile_for_auth(value)
            self.assertFalse(valid)
            self.assertTrue(error)

    def test_auth_status_is_public_for_anonymous_user(self):
        response = self.client.get(reverse("api:v1:auth_status"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["authenticated"], False)
        self.assertIsNone(payload["data"]["user"])
        self.assertFalse(payload["data"]["session"]["active"])
