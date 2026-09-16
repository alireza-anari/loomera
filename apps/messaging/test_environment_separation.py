from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.bale_bot.client import BaleBotClient
from apps.telegram_bot.client import TelegramBotClient
from apps.messaging.links import (
    build_bale_start_url, build_provider_start_url, build_loomi_provider_start_url,
)
from apps.messaging.management.commands.bale_webhook_admin import build_bale_webhook_url


class MessagingEnvironmentSeparationTests(SimpleTestCase):
    @override_settings(BALE_BOT_USERNAME="ExampleStageBot",
        BALE_BOT_START_URL_TEMPLATE="https://ble.ir/ExampleLiveBot?start={payload}")
    def test_stale_template_cannot_override_environment_username(self):
        with self.assertLogs("apps.messaging.links", level="WARNING") as logs:
            self.assertEqual(build_bale_start_url("fake-connect-token"),
                "https://ble.ir/ExampleStageBot?start=connect_fake-connect-token")
            self.assertEqual(build_loomi_provider_start_url("bale", "salon", 12),
                "https://ble.ir/ExampleStageBot?start=loomi_s_12")
        self.assertNotIn("fake-connect-token", " ".join(logs.output))
        self.assertNotIn("ExampleLiveBot", " ".join(logs.output))

    @override_settings(BALE_BOT_USERNAME="@ExampleStageBot",
        BALE_BOT_START_URL_TEMPLATE="https://ble.ir/{username}?start={payload}&ref=profile")
    def test_portable_template_uses_environment_username(self):
        self.assertEqual(build_provider_start_url("bale", "fake-token"),
            "https://ble.ir/ExampleStageBot?start=connect_fake-token&ref=profile")
        self.assertEqual(build_loomi_provider_start_url("bale", "stylist", 12),
            "https://ble.ir/ExampleStageBot?start=loomi_p_12&ref=profile")

    @override_settings(BALE_BOT_USERNAME="", BALE_BOT_START_URL_TEMPLATE="https://ble.ir/ExampleLiveBot?start={payload}")
    def test_missing_username_does_not_fall_back_to_template_bot(self):
        self.assertEqual(build_bale_start_url("fake-token"), "")
        self.assertEqual(build_loomi_provider_start_url("bale", "salon", 1), "")

    @override_settings(BALE_BOT_USERNAME="ExampleStageBot")
    def test_invalid_template_falls_back_without_leaking_connect_token(self):
        for template in ["https://wrong.example/{username}?start={payload}",
                         "https://ble.ir/{unknown}", "https://ble.ir/{username", "http://ble.ir/{username}?start={payload}"]:
            with self.subTest(template=template), override_settings(BALE_BOT_START_URL_TEMPLATE=template):
                with self.assertLogs("apps.messaging.links", level="WARNING"):
                    self.assertEqual(build_bale_start_url("fake-token"),
                        "https://ble.ir/ExampleStageBot?start=connect_fake-token")

    def test_each_environment_selects_its_own_links_clients_and_webhooks(self):
        for environment in ["stage", "live"]:
            with self.subTest(environment=environment), override_settings(
                BALE_BOT_USERNAME=f"Example_{environment}_bot",
                TELEGRAM_BOT_USERNAME=f"Example_{environment}_bot",
                BALE_BOT_TOKEN=f"fake-bale-{environment}",
                TELEGRAM_BOT_TOKEN=f"fake-telegram-{environment}",
                BALE_BOT_START_URL_TEMPLATE="https://ble.ir/{username}?start={payload}",
                TELEGRAM_RELAY_URL="", TELEGRAM_RELAY_SECRET="",
                MESSAGING_PUBLIC_BASE_URL=f"https://{environment}.example.com",
                TELEGRAM_BOT_ENABLED=True, TELEGRAM_WEBHOOK_SECRET=f"fake-hook-{environment}",
            ):
                self.assertEqual(BaleBotClient().token, f"fake-bale-{environment}")
                self.assertEqual(TelegramBotClient().token, f"fake-telegram-{environment}")
                self.assertIn(f"Example_{environment}_bot", build_provider_start_url("telegram", "fake-token"))
                self.assertIn(f"Example_{environment}_bot", build_loomi_provider_start_url("telegram", "salon", 1))
                self.assertIn(f"Example_{environment}_bot", build_loomi_provider_start_url("bale", "salon", 1))
                self.assertEqual(build_bale_webhook_url(),
                    f"https://{environment}.example.com{reverse('bale_bot:webhook')}")
                with patch("apps.telegram_bot.management.commands.telegram_webhook.TelegramBotClient") as client:
                    client.return_value.set_webhook.return_value = {"ok": True}
                    call_command("telegram_webhook", "set", stdout=StringIO())
                    client.return_value.set_webhook.assert_called_once_with(
                        f"https://{environment}.example.com{reverse('telegram_bot:webhook')}",
                        secret_token=f"fake-hook-{environment}", drop_pending_updates=False,
                    )

    @override_settings(MESSAGING_ENABLED=True, BALE_BOT_ENABLED=True, TELEGRAM_BOT_ENABLED=True,
        BALE_WEBHOOK_SECRET="fake-stage-bale", TELEGRAM_WEBHOOK_SECRET="fake-stage-telegram")
    def test_other_environment_webhook_secrets_are_rejected(self):
        for provider, header in [("bale", "HTTP_X_LOOMERA_BALE_SECRET"), ("telegram", "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN")]:
            response = self.client.post(reverse(f"{provider}_bot:webhook"), data="{}",
                content_type="application/json", **{header: "fake-live-secret"})
            self.assertEqual(response.status_code, 403)

    def test_salon_page_has_no_extra_loomi_ui_or_unused_library(self):
        source = (Path(settings.BASE_DIR) / "templates/pages/detail_salon.html").read_text(encoding="utf-8")
        self.assertNotIn("loomi_links", source)
        self.assertNotIn("load messaging_connect", source)
