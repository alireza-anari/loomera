from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.messaging.actions import (
    build_action_callback_data,
    clear_messaging_action_handlers_for_tests,
    dispatch_messaging_action_callback,
    issue_action_token,
    register_messaging_action,
)
from apps.messaging.constants import (
    MessagingActionStatus,
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingProviderKey,
)
from apps.messaging.models import MessagingAccountConnection, MessagingProvider
from apps.messaging.services import (
    connect_identity_to_user,
    disconnect_identity,
    ensure_default_providers,
    get_or_create_identity,
    identity_has_active_connection,
)


@override_settings(
    MESSAGING_ENABLED=True,
    MESSAGING_ACTIONS_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
)
class BaleDisconnectHardeningTests(TestCase):
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
            mobile_number="09125556677",
            email="bale-disconnect@example.com",
            name="Bale",
            family="Disconnect",
            password="pass12345",
        )
        self.identity, _created = get_or_create_identity(
            provider=self.provider,
            provider_user_id="bale-disconnect-user",
            chat_id="bale-disconnect-chat",
            display_name="کاربر قطع اتصال",
        )
        connect_identity_to_user(self.identity, self.user)

    def tearDown(self):
        clear_messaging_action_handlers_for_tests()

    def _issue_test_action(self, *, action_key="disconnect_guard_test"):
        calls = []

        def handler(context):
            calls.append(context.token.pk)
            from apps.messaging.actions import MessagingActionResult

            return MessagingActionResult(
                status=MessagingActionStatus.SUCCEEDED,
                user_message="done",
                result={"called": True},
            )

        register_messaging_action(action_key, handler, replace=True)
        raw_token, token = issue_action_token(
            provider=self.provider,
            identity=self.identity,
            user=self.user,
            action_key=action_key,
        )
        return raw_token, token, calls

    def test_identity_has_active_connection_for_connected_identity(self):
        self.identity.refresh_from_db()

        self.assertEqual(self.identity.status, MessagingIdentityStatus.LINKED)
        self.assertTrue(identity_has_active_connection(self.identity, user=self.user))

    def test_disconnect_revokes_active_identity_tokens(self):
        raw_token, token, calls = self._issue_test_action()

        result = disconnect_identity(self.identity)

        self.identity.refresh_from_db()
        token.refresh_from_db()
        connection = MessagingAccountConnection.objects.get(identity=self.identity)

        self.assertEqual(self.identity.status, MessagingIdentityStatus.DISCONNECTED)
        self.assertEqual(connection.status, MessagingConnectionStatus.DISCONNECTED)
        self.assertGreaterEqual(result["disconnected_connections"], 1)
        self.assertGreaterEqual(result["revoked_tokens"], 1)
        self.assertIsNotNone(token.revoked_at)
        self.assertFalse(identity_has_active_connection(self.identity, user=self.user))

        action_result = dispatch_messaging_action_callback(
            provider=self.provider,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        self.assertEqual(action_result.status, MessagingActionStatus.DENIED)
        self.assertEqual(action_result.result["error_code"], "identity_not_linked")
        self.assertEqual(calls, [])

    def test_action_denied_when_identity_is_linked_but_connection_is_inactive(self):
        raw_token, token, calls = self._issue_test_action()

        MessagingAccountConnection.objects.filter(identity=self.identity).update(
            status=MessagingConnectionStatus.DISCONNECTED,
        )
        self.identity.status = MessagingIdentityStatus.LINKED
        self.identity.save(update_fields=["status"])

        action_result = dispatch_messaging_action_callback(
            provider=self.provider,
            identity=self.identity,
            callback_data=build_action_callback_data(raw_token),
        )

        token.refresh_from_db()

        self.assertEqual(action_result.status, MessagingActionStatus.DENIED)
        self.assertEqual(
            action_result.result["error_code"], "identity_connection_inactive"
        )
        self.assertIsNone(token.used_at)
        self.assertEqual(calls, [])

    def test_disconnect_does_not_remove_user_from_identity(self):
        disconnect_identity(self.identity)

        self.identity.refresh_from_db()

        self.assertEqual(self.identity.user_id, self.user.pk)
        self.assertEqual(self.identity.status, MessagingIdentityStatus.DISCONNECTED)
        self.assertIsNotNone(self.identity.disconnected_at)
