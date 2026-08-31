from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager
from apps.salons.models import Salon

from .models import (
    InstagramAccountConnection,
    InstagramConnectionStatus,
    InstagramInboundMessage,
    InstagramInboundMessageStatus,
    InstagramReplySendStatus,
)
from .send_api import dispatch_lumi_reply


FERNET_TEST_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

SEND_SETTINGS = {
    "INSTAGRAM_ENABLED": True,
    "INSTAGRAM_MESSAGING_ENABLED": True,
    "INSTAGRAM_SEND_ENABLED": True,
    "INSTAGRAM_TOKEN_ENCRYPTION_KEY": FERNET_TEST_KEY,
    "INSTAGRAM_GRAPH_BASE_URL": "https://graph.instagram.com",
    "INSTAGRAM_GRAPH_API_VERSION": "v24.0",
    "INSTAGRAM_REQUEST_TIMEOUT": 10,
}


@override_settings(**SEND_SETTINGS)
class InstagramSendApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        manager_user = CustomUser.objects.create_user(
            mobile_number="09124444001",
            name="Send",
            family="Manager",
            password="test-password",
        )
        manager_user.is_active = True
        manager_user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=manager_user,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="Send Salon",
            salon_manager=cls.manager,
            is_active=True,
        )

    def setUp(self):
        self.connection = InstagramAccountConnection(
            salon=self.salon,
            instagram_account_id="ig-business-123",
            username="send_salon",
            granted_scopes=[
                "instagram_business_basic",
                "instagram_business_manage_messages",
            ],
        )
        self.connection.set_access_token("super-secret-token")
        self.connection.mark_connected()
        self.connection.save()

    def _inbound(
        self,
        *,
        mid="inbound-mid-1",
        sender="customer-igsid-1",
        reply="سلام، چطور می‌تونم کمکت کنم؟",
        requires_human=False,
        disposition="answer",
    ):
        return InstagramInboundMessage.objects.create(
            connection=self.connection,
            provider_message_id=mid,
            sender_igsid=sender,
            recipient_instagram_account_id=self.connection.instagram_account_id,
            message_text="سلام",
            status=InstagramInboundMessageStatus.PROCESSED,
            lumi_disposition=disposition,
            lumi_reply_text=reply,
            lumi_facts={},
            requires_human=requires_human,
        )

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_sends_to_exact_inbound_customer_with_business_account_endpoint(
        self,
        post,
    ):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "recipient_id": "customer-igsid-1",
            "message_id": "provider-reply-mid-1",
        }
        post.return_value = response

        inbound = self._inbound()
        result = dispatch_lumi_reply(inbound.pk)

        self.assertEqual(result.status, InstagramReplySendStatus.SENT)
        post.assert_called_once()

        args, kwargs = post.call_args
        self.assertEqual(
            args[0],
            "https://graph.instagram.com/v24.0/me/messages",
        )
        self.assertEqual(
            kwargs["json"]["recipient"]["id"],
            "customer-igsid-1",
        )
        self.assertEqual(
            kwargs["json"]["message"]["text"],
            "سلام، چطور می‌تونم کمکت کنم؟",
        )
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer super-secret-token",
        )
        self.assertNotIn("super-secret-token", args[0])

        inbound.refresh_from_db()
        self.assertEqual(
            inbound.reply_provider_message_id,
            "provider-reply-mid-1",
        )
        self.assertIsNotNone(inbound.reply_sent_at)
        self.assertEqual(inbound.reply_send_attempts, 1)

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_sent_reply_is_idempotent_and_never_sent_twice(self, post):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {"message_id": "provider-mid-once"}
        post.return_value = response

        inbound = self._inbound(mid="idempotent-mid")
        first = dispatch_lumi_reply(inbound.pk)
        second = dispatch_lumi_reply(inbound.pk)

        self.assertEqual(first.status, InstagramReplySendStatus.SENT)
        self.assertEqual(second.status, InstagramReplySendStatus.SENT)
        self.assertEqual(post.call_count, 1)

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_human_handoff_is_never_sent(self, post):
        inbound = self._inbound(
            mid="human-mid",
            reply="",
            requires_human=True,
            disposition="human_handoff",
        )
        result = dispatch_lumi_reply(inbound.pk)

        post.assert_not_called()
        self.assertEqual(
            result.status,
            InstagramReplySendStatus.SUPPRESSED,
        )
        inbound.refresh_from_db()
        self.assertEqual(
            inbound.reply_last_error_code,
            "human_handoff",
        )

    @override_settings(INSTAGRAM_SEND_ENABLED=False)
    @patch("apps.instagram_integration.send_api.requests.post")
    def test_send_flag_off_has_no_external_side_effect(self, post):
        inbound = self._inbound(mid="disabled-mid")
        result = dispatch_lumi_reply(inbound.pk)

        post.assert_not_called()
        self.assertEqual(
            result.status,
            InstagramReplySendStatus.SUPPRESSED,
        )
        inbound.refresh_from_db()
        self.assertEqual(
            inbound.reply_last_error_code,
            "send_disabled",
        )

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_network_error_is_isolated_and_does_not_raise(self, post):
        post.side_effect = requests.Timeout("provider timeout")
        inbound = self._inbound(mid="network-mid")

        result = dispatch_lumi_reply(inbound.pk)

        self.assertEqual(result.status, InstagramReplySendStatus.FAILED)
        inbound.refresh_from_db()
        self.assertEqual(inbound.reply_last_error_code, "network_error")
        self.assertEqual(inbound.reply_send_attempts, 1)

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_unauthorized_provider_response_marks_connection_for_reauth(
        self,
        post,
    ):
        response = Mock()
        response.ok = False
        response.status_code = 401
        post.return_value = response

        inbound = self._inbound(mid="unauthorized-mid")
        result = dispatch_lumi_reply(inbound.pk)

        self.assertEqual(result.status, InstagramReplySendStatus.FAILED)
        self.connection.refresh_from_db()
        self.assertEqual(
            self.connection.status,
            InstagramConnectionStatus.NEEDS_REAUTH,
        )

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_expired_token_is_rejected_before_network_call(self, post):
        self.connection.token_expires_at = timezone.now() - timedelta(minutes=1)
        self.connection.save(update_fields=["token_expires_at"])

        inbound = self._inbound(mid="expired-mid")
        result = dispatch_lumi_reply(inbound.pk)

        post.assert_not_called()
        self.assertEqual(result.error_code, "token_expired")
        self.connection.refresh_from_db()
        self.assertEqual(
            self.connection.status,
            InstagramConnectionStatus.NEEDS_REAUTH,
        )

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_missing_manage_messages_scope_is_rejected(self, post):
        self.connection.granted_scopes = ["instagram_business_basic"]
        self.connection.save(update_fields=["granted_scopes"])

        inbound = self._inbound(mid="scope-mid")
        result = dispatch_lumi_reply(inbound.pk)

        post.assert_not_called()
        self.assertEqual(
            result.error_code,
            "missing_manage_messages_scope",
        )

    @patch("apps.instagram_integration.send_api.requests.post")
    def test_provider_body_is_not_saved_when_request_fails(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 500
        response.text = "sensitive provider response"
        post.return_value = response

        inbound = self._inbound(mid="provider-error-mid")
        result = dispatch_lumi_reply(inbound.pk)

        self.assertEqual(result.error_code, "http_5xx")
        inbound.refresh_from_db()
        self.assertNotIn(
            "sensitive",
            inbound.reply_last_error_code,
        )
