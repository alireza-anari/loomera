from __future__ import annotations

import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.messaging.constants import (
    MessagingProviderKey,
    MessagingWebhookEventStatus,
)
from apps.messaging.management.commands.bale_webhook_event_check import (
    run_bale_webhook_event_check,
)
from apps.messaging.models import MessagingProvider, MessagingWebhookEvent
from apps.messaging.services import ensure_default_providers

BALE_MESSAGE_PAYLOAD = {
    "update_id": 7001,
    "message": {
        "message_id": 88,
        "chat": {"id": "bale-chat-1"},
        "from": {
            "id": "bale-user-1",
            "first_name": "کاربر",
            "last_name": "تست",
            "username": "bale_test",
        },
        "text": "/start secret-body-should-not-print",
    },
}


@override_settings(
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    BALE_BOT_TOKEN="123:token",
    BALE_WEBHOOK_SECRET="strong-secret",
    MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
)
class BaleWebhookEventCheckTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.supports_webhook = True
        self.bale.supports_callback = True
        self.bale.supports_outbound = True
        self.bale.save(
            update_fields=[
                "is_active",
                "supports_webhook",
                "supports_callback",
                "supports_outbound",
            ]
        )

    def _make_event(self, *, status, error_message=""):
        return MessagingWebhookEvent.objects.create(
            provider=self.bale,
            event_id="message:bale-chat-1:88",
            update_id="7001",
            event_type="message",
            payload=BALE_MESSAGE_PAYLOAD,
            headers={"HTTP_USER_AGENT": "test-agent"},
            status=status,
            error_message=error_message,
        )

    def test_default_dry_run_does_not_reprocess_failed_event(self):
        event = self._make_event(
            status=MessagingWebhookEventStatus.FAILED,
            error_message="handler failed",
        )

        with patch(
            "apps.bale_bot.services.handle_bale_update_stage11"
        ) as mocked_handler:
            result = run_bale_webhook_event_check(reprocess_failed=True)

        event.refresh_from_db()
        mocked_handler.assert_not_called()
        self.assertTrue(result["summary"]["dry_run"])
        self.assertEqual(result["summary"]["reprocessed_count"], 0)
        self.assertEqual(event.status, MessagingWebhookEventStatus.FAILED)
        self.assertEqual(event.error_message, "handler failed")

    def test_apply_reprocesses_failed_event(self):
        event = self._make_event(
            status=MessagingWebhookEventStatus.FAILED,
            error_message="handler failed",
        )

        with patch(
            "apps.bale_bot.services.handle_bale_update_stage11",
            return_value="handled",
        ) as mocked_handler:
            result = run_bale_webhook_event_check(
                event_ids=[event.pk],
                reprocess_failed=True,
                apply=True,
            )

        event.refresh_from_db()
        self.assertEqual(result["summary"]["reprocessed_count"], 1)
        self.assertEqual(event.status, MessagingWebhookEventStatus.PROCESSED)
        self.assertEqual(event.error_message, "")
        self.assertIsNotNone(event.identity_id)
        mocked_handler.assert_called_once()

    def test_received_event_requires_explicit_reprocess_received_flag(self):
        event = self._make_event(status=MessagingWebhookEventStatus.RECEIVED)

        with patch(
            "apps.bale_bot.services.handle_bale_update_stage11",
            return_value="handled",
        ) as mocked_handler:
            result = run_bale_webhook_event_check(
                event_ids=[event.pk],
                reprocess_failed=True,
                apply=True,
            )

        event.refresh_from_db()
        self.assertEqual(result["summary"]["reprocessed_count"], 0)
        self.assertEqual(event.status, MessagingWebhookEventStatus.RECEIVED)
        mocked_handler.assert_not_called()

        with patch(
            "apps.bale_bot.services.handle_bale_update_stage11",
            return_value="handled",
        ) as mocked_handler:
            result = run_bale_webhook_event_check(
                event_ids=[event.pk],
                reprocess_received=True,
                apply=True,
            )

        event.refresh_from_db()
        self.assertEqual(result["summary"]["reprocessed_count"], 1)
        self.assertEqual(event.status, MessagingWebhookEventStatus.PROCESSED)
        mocked_handler.assert_called_once()

    def test_apply_does_not_touch_processed_event(self):
        event = self._make_event(status=MessagingWebhookEventStatus.PROCESSED)

        with patch(
            "apps.bale_bot.services.handle_bale_update_stage11"
        ) as mocked_handler:
            result = run_bale_webhook_event_check(
                event_ids=[event.pk],
                statuses=[MessagingWebhookEventStatus.PROCESSED],
                reprocess_failed=True,
                reprocess_received=True,
                apply=True,
            )

        event.refresh_from_db()
        self.assertEqual(result["summary"]["reprocessed_count"], 0)
        self.assertEqual(event.status, MessagingWebhookEventStatus.PROCESSED)
        mocked_handler.assert_not_called()

    def test_reprocess_failure_marks_event_failed(self):
        event = self._make_event(
            status=MessagingWebhookEventStatus.FAILED,
            error_message="old error",
        )

        with patch(
            "apps.bale_bot.services.handle_bale_update_stage11",
            side_effect=RuntimeError("new handler error"),
        ):
            result = run_bale_webhook_event_check(
                event_ids=[event.pk],
                reprocess_failed=True,
                apply=True,
            )

        event.refresh_from_db()
        self.assertEqual(result["summary"]["reprocessed_count"], 1)
        self.assertEqual(event.status, MessagingWebhookEventStatus.FAILED)
        self.assertIn("new handler error", event.error_message)

    def test_json_output_does_not_print_token_secret_or_payload_text(self):
        token_value = "real-bale-token-should-not-appear"
        secret_value = "real-webhook-secret-should-not-appear"
        self._make_event(
            status=MessagingWebhookEventStatus.FAILED,
            error_message="handler failed",
        )

        out = io.StringIO()
        with self.settings(
            BALE_BOT_TOKEN=token_value,
            BALE_WEBHOOK_SECRET=secret_value,
        ):
            call_command("bale_webhook_event_check", "--json", stdout=out)

        raw = out.getvalue()
        payload = json.loads(raw)

        self.assertNotIn(token_value, raw)
        self.assertNotIn(secret_value, raw)
        self.assertNotIn("secret-body-should-not-print", raw)
        self.assertEqual(
            payload["counts"]["events"][MessagingWebhookEventStatus.FAILED], 1
        )

    def test_strict_fails_when_webhook_event_issue_exists(self):
        self._make_event(
            status=MessagingWebhookEventStatus.FAILED,
            error_message="handler failed",
        )

        with self.assertRaises(CommandError):
            call_command("bale_webhook_event_check", "--strict")
