from __future__ import annotations

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(CUSTOMER_NOTIFICATION_SETTINGS_MAX_BYTES=64)
class CustomerNotificationSettingsSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def test_notification_settings_requires_login(self):
        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps({"notify_marketing_sms": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_notification_settings_rejects_get_method(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.get(reverse("accounts:update_notification_settings"))

        self.assertEqual(response.status_code, 405)

    def test_notification_settings_forbids_non_customer_user(self):
        manager = self.make_salon_manager()
        self.client.force_login(manager.user)

        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps({"notify_marketing_sms": False}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_notification_settings_rejects_oversized_payload(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps({"notify_marketing_sms": "x" * 100}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

    def test_notification_settings_rejects_json_array(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps(["notify_marketing_sms"]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_json")

    def test_notification_settings_rejects_invalid_boolean_value(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps({"notify_marketing_sms": "definitely"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_notification_value")

    def test_notification_settings_string_false_is_saved_as_false(self):
        customer = self.make_customer()
        customer.notify_marketing_sms = True
        customer.save(update_fields=["notify_marketing_sms"])

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps({"notify_marketing_sms": "false"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        customer.refresh_from_db()
        self.assertFalse(customer.notify_marketing_sms)

    def test_notification_settings_accepts_boolean_values(self):
        customer = self.make_customer()
        customer.notify_appointment_email = False
        customer.save(update_fields=["notify_appointment_email"])

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps({"notify_appointment_email": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        customer.refresh_from_db()
        self.assertTrue(customer.notify_appointment_email)
        
    @override_settings(CUSTOMER_NOTIFICATION_SETTINGS_MAX_BYTES=512)
    def test_notification_settings_ignores_unknown_fields(self):
        customer = self.make_customer()
        customer.notify_marketing_email = False
        customer.save(update_fields=["notify_marketing_email"])

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:update_notification_settings"),
            data=json.dumps(
                {
                    "notify_marketing_email": True,
                    "is_staff": True,
                    "mobile_number": "09120000000",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        customer.refresh_from_db()
        self.assertTrue(customer.notify_marketing_email)
        self.assertFalse(customer.user.is_staff)