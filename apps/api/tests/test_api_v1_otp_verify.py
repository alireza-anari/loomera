import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.api.v1.auth_otp import (
    API_AUTH_OTP_PURPOSE_LOGIN,
    load_api_otp_record,
    otp_record_cache_key,
)
from apps.api.v1.auth_serializers import normalize_iran_mobile
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-auth-otp-verify-tests",
        }
    },
    LOOMERA_API_AUTH_OTP_CACHE_PREFIX="loomera:test-api-auth-otp-verify",
    LOOMERA_API_AUTH_OTP_LENGTH=6,
    LOOMERA_API_AUTH_OTP_TTL_SECONDS=120,
    LOOMERA_API_AUTH_OTP_RESEND_SECONDS=60,
    LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS=3,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR=5,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR=30,
)
class ApiV1OtpVerifyTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.request_url = reverse("api:v1:auth_otp_request")
        self.verify_url = reverse("api:v1:auth_otp_verify")

    def _make_existing_user(self, mobile_number="09121234567"):
        customer = self.make_customer(
            user_kwargs={
                "name": "کاربر",
                "family": "اپ",
                "mobile_number": mobile_number,
                "email": "otp-verify-private@example.com",
            }
        )
        return customer.user

    def _request_known_otp(self, mobile_number="09121234567", code="123456"):
        with patch("apps.api.v1.auth_otp.generate_numeric_otp", return_value=code):
            response = self.client.post(
                self.request_url,
                data={"mobile_number": mobile_number},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        return response

    def test_otp_verify_logs_in_existing_active_user_and_deletes_otp_record(self):
        user = self._make_existing_user()
        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["verified"])
        self.assertTrue(payload["data"]["authenticated"])
        self.assertEqual(payload["data"]["user"]["id"], user.pk)
        self.assertEqual(payload["data"]["user"]["mobile_number"], "09121234567")
        self.assertEqual(
            payload["data"]["user"]["email"], "otp-verify-private@example.com"
        )
        self.assertEqual(payload["data"]["session"]["type"], "django_session")

        self.assertNotIn("code", response.content.decode("utf-8"))

        record = load_api_otp_record(mobile_number="09121234567")
        self.assertIsNone(record)

        me_response = self.client.get(reverse("api:v1:auth_me"))
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["data"]["user"]["id"], user.pk)

    def test_otp_verify_rejects_invalid_code_and_keeps_attempt_count(self):
        self._make_existing_user()
        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "000000",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_otp_code")
        self.assertEqual(payload["error"]["details"]["attempts_remaining"], 2)

        record = load_api_otp_record(mobile_number="09121234567")
        self.assertIsNotNone(record)
        self.assertEqual(record["attempts"], 1)
        self.assertFalse(record["verified"])

    def test_otp_verify_deletes_record_after_max_attempts(self):
        self._make_existing_user()
        self._request_known_otp(mobile_number="09121234567", code="123456")

        for index in range(2):
            response = self.client.post(
                self.verify_url,
                data={
                    "mobile_number": "09121234567",
                    "code": "000000",
                },
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "000000",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "otp_max_attempts_exceeded")
        self.assertIsNone(load_api_otp_record(mobile_number="09121234567"))

    def test_otp_verify_rejects_missing_or_expired_record(self):
        self._make_existing_user()

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "otp_not_found")

    @patch("apps.api.v1.auth_otp.api_otp_now_ts")
    def test_otp_verify_rejects_expired_otp(self, mocked_now):
        self._make_existing_user()

        mocked_now.return_value = 1000
        self._request_known_otp(mobile_number="09121234567", code="123456")

        mocked_now.return_value = 1200
        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "otp_expired")

    def test_otp_verify_rejects_unknown_user_after_valid_otp_without_creating_user(
        self,
    ):
        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "auth_user_not_found")

        me_response = self.client.get(reverse("api:v1:auth_me"))
        self.assertIn(me_response.status_code, [401, 403])

    def test_otp_verify_rejects_inactive_user_after_valid_otp(self):
        user = self._make_existing_user()
        user.is_active = False
        user.save(update_fields=["is_active"])

        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "auth_user_not_found")

    def test_otp_verify_rejects_invalid_mobile(self):
        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "not-a-phone",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_mobile_number")

    def test_otp_verify_rejects_invalid_payload(self):
        response = self.client.post(
            self.verify_url,
            data="{not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_payload")

        response = self.client.post(
            self.verify_url,
            data=json.dumps(["09121234567", "123456"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_payload")

    @override_settings(LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES=16)
    def test_otp_verify_rejects_large_payload(self):
        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
                "extra": "x" * 100,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "payload_too_large")

    def test_otp_verify_does_not_accept_code_for_another_mobile(self):
        first_user = self._make_existing_user(mobile_number="09121234567")
        second_user = self._make_existing_user(mobile_number="09129876543")

        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": "09129876543",
                "code": "123456",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "otp_not_found")

    def test_otp_record_does_not_store_plain_code(self):
        self._request_known_otp(mobile_number="09121234567", code="123456")
        normalized = normalize_iran_mobile("09121234567")
        key = otp_record_cache_key(
            purpose=API_AUTH_OTP_PURPOSE_LOGIN,
            mobile_number=normalized,
        )
        record = cache.get(key)

        self.assertIsNotNone(record)
        self.assertIn("code_hash", record)
        self.assertNotIn("code", record)
