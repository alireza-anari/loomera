from __future__ import annotations

import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.messaging.constants import MessagingProviderKey
from apps.messaging.management.commands.messaging_qa_check import run_messaging_qa_check
from apps.messaging.models import MessagingProvider
from apps.messaging.services import ensure_default_providers
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationRecipient,
)


class MessagingQACheckTests(TestCase):
    def setUp(self):
        ensure_default_providers()

    def test_json_output_does_not_print_bale_token_or_webhook_secret(self):
        token_value = "real-bale-token-should-not-appear"
        secret_value = "real-webhook-secret-should-not-appear"

        out = io.StringIO()

        with self.settings(
            MESSAGING_ENABLED=True,
            BALE_BOT_ENABLED=True,
            MESSAGING_OUTBOUND_ENABLED=True,
            MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
            BALE_BOT_TOKEN=token_value,
            BALE_WEBHOOK_SECRET=secret_value,
            MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
        ):
            call_command("messaging_qa_check", "--json", stdout=out)

        raw = out.getvalue()
        payload = json.loads(raw)

        self.assertNotIn(token_value, raw)
        self.assertNotIn(secret_value, raw)
        self.assertTrue(payload["settings"]["bale_bot_token_configured"])
        self.assertTrue(payload["settings"]["bale_webhook_secret_configured"])

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="",
        BALE_WEBHOOK_SECRET="",
        BALE_WEBHOOK_REQUIRE_SECRET=True,
    )
    def test_strict_fails_when_required_bale_secrets_are_missing(self):
        out = io.StringIO()

        with self.assertRaises(CommandError):
            call_command("messaging_qa_check", "--strict", stdout=out)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=False,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
        BALE_WEBHOOK_SECRET="strong-secret",
        MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
    )
    def test_command_reports_webhook_reverse_and_queue_readiness(self):
        result = run_messaging_qa_check()

        self.assertTrue(result["webhook"]["reverse_ok"])
        self.assertEqual(result["webhook"]["path"], reverse("bale_bot:webhook"))
        self.assertFalse(result["queue"]["bale_outbound_queue_ready"])

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_OUTBOUND_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_BOT_TOKEN="123:token",
        BALE_WEBHOOK_SECRET="strong-secret",
        MESSAGING_PUBLIC_BASE_URL="https://staging.example.com",
    )
    def test_command_reports_bale_delivery_counts(self):
        bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        bale.is_active = True
        bale.supports_outbound = True
        bale.supports_webhook = True
        bale.save(update_fields=["is_active", "supports_outbound", "supports_webhook"])

        user = CustomUser.objects.create_user(
            mobile_number="09128889900",
            email="messaging-qa@example.com",
            name="QA",
            family="Bale",
            password="pass12345",
        )
        notification = Notification.objects.create(
            event_type="messaging.qa",
            title="تست QA",
            body="این یک اعلان تستی است.",
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=user,
            audience_role=NotificationAudienceRole.CUSTOMER,
        )
        NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.BALE,
            status=NotificationDeliveryStatus.QUEUED,
        )

        result = run_messaging_qa_check()

        self.assertEqual(result["queue"]["bale"]["queued"], 1)
        self.assertTrue(result["queue"]["bale_outbound_queue_ready"])
