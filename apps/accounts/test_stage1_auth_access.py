from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.accounts.services.sms import SMSDeliveryResult
from apps.accounts.views import (
    USER_SESSION_KEY,
    _get_valid_password_reset_session,
    _role_redirect_name,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin

TEST_LOC_MEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "stage1-auth-access-tests",
    }
}


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SMS_OTP_CODE_LENGTH=5,
    OTP_EXPIRY_SECONDS=180,
    OTP_MAX_ATTEMPTS=5,
    OTP_RESEND_COOLDOWN_SECONDS=30,
    PASSWORD_RESET_SESSION_TTL_SECONDS=900,
    CACHES=TEST_LOC_MEM_CACHES,
)
class Stage1AuthAndAccessTests(Stage1DomainFactoryMixin, TestCase):
    def test_role_redirect_name_maps_known_profiles(self):
        customer = self.make_customer()
        manager = self.make_salon_manager()
        stylist = self.make_stylist()
        neutral = self.make_user()

        self.assertEqual(_role_redirect_name(customer.user), "accounts:customer_panel")
        self.assertEqual(
            _role_redirect_name(manager.user), "dashboards:salon_manager_dashboard"
        )
        self.assertEqual(
            _role_redirect_name(stylist.user), "dashboards:stylist_dashboard"
        )
        self.assertEqual(_role_redirect_name(neutral), "salons:show_salons")

    @patch("apps.accounts.views.utils.send_otp_sms")
    @patch("apps.accounts.views.utils.create_random_code", return_value=12345)
    def test_customer_signup_starts_otp_flow_and_creates_inactive_customer(
        self, _mock_code, mock_send_sms
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
                "mobile_number": "09123456789",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "agree_to_terms": "on",
            },
        )

        self.assertRedirects(response, reverse("accounts:verify"))
        user = get_user_model().objects.get(mobile_number="09123456789")
        self.assertFalse(user.is_active)
        self.assertTrue(Customer.objects.filter(user=user).exists())
        session = self.client.session[USER_SESSION_KEY]
        self.assertEqual(session["mobile_number"], "09123456789")
        self.assertEqual(session["active_code"], "12345")
        self.assertEqual(session["signup_kind"], "customer")

    def test_verify_register_success_activates_customer_and_logs_in(self):
        customer = self.make_customer(is_active=False)
        session = self.client.session
        session[USER_SESSION_KEY] = {
            "mobile_number": customer.user.mobile_number,
            "active_code": "12345",
            "remember_password": False,
            "signup_kind": "customer",
            "otp_expires_at": 9999999999,
            "otp_attempts": 0,
            "otp_max_attempts": 5,
            "otp_verified": False,
        }
        session.save()

        response = self.client.post(
            reverse("accounts:verify"), {"active_code": "12345"}
        )

        self.assertRedirects(response, reverse("accounts:customer_panel"))
        customer.user.refresh_from_db()
        self.assertTrue(customer.user.is_active)
        self.assertEqual(
            int(self.client.session.get("_auth_user_id")), customer.user.pk
        )
        self.assertNotIn(USER_SESSION_KEY, self.client.session)

    def test_verify_register_wrong_otp_increments_attempts(self):
        customer = self.make_customer(is_active=False)
        session = self.client.session
        session[USER_SESSION_KEY] = {
            "mobile_number": customer.user.mobile_number,
            "active_code": "12345",
            "remember_password": False,
            "signup_kind": "customer",
            "otp_expires_at": 9999999999,
            "otp_attempts": 0,
            "otp_max_attempts": 5,
            "otp_verified": False,
        }
        session.save()

        response = self.client.post(
            reverse("accounts:verify"), {"active_code": "99999"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[USER_SESSION_KEY]["otp_attempts"], 1)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("تلاش دیگر" in message for message in messages))

    def test_password_reset_session_is_valid_before_expiry(self):
        request_session = self.client.session
        request_session[USER_SESSION_KEY] = {
            "remember_password": True,
            "otp_verified": True,
            "password_reset_authorized_until": 9999999999,
        }
        request_session.save()

        request = self.client.get(reverse("accounts:login")).wsgi_request
        request.session = self.client.session

        self.assertIsNotNone(_get_valid_password_reset_session(request))

    def test_customer_panel_redirects_manager_user_to_manager_dashboard(self):
        manager = self.make_salon_manager(password="StrongPass123!")
        self.client.force_login(manager.user)

        response = self.client.get(
            reverse("accounts:customer_panel"),
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse("dashboards:salon_manager_dashboard"),
            fetch_redirect_response=False,
        )
