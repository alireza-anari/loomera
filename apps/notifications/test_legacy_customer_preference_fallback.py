from django.test import TestCase

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
)
from apps.notifications.services import notification_preference_enabled


class LegacyCustomerPreferenceFallbackTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def _is_enabled(
        self,
        *,
        user,
        channel,
        category=NotificationCategory.BOOKING,
    ):
        return notification_preference_enabled(
            user=user,
            audience_role=NotificationAudienceRole.CUSTOMER,
            category=category,
            event_type="reminder_due",
            channel=channel,
            priority=NotificationPriority.NORMAL,
        )

    def test_booking_email_falls_back_to_legacy_opt_out(self):
        customer = self.make_customer()
        customer.notify_appointment_email = False
        customer.save(update_fields=["notify_appointment_email"])

        self.assertFalse(
            self._is_enabled(
                user=customer.user,
                channel=NotificationChannel.EMAIL,
            )
        )

    def test_booking_sms_falls_back_to_legacy_opt_out(self):
        customer = self.make_customer()
        customer.notify_appointment_sms = False
        customer.save(update_fields=["notify_appointment_sms"])

        self.assertFalse(
            self._is_enabled(
                user=customer.user,
                channel=NotificationChannel.SMS,
            )
        )

    def test_booking_legacy_enabled_value_remains_enabled(self):
        customer = self.make_customer()
        customer.notify_appointment_email = True
        customer.save(update_fields=["notify_appointment_email"])

        self.assertTrue(
            self._is_enabled(
                user=customer.user,
                channel=NotificationChannel.EMAIL,
            )
        )

    def test_explicit_unified_preference_overrides_legacy_value(self):
        customer = self.make_customer()
        customer.notify_appointment_email = False
        customer.save(update_fields=["notify_appointment_email"])

        NotificationPreference.objects.create(
            user=customer.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
            category=NotificationCategory.BOOKING,
            event_type="",
            channel=NotificationChannel.EMAIL,
            is_enabled=True,
        )

        self.assertTrue(
            self._is_enabled(
                user=customer.user,
                channel=NotificationChannel.EMAIL,
            )
        )

    def test_marketing_email_uses_legacy_marketing_setting(self):
        customer = self.make_customer()
        customer.notify_marketing_email = False
        customer.save(update_fields=["notify_marketing_email"])

        self.assertFalse(
            self._is_enabled(
                user=customer.user,
                channel=NotificationChannel.EMAIL,
                category=NotificationCategory.MARKETING,
            )
        )

    def test_non_customer_role_keeps_default_behavior(self):
        customer = self.make_customer()

        enabled = notification_preference_enabled(
            user=customer.user,
            audience_role=NotificationAudienceRole.MANAGER,
            category=NotificationCategory.BOOKING,
            event_type="booking_created",
            channel=NotificationChannel.EMAIL,
            priority=NotificationPriority.NORMAL,
        )

        self.assertTrue(enabled)
