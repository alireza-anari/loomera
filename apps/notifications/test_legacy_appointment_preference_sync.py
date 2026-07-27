from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationDeliveryStatus,
)
from apps.orders.lifecycle import (
    dispatch_due_order_reminders,
)
from apps.orders.models import AppointmentNotification
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers." "MD5PasswordHasher"],
    EMAIL_BACKEND=("django.core.mail.backends." "dummy.EmailBackend"),
    DEFAULT_FROM_EMAIL="staging@loomera.ir",
    SMS_PROVIDER="disabled",
    LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY=True,
)
class LegacyAppointmentPreferenceSyncTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        super().setUp()

        self.customer = self.make_customer(
            notify_appointment_email=False,
            notify_appointment_sms=False,
        )
        manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=manager,
        )

        self.order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            status="pending",
            reminder_status="scheduled",
            reminder_due_at=(timezone.now() - timedelta(minutes=5)),
        )

    def _unified_delivery(self, legacy):
        notification = Notification.objects.get(
            dedupe_key=("legacy_appointment_notification:" f"{legacy.pk}")
        )

        return NotificationDelivery.objects.get(
            recipient__notification=notification,
            recipient__audience_role=legacy.audience_role,
            channel=legacy.channel,
        )

    def test_customer_reminder_opt_out_skips_both_layers(
        self,
    ):
        result = dispatch_due_order_reminders(limit=1)

        self.assertEqual(
            result,
            {
                "processed": 1,
                "sent": 1,
            },
        )

        self.order.refresh_from_db()

        self.assertEqual(
            self.order.reminder_status,
            "sent",
        )
        self.assertIsNotNone(self.order.reminder_sent_at)

        reminders = {
            item.channel: item
            for item in (
                AppointmentNotification.objects.filter(
                    order=self.order,
                    event_type="reminder_due",
                )
            )
        }

        self.assertEqual(
            set(reminders),
            {
                "dashboard",
                "email",
                "sms",
            },
        )

        self.assertEqual(
            reminders["dashboard"].delivery_status,
            "sent",
        )
        self.assertEqual(
            reminders["email"].delivery_status,
            "skipped",
        )
        self.assertEqual(
            reminders["sms"].delivery_status,
            "skipped",
        )

        self.assertEqual(
            reminders["email"].meta.get("reason"),
            "customer_email_opt_out",
        )
        self.assertEqual(
            reminders["sms"].meta.get("reason"),
            "customer_sms_opt_out",
        )

        email_delivery = self._unified_delivery(reminders["email"])
        sms_delivery = self._unified_delivery(reminders["sms"])

        self.assertEqual(
            email_delivery.status,
            NotificationDeliveryStatus.SKIPPED,
        )
        self.assertEqual(
            sms_delivery.status,
            NotificationDeliveryStatus.SKIPPED,
        )

        self.assertEqual(
            email_delivery.metadata.get("reason"),
            "customer_email_opt_out",
        )
        self.assertEqual(
            sms_delivery.metadata.get("reason"),
            "customer_sms_opt_out",
        )

        self.assertEqual(
            email_delivery.attempt_count,
            0,
        )
        self.assertEqual(
            sms_delivery.attempt_count,
            0,
        )

        self.assertFalse(
            NotificationDelivery.objects.filter(
                channel__in=["email", "sms"],
                status__in=["queued", "failed"],
            ).exists()
        )
