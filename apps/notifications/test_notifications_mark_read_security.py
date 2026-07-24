from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationCategory,
    NotificationPriority,
    NotificationRecipient,
)


class NotificationsMarkReadSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _create_recipient(
        self,
        *,
        user,
        title="اعلان تست",
        audience_role=NotificationAudienceRole.CUSTOMER,
        is_read=False,
        action_url="/notifications/",
    ):
        notification = Notification.objects.create(
            event_type="mark_read_security_test",
            category=NotificationCategory.SYSTEM,
            priority=NotificationPriority.NORMAL,
            title=title,
            body="متن اعلان تست",
            action_url=action_url,
            icon="fa-regular fa-bell",
        )
        return NotificationRecipient.objects.create(
            notification=notification,
            user=user,
            audience_role=audience_role,
            is_read=is_read,
        )

    def test_mark_notification_read_requires_login(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        response = self.client.post(reverse("notifications:read", args=[recipient.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

        recipient.refresh_from_db()
        self.assertFalse(recipient.is_read)

    def test_mark_notification_read_cannot_read_other_user_recipient(self):
        customer = self.make_customer()
        other_customer = self.make_customer()
        recipient = self._create_recipient(user=other_customer.user)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("notifications:read", args=[recipient.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)

        recipient.refresh_from_db()
        self.assertFalse(recipient.is_read)

    def test_mark_notification_read_rejects_get_method(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.get(reverse("notifications:read", args=[recipient.pk]))

        self.assertEqual(response.status_code, 405)

        recipient.refresh_from_db()
        self.assertFalse(recipient.is_read)

    def test_mark_notification_read_external_next_falls_back_to_center(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("notifications:read", args=[recipient.pk]),
            {"next": "https://evil.example/phish"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("notifications:center"))

        recipient.refresh_from_db()
        self.assertTrue(recipient.is_read)

    def test_mark_notification_read_preserves_safe_relative_next(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("notifications:read", args=[recipient.pk]),
            {"next": "/notifications/?filter=unread"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/notifications/?filter=unread")

        recipient.refresh_from_db()
        self.assertTrue(recipient.is_read)

    def test_mark_notifications_read_all_rejects_get_method(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.get(reverse("notifications:read_all"))

        self.assertEqual(response.status_code, 405)

        recipient.refresh_from_db()
        self.assertFalse(recipient.is_read)

    def test_mark_notifications_read_all_rejects_invalid_role_in_post(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("notifications:read_all"),
            {"role": "customer;DROP"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_role")

        recipient.refresh_from_db()
        self.assertFalse(recipient.is_read)

    def test_mark_notifications_read_all_rejects_invalid_role_in_query(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.post(
            f"{reverse('notifications:read_all')}?role=bad-role",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_role")

        recipient.refresh_from_db()
        self.assertFalse(recipient.is_read)

    def test_mark_notifications_read_all_valid_role_marks_only_that_role(self):
        customer = self.make_customer()

        customer_recipient = self._create_recipient(
            user=customer.user,
            title="اعلان مشتری",
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        manager_recipient = self._create_recipient(
            user=customer.user,
            title="اعلان مدیر",
            audience_role=NotificationAudienceRole.MANAGER,
        )

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("notifications:read_all"),
            {"role": NotificationAudienceRole.CUSTOMER},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["unread_count"], 0)

        customer_recipient.refresh_from_db()
        manager_recipient.refresh_from_db()

        self.assertTrue(customer_recipient.is_read)
        self.assertFalse(manager_recipient.is_read)

    def test_mark_notifications_read_all_external_next_falls_back_to_center(self):
        customer = self.make_customer()
        recipient = self._create_recipient(user=customer.user)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("notifications:read_all"),
            {
                "next": "https://evil.example/phish",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("notifications:center"))

        recipient.refresh_from_db()
        self.assertTrue(recipient.is_read)
