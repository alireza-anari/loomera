from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.accounts.models import CustomerNotification


class CustomerNotificationsSummarySecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _url(self):
        return reverse("accounts:notifications_summary")

    def _create_notification(self, *, customer, **kwargs):
        defaults = {
            "user": customer.user,
            "customer": customer,
            "category": CustomerNotification.CATEGORY_SYSTEM,
            "title": "اعلان تست",
            "body": "متن اعلان تست",
            "action_url": "/accounts/notifications/",
            "priority": CustomerNotification.PRIORITY_NORMAL,
            "is_read": False,
        }
        defaults.update(kwargs)
        return CustomerNotification.objects.create(**defaults)

    def test_notifications_summary_requires_login(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_notifications_summary_rejects_post_method(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(self._url())

        self.assertEqual(response.status_code, 405)

    def test_notifications_summary_forbids_non_customer_user(self):
        manager = self.make_salon_manager()
        self.client.force_login(manager.user)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "not_customer")

    def test_notifications_summary_returns_only_current_user_notifications(self):
        customer = self.make_customer()
        other_customer = self.make_customer()

        own_notification = self._create_notification(
            customer=customer,
            title="اعلان خود کاربر",
        )
        self._create_notification(
            customer=other_customer,
            title="اعلان کاربر دیگر",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        ids = {item["id"] for item in payload["notifications"]}

        self.assertIn(own_notification.id, ids)
        self.assertEqual(len(ids), 1)
        self.assertEqual(payload["unread_count"], 1)

    def test_notifications_summary_preserves_safe_relative_action_url(self):
        customer = self.make_customer()
        self._create_notification(
            customer=customer,
            action_url="/orders/appointments/",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        notification = response.json()["notifications"][0]
        self.assertEqual(notification["action_url"], "/orders/appointments/")

    def test_notifications_summary_strips_external_action_url(self):
        customer = self.make_customer()
        self._create_notification(
            customer=customer,
            action_url="https://evil.example/phish",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url(), HTTP_HOST="testserver")

        self.assertEqual(response.status_code, 200)
        notification = response.json()["notifications"][0]
        self.assertEqual(notification["action_url"], "")

    def test_notifications_summary_strips_javascript_action_url(self):
        customer = self.make_customer()
        self._create_notification(
            customer=customer,
            action_url="javascript:alert(1)",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        notification = response.json()["notifications"][0]
        self.assertEqual(notification["action_url"], "")

    @override_settings(CUSTOMER_NOTIFICATION_SUMMARY_BODY_MAX_CHARS=12)
    def test_notifications_summary_truncates_body(self):
        customer = self.make_customer()
        self._create_notification(
            customer=customer,
            body="این متن اعلان بیشتر از حد مجاز summary است",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)

        notification = response.json()["notifications"][0]
        self.assertLessEqual(len(notification["body"]), 12)

    def test_notifications_summary_limits_latest_notifications_to_five(self):
        customer = self.make_customer()

        for index in range(7):
            self._create_notification(
                customer=customer,
                title=f"اعلان {index}",
            )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["notifications"]), 5)
