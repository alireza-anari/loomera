from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationCategory,
    NotificationPriority,
    NotificationRecipient,
)


class NotificationsSummarySecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _url(self):
        return reverse("notifications:summary")

    def _create_recipient(self, *, user, title="اعلان تست", body="متن اعلان", **kwargs):
        notification_defaults = {
            "event_type": kwargs.pop("event_type", "security_test_event"),
            "category": kwargs.pop("category", NotificationCategory.SYSTEM),
            "priority": kwargs.pop("priority", NotificationPriority.NORMAL),
            "title": title,
            "body": body,
            "action_url": kwargs.pop("action_url", "/notifications/"),
            "icon": kwargs.pop("icon", "fa-regular fa-bell"),
        }
        notification = Notification.objects.create(**notification_defaults)
        return NotificationRecipient.objects.create(
            notification=notification,
            user=user,
            audience_role=kwargs.pop(
                "audience_role",
                NotificationAudienceRole.CUSTOMER,
            ),
            is_read=kwargs.pop("is_read", False),
        )

    def test_notifications_summary_requires_login(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_notifications_summary_rejects_post_method(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(self._url())

        self.assertEqual(response.status_code, 405)

    def test_notifications_summary_rejects_invalid_role(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.get(self._url(), {"role": "owner;DROP"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_role")

    def test_notifications_summary_returns_only_current_user_notifications(self):
        customer = self.make_customer()
        other_customer = self.make_customer()

        own_recipient = self._create_recipient(
            user=customer.user,
            title="اعلان خود کاربر",
        )
        self._create_recipient(
            user=other_customer.user,
            title="اعلان کاربر دیگر",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        ids = {item["id"] for item in payload["notifications"]}

        self.assertIn(own_recipient.id, ids)
        self.assertEqual(len(ids), 1)
        self.assertEqual(payload["unread_count"], 1)

    def test_notifications_summary_filters_valid_role(self):
        customer = self.make_customer()

        customer_recipient = self._create_recipient(
            user=customer.user,
            title="اعلان مشتری",
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        self._create_recipient(
            user=customer.user,
            title="اعلان مدیر",
            audience_role=NotificationAudienceRole.MANAGER,
        )

        self.client.force_login(customer.user)
        response = self.client.get(
            self._url(),
            {"role": NotificationAudienceRole.CUSTOMER},
        )

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        ids = {item["id"] for item in payload["notifications"]}

        self.assertIn(customer_recipient.id, ids)
        self.assertEqual(len(ids), 1)
        self.assertEqual(payload["unread_count"], 1)

    def test_notifications_summary_preserves_safe_relative_action_url(self):
        customer = self.make_customer()
        self._create_recipient(
            user=customer.user,
            action_url="/orders/appointments/",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        notification = response.json()["notifications"][0]
        self.assertEqual(notification["action_url"], "/orders/appointments/")

    def test_notifications_summary_strips_external_action_url(self):
        customer = self.make_customer()
        self._create_recipient(
            user=customer.user,
            action_url="https://evil.example/phish",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url(), HTTP_HOST="testserver")

        self.assertEqual(response.status_code, 200)
        notification = response.json()["notifications"][0]
        self.assertEqual(notification["action_url"], "")

    def test_notifications_summary_strips_javascript_action_url(self):
        customer = self.make_customer()
        self._create_recipient(
            user=customer.user,
            action_url="javascript:alert(1)",
        )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        notification = response.json()["notifications"][0]
        self.assertEqual(notification["action_url"], "")

    @override_settings(NOTIFICATIONS_SUMMARY_BODY_MAX_CHARS=12)
    def test_notifications_summary_truncates_body(self):
        customer = self.make_customer()
        self._create_recipient(
            user=customer.user,
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
            self._create_recipient(
                user=customer.user,
                title=f"اعلان {index}",
            )

        self.client.force_login(customer.user)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["notifications"]), 5)
