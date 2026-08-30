from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.messaging.constants import MessagingMessageStatus, MessagingProviderKey, MessagingTokenPurpose
from apps.messaging.models import MessagingMessageLog, MessagingToken, MessagingWebhookEvent
from apps.messaging.notification_delivery import deliver_simple_notification, messaging_delivery_preference_enabled
from apps.messaging.preferences import set_stream_enabled
from apps.messaging.services import connect_identity_to_user, ensure_default_providers, get_or_create_identity, issue_messaging_token
from apps.notifications.models import (
    Notification, NotificationAudienceRole, NotificationCategory, NotificationChannel,
    NotificationDelivery, NotificationPriority, NotificationRecipient,
)
from .client import TelegramBotApiError, TelegramBotClient

TELEGRAM_LIVE = dict(
    MESSAGING_ENABLED=True, MESSAGING_OUTBOUND_ENABLED=True, MESSAGING_ACTIONS_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=["telegram"], TELEGRAM_BOT_ENABLED=True,
    TELEGRAM_BOT_TOKEN="test-token-not-real", TELEGRAM_BOT_USERNAME="loomera_test_bot",
    TELEGRAM_WEBHOOK_SECRET="test-secret-not-real",
)


class TelegramWebhookTests(TestCase):
    def setUp(self):
        self.url = reverse("telegram_bot:webhook")

    def payload(self, update_id=100, text="/start"):
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "from": {"id": 7001, "first_name": "Test", "username": "telegram_test", "language_code": "fa"},
                "chat": {"id": 7001, "type": "private"},
                "text": text,
            },
        }

    @override_settings(MESSAGING_ENABLED=False, TELEGRAM_BOT_ENABLED=False)
    def test_disabled_provider_returns_404(self):
        self.assertEqual(self.client.post(self.url, data=self.payload(), content_type="application/json").status_code, 404)

    @override_settings(MESSAGING_ENABLED=True, TELEGRAM_BOT_ENABLED=True, TELEGRAM_WEBHOOK_SECRET="")
    def test_enabled_without_secret_fails_closed(self):
        self.assertEqual(self.client.post(self.url, data=self.payload(), content_type="application/json").status_code, 503)

    @override_settings(**TELEGRAM_LIVE)
    def test_wrong_secret_is_rejected(self):
        response = self.client.post(self.url, data=self.payload(), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong")
        self.assertEqual(response.status_code, 403)

    @override_settings(**TELEGRAM_LIVE)
    def test_malformed_and_missing_update_id_are_rejected(self):
        malformed = self.client.post(self.url, data="{bad", content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret-not-real")
        invalid = self.client.post(self.url, data={}, content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret-not-real")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(invalid.status_code, 400)

    @override_settings(**{**TELEGRAM_LIVE, "MESSAGING_OUTBOUND_ENABLED": False})
    def test_duplicate_update_is_stored_once(self):
        kwargs = dict(content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret-not-real")
        first = self.client.post(self.url, data=self.payload(), **kwargs)
        second = self.client.post(self.url, data=self.payload(), **kwargs)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(MessagingWebhookEvent.objects.filter(provider__key="telegram").count(), 1)


class TelegramLinkingTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            mobile_number="09129999001", email="telegram-link@example.com",
            name="تلگرام", family="تست", password="pass12345",
        )
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])

    @override_settings(**{**TELEGRAM_LIVE, "MESSAGING_OUTBOUND_ENABLED": False})
    def test_start_token_links_once_and_reuse_is_safe(self):
        telegram = ensure_default_providers()[MessagingProviderKey.TELEGRAM]
        raw, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT, provider=telegram, user=self.user,
            expires_in=timedelta(minutes=10),
        )
        payload = {
            "update_id": 201,
            "message": {"message_id": 201, "from": {"id": 8001, "first_name": "Linked"}, "chat": {"id": 8001, "type": "private"}, "text": f"/start connect_{raw}"},
        }
        kwargs = dict(content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-secret-not-real")
        self.assertEqual(self.client.post(reverse("telegram_bot:webhook"), data=payload, **kwargs).status_code, 200)
        token.refresh_from_db()
        self.assertTrue(token.is_used)
        identity = telegram.identities.get(provider_user_id="8001")
        self.assertEqual(identity.user, self.user)
        payload["update_id"] = 202
        payload["message"]["message_id"] = 202
        self.assertEqual(self.client.post(reverse("telegram_bot:webhook"), data=payload, **kwargs).status_code, 200)
        identity.refresh_from_db()
        self.assertEqual(identity.user, self.user)

    @override_settings(**TELEGRAM_LIVE)
    def test_quick_connect_requires_login_and_uses_t_me(self):
        url = reverse("messaging:provider_quick_connect", kwargs={"provider_key": "telegram"})
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertTrue(self.client.login(mobile_number="09129999001", password="pass12345"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://t.me/loomera_test_bot"))
        self.assertTrue(MessagingToken.objects.filter(user=self.user, provider__key="telegram", purpose=MessagingTokenPurpose.CONNECT_ACCOUNT).exists())


class TelegramOutboundPreferenceTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            mobile_number="09129999002", email="telegram-out@example.com",
            name="ارسال", family="تلگرام", password="pass12345",
        )

    def link(self, provider_key, provider_user_id, chat_id):
        provider = ensure_default_providers()[provider_key]
        provider.is_active = True
        provider.save(update_fields=["is_active"])
        identity, _ = get_or_create_identity(provider=provider, provider_user_id=provider_user_id, chat_id=chat_id)
        connect_identity_to_user(identity, self.user)

    def delivery(self, channel, priority=NotificationPriority.NORMAL):
        notification = Notification.objects.create(
            event_type="booking_created", title="نوبت جدید",
            body="مشتری: تست | سرویس: کوتاهی | ساعت: 10:00",
            category=NotificationCategory.BOOKING, priority=priority,
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification, user=self.user, audience_role=NotificationAudienceRole.STYLIST,
        )
        return NotificationDelivery.objects.create(recipient=recipient, channel=channel)

    @override_settings(**TELEGRAM_LIVE)
    @patch.object(TelegramBotClient, "request", return_value={"ok": True, "result": {"message_id": 901}})
    def test_outbound_uses_shared_delivery(self, request_mock):
        self.link(MessagingProviderKey.TELEGRAM, "tg-1", "tg-chat-1")
        result = deliver_simple_notification(self.delivery(NotificationChannel.TELEGRAM))
        self.assertEqual(result.status, "sent")
        request_mock.assert_called_once()
        self.assertTrue(MessagingMessageLog.objects.filter(provider__key="telegram", status=MessagingMessageStatus.SENT).exists())

    @override_settings(**TELEGRAM_LIVE)
    @patch.object(TelegramBotClient, "request")
    def test_preference_off_blocks_critical_external_message(self, request_mock):
        self.link(MessagingProviderKey.TELEGRAM, "tg-2", "tg-chat-2")
        set_stream_enabled(user=self.user, channel=NotificationChannel.TELEGRAM, stream="operational", enabled=False)
        delivery = self.delivery(NotificationChannel.TELEGRAM, NotificationPriority.CRITICAL)
        self.assertFalse(messaging_delivery_preference_enabled(delivery))
        self.assertEqual(deliver_simple_notification(delivery).status, "skipped")
        request_mock.assert_not_called()

    def test_four_preference_combinations_are_independent(self):
        for bale_on, telegram_on in ((True, True), (False, True), (True, False), (False, False)):
            set_stream_enabled(user=self.user, channel=NotificationChannel.BALE, stream="operational", enabled=bale_on)
            set_stream_enabled(user=self.user, channel=NotificationChannel.TELEGRAM, stream="operational", enabled=telegram_on)
            self.assertEqual(messaging_delivery_preference_enabled(self.delivery(NotificationChannel.BALE)), bale_on)
            self.assertEqual(messaging_delivery_preference_enabled(self.delivery(NotificationChannel.TELEGRAM)), telegram_on)

    @override_settings(
        MESSAGING_ENABLED=True, MESSAGING_OUTBOUND_ENABLED=True, MESSAGING_ACTIONS_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=["bale", "telegram"],
        BALE_BOT_ENABLED=True, BALE_BOT_TOKEN="bale-test-not-real",
        TELEGRAM_BOT_ENABLED=True, TELEGRAM_BOT_TOKEN="telegram-test-not-real",
    )
    @patch("apps.bale_bot.client.BaleBotClient.request", return_value={"ok": True, "result": {"message_id": 777}})
    @patch.object(TelegramBotClient, "request", side_effect=TelegramBotApiError("telegram_api_request_failed", response={"error_type": "TimeoutError"}))
    def test_telegram_failure_does_not_break_bale(self, telegram_mock, bale_mock):
        self.link(MessagingProviderKey.TELEGRAM, "tg-iso", "tg-chat-iso")
        self.link(MessagingProviderKey.BALE, "bale-iso", "bale-chat-iso")
        self.assertEqual(deliver_simple_notification(self.delivery(NotificationChannel.TELEGRAM)).status, "failed")
        self.assertEqual(deliver_simple_notification(self.delivery(NotificationChannel.BALE)).status, "sent")
        telegram_mock.assert_called_once()
        bale_mock.assert_called_once()
