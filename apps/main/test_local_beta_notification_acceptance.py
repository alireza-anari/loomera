from __future__ import annotations

from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.main.management.commands.seed_local_demo_data import (
    SEED_TAG,
)
from apps.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryStatus,
    NotificationRecipient,
)
from apps.orders.lifecycle import (
    notify_manager_and_stylists_for_booking,
    schedule_order_reminder,
)
from apps.orders.models import (
    AppointmentNotification,
    Order,
)
from apps.payments.models import (
    LedgerEntry,
    Payment,
    StaffEarning,
    WalletTransaction,
)


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ],
    ONLINE_PAYMENT_ENABLED=False,
    PAYMENT_MODE="mock",
    LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY=False,
    LOOMERA_NOTIFICATION_MAX_ATTEMPTS=3,
    EMAIL_BACKEND=("django.core.mail.backends.dummy.EmailBackend"),
    DEFAULT_FROM_EMAIL="local@loomera.test",
    SMS_PROVIDER="disabled",
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    BALE_BOT_TOKEN="local-test-token",
    MESSAGING_OUTBOUND_ENABLED=False,
    MESSAGING_ACTIONS_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=["bale"],
    CACHES={
        "default": {
            "BACKEND": ("django.core.cache.backends.locmem." "LocMemCache"),
            "LOCATION": ("local-beta-notification-acceptance"),
        }
    },
    STORAGES={
        "default": {
            "BACKEND": ("django.core.files.storage." "FileSystemStorage"),
        },
        "staticfiles": {
            "BACKEND": ("django.contrib.staticfiles.storage." "StaticFilesStorage"),
        },
    },
)
class LocalBetaNotificationAcceptanceTests(TestCase):
    def test_booking_notifications_are_queued_and_processed_safely(
        self,
    ):
        with TemporaryDirectory() as media_root:
            with self.settings(
                MEDIA_ROOT=media_root,
            ):
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    beta_acceptance=True,
                    days=14,
                    stdout=StringIO(),
                )

                order = (
                    Order.objects.select_related(
                        "customer__user",
                        "salon__salon_manager__user",
                    )
                    .prefetch_related(
                        "order_details1__stylist__user",
                        "order_details1__service",
                    )
                    .get(description=(f"{SEED_TAG}:order:" "pending-pay-in-salon"))
                )

                appointment = order.order_details1.select_related(
                    "stylist__user",
                    "service",
                ).get()

                customer_user = order.customer.user
                manager_user = order.salon.salon_manager.user
                stylist_user = appointment.stylist.user

                expected_recipient_ids = {
                    customer_user.pk,
                    manager_user.pk,
                    stylist_user.pk,
                }

                financial_counts_before = {
                    "payments": Payment.objects.count(),
                    "wallet_transactions": (WalletTransaction.objects.count()),
                    "ledger_entries": (LedgerEntry.objects.count()),
                    "staff_earnings": (StaffEarning.objects.count()),
                }

                legacy_ids_before = set(
                    AppointmentNotification.objects.values_list("pk", flat=True)
                )
                unified_ids_before = set(
                    Notification.objects.values_list(
                        "pk",
                        flat=True,
                    )
                )
                recipient_ids_before = set(
                    NotificationRecipient.objects.values_list("pk", flat=True)
                )
                delivery_ids_before = set(
                    NotificationDelivery.objects.values_list("pk", flat=True)
                )

                schedule_order_reminder(order)

                notify_manager_and_stylists_for_booking(
                    order,
                    event_type="booking_created",
                )

                order.refresh_from_db()

                self.assertEqual(
                    order.reminder_status,
                    "scheduled",
                )
                self.assertIsNotNone(order.reminder_due_at)

                new_legacy_notifications = AppointmentNotification.objects.exclude(
                    pk__in=legacy_ids_before
                ).filter(order=order)

                self.assertTrue(new_legacy_notifications.exists())

                dashboard_roles = set(
                    new_legacy_notifications.filter(
                        event_type="booking_created",
                        channel="dashboard",
                    ).values_list(
                        "audience_role",
                        flat=True,
                    )
                )

                self.assertEqual(
                    dashboard_roles,
                    {
                        "customer",
                        "manager",
                        "stylist",
                    },
                )

                self.assertTrue(
                    new_legacy_notifications.filter(
                        event_type="booking_created",
                        audience_role="stylist",
                        channel="email",
                        delivery_status="queued",
                    ).exists()
                )
                self.assertTrue(
                    new_legacy_notifications.filter(
                        event_type="booking_created",
                        audience_role="stylist",
                        channel="sms",
                        delivery_status="queued",
                    ).exists()
                )
                self.assertTrue(
                    new_legacy_notifications.filter(
                        event_type="reminder_scheduled",
                        audience_role="system",
                        channel="system",
                    ).exists()
                )

                new_unified_notifications = Notification.objects.exclude(
                    pk__in=unified_ids_before
                )

                self.assertTrue(new_unified_notifications.exists())

                new_recipients = NotificationRecipient.objects.exclude(
                    pk__in=recipient_ids_before
                ).select_related(
                    "notification",
                    "user",
                )

                actual_recipient_ids = set(
                    new_recipients.values_list(
                        "user_id",
                        flat=True,
                    )
                )

                self.assertEqual(
                    actual_recipient_ids,
                    expected_recipient_ids,
                )

                self.assertFalse(
                    new_recipients.exclude(user_id__in=expected_recipient_ids).exists()
                )

                new_deliveries = NotificationDelivery.objects.exclude(
                    pk__in=delivery_ids_before
                ).select_related(
                    "recipient__notification",
                    "recipient__user",
                )

                self.assertTrue(
                    new_deliveries.filter(
                        channel="dashboard",
                        status=(NotificationDeliveryStatus.SENT),
                    ).exists()
                )

                bale_deliveries = new_deliveries.filter(channel="bale")

                self.assertTrue(bale_deliveries.exists())
                self.assertFalse(
                    bale_deliveries.exclude(
                        status=(NotificationDeliveryStatus.QUEUED)
                    ).exists()
                )
                self.assertFalse(bale_deliveries.exclude(attempt_count=0).exists())

                with (
                    patch(
                        "apps.notifications.delivery." "send_mail",
                        return_value=1,
                    ),
                    patch(
                        "apps.orders.notification_delivery." "send_mail",
                        return_value=1,
                    ),
                    patch(
                        "apps.notifications.delivery." "urllib.request.urlopen"
                    ) as unified_urlopen,
                    patch(
                        "apps.orders.notification_delivery." "urllib.request.urlopen"
                    ) as legacy_urlopen,
                ):
                    unified_output = StringIO()

                    call_command(
                        "process_notification_deliveries",
                        limit=100,
                        include_failed=True,
                        stdout=unified_output,
                    )

                    legacy_output = StringIO()

                    call_command(
                        "dispatch_appointment_notifications",
                        limit=100,
                        include_failed=True,
                        skip_reminders=True,
                        stdout=legacy_output,
                    )

                unified_urlopen.assert_not_called()
                legacy_urlopen.assert_not_called()

                new_deliveries = NotificationDelivery.objects.exclude(
                    pk__in=delivery_ids_before
                )

                # Email/SMS workers may mark rows as sent,
                # skipped or pending_setup, but they must
                # no longer remain unprocessed.
                self.assertFalse(
                    new_deliveries.filter(
                        channel__in=[
                            "email",
                            "sms",
                        ],
                        status=(NotificationDeliveryStatus.QUEUED),
                    ).exists()
                )

                new_legacy_notifications = AppointmentNotification.objects.exclude(
                    pk__in=legacy_ids_before
                ).filter(order=order)

                self.assertFalse(
                    new_legacy_notifications.filter(
                        channel__in=[
                            "email",
                            "sms",
                        ],
                        delivery_status="queued",
                    ).exists()
                )

                # Bale must remain untouched because outbound
                # delivery is intentionally disabled.
                bale_deliveries = NotificationDelivery.objects.exclude(
                    pk__in=delivery_ids_before
                ).filter(channel="bale")

                self.assertTrue(bale_deliveries.exists())
                self.assertFalse(
                    bale_deliveries.exclude(
                        status=(NotificationDeliveryStatus.QUEUED)
                    ).exists()
                )
                self.assertFalse(bale_deliveries.exclude(attempt_count=0).exists())

                self.assertFalse(
                    NotificationDeliveryAttempt.objects.filter(
                        delivery__in=bale_deliveries
                    ).exists()
                )

                # No notification command may create or alter
                # booking financial artifacts.
                self.assertEqual(
                    Payment.objects.count(),
                    financial_counts_before["payments"],
                )
                self.assertEqual(
                    WalletTransaction.objects.count(),
                    financial_counts_before["wallet_transactions"],
                )
                self.assertEqual(
                    LedgerEntry.objects.count(),
                    financial_counts_before["ledger_entries"],
                )
                self.assertEqual(
                    StaffEarning.objects.count(),
                    financial_counts_before["staff_earnings"],
                )
