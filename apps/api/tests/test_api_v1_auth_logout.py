from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-auth-logout-tests",
        }
    },
    LOOMERA_API_AUTH_OTP_CACHE_PREFIX="loomera:test-api-auth-logout",
    LOOMERA_API_AUTH_OTP_LENGTH=6,
    LOOMERA_API_AUTH_OTP_TTL_SECONDS=120,
    LOOMERA_API_AUTH_OTP_RESEND_SECONDS=60,
    LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS=3,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR=5,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR=30,
)
class ApiV1AuthLogoutTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.request_url = reverse("api:v1:auth_otp_request")
        self.verify_url = reverse("api:v1:auth_otp_verify")
        self.logout_url = reverse("api:v1:auth_logout")
        self.status_url = reverse("api:v1:auth_status")
        self.me_url = reverse("api:v1:auth_me")

    def _make_existing_user(self, mobile_number="09121234567"):
        customer = self.make_customer(
            user_kwargs={
                "name": "کاربر",
                "family": "خروج",
                "mobile_number": mobile_number,
                "email": "logout-private@example.com",
            }
        )
        return customer.user

    def _login_with_known_otp(self, *, mobile_number="09121234567", code="123456"):
        user = self._make_existing_user(mobile_number=mobile_number)

        with patch("apps.api.v1.auth_otp.generate_numeric_otp", return_value=code):
            request_response = self.client.post(
                self.request_url,
                data={"mobile_number": mobile_number},
                content_type="application/json",
            )
        self.assertEqual(request_response.status_code, 200)

        verify_response = self.client.post(
            self.verify_url,
            data={
                "mobile_number": mobile_number,
                "code": code,
            },
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)

        return user

    def test_status_reports_authenticated_session_after_otp_verify(self):
        user = self._login_with_known_otp()

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["authenticated"])
        self.assertTrue(payload["data"]["session"]["active"])
        self.assertEqual(payload["data"]["session"]["type"], "django_session")
        self.assertEqual(payload["data"]["user"]["id"], user.pk)
        self.assertEqual(payload["data"]["user"]["display_name"], "کاربر خروج")

        body = response.content.decode("utf-8")
        self.assertNotIn("09121234567", body)
        self.assertNotIn("logout-private@example.com", body)

    def test_logout_clears_session_and_blocks_auth_me(self):
        user = self._login_with_known_otp()

        before_me = self.client.get(self.me_url)
        self.assertEqual(before_me.status_code, 200)
        self.assertEqual(before_me.json()["data"]["user"]["id"], user.pk)

        logout_response = self.client.post(self.logout_url)

        self.assertEqual(logout_response.status_code, 200)
        payload = logout_response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["logged_out"])
        self.assertTrue(payload["data"]["was_authenticated"])
        self.assertFalse(payload["data"]["session"]["active"])

        after_status = self.client.get(self.status_url)
        self.assertEqual(after_status.status_code, 200)
        self.assertFalse(after_status.json()["data"]["authenticated"])
        self.assertFalse(after_status.json()["data"]["session"]["active"])
        self.assertIsNone(after_status.json()["data"]["user"])

        after_me = self.client.get(self.me_url)
        self.assertIn(after_me.status_code, [401, 403])

    def test_logout_is_idempotent_for_anonymous_user(self):
        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["logged_out"])
        self.assertFalse(payload["data"]["was_authenticated"])
        self.assertFalse(payload["data"]["session"]["active"])

    def test_logout_does_not_require_csrf_for_api_session(self):
        self._login_with_known_otp()

        csrf_enforcing_client = self.client_class(enforce_csrf_checks=True)
        csrf_enforcing_client.cookies = self.client.cookies

        response = csrf_enforcing_client.post(self.logout_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["logged_out"])

    def test_auth_policy_includes_logout_endpoint(self):
        response = self.client.get(reverse("api:v1:auth_policy"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["data"]["endpoints"]["logout"], "/api/v1/auth/logout/")
        self.assertEqual(
            payload["data"]["endpoints"]["otp_request"],
            "/api/v1/auth/otp/request/",
        )
        self.assertEqual(
            payload["data"]["endpoints"]["otp_verify"],
            "/api/v1/auth/otp/verify/",
        )
