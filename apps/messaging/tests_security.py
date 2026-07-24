from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.notifications.delivery import process_queued_deliveries
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPreference,
    NotificationPriority,
    NotificationRecipient,
)

from .actions import (
    build_action_callback_data,
    dispatch_messaging_action_callback,
    issue_action_token,
    register_messaging_action,
    sanitize_reply_markup_for_log,
)
from .constants import (
    MessagingActionStatus,
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingMessageStatus,
    MessagingProviderKey,
)
from .models import MessagingActionExecution, MessagingAccountConnection, MessagingMessageLog, MessagingToken
from .notification_delivery import deliver_simple_notification
from .services import connect_identity_to_user, ensure_default_providers, get_or_create_identity


@override_settings(MESSAGING_ACTIONS_ENABLED=True)
class MessagingActionSecurityStage12Tests(TestCase):
    def setUp(self):
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]
        self.telegram = self.providers[MessagingProviderKey.TELEGRAM]
        self.bale.is_active = True
        self.telegram.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.telegram.save(update_fields=["is_active"])

        self.user = CustomUser.objects.create_user(
            mobile_number="09121212001",
            email="stage12-user@example.com",
            name="امنیت",
            family="کاربر",
            password="pass12345",
        )
        self.other_user = CustomUser.objects.create_user(
            mobile_number="09121212002",
            email="stage12-other@example.com",
            name="کاربر",
            family="دیگر",
            password="pass12345",
        )
        self.identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage12-bale-user-1",
            chat_id="stage12-chat-1",
        )
        connect_identity_to_user(self.identity, self.user)
        self.other_identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage12-bale-user-2",
            chat_id="stage12-chat-2",
        )
        connect_identity_to_user(self.other_identity, self.other_user)

    def _issue_ack(self, **kwargs):
        return issue_action_token(
            provider=kwargs.pop("provider", self.bale),
            identity=kwargs.pop("identity", self.identity),
            user=kwargs.pop("user", self.user),
            action_key=kwargs.pop("action_key", "messaging.acknowledge"),
            expires_in=kwargs.pop("expires_in", timedelta(minutes=10)),
            **kwargs,
        )

    def test_fake_callback_token_is_denied_and_audited(self):
        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data="action:this-token-does-not-exist",
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertEqual(result.result.get("error_code"), "invalid_action_token")
        self.assertEqual(MessagingActionExecution.objects.count(), 1)
        self.assertEqual(MessagingActionExecution.objects.first().status, MessagingActionStatus.DENIED)

    @override_settings(MESSAGING_ACTIONS_ENABLED=False)
    def test_action_callbacks_are_denied_without_consuming_token_when_feature_flag_is_off(self):
        raw_token, token = self._issue_ack()

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertEqual(result.result.get("error_code"), "messaging_actions_disabled")
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_guest_identity_cannot_execute_even_with_a_valid_token(self):
        guest_identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage12-guest-user",
            chat_id="stage12-guest-chat",
        )
        raw_token, token = self._issue_ack(identity=guest_identity, user=self.user)

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=guest_identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertEqual(result.result.get("error_code"), "missing_identity_user")
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_token_for_another_identity_is_denied_and_not_consumed(self):
        raw_token, token = self._issue_ack()

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.other_identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertEqual(result.result.get("error_code"), "token_identity_mismatch")
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_token_for_another_user_is_denied_and_not_consumed(self):
        raw_token, token = self._issue_ack(user=self.other_user)

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertEqual(result.result.get("error_code"), "token_user_mismatch")
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_token_for_another_provider_is_denied_and_not_consumed(self):
        raw_token, token = self._issue_ack()
        telegram_identity, _ = get_or_create_identity(
            provider=self.telegram,
            provider_user_id="stage12-telegram-user",
            chat_id="stage12-telegram-chat",
        )
        connect_identity_to_user(telegram_identity, self.user)

        result = dispatch_messaging_action_callback(
            provider=self.telegram,
            identity=telegram_identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.DENIED)
        self.assertEqual(result.result.get("error_code"), "token_provider_mismatch")
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_expired_token_is_rejected_and_not_consumed(self):
        raw_token, token = self._issue_ack(expires_in=timedelta(seconds=-1))

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.EXPIRED)
        self.assertEqual(result.result.get("error_code"), "token_expired")
        token.refresh_from_db()
        self.assertIsNone(token.used_at)

    def test_action_token_is_one_time_use(self):
        raw_token, token = self._issue_ack()
        callback_data = build_action_callback_data(raw_token)

        first = dispatch_messaging_action_callback(provider=self.bale, identity=self.identity, callback_data=callback_data)
        second = dispatch_messaging_action_callback(provider=self.bale, identity=self.identity, callback_data=callback_data)

        self.assertEqual(first.status, MessagingActionStatus.SUCCEEDED)
        self.assertEqual(second.status, MessagingActionStatus.ALREADY_USED)
        self.assertEqual(second.result.get("error_code"), "token_already_used")
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)

    def test_related_object_deleted_before_click_is_blocked(self):
        notification = Notification.objects.create(event_type="stage12.object", title="آبجکت", body="حذف می‌شود")
        raw_token, token = self._issue_ack(related_object=notification)
        notification.delete()

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.FAILED)
        self.assertEqual(result.result.get("error_code"), "related_object_missing")
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)

    def test_handler_exception_is_logged_without_crashing_dispatcher(self):
        def boom(_context):
            raise RuntimeError("boom")

        register_messaging_action("stage12.boom", boom, replace=True)
        raw_token, _token = self._issue_ack(action_key="stage12.boom")

        result = dispatch_messaging_action_callback(
            provider=self.bale,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(result.status, MessagingActionStatus.FAILED)
        self.assertEqual(result.result.get("error_code"), "action_handler_failed")
        self.assertEqual(MessagingActionExecution.objects.order_by("-id").first().status, MessagingActionStatus.FAILED)

    def test_callback_token_is_masked_in_message_log_payloads(self):
        raw_token = "abcdef1234567890-secret-token"
        markup = {"inline_keyboard": [[{"text": "تایید", "callback_data": f"action:{raw_token}"}]]}

        cleaned = sanitize_reply_markup_for_log(markup)

        callback_data = cleaned["inline_keyboard"][0][0]["callback_data"]
        self.assertNotIn(raw_token, callback_data)
        self.assertEqual(callback_data, "action:abcdef…")


class MessagingDeliverySecurityStage12Tests(TestCase):
    def setUp(self):
        self.providers = ensure_default_providers()
        self.bale = self.providers[MessagingProviderKey.BALE]
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.user = CustomUser.objects.create_user(
            mobile_number="09121212101",
            email="stage12-delivery@example.com",
            name="اعلان",
            family="امن",
            password="pass12345",
        )
        self.identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="stage12-delivery-user",
            chat_id="stage12-delivery-chat",
        )
        connect_identity_to_user(self.identity, self.user)

    def _delivery(self, *, category=NotificationCategory.SYSTEM, priority=NotificationPriority.NORMAL):
        notification = Notification.objects.create(
            event_type="stage12.delivery",
            category=category,
            priority=priority,
            title="اعلان تست",
            body="این اعلان برای تست امنیت پیام‌رسان است.",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        return NotificationDelivery.objects.create(recipient=recipient, channel=NotificationChannel.BALE)

    @override_settings(MESSAGING_ENABLED=False, MESSAGING_ALLOWED_PROVIDERS=[])
    def test_process_queue_does_not_consume_bale_delivery_when_feature_flag_is_off(self):
        delivery = self._delivery()

        result = process_queued_deliveries(limit=10)

        delivery.refresh_from_db()
        self.assertEqual(result["processed"], 0)
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)
        self.assertEqual(delivery.attempt_count, 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    )
    def test_user_preference_opt_out_skips_non_critical_messaging_delivery(self):
        NotificationPreference.objects.create(
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
            category=NotificationCategory.MARKETING,
            channel=NotificationChannel.BALE,
            is_enabled=False,
        )
        delivery = self._delivery(category=NotificationCategory.MARKETING)

        result = deliver_simple_notification(delivery)

        self.assertEqual(result.status, NotificationDeliveryStatus.SKIPPED)
        self.assertEqual(result.error, "messaging_user_preference_disabled")
        self.assertFalse(MessagingMessageLog.objects.exists())

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    )
    def test_critical_notification_bypasses_user_preference_but_still_respects_outbound_flag(self):
        NotificationPreference.objects.create(
            user=self.user,
            audience_role=NotificationAudienceRole.CUSTOMER,
            category=NotificationCategory.SYSTEM,
            channel=NotificationChannel.BALE,
            is_enabled=False,
        )
        delivery = self._delivery(category=NotificationCategory.SYSTEM, priority=NotificationPriority.CRITICAL)

        result = deliver_simple_notification(delivery)

        self.assertEqual(result.status, NotificationDeliveryStatus.SKIPPED)
        self.assertEqual(result.error, "bale_outbound_disabled")
        message_log = MessagingMessageLog.objects.get()
        self.assertEqual(message_log.status, MessagingMessageStatus.SKIPPED)
        self.assertEqual(message_log.identity, self.identity)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    )
    def test_disconnected_identity_is_not_used_for_delivery(self):
        MessagingAccountConnection.objects.filter(identity=self.identity).update(status=MessagingConnectionStatus.DISCONNECTED)
        self.identity.status = MessagingIdentityStatus.DISCONNECTED
        self.identity.save(update_fields=["status", "updated_at"])
        delivery = self._delivery()

        result = deliver_simple_notification(delivery)

        self.assertEqual(result.status, NotificationDeliveryStatus.PENDING_SETUP)
        self.assertEqual(result.error, "missing_linked_messaging_identity")
        self.assertFalse(MessagingMessageLog.objects.exists())


class MessagingStaticSecurityGuardsStage12Tests(TestCase):
    def _read(self, relative_path: str) -> str:
        root = Path(settings.BASE_DIR)
        return (root / relative_path).read_text(encoding="utf-8")

    def test_dispatcher_checks_identity_user_provider_and_related_object(self):
        source = self._read("apps/messaging/actions.py")

        self.assertIn("missing_identity_user", source)
        self.assertIn("token_provider_mismatch", source)
        self.assertIn("token_identity_mismatch", source)
        self.assertIn("token_user_mismatch", source)
        self.assertIn("related_object_missing", source)
        self.assertLess(source.index("token_provider_mismatch"), source.index("token.mark_used()"))
        self.assertLess(source.index("token_identity_mismatch"), source.index("token.mark_used()"))
        self.assertLess(source.index("token_user_mismatch"), source.index("token.mark_used()"))

    def test_stylist_actions_keep_multi_salon_scope(self):
        source = self._read("apps/messaging/stylist_actions.py")

        self.assertIn("detail.stylist_id != stylist.pk", source)
        self.assertIn("context.salon_id", source)
        self.assertIn("detail.salon_id", source)
        self.assertIn("SalonMembership.objects.filter", source)
        self.assertIn("status=SalonMembershipStatus.ACTIVE", source)
        self.assertIn("ensure_membership_permissions", source)
        self.assertIn("_apply_lightweight_stylist_lifecycle_action", source)

    def test_manager_actions_use_existing_scope_safe_services(self):
        source = self._read("apps/messaging/manager_actions.py")

        self.assertIn("_check_manager_salon_scope", source)
        self.assertIn("review_leave_request", source)
        self.assertIn("review_schedule_request", source)
        self.assertIn("change_membership_status", source)
        self.assertIn("ensure_membership_permissions", source)
        self.assertIn("SalonMembershipStatus.PENDING_ACCEPTANCE", source)
