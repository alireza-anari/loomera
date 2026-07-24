from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.accounts.models import CustomerNotification


class CustomerNotificationActionsSecurityTests(Stage1DomainFactoryMixin, TestCase):
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

    def test_mark_customer_notification_read_requires_login(self):
        customer = self.make_customer()
        notification = self._create_notification(customer=customer)

        response = self.client.post(
            reverse("accounts:notification_read", args=[notification.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_customer_notification_read_rejects_get_method(self):
        customer = self.make_customer()
        notification = self._create_notification(customer=customer)

        self.client.force_login(customer.user)
        response = self.client.get(
            reverse("accounts:notification_read", args=[notification.pk])
        )

        self.assertEqual(response.status_code, 405)

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_customer_notification_read_forbids_non_customer_user(self):
        customer = self.make_customer()
        manager = self.make_salon_manager()
        notification = self._create_notification(customer=customer)

        self.client.force_login(manager.user)
        response = self.client.post(
            reverse("accounts:notification_read", args=[notification.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "not_customer")

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_customer_notification_read_cannot_read_other_user_notification(self):
        customer = self.make_customer()
        other_customer = self.make_customer()
        notification = self._create_notification(customer=other_customer)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:notification_read", args=[notification.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    @override_settings(CUSTOMER_NOTIFICATION_ACTION_POST_MAX_BYTES=32)
    def test_mark_customer_notification_read_rejects_oversized_payload(self):
        customer = self.make_customer()
        notification = self._create_notification(customer=customer)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:notification_read", args=[notification.pk]),
            {"payload": "x" * 200},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_customer_notification_read_marks_own_notification(self):
        customer = self.make_customer()
        notification = self._create_notification(customer=customer)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:notification_read", args=[notification.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["notification_id"], notification.pk)
        self.assertEqual(payload["unread_count"], 0)

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_all_customer_notifications_read_rejects_get_method(self):
        customer = self.make_customer()
        notification = self._create_notification(customer=customer)

        self.client.force_login(customer.user)
        response = self.client.get(reverse("accounts:notifications_read_all"))

        self.assertEqual(response.status_code, 405)

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_customer_notifications_read_forbids_non_customer_user(self):
        customer = self.make_customer()
        manager = self.make_salon_manager()
        notification = self._create_notification(customer=customer)

        self.client.force_login(manager.user)
        response = self.client.post(
            reverse("accounts:notifications_read_all"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "not_customer")

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    @override_settings(CUSTOMER_NOTIFICATION_ACTION_POST_MAX_BYTES=32)
    def test_mark_all_customer_notifications_read_rejects_oversized_payload(self):
        customer = self.make_customer()
        notification = self._create_notification(customer=customer)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:notifications_read_all"),
            {"payload": "x" * 200},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_customer_notifications_read_marks_only_current_user(self):
        customer = self.make_customer()
        other_customer = self.make_customer()

        own_one = self._create_notification(customer=customer)
        own_two = self._create_notification(customer=customer)
        other_notification = self._create_notification(customer=other_customer)

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("accounts:notifications_read_all"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["updated"], 2)
        self.assertEqual(payload["unread_count"], 0)

        own_one.refresh_from_db()
        own_two.refresh_from_db()
        other_notification.refresh_from_db()

        self.assertTrue(own_one.is_read)
        self.assertTrue(own_two.is_read)
        self.assertFalse(other_notification.is_read)
