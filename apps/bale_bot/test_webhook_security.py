from django.test import TestCase, override_settings
from django.urls import reverse

from apps.messaging.constants import MessagingProviderKey
from apps.messaging.models import MessagingProvider, MessagingWebhookEvent
from apps.messaging.services import ensure_default_providers
from apps.bale_bot.webhook_auth import (
    derive_bale_webhook_path_token,
)


class BaleWebhookSecretSecurityTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.bale.is_active = True
        self.bale.save(update_fields=["is_active"])
        self.url = reverse("bale_bot:webhook")
        self.payload = {
            "update_id": 9001,
            "message": {
                "message_id": 10,
                "from": {
                    "id": 123456,
                    "first_name": "کاربر",
                    "username": "loomera_guest",
                    "language_code": "fa",
                },
                "chat": {"id": 987654, "type": "private"},
                "date": 1710000000,
                "text": "/start",
            },
        }

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_REQUIRE_SECRET=True,
        BALE_WEBHOOK_SECRET="",
    )
    def test_enabled_webhook_requires_configured_secret(self):
        response = self.client.post(
            self.url,
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "webhook_secret_not_configured")
        self.assertEqual(MessagingWebhookEvent.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
        BALE_WEBHOOK_ALLOW_QUERY_SECRET=False,
    )
    def test_query_string_secret_is_rejected_by_default(self):
        response = self.client.post(
            f"{self.url}?secret=test-secret",
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "invalid_webhook_secret")
        self.assertEqual(MessagingWebhookEvent.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
    )
    def test_header_secret_is_accepted(self):
        response = self.client.post(
            self.url,
            data=self.payload,
            content_type="application/json",
            HTTP_X_LOOMERA_BALE_SECRET="test-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(MessagingWebhookEvent.objects.count(), 1)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
    )
    def test_wrong_header_secret_is_rejected(self):
        response = self.client.post(
            self.url,
            data=self.payload,
            content_type="application/json",
            HTTP_X_LOOMERA_BALE_SECRET="wrong-secret",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "invalid_webhook_secret")
        self.assertEqual(MessagingWebhookEvent.objects.count(), 0)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
        BALE_WEBHOOK_ALLOW_QUERY_SECRET=True,
    )
    def test_query_string_secret_is_only_allowed_when_compat_flag_is_enabled(self):
        response = self.client.post(
            f"{self.url}?secret=test-secret",
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(MessagingWebhookEvent.objects.count(), 1)

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
        BALE_WEBHOOK_ALLOW_PATH_TOKEN=True,
        BALE_WEBHOOK_ALLOW_QUERY_SECRET=False,
    )
    def test_derived_path_token_is_accepted(self):
        path_token = derive_bale_webhook_path_token("test-secret")
        url = reverse(
            "bale_bot:webhook_path_token",
            kwargs={"path_token": path_token},
        )

        response = self.client.post(
            url,
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            MessagingWebhookEvent.objects.count(),
            1,
        )

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
        BALE_WEBHOOK_ALLOW_PATH_TOKEN=True,
        BALE_WEBHOOK_ALLOW_QUERY_SECRET=False,
    )
    def test_wrong_path_token_is_rejected(self):
        url = reverse(
            "bale_bot:webhook_path_token",
            kwargs={"path_token": "a" * 64},
        )

        response = self.client.post(
            url,
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"],
            "invalid_webhook_secret",
        )
        self.assertEqual(
            MessagingWebhookEvent.objects.count(),
            0,
        )

    @override_settings(
        MESSAGING_ENABLED=True,
        BALE_BOT_ENABLED=True,
        MESSAGING_ALLOWED_PROVIDERS=[MessagingProviderKey.BALE],
        BALE_WEBHOOK_SECRET="test-secret",
        BALE_WEBHOOK_ALLOW_PATH_TOKEN=False,
    )
    def test_path_token_is_rejected_when_disabled(self):
        path_token = derive_bale_webhook_path_token("test-secret")
        url = reverse(
            "bale_bot:webhook_path_token",
            kwargs={"path_token": path_token},
        )

        response = self.client.post(
            url,
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"],
            "invalid_webhook_secret",
        )
