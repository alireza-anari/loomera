from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.messaging.constants import (
    MessagingConnectionStatus,
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
    MessagingTokenPurpose,
)
from apps.messaging.models import (
    MessagingAccountConnection,
    MessagingIdentity,
    MessagingMessageLog,
    MessagingProvider,
    MessagingToken,
    MessagingWebhookEvent,
)
from apps.messaging.services import connect_identity_to_user, ensure_default_providers, get_or_create_identity, issue_messaging_token

from .client import BaleBotClient
from .parser import BaleUpdateType, parse_bale_update


@override_settings(
    BALE_WEBHOOK_SECRET="",
    BALE_WEBHOOK_REQUIRE_SECRET=False,
)
class BaleBotWebhookStage2Tests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.url = reverse("bale_bot:webhook")
        self.payload = {
            "update_id": 101,
            "message": {
                "message_id": 55,
                "from": {
                    "id": 123456,
                    "first_name": "کاربر",
                    "last_name": "مهمان",
                    "username": "loomera_guest",
                    "language_code": "fa",
                },
                "chat": {"id": 987654, "type": "private"},
                "date": 1710000000,
                "text": "/start invite_abc",
            },
        }

    def test_parser_extracts_message_identity_and_text(self):
        parsed = parse_bale_update(self.payload)

        self.assertEqual(parsed.event_type, BaleUpdateType.MESSAGE)
        self.assertEqual(parsed.update_id, "101")
        self.assertEqual(parsed.user_id, "123456")
        self.assertEqual(parsed.chat_id, "987654")
        self.assertEqual(parsed.text, "/start invite_abc")
        self.assertEqual(parsed.display_name, "کاربر مهمان")

    @override_settings(MESSAGING_ENABLED=False, BALE_BOT_ENABLED=False)
    def test_webhook_is_disabled_by_default(self):
        response = self.client.post(self.url, data=self.payload, content_type="application/json")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(MessagingWebhookEvent.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
    )
    def test_webhook_rejects_wrong_secret(self):
        response = self.client.post(self.url, data=self.payload, content_type="application/json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(MessagingWebhookEvent.objects.count(), 0)

    @override_settings(
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    BALE_WEBHOOK_SECRET="test-secret",
    )
    def test_webhook_stores_raw_event_identity_and_inbound_log(self):
        response = self.client.post(
            self.url,
            data=self.payload,
            content_type="application/json",
            HTTP_X_LOOMERA_BALE_SECRET="test-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stored"], True)
        self.assertEqual(MessagingWebhookEvent.objects.count(), 1)
        event = MessagingWebhookEvent.objects.get()
        self.assertEqual(event.provider, self.bale)
        self.assertEqual(event.update_id, "101")
        self.assertEqual(event.event_type, BaleUpdateType.MESSAGE)
        self.assertEqual(event.payload["message"]["text"], "/start invite_abc")

        identity = MessagingIdentity.objects.get(provider=self.bale, provider_user_id="123456")
        self.assertEqual(identity.chat_id, "987654")
        self.assertIsNone(identity.user)

        log = MessagingMessageLog.objects.get(direction=MessagingMessageDirection.INBOUND)
        self.assertEqual(log.identity, identity)
        self.assertEqual(log.text, "/start invite_abc")

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    )
    def test_duplicate_update_id_is_not_logged_twice(self):
        first = self.client.post(self.url, data=self.payload, content_type="application/json")
        second = self.client.post(self.url, data=self.payload, content_type="application/json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["duplicate"], True)
        self.assertEqual(MessagingWebhookEvent.objects.count(), 1)
        self.assertEqual(MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.INBOUND).count(), 1)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    )
    def test_callback_query_is_stored_but_not_executed(self):
        payload = {
            "update_id": 202,
            "callback_query": {
                "id": "cb-1",
                "from": {"id": 123456, "first_name": "کاربر"},
                "message": {"message_id": 90, "chat": {"id": 987654, "type": "private"}},
                "data": "action:unsafe-token",
            },
        }

        response = self.client.post(self.url, data=payload, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        event = MessagingWebhookEvent.objects.get(update_id="202")
        self.assertEqual(event.event_type, BaleUpdateType.CALLBACK_QUERY)
        log = MessagingMessageLog.objects.get(direction=MessagingMessageDirection.INBOUND, payload__update_id=202)
        self.assertEqual(log.text, "action:unsafe-token")

    @override_settings(MESSAGING_ENABLED=True, BALE_BOT_ENABLED=True, BALE_WEBHOOK_MAX_BYTES=8)
    def test_large_payload_is_rejected_before_database_write(self):
        response = self.client.post(self.url, data=self.payload, content_type="application/json")

        self.assertEqual(response.status_code, 413)
        self.assertEqual(MessagingWebhookEvent.objects.count(), 0)


class BaleBotClientStage2Tests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_send_message_is_logged_as_skipped_when_outbound_is_disabled(self):
        client = BaleBotClient()

        log = client.send_message(provider=self.bale, chat_id="987654", text="سلام")

        self.assertIsNotNone(log)
        self.assertEqual(log.status, MessagingMessageStatus.SKIPPED)
        self.assertEqual(log.error_message, "bale_outbound_disabled")
        self.assertEqual(MessagingMessageLog.objects.count(), 1)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="",
    )
    def test_send_message_missing_token_is_logged_without_crashing(self):
        client = BaleBotClient()

        log = client.send_message(provider=self.bale, chat_id="987654", text="سلام")

        self.assertIsNotNone(log)
        self.assertEqual(log.status, MessagingMessageStatus.FAILED)
        self.assertEqual(log.error_message, "bale_bot_token_missing")

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    @patch("apps.bale_bot.client.request.urlopen")
    def test_send_message_success_is_logged_without_action_processing(self, mocked_urlopen):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"ok": true, "result": {"message_id": 777}}'

        mocked_urlopen.return_value = FakeResponse()
        client = BaleBotClient()

        log = client.send_message(provider=self.bale, chat_id="987654", text="سلام")

        self.assertEqual(log.status, MessagingMessageStatus.SENT)
        self.assertEqual(log.external_message_id, "777")
        mocked_urlopen.assert_called_once()


@override_settings(
    BALE_WEBHOOK_SECRET="",
    BALE_WEBHOOK_REQUIRE_SECRET=False,
)
class BaleBotStartAndConnectStage3Tests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.url = reverse("bale_bot:webhook")
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000031",
            email="stage3@example.com",
            name="کاربر",
            family="اتصال",
            password="pass12345",
        )

    def _message_payload(self, text: str, *, update_id: int = 301):
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id + 1000,
                "from": {"id": 223344, "first_name": "کاربر", "last_name": "بله"},
                "chat": {"id": 998877, "type": "private"},
                "date": 1710000000,
                "text": text,
            },
        }

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_plain_start_creates_guest_identity_and_sends_guest_menu_log(self):
        response = self.client.post(self.url, data=self._message_payload("/start"), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        identity = MessagingIdentity.objects.get(provider=self.bale, provider_user_id="223344")
        self.assertIsNone(identity.user)
        self.assertEqual(identity.chat_id, "998877")

        outbound = MessagingMessageLog.objects.get(direction=MessagingMessageDirection.OUTBOUND)
        self.assertEqual(outbound.status, MessagingMessageStatus.SKIPPED)
        self.assertIn("به Loomera خوش آمدی", outbound.text)
        self.assertIn("inline_keyboard", outbound.payload.get("reply_markup", {}))

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_start_with_connect_token_links_identity_to_user_once(self):
        raw_token, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT,
            provider=self.bale,
            user=self.user,
            expires_in=timedelta(minutes=30),
        )

        response = self.client.post(
            self.url,
            data=self._message_payload(f"/start connect_{raw_token}", update_id=302),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        identity = MessagingIdentity.objects.get(provider=self.bale, provider_user_id="223344")
        identity.refresh_from_db()
        self.assertEqual(identity.user, self.user)
        self.assertEqual(identity.status, "linked")

        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        connection = MessagingAccountConnection.objects.get(identity=identity, user=self.user)
        self.assertEqual(connection.status, MessagingConnectionStatus.ACTIVE)

        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        self.assertIn("با موفقیت به ربات بله وصل شد", outbound.text)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_invalid_connect_token_does_not_link_identity(self):
        response = self.client.post(
            self.url,
            data=self._message_payload("/start connect_bad-token", update_id=303),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        identity = MessagingIdentity.objects.get(provider=self.bale, provider_user_id="223344")
        self.assertIsNone(identity.user)
        self.assertFalse(MessagingAccountConnection.objects.exists())
        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        self.assertIn("اتصال حساب انجام نشد", outbound.text)


@override_settings(
    BALE_WEBHOOK_SECRET="",
    BALE_WEBHOOK_REQUIRE_SECRET=False,
)
class BaleBotRoleMenusStage4Tests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.url = reverse("bale_bot:webhook")
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000404",
            email="stage4@example.com",
            name="کاربر",
            family="چندنقشی",
            password="pass12345",
        )
        Customer.objects.create(user=self.user)
        Stylist.objects.create(user=self.user, expert="مو", is_active=True)
        SalonManager.objects.create(user=self.user, is_active=True)

    def _message_payload(self, text: str, *, update_id: int = 401):
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id + 2000,
                "from": {"id": 444555, "first_name": "کاربر", "last_name": "چندنقشی"},
                "chat": {"id": 999888, "type": "private"},
                "date": 1710000000,
                "text": text,
            },
        }

    def _callback_payload(self, data: str, *, update_id: int = 450):
        return {
            "update_id": update_id,
            "callback_query": {
                "id": f"cb-{update_id}",
                "from": {"id": 444555, "first_name": "کاربر", "last_name": "چندنقشی"},
                "message": {"message_id": update_id + 3000, "chat": {"id": 999888, "type": "private"}},
                "data": data,
            },
        }

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_connecting_multi_role_user_returns_role_selector_buttons(self):
        raw_token, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT,
            provider=self.bale,
            user=self.user,
            expires_in=timedelta(minutes=30),
        )

        response = self.client.post(
            self.url,
            data=self._message_payload(f"/start connect_{raw_token}", update_id=401),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        markup = outbound.payload.get("reply_markup", {})
        flat_buttons = [button for row in markup.get("inline_keyboard", []) for button in row]
        callback_values = {button.get("callback_data") for button in flat_buttons}
        self.assertIn("menu:customer", callback_values)
        self.assertIn("menu:stylist", callback_values)
        self.assertIn("menu:manager", callback_values)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_connected_user_can_open_customer_menu_by_menu_callback(self):
        identity, _ = get_or_create_identity(provider=self.bale, provider_user_id="444555", chat_id="999888")
        connect_identity_to_user(identity, self.user)

        response = self.client.post(
            self.url,
            data=self._callback_payload("menu:customer", update_id=402),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        self.assertIn("منوی مشتری", outbound.text)
        markup = outbound.payload.get("reply_markup", {})
        flat_buttons = [
            button
            for row in markup.get("inline_keyboard", [])
            for button in row
        ]

        self.assertIn(
            ("نوبت‌های من", "menu:customer_appointments"),
            {
                (button.get("text"), button.get("callback_data"))
                for button in flat_buttons
            },
        )

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
    )
    def test_guest_cannot_open_role_menu_callback_without_account_connection(self):
        response = self.client.post(
            self.url,
            data=self._callback_payload("menu:manager", update_id=403),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        identity = MessagingIdentity.objects.get(provider=self.bale, provider_user_id="444555")
        self.assertIsNone(identity.user)
        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        self.assertIn("ابتدا حساب سایتت را به ربات وصل کن", outbound.text)


@override_settings(
    BALE_WEBHOOK_SECRET="",
    BALE_WEBHOOK_REQUIRE_SECRET=False,
)
class BaleBotActionCallbackStage6Tests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.url = reverse("bale_bot:webhook")
        self.user = CustomUser.objects.create_user(
            mobile_number="09120000651",
            email="bale-stage6@example.com",
            name="بله",
            family="اکشن",
            password="pass12345",
        )
        self.identity, _ = get_or_create_identity(
            provider=self.bale,
            provider_user_id="665544",
            chat_id="445566",
            display_name="بله اکشن",
        )
        connect_identity_to_user(self.identity, self.user)

    def _callback_payload(self, data: str, *, update_id: int = 601):
        return {
            "update_id": update_id,
            "callback_query": {
                "id": f"cb-stage6-{update_id}",
                "from": {"id": 665544, "first_name": "بله", "last_name": "اکشن"},
                "message": {"message_id": update_id + 4000, "chat": {"id": 445566, "type": "private"}},
                "data": data,
            },
        }

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
        MESSAGING_ACTIONS_ENABLED=True,
    )
    def test_bale_action_callback_uses_secure_dispatcher(self):
        from apps.messaging.actions import build_action_callback_data, issue_action_token
        from apps.messaging.constants import MessagingActionStatus
        from apps.messaging.models import MessagingActionExecution

        raw_token, token = issue_action_token(
            provider=self.bale,
            identity=self.identity,
            user=self.user,
            action_key="messaging.acknowledge",
        )

        response = self.client.post(
            self.url,
            data=self._callback_payload(build_action_callback_data(raw_token), update_id=601),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        execution = MessagingActionExecution.objects.get(token=token)
        self.assertEqual(execution.status, MessagingActionStatus.SUCCEEDED)

        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        self.assertIn("دریافت شد", outbound.text)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
        MESSAGING_ACTIONS_ENABLED=True,
    )
    def test_invalid_action_callback_does_not_crash_webhook(self):
        response = self.client.post(
            self.url,
            data=self._callback_payload("action:not-a-real-token", update_id=602),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        outbound = MessagingMessageLog.objects.filter(direction=MessagingMessageDirection.OUTBOUND).latest("id")
        self.assertIn("نامعتبر", outbound.text)
