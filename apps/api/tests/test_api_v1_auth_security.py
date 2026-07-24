from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.api.v1.auth_otp import load_api_otp_record
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-auth-security-tests",
        }
    },
    LOOMERA_API_AUTH_OTP_CACHE_PREFIX="loomera:test-api-auth-security",
    LOOMERA_API_AUTH_OTP_LENGTH=6,
    LOOMERA_API_AUTH_OTP_TTL_SECONDS=120,
    LOOMERA_API_AUTH_OTP_RESEND_SECONDS=60,
    LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS=3,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR=5,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR=30,
)
class ApiV1AuthSecurityRegressionTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.request_url = reverse("api:v1:auth_otp_request")
        self.verify_url = reverse("api:v1:auth_otp_verify")
        self.logout_url = reverse("api:v1:auth_logout")
        self.status_url = reverse("api:v1:auth_status")
        self.me_url = reverse("api:v1:auth_me")

    def _make_existing_user(
        self,
        *,
        mobile_number="09121234567",
        email="auth-security-private@example.com",
        name="کاربر",
        family="امنیت",
    ):
        customer = self.make_customer(
            user_kwargs={
                "name": name,
                "family": family,
                "mobile_number": mobile_number,
                "email": email,
            }
        )
        return customer.user

    def _request_known_otp(
        self, *, mobile_number="09121234567", code="123456", client=None
    ):
        client = client or self.client
        with patch("apps.api.v1.auth_otp.generate_numeric_otp", return_value=code):
            response = client.post(
                self.request_url,
                data={"mobile_number": mobile_number},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        return response

    def _verify_otp(self, *, mobile_number="09121234567", code="123456", client=None):
        client = client or self.client
        return client.post(
            self.verify_url,
            data={
                "mobile_number": mobile_number,
                "code": code,
            },
            content_type="application/json",
        )

    def test_otp_code_cannot_be_replayed_after_successful_verify(self):
        user = self._make_existing_user()
        self._request_known_otp(mobile_number="09121234567", code="123456")

        first_response = self._verify_otp(mobile_number="09121234567", code="123456")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["data"]["user"]["id"], user.pk)
        self.assertIsNone(load_api_otp_record(mobile_number="09121234567"))

        replay_client = Client()
        second_response = self._verify_otp(
            mobile_number="09121234567",
            code="123456",
            client=replay_client,
        )

        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()["error"]["code"], "otp_not_found")

        replay_me = replay_client.get(self.me_url)
        self.assertIn(replay_me.status_code, [401, 403])

    def test_wrong_otp_never_creates_authenticated_session(self):
        self._make_existing_user()
        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self._verify_otp(mobile_number="09121234567", code="000000")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_otp_code")

        status_response = self.client.get(self.status_url)
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.json()["data"]["authenticated"])

        me_response = self.client.get(self.me_url)
        self.assertIn(me_response.status_code, [401, 403])

    def test_correct_code_after_max_attempts_is_not_accepted(self):
        self._make_existing_user()
        self._request_known_otp(mobile_number="09121234567", code="123456")

        for _ in range(2):
            response = self._verify_otp(mobile_number="09121234567", code="000000")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "invalid_otp_code")

        third_response = self._verify_otp(mobile_number="09121234567", code="000000")
        self.assertEqual(third_response.status_code, 429)
        self.assertEqual(
            third_response.json()["error"]["code"],
            "otp_max_attempts_exceeded",
        )

        correct_after_lock = self._verify_otp(
            mobile_number="09121234567", code="123456"
        )
        self.assertEqual(correct_after_lock.status_code, 400)
        self.assertEqual(correct_after_lock.json()["error"]["code"], "otp_not_found")

        me_response = self.client.get(self.me_url)
        self.assertIn(me_response.status_code, [401, 403])

    def test_otp_for_one_mobile_cannot_login_another_mobile(self):
        first_user = self._make_existing_user(
            mobile_number="09121234567",
            email="first-auth-security@example.com",
        )
        second_user = self._make_existing_user(
            mobile_number="09129876543",
            email="second-auth-security@example.com",
        )

        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self._verify_otp(mobile_number="09129876543", code="123456")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "otp_not_found")

        me_response = self.client.get(self.me_url)
        self.assertIn(me_response.status_code, [401, 403])

        body = response.content.decode("utf-8")
        self.assertNotIn(str(first_user.pk), body)
        self.assertNotIn(str(second_user.pk), body)
        self.assertNotIn("first-auth-security@example.com", body)
        self.assertNotIn("second-auth-security@example.com", body)

    def test_otp_request_does_not_authenticate_existing_user(self):
        self._make_existing_user(mobile_number="09121234567")

        response = self._request_known_otp(mobile_number="09121234567", code="123456")
        self.assertEqual(response.status_code, 200)

        status_response = self.client.get(self.status_url)
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.json()["data"]["authenticated"])
        self.assertIsNone(status_response.json()["data"]["user"])

        me_response = self.client.get(self.me_url)
        self.assertIn(me_response.status_code, [401, 403])

    def test_inactive_user_is_not_logged_in_and_otp_is_consumed(self):
        user = self._make_existing_user(mobile_number="09121234567")
        user.is_active = False
        user.save(update_fields=["is_active"])

        self._request_known_otp(mobile_number="09121234567", code="123456")

        response = self._verify_otp(mobile_number="09121234567", code="123456")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "auth_user_not_found")
        self.assertIsNone(load_api_otp_record(mobile_number="09121234567"))

        replay_response = self._verify_otp(mobile_number="09121234567", code="123456")
        self.assertEqual(replay_response.status_code, 400)
        self.assertEqual(replay_response.json()["error"]["code"], "otp_not_found")

        me_response = self.client.get(self.me_url)
        self.assertIn(me_response.status_code, [401, 403])

    def test_status_does_not_expose_private_user_data(self):
        user = self._make_existing_user(
            mobile_number="09121234567",
            email="status-private-security@example.com",
        )
        self.client.force_login(user)

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["data"]["authenticated"])
        self.assertEqual(payload["data"]["user"]["id"], user.pk)
        self.assertEqual(payload["data"]["user"]["display_name"], "کاربر امنیت")

        body = response.content.decode("utf-8")
        self.assertNotIn("09121234567", body)
        self.assertNotIn("status-private-security@example.com", body)

    def test_logout_does_not_expose_private_user_data(self):
        user = self._make_existing_user(
            mobile_number="09121234567",
            email="logout-private-security@example.com",
        )
        self.client.force_login(user)

        response = self.client.post(self.logout_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["data"]["logged_out"])
        self.assertTrue(payload["data"]["was_authenticated"])

        body = response.content.decode("utf-8")
        self.assertNotIn("09121234567", body)
        self.assertNotIn("logout-private-security@example.com", body)
        self.assertNotIn(str(user.pk), body)

    def test_logout_only_clears_current_client_session(self):
        first_user = self._make_existing_user(
            mobile_number="09121234567",
            email="first-session-security@example.com",
            family="اول",
        )
        second_user = self._make_existing_user(
            mobile_number="09129876543",
            email="second-session-security@example.com",
            family="دوم",
        )

        first_client = Client()
        second_client = Client()

        first_client.force_login(first_user)
        second_client.force_login(second_user)

        first_logout = first_client.post(self.logout_url)
        self.assertEqual(first_logout.status_code, 200)
        self.assertTrue(first_logout.json()["data"]["was_authenticated"])

        first_me = first_client.get(self.me_url)
        self.assertIn(first_me.status_code, [401, 403])

        second_me = second_client.get(self.me_url)
        self.assertEqual(second_me.status_code, 200)
        self.assertEqual(second_me.json()["data"]["user"]["id"], second_user.pk)

    def test_otp_request_verify_and_logout_do_not_require_csrf(self):
        user = self._make_existing_user(mobile_number="09121234567")
        csrf_client = self.client_class(enforce_csrf_checks=True)

        with patch("apps.api.v1.auth_otp.generate_numeric_otp", return_value="123456"):
            request_response = csrf_client.post(
                self.request_url,
                data={"mobile_number": "09121234567"},
                content_type="application/json",
            )
        self.assertEqual(request_response.status_code, 200)

        verify_response = csrf_client.post(
            self.verify_url,
            data={
                "mobile_number": "09121234567",
                "code": "123456",
            },
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.json()["data"]["user"]["id"], user.pk)

        logout_response = csrf_client.post(self.logout_url)
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["data"]["logged_out"])

    def test_malformed_payloads_do_not_leak_settings_or_traceback(self):
        endpoints = [
            self.request_url,
            self.verify_url,
        ]

        for url in endpoints:
            response = self.client.post(
                url,
                data="{not-json",
                content_type="application/json",
            )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "invalid_payload")

            body = response.content.decode("utf-8")
            self.assertNotIn("SECRET_KEY", body)
            self.assertNotIn("DATABASES", body)
            self.assertNotIn("Traceback", body)
            self.assertNotIn("settings.py", body)
