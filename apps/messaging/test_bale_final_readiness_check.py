from __future__ import annotations

import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import CustomUser
from apps.messaging.constants import MessagingProviderKey
from apps.messaging.management.commands.bale_final_readiness_check import (
    run_bale_final_readiness_check,
)
from apps.messaging.models import MessagingProvider
from apps.messaging.services import (
    connect_identity_to_user,
    ensure_default_providers,
    get_or_create_identity,
)
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationRecipient,
)


@override_settings(
    MESSAGING_ENABLED=True,
    BALE_BOT_ENABLED=True,
    MESSAGING_OUTBOUND_ENABLED=True,
    MESSAGING_ACTIONS_ENABLED=True,
    MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
    BALE_BOT_TOKEN="123:token",
    BALE_WEBHOOK_SECRET="strong-secret",
    BALE_WEBHOOK_REQUIRE_SECRET=True,
    BALE_WEBHOOK_ALLOW_QUERY_SECRET=False,
    MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
)
class BaleFinalReadinessCheckTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.provider = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.provider.is_active = True
        self.provider.supports_webhook = True
        self.provider.supports_callback = True
        self.provider.supports_outbound = True
        self.provider.save(
            update_fields=[
                "is_active",
                "supports_webhook",
                "supports_callback",
                "supports_outbound",
            ]
        )

    def test_final_readiness_has_runbook_and_no_secret_output(self):
        token_value = "real-token-should-not-print"
        secret_value = "real-secret-should-not-print"

        out = io.StringIO()
        with self.settings(
            BALE_BOT_TOKEN=token_value,
            BALE_WEBHOOK_SECRET=secret_value,
        ):
            call_command("bale_final_readiness_check", "--json", stdout=out)

        raw = out.getvalue()
        payload = json.loads(raw)

        self.assertNotIn(token_value, raw)
        self.assertNotIn(secret_value, raw)
        self.assertIn("staging_runbook", payload)
        self.assertIn("production_policy", payload)
        self.assertIn("recommended_order", payload)

    def test_final_readiness_detects_failed_queue_problem(self):
        user = CustomUser.objects.create_user(
            mobile_number="09123330044",
            email="bale-final@example.com",
            name="Bale",
            family="Final",
            password="pass12345",
        )
        identity, _created = get_or_create_identity(
            provider=self.provider,
            provider_user_id="bale-final-user",
            chat_id="bale-final-chat",
            display_name="Bale Final",
        )
        connect_identity_to_user(identity, user)

        notification = Notification.objects.create(
            event_type="bale.final",
            title="Final",
            body="Final readiness test",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
            status=NotificationDeliveryStatus.FAILED,
            last_error="provider failed",
        )

        result = run_bale_final_readiness_check()

        self.assertFalse(result["summary"]["staging_ready"])
        self.assertGreaterEqual(result["summary"]["warning_count"], 1)
        issue_codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("BALE_QUEUE_HAS_RETRYABLE_PROBLEMS", issue_codes)

    @override_settings(BALE_BOT_TOKEN="")
    def test_strict_fails_when_bale_config_has_issue(self):
        with self.assertRaises(CommandError):
            call_command("bale_final_readiness_check", "--strict")

    def test_final_readiness_command_text_output_runs(self):
        out = io.StringIO()

        call_command("bale_final_readiness_check", stdout=out)

        raw = out.getvalue()
        self.assertIn("Bale Final Readiness Check", raw)
        self.assertIn("Staging runbook", raw)
        self.assertNotIn("123:token", raw)
        self.assertNotIn("strong-secret", raw)
