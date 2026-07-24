from __future__ import annotations

import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.messaging.constants import (
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
)
from apps.messaging.management.commands.bale_delivery_queue_check import (
    run_bale_delivery_queue_check,
)
from apps.messaging.models import MessagingMessageLog, MessagingProvider
from apps.messaging.services import ensure_default_providers
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationRecipient,
)


class BaleDeliveryQueueCheckTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.user = CustomUser.objects.create_user(
            mobile_number="09127770011",
            email="bale-queue-check@example.com",
            name="Bale",
            family="Queue",
            password="pass12345",
        )

    def _make_delivery(self, *, status, attempt_count=0, last_error=""):
        notification = Notification.objects.create(
            event_type="bale.queue.check",
            title="تست صف بله",
            body="این متن نباید در خروجی command چاپ شود.",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        return NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
            status=status,
            attempt_count=attempt_count,
            last_error=last_error,
        )

    def test_default_dry_run_does_not_requeue_failed_delivery(self):
        delivery = self._make_delivery(
            status=NotificationDeliveryStatus.FAILED,
            attempt_count=3,
            last_error="provider timeout",
        )

        result = run_bale_delivery_queue_check(requeue_failed=True)

        delivery.refresh_from_db()
        self.assertTrue(result["summary"]["dry_run"])
        self.assertEqual(result["summary"]["requeued_count"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.FAILED)
        self.assertEqual(delivery.attempt_count, 3)
        self.assertEqual(delivery.last_error, "provider timeout")

    def test_apply_requeues_failed_delivery_without_sending_message(self):
        delivery = self._make_delivery(
            status=NotificationDeliveryStatus.FAILED,
            attempt_count=3,
            last_error="provider timeout",
        )

        result = run_bale_delivery_queue_check(
            delivery_ids=[delivery.pk],
            requeue_failed=True,
            apply=True,
        )

        delivery.refresh_from_db()
        self.assertFalse(result["summary"]["dry_run"])
        self.assertEqual(result["summary"]["requeued_count"], 1)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)
        self.assertEqual(delivery.last_error, "")
        self.assertIsNone(delivery.failed_at)
        self.assertIn("bale_requeue_history", delivery.metadata)

    def test_apply_does_not_touch_sent_delivery(self):
        delivery = self._make_delivery(
            status=NotificationDeliveryStatus.SENT,
            attempt_count=1,
            last_error="",
        )

        result = run_bale_delivery_queue_check(
            delivery_ids=[delivery.pk],
            statuses=[NotificationDeliveryStatus.SENT],
            requeue_failed=True,
            requeue_pending_setup=True,
            apply=True,
        )

        delivery.refresh_from_db()
        self.assertEqual(result["summary"]["requeued_count"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SENT)
        self.assertEqual(delivery.attempt_count, 1)

    def test_pending_setup_requires_explicit_requeue_flag(self):
        delivery = self._make_delivery(
            status=NotificationDeliveryStatus.PENDING_SETUP,
            attempt_count=2,
            last_error="missing identity",
        )

        result = run_bale_delivery_queue_check(
            delivery_ids=[delivery.pk],
            requeue_failed=True,
            apply=True,
        )

        delivery.refresh_from_db()
        self.assertEqual(result["summary"]["requeued_count"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.PENDING_SETUP)

        result = run_bale_delivery_queue_check(
            delivery_ids=[delivery.pk],
            requeue_pending_setup=True,
            apply=True,
        )

        delivery.refresh_from_db()
        self.assertEqual(result["summary"]["requeued_count"], 1)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)

    def test_json_output_does_not_print_token_secret_or_message_body(self):
        token_value = "real-bale-token-should-not-appear"
        secret_value = "real-bale-secret-should-not-appear"
        delivery = self._make_delivery(
            status=NotificationDeliveryStatus.FAILED,
            attempt_count=1,
            last_error="failed without secret",
        )
        MessagingMessageLog.objects.create(
            provider=self.bale,
            notification_delivery=delivery,
            direction=MessagingMessageDirection.OUTBOUND,
            status=MessagingMessageStatus.FAILED,
            text="این متن پیام نباید در خروجی چاپ شود.",
            error_message="provider failed",
        )

        out = io.StringIO()
        with self.settings(
            BALE_BOT_TOKEN=token_value,
            BALE_WEBHOOK_SECRET=secret_value,
        ):
            call_command("bale_delivery_queue_check", "--json", stdout=out)

        raw = out.getvalue()
        payload = json.loads(raw)

        self.assertNotIn(token_value, raw)
        self.assertNotIn(secret_value, raw)
        self.assertNotIn("این متن پیام نباید در خروجی چاپ شود", raw)
        self.assertEqual(payload["counts"]["failed_outbound_message_logs"], 1)

    def test_strict_fails_when_queue_has_warning_issue(self):
        self._make_delivery(
            status=NotificationDeliveryStatus.FAILED,
            attempt_count=1,
            last_error="provider failed",
        )

        with self.assertRaises(CommandError):
            call_command("bale_delivery_queue_check", "--strict")
