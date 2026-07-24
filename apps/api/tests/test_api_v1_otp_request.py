import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.api.v1.auth_otp import (
    API_AUTH_OTP_PURPOSE_LOGIN,
    load_api_otp_record,
    otp_record_cache_key,
    otp_resend_cache_key,
)
from apps.api.v1.auth_serializers import normalize_iran_mobile


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-auth-otp-tests",
        }
    },
    LOOMERA_API_AUTH_OTP_CACHE_PREFIX="loomera:test-api-auth-otp",
    LOOMERA_API_AUTH_OTP_LENGTH=6,
    LOOMERA_API_AUTH_OTP_TTL_SECONDS=120,
    LOOMERA_API_AUTH_OTP_RESEND_SECONDS=60,
    LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS=5,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR=5,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR=30,
)
class ApiV1OtpRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("api:v1:auth_otp_request")

    def test_otp_request_accepts_valid_mobile_and_stores_hashed_record(self):
        response = self.client.post(
            self.url,
            data={"mobile_number": "+989121234567"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["accepted"])
        self.assertEqual(payload["data"]["mobile_number"], "0912***567")
        self.assertEqual(payload["data"]["delivery"]["mode"], "simulated")
        self.assertFalse(payload["data"]["delivery"]["sent"])
        self.assertEqual(payload["data"]["otp"]["ttl_seconds"], 120)
        self.assertEqual(payload["data"]["otp"]["resend_seconds"], 60)
        self.assertEqual(payload["data"]["otp"]["length"], 6)

        record = load_api_otp_record(mobile_number="09121234567")
        self.assertIsNotNone(record)
        self.assertEqual(record["mobile_number"], "09121234567")
        self.assertEqual(record["purpose"], API_AUTH_OTP_PURPOSE_LOGIN)
        self.assertEqual(record["attempts"], 0)
        self.assertEqual(record["max_attempts"], 5)
        self.assertFalse(record["verified"])
        self.assertIn("code_hash", record)
        self.assertNotIn("code", record)

        body = response.content.decode("utf-8")
        self.assertNotIn("09121234567", body)
        self.assertNotIn(record["code_hash"], body)

    def test_otp_request_rejects_invalid_mobile(self):
        invalid_cases = [
            "",
            "9121234567",
            "08121234567",
            "0912123456",
            "091212345678",
            "not-a-phone",
        ]

        for value in invalid_cases:
            response = self.client.post(
                self.url,
                data={"mobile_number": value},
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "invalid_mobile_number")

    @override_settings(LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES=16)
    def test_otp_request_rejects_large_payload(self):
        response = self.client.post(
            self.url,
            data={"mobile_number": "09121234567", "extra": "x" * 100},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "payload_too_large")

    def test_otp_request_rejects_invalid_json_payload(self):
        response = self.client.post(
            self.url,
            data="{not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_payload")

    def test_otp_request_rejects_non_object_payload(self):
        response = self.client.post(
            self.url,
            data=json.dumps(["09121234567"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_payload")

    def test_otp_request_enforces_resend_cooldown(self):
        first = self.client.post(
            self.url,
            data={"mobile_number": "09121234567"},
            content_type="application/json",
        )
        second = self.client.post(
            self.url,
            data={"mobile_number": "09121234567"},
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        payload = second.json()
        self.assertEqual(payload["error"]["code"], "otp_rate_limited")
        self.assertEqual(payload["error"]["details"]["scope"], "mobile_resend")
        self.assertGreater(payload["error"]["details"]["retry_after_seconds"], 0)

    @override_settings(
        LOOMERA_API_AUTH_OTP_RESEND_SECONDS=30,
        LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR=1,
    )
    @patch("apps.api.v1.auth_otp.api_otp_now_ts")
    def test_otp_request_enforces_mobile_hour_limit_after_cooldown(self, mocked_now):
        mocked_now.return_value = 1000
        first = self.client.post(
            self.url,
            data={"mobile_number": "09121234567"},
            content_type="application/json",
        )

        mocked_now.return_value = 1031
        second = self.client.post(
            self.url,
            data={"mobile_number": "09121234567"},
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"]["details"]["scope"], "mobile")

    @override_settings(
        LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR=1,
    )
    def test_otp_request_enforces_ip_hour_limit(self):
        first = self.client.post(
            self.url,
            data={"mobile_number": "09121234567"},
            content_type="application/json",
            REMOTE_ADDR="10.0.0.1",
        )
        second = self.client.post(
            self.url,
            data={"mobile_number": "09129876543"},
            content_type="application/json",
            REMOTE_ADDR="10.0.0.1",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"]["details"]["scope"], "ip")

    def test_otp_request_overwrites_previous_record_after_cooldown_without_plain_code(
        self,
    ):
        mobile = "09121234567"
        normalized = normalize_iran_mobile(mobile)

        first = self.client.post(
            self.url,
            data={"mobile_number": mobile},
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        key = otp_record_cache_key(
            purpose=API_AUTH_OTP_PURPOSE_LOGIN,
            mobile_number=normalized,
        )
        first_record = cache.get(key)
        first_hash = first_record["code_hash"]

        cache.delete(
            otp_resend_cache_key(
                purpose=API_AUTH_OTP_PURPOSE_LOGIN,
                mobile_number=normalized,
            )
        )

        second = self.client.post(
            self.url,
            data={"mobile_number": mobile},
            content_type="application/json",
        )
        self.assertEqual(second.status_code, 200)

        second_record = cache.get(key)
        self.assertNotEqual(first_hash, second_record["code_hash"])
        self.assertNotIn("code", second_record)

    @override_settings(LOOMERA_API_AUTH_OTP_FAIL_CLOSED=True)
    @patch("apps.api.v1.auth_otp.cache.get", side_effect=RuntimeError("cache down"))
    def test_otp_request_fails_closed_when_cache_is_unavailable(self, mocked_cache_get):
        response = self.client.post(
            self.url,
            data={"mobile_number": "09121234567"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "otp_rate_limit_unavailable")
