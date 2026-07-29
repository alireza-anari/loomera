from __future__ import annotations

from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.messaging.constants import MessagingProviderKey
from apps.messaging.models import MessagingMessageLog, MessagingProvider, MessagingWebhookEvent
from apps.messaging.services import ensure_default_providers

from .client import BaleBotClient
from .polling import (
    BALE_POLLING_LOCK_KEY,
    BALE_POLLING_OFFSET_METADATA_KEY,
    BalePollingError,
    poll_bale_updates,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": (
                "django.core.cache.backends."
                "locmem.LocMemCache"
            ),
            "LOCATION": "bale-polling-tests",
        },
    },
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    BALE_POLLING_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    BALE_BOT_TOKEN="123:token",
    MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
    BALE_POLLING_LIMIT=100,
    BALE_POLLING_TIMEOUT_SECONDS=0,
    BALE_POLLING_LOCK_TTL_SECONDS=120,
)
class BalePollingTests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_default_providers()
        self.provider = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.provider.is_active = True
        self.provider.save(update_fields=["is_active"])

    def _update(self, update_id: int, *, text: str = "/start"):
        return {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "from": {
                    "id": 5000 + update_id,
                    "first_name": "polling failure",
                    "username": f"user_{update_id}",
                },
                "chat": {
                    "id": 7000 + update_id,
                    "type": "private",
                },
                "text": text,
            },
        }

    @override_settings(BALE_POLLING_ENABLED=False)
    def test_disabled_polling_does_not_call_provider(self):
        client = Mock(spec=BaleBotClient)

        result = poll_bale_updates(client=client)

        self.assertEqual(result.status, "disabled")
        client.get_updates.assert_not_called()

    @patch(
        "apps.bale_bot.polling.record_bale_webhook_update",
        side_effect=[
            {"duplicate": False},
            {"duplicate": False},
        ],
    )
    def test_processes_updates_in_order_and_persists_next_offset(self, mocked_record):
        client = Mock(spec=BaleBotClient)
        client.get_updates.return_value = {
            "ok": True,
            "result": [self._update(12), self._update(11)],
        }

        result = poll_bale_updates(client=client)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.fetched, 2)
        self.assertEqual(result.processed, 2)
        self.assertEqual(result.next_offset, 13)
        seen_ids = [
            call.kwargs["payload"]["update_id"]
            for call in mocked_record.call_args_list
        ]
        self.assertEqual(seen_ids, [11, 12])

        self.provider.refresh_from_db()
        self.assertEqual(
            self.provider.metadata[BALE_POLLING_OFFSET_METADATA_KEY],
            13,
        )

    @patch(
        "apps.bale_bot.polling.record_bale_webhook_update",
        return_value={"duplicate": True},
    )
    def test_duplicate_update_advances_offset_without_reprocessing(self, mocked_record):
        self.provider.metadata = {BALE_POLLING_OFFSET_METADATA_KEY: 21}
        self.provider.save(update_fields=["metadata"])
        client = Mock(spec=BaleBotClient)
        client.get_updates.return_value = {
            "ok": True,
            "result": [self._update(21)],
        }

        result = poll_bale_updates(client=client)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.processed, 0)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.next_offset, 22)
        mocked_record.assert_called_once()

    @patch("apps.bale_bot.polling.record_bale_webhook_update")
    def test_processing_failure_does_not_ack_failed_or_later_update(self, mocked_record):
        mocked_record.side_effect = [
            {"duplicate": False},
            RuntimeError("handler_failed"),
        ]
        client = Mock(spec=BaleBotClient)
        client.get_updates.return_value = {
            "ok": True,
            "result": [
                self._update(31),
                self._update(32),
                self._update(33),
            ],
        }

        result = poll_bale_updates(client=client)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.failed_update_id, 32)
        self.assertEqual(result.next_offset, 32)
        self.assertEqual(mocked_record.call_count, 2)

        self.provider.refresh_from_db()
        self.assertEqual(
            self.provider.metadata[BALE_POLLING_OFFSET_METADATA_KEY],
            32,
        )

    def test_lock_contention_skips_second_poller(self):
        cache.set(BALE_POLLING_LOCK_KEY, "other-run", timeout=120)
        client = Mock(spec=BaleBotClient)

        result = poll_bale_updates(client=client)

        self.assertEqual(result.status, "locked")
        client.get_updates.assert_not_called()

    @patch("apps.bale_bot.client.BaleBotClient.request")
    def test_client_get_updates_uses_offset_limit_and_timeout(self, mocked_request):
        mocked_request.return_value = {"ok": True, "result": []}

        BaleBotClient().get_updates(offset=50, limit=25, timeout=0)

        mocked_request.assert_called_once_with(
            "getUpdates",
            {"offset": 50, "limit": 25, "timeout": 0},
        )

    @patch("apps.messaging.management.commands.poll_bale_updates.poll_bale_updates")
    def test_command_does_not_print_token_or_secret(self, mocked_poll):
        from .polling import BalePollingResult

        mocked_poll.return_value = BalePollingResult(
            status="ok",
            fetched=1,
            processed=1,
            next_offset=91,
        )

        with self.settings(
            BALE_BOT_TOKEN="token-must-not-print",
            BALE_WEBHOOK_SECRET="secret-must-not-print",
        ):
            from io import StringIO

            out = StringIO()
            call_command("poll_bale_updates", stdout=out)

        raw = out.getvalue()
        self.assertNotIn("token-must-not-print", raw)
        self.assertNotIn("secret-must-not-print", raw)
        self.assertIn("status=ok", raw)

    @patch(
        "apps.messaging.management.commands."
        "poll_bale_updates.poll_bale_updates"
    )
    def test_command_converts_expected_polling_error_to_command_error(
        self,
        mocked_poll,
    ):
        mocked_poll.side_effect = BalePollingError(
            "bale_polling_lock_unavailable"
        )

        with self.assertRaisesMessage(
            CommandError,
            "bale_polling_lock_unavailable",
        ):
            call_command("poll_bale_updates")

    @patch(
        "apps.messaging.management.commands."
        "poll_bale_updates.poll_bale_updates"
    )
    def test_command_does_not_hide_unexpected_programming_error(
        self,
        mocked_poll,
    ):
        mocked_poll.side_effect = RuntimeError(
            "unexpected_polling_bug"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpected_polling_bug",
        ):
            call_command("poll_bale_updates")

    @patch("apps.messaging.management.commands.poll_bale_updates.poll_bale_updates")
    def test_command_fails_when_provider_polling_fails(self, mocked_poll):
        from .polling import BalePollingResult

        mocked_poll.return_value = BalePollingResult(
            status="provider_error",
            error="bale_api_request_failed",
        )

        with self.assertRaises(CommandError):
            call_command("poll_bale_updates")

    def tearDown(self):
        cache.clear()
        MessagingMessageLog.objects.all().delete()
        MessagingWebhookEvent.objects.all().delete()
