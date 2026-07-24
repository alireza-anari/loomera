from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.messaging.actions import (
    build_action_callback_data,
    clear_messaging_action_handlers_for_tests,
    issue_action_token,
    register_messaging_action,
)
from apps.messaging.constants import (
    MessagingActionStatus,
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingProviderKey,
)
from apps.messaging.models import (
    MessagingAccountConnection,
    MessagingMessageLog,
    MessagingProvider,
)
from apps.messaging.services import (
    connect_identity_to_user,
    ensure_default_providers,
    get_or_create_identity,
)

from apps.bale_bot.handlers import handle_bale_update_stage11
from apps.bale_bot.parser import parse_bale_update


@override_settings(
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    MESSAGING_ACTIONS_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    MESSAGING_OUTBOUND_ENABLED=False,
)
class BaleDisconnectCommandTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.provider = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.provider.is_active = True
        self.provider.supports_callback = True
        self.provider.supports_outbound = True
        self.provider.save(
            update_fields=["is_active", "supports_callback", "supports_outbound"]
        )

        self.user = CustomUser.objects.create_user(
            mobile_number="09126667788",
            email="bale-stop@example.com",
            name="Bale",
            family="Stop",
            password="pass12345",
        )
        self.identity, _created = get_or_create_identity(
            provider=self.provider,
            provider_user_id="bale-stop-user",
            chat_id="bale-stop-chat",
            display_name="کاربر توقف",
        )
        connect_identity_to_user(self.identity, self.user)

    def tearDown(self):
        clear_messaging_action_handlers_for_tests()

    def _message_update(self, text: str, *, update_id=9001):
        return parse_bale_update(
            {
                "update_id": update_id,
                "message": {
                    "message_id": update_id + 100,
                    "from": {
                        "id": "bale-stop-user",
                        "first_name": "Bale",
                        "last_name": "Stop",
                    },
                    "chat": {"id": "bale-stop-chat", "type": "private"},
                    "text": text,
                },
            }
        )

    def _issue_action_token(self):
        calls = []

        def handler(context):
            calls.append(context.token.pk)
            from apps.messaging.actions import MessagingActionResult

            return MessagingActionResult(
                status=MessagingActionStatus.SUCCEEDED,
                user_message="done",
                result={"called": True},
            )

        register_messaging_action("stop_guard_action", handler, replace=True)
        raw_token, token = issue_action_token(
            provider=self.provider,
            identity=self.identity,
            user=self.user,
            action_key="stop_guard_action",
        )
        return raw_token, token, calls

    def test_stop_command_disconnects_identity_and_revokes_tokens(self):
        raw_token, token, calls = self._issue_action_token()

        result = handle_bale_update_stage11(
            parsed=self._message_update("/stop"),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.identity.refresh_from_db()
        token.refresh_from_db()
        connection = MessagingAccountConnection.objects.get(identity=self.identity)

        self.assertEqual(result, "disconnected")
        self.assertEqual(self.identity.status, MessagingIdentityStatus.DISCONNECTED)
        self.assertEqual(connection.status, MessagingConnectionStatus.DISCONNECTED)
        self.assertIsNotNone(token.revoked_at)
        self.assertEqual(calls, [])

        sent_log = (
            MessagingMessageLog.objects.filter(
                provider=self.provider,
                identity=self.identity,
                direction="outbound",
            )
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(sent_log)
        self.assertIn("قطع شد", sent_log.text)

    def test_farsi_disconnect_text_disconnects_identity(self):
        result = handle_bale_update_stage11(
            parsed=self._message_update("قطع اتصال"),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.identity.refresh_from_db()

        self.assertEqual(result, "disconnected")
        self.assertEqual(self.identity.status, MessagingIdentityStatus.DISCONNECTED)

    def test_stop_command_for_already_disconnected_identity_is_idempotent(self):
        handle_bale_update_stage11(
            parsed=self._message_update("/stop"),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.identity.refresh_from_db()
        result = handle_bale_update_stage11(
            parsed=self._message_update("/stop", update_id=9002),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.identity.refresh_from_db()

        self.assertEqual(result, "already_disconnected")
        self.assertEqual(self.identity.status, MessagingIdentityStatus.DISCONNECTED)

    def test_menu_after_disconnect_is_guest_menu_not_connected_menu(self):
        handle_bale_update_stage11(
            parsed=self._message_update("/stop"),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.identity.refresh_from_db()

        result = handle_bale_update_stage11(
            parsed=self._message_update("/menu", update_id=9003),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.assertEqual(result, "guest_menu")

    def test_connected_command_requires_active_connection_not_only_user_id(self):
        MessagingAccountConnection.objects.filter(identity=self.identity).update(
            status=MessagingConnectionStatus.DISCONNECTED,
        )
        self.identity.status = MessagingIdentityStatus.LINKED
        self.identity.save(update_fields=["status"])

        result = handle_bale_update_stage11(
            parsed=self._message_update("نوبت‌های من"),
            identity=self.identity,
            provider=self.provider,
            base_url="https://example.com",
        )

        self.assertEqual(result, "appointments_requires_connection")
