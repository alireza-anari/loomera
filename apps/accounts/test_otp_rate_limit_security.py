from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.services.sms import SMSDeliveryResult


TEST_LOC_MEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "otp-rate-limit-security-tests",
    }
}

@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES=TEST_LOC_MEM_CACHES,
    SMS_OTP_CODE_LENGTH=5,
    OTP_EXPIRY_SECONDS=180,
    OTP_MAX_ATTEMPTS=5,
    OTP_RESEND_COOLDOWN_SECONDS=30,
    OTP_RATE_LIMIT_FAIL_CLOSED=True,
)
class OtpRateLimitSecurityTests(TestCase):
    @patch("apps.accounts.views.cache.get", side_effect=RuntimeError("cache down"))
    @patch("apps.accounts.views.utils.send_otp_sms")
    def test_signup_does_not_send_otp_when_cooldown_cache_get_fails(
        self,
        mock_send_sms,
        _mock_cache_get,
    ):
        response = self.client.post(
            reverse("accounts:customer_signup"),
            {
                "name": "Sara",
                "family": "Ahmadi",
                "mobile_number": "09123456789",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "agree_to_terms": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        mock_send_sms.assert_not_called()
        self.assertFalse(
            get_user_model().objects.filter(mobile_number="09123456789").exists()
        )

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("امکان ارسال کد تایید وجود ندارد" in message for message in messages)
        )

    @patch("apps.accounts.views.cache.get", return_value=None)
    @patch("apps.accounts.views.cache.set", side_effect=RuntimeError("cache down"))
    @patch("apps.accounts.views.utils.send_otp_sms")
    def test_signup_does_not_send_otp_when_cooldown_cache_set_fails(
        self,
        mock_send_sms,
        _mock_cache_set,
        _mock_cache_get,
    ):
        response = self.client.post(
            reverse("accounts:customer_signup"),
            {
                "name": "Sara",
                "family": "Ahmadi",
                "mobile_number": "09123456780",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "agree_to_terms": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        mock_send_sms.assert_not_called()
        self.assertFalse(
            get_user_model().objects.filter(mobile_number="09123456780").exists()
        )

        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("امکان ارسال کد تایید وجود ندارد" in message for message in messages)
        )

    @patch("apps.accounts.views.utils.create_random_code", return_value=12345)
    @patch("apps.accounts.views.utils.send_otp_sms")
    def test_signup_still_sends_otp_when_rate_limit_cache_is_available(
        self,
        mock_send_sms,
        _mock_code,
    ):
        mock_send_sms.return_value = SMSDeliveryResult(
            success=True,
            provider="test",
            mode="sandbox",
            simulated=True,
        )

        response = self.client.post(
            reverse("accounts:customer_signup"),
            {
                "name": "Sara",
                "family": "Ahmadi",
                "mobile_number": "09123456781",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "agree_to_terms": "on",
            },
        )

        self.assertRedirects(response, reverse("accounts:verify"))
        mock_send_sms.assert_called_once()
        self.assertTrue(
            get_user_model().objects.filter(mobile_number="09123456781").exists()
        )