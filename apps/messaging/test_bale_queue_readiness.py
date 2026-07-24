from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.messaging.constants import MessagingProviderKey
from apps.messaging.models import MessagingProvider, MessagingMessageLog
from apps.messaging.notification_delivery import (
    bale_outbound_queue_ready,
    queue_processable_messaging_channels,
)
from apps.messaging.services import (
    connect_identity_to_user,
    ensure_default_providers,
    get_or_create_identity,
)
from apps.notifications.delivery import process_queued_deliveries
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryStatus,
    NotificationRecipient,
)


class BaleQueueReadinessTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.supports_outbound = True
        self.bale.save(update_fields=["is_active", "supports_outbound"])

        self.user = CustomUser.objects.create_user(
            mobile_number="09123334455",
            email="bale-queue@example.com",
            name="کاربر",
            family="بله",
            password="pass12345",
        )

    def _connect_identity(self):
        identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="bale-queue-user",
            chat_id="bale-queue-chat",
            display_name="کاربر صف بله",
        )
        connect_identity_to_user(identity, self.user)
        return identity

    def _delivery(self):
        notification = Notification.objects.create(
            event_type="bale.queue.readiness",
            title="یادآوری نوبت",
            body="این یک پیام تست بله است.",
            action_url="/orders/1/",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        return NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
            status=NotificationDeliveryStatus.QUEUED,
        )

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_queue_does_not_consume_bale_delivery_when_outbound_is_disabled(self):
        self._connect_identity()
        delivery = self._delivery()

        self.assertFalse(bale_outbound_queue_ready())
        self.assertEqual(queue_processable_messaging_channels(), [])

        result = process_queued_deliveries(limit=10)

        delivery.refresh_from_db()
        self.assertEqual(result["processed"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)
        self.assertEqual(NotificationDeliveryAttempt.objects.count(), 0)
        self.assertEqual(MessagingMessageLog.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=False,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_queue_does_not_consume_bale_delivery_when_bale_bot_is_disabled(self):
        self._connect_identity()
        delivery = self._delivery()

        result = process_queued_deliveries(limit=10)

        delivery.refresh_from_db()
        self.assertEqual(result["processed"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="",
    )
    def test_queue_does_not_consume_bale_delivery_when_token_is_missing(self):
        self._connect_identity()
        delivery = self._delivery()

        result = process_queued_deliveries(limit=10)

        delivery.refresh_from_db()
        self.assertEqual(result["processed"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    @patch("apps.bale_bot.client.request.urlopen")
    def test_queue_processes_bale_delivery_when_outbound_is_ready(self, mocked_urlopen):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true, "result": {"message_id": 77}}'

        mocked_urlopen.return_value = FakeResponse()

        self._connect_identity()
        delivery = self._delivery()

        self.assertTrue(bale_outbound_queue_ready())
        self.assertEqual(
            queue_processable_messaging_channels(), [NotificationChannel.BALE]
        )

        result = process_queued_deliveries(limit=10)

        delivery.refresh_from_db()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SENT)
        self.assertEqual(delivery.attempt_count, 1)
        self.assertEqual(NotificationDeliveryAttempt.objects.count(), 1)
        self.assertEqual(
            MessagingMessageLog.objects.filter(notification_delivery=delivery).count(),
            1,
        )
