from __future__ import annotations

import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from apps.telegram_bot.client import TelegramBotApiError, TelegramBotClient


class Command(BaseCommand):
    help = "Set, inspect, or delete Telegram webhook without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument("action", nargs="?", choices=("info", "set", "delete"), default="info")
        parser.add_argument("--drop-pending", action="store_true")

    def handle(self, *args, **options):
        action = options["action"]
        if not str(getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip():
            raise CommandError("TELEGRAM_BOT_TOKEN is not configured.")
        client = TelegramBotClient()
        try:
            if action == "info":
                result = client.get_webhook_info()
            elif action == "delete":
                result = client.delete_webhook(drop_pending_updates=bool(options.get("drop_pending")))
            else:
                if not bool(getattr(settings, "TELEGRAM_BOT_ENABLED", False)):
                    raise CommandError("TELEGRAM_BOT_ENABLED is False.")
                secret = str(getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
                if not secret:
                    raise CommandError("TELEGRAM_WEBHOOK_SECRET is not configured.")
                base_url = str(getattr(settings, "MESSAGING_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
                if not base_url.startswith("https://"):
                    raise CommandError("MESSAGING_PUBLIC_BASE_URL must be a public HTTPS URL.")
                result = client.set_webhook(
                    f"{base_url}{reverse('telegram_bot:webhook')}",
                    secret_token=secret,
                    drop_pending_updates=bool(options.get("drop_pending")),
                )
        except TelegramBotApiError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
