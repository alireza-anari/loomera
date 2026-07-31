from __future__ import annotations

import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.bale_bot.constants import BALE_WEBHOOK_PROVIDER_SECRET_HEADER
from apps.messaging.constants import MessagingProviderKey
from apps.messaging.management.commands.bale_webhook_admin import (
    build_bale_webhook_url,
    run_bale_webhook_admin,
)
from apps.messaging.models import MessagingProvider
from apps.messaging.services import ensure_default_providers
from apps.bale_bot.webhook_auth import (
    derive_bale_webhook_path_token,
)


@override_settings(
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    BALE_BOT_TOKEN="123:token",
    BALE_WEBHOOK_SECRET="strong-secret",
    BALE_WEBHOOK_REQUIRE_SECRET=True,
    BALE_WEBHOOK_ALLOW_QUERY_SECRET=False,
    BALE_WEBHOOK_ALLOW_PATH_TOKEN=False,
    MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
)
class BaleWebhookAdminTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        provider = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        provider.is_active = True
        provider.supports_webhook = True
        provider.supports_callback = True
        provider.supports_outbound = True
        provider.save(
            update_fields=[
                "is_active",
                "supports_webhook",
                "supports_callback",
                "supports_outbound",
            ]
        )

    def test_build_webhook_url_without_printing_secret_by_default(self):
        url = build_bale_webhook_url()

        self.assertEqual(
            url,
            f"https://staging.example.com{reverse('bale_bot:webhook')}",
        )
        self.assertNotIn("strong-secret", url)

    def test_webhook_accepts_provider_secret_header(self):
        response = self.client.post(
            reverse("bale_bot:webhook"),
            data={"update_id": 1, "message": {"message_id": 1}},
            content_type="application/json",
            **{BALE_WEBHOOK_PROVIDER_SECRET_HEADER: "strong-secret"},
        )

        self.assertIn(response.status_code, {200, 500})
        self.assertNotEqual(response.status_code, 403)

    def test_default_command_does_not_call_provider(self):
        with patch("apps.bale_bot.client.BaleBotClient.request") as mocked_request:
            result = run_bale_webhook_admin()

        mocked_request.assert_not_called()
        self.assertTrue(result["webhook"]["reverse_ok"])
        self.assertTrue(result["webhook"]["uses_secret_token"])
        self.assertFalse(result["webhook"]["uses_query_secret"])

    def test_set_without_apply_is_dry_run_and_does_not_call_provider(self):
        with patch("apps.bale_bot.client.BaleBotClient.set_webhook") as mocked_set:
            result = run_bale_webhook_admin(set_webhook=True)

        mocked_set.assert_not_called()
        self.assertTrue(result["operation"]["dry_run"])
        self.assertFalse(result["operation"]["applied"])

    def test_set_with_apply_calls_provider_with_secret_token(self):
        with patch(
            "apps.bale_bot.client.BaleBotClient.set_webhook",
            return_value={"ok": True, "result": True},
        ) as mocked_set:
            result = run_bale_webhook_admin(set_webhook=True, apply=True)

        mocked_set.assert_called_once()
        _args, kwargs = mocked_set.call_args
        self.assertEqual(kwargs["secret_token"], "strong-secret")
        self.assertFalse(result["operation"]["dry_run"])
        self.assertTrue(result["operation"]["applied"])

    def test_delete_without_apply_is_dry_run_and_does_not_call_provider(self):
        with patch(
            "apps.bale_bot.client.BaleBotClient.delete_webhook"
        ) as mocked_delete:
            result = run_bale_webhook_admin(delete_webhook=True)

        mocked_delete.assert_not_called()
        self.assertTrue(result["operation"]["dry_run"])
        self.assertFalse(result["operation"]["applied"])

    def test_check_provider_handles_webhook_info_response(self):
        with patch(
            "apps.bale_bot.client.BaleBotClient.get_webhook_info",
            return_value={
                "ok": True,
                "result": {
                    "url": f"https://staging.example.com{reverse('bale_bot:webhook')}",
                    "pending_update_count": 0,
                },
            },
        ):
            result = run_bale_webhook_admin(check_provider=True)

        self.assertTrue(result["operation"]["provider_response"]["ok"])
        self.assertEqual(
            result["operation"]["provider_response"]["result"]["pending_update_count"],
            0,
        )

    def test_json_output_does_not_print_token_or_secret(self):
        token_value = "real-token-should-not-print"
        secret_value = "real-secret-should-not-print"
        out = io.StringIO()

        with self.settings(
            BALE_BOT_TOKEN=token_value,
            BALE_WEBHOOK_SECRET=secret_value,
        ):
            call_command("bale_webhook_admin", "--json", stdout=out)

        raw = out.getvalue()
        payload = json.loads(raw)

        self.assertNotIn(token_value, raw)
        self.assertNotIn(secret_value, raw)
        self.assertTrue(payload["settings"]["bale_bot_token_configured"])
        self.assertTrue(payload["settings"]["bale_webhook_secret_configured"])

    @override_settings(
        BALE_WEBHOOK_ALLOW_QUERY_SECRET=True,
        BALE_WEBHOOK_SECRET="query-secret-should-redact",
    )
    def test_query_secret_url_is_redacted_in_output(self):
        result = run_bale_webhook_admin(include_query_secret=True)

        self.assertNotIn("query-secret-should-redact", result["webhook"]["url"])
        self.assertIn("secret=%2A%2A%2A", result["webhook"]["url"])

    @override_settings(BALE_BOT_TOKEN="")
    def test_strict_fails_when_provider_action_requires_missing_token(self):
        with self.assertRaises(CommandError):
            call_command("bale_webhook_admin", "--check-provider", "--strict")

    @override_settings(
        BALE_WEBHOOK_ALLOW_PATH_TOKEN=True,
    )
    def test_path_token_url_does_not_contain_raw_secret(self):
        url = build_bale_webhook_url(include_path_token=True)

        expected_token = derive_bale_webhook_path_token("strong-secret")

        self.assertIn(expected_token, url)
        self.assertNotIn("strong-secret", url)

    @override_settings(
        BALE_WEBHOOK_ALLOW_PATH_TOKEN=True,
    )
    def test_path_token_is_redacted_from_command_output(self):
        result = run_bale_webhook_admin(include_path_token=True)

        self.assertTrue(result["webhook"]["uses_path_token"])
        self.assertFalse(result["webhook"]["uses_query_secret"])
        self.assertFalse(result["webhook"]["uses_secret_token"])
        self.assertNotIn(
            derive_bale_webhook_path_token("strong-secret"),
            result["webhook"]["url"],
        )
        self.assertIn(
            "***/",
            result["webhook"]["url"],
        )

    @override_settings(
        BALE_WEBHOOK_ALLOW_PATH_TOKEN=True,
    )
    def test_set_with_path_token_does_not_send_header_secret(self):
        with patch(
            "apps.bale_bot.client.BaleBotClient.set_webhook",
            return_value={"ok": True, "result": True},
        ) as mocked_set:
            result = run_bale_webhook_admin(
                set_webhook=True,
                apply=True,
                include_path_token=True,
            )

        mocked_set.assert_called_once()

        args, kwargs = mocked_set.call_args
        registered_url = args[0]

        self.assertNotIn(
            "strong-secret",
            registered_url,
        )
        self.assertEqual(
            kwargs["secret_token"],
            "",
        )
        self.assertTrue(result["operation"]["applied"])
