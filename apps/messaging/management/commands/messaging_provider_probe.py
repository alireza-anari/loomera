from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.bale_bot.client import BaleBotApiError, BaleBotClient
from apps.telegram_bot.client import TelegramBotApiError, TelegramBotClient


class Command(BaseCommand):
    help = "Probe Bale and Telegram outbound credentials without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            choices=("bale", "telegram", "all"),
            default="all",
            help="Provider to probe (default: all).",
        )
        parser.add_argument(
            "--chat-id",
            default="",
            help="Optional chat id for an explicit sendMessage probe.",
        )
        parser.add_argument(
            "--text",
            default="Loomera provider probe",
            help="Text used only when --chat-id is supplied.",
        )

    def _probe_bale(self, chat_id: str, text: str):
        self.stdout.write("Bale:")
        client = BaleBotClient()
        try:
            response = client.get_me()
            result = response.get("result") or {}
            self.stdout.write(
                self.style.SUCCESS(
                    f"  getMe=OK username=@{result.get('username') or '?'} id={result.get('id') or '?'}"
                )
            )
        except BaleBotApiError as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"  getMe=FAILED error={exc} response={exc.response}"
                )
            )
            return False
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"  getMe=FAILED error_type={type(exc).__name__}")
            )
            return False

        if chat_id:
            try:
                response = client.request(
                    "sendMessage", {"chat_id": chat_id, "text": text}
                )
                message_id = (response.get("result") or {}).get("message_id")
                self.stdout.write(
                    self.style.SUCCESS(f"  sendMessage=OK message_id={message_id or '?'}")
                )
            except BaleBotApiError as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"  sendMessage=FAILED error={exc} response={exc.response}"
                    )
                )
                return False
        return True

    def _probe_telegram(self, chat_id: str, text: str):
        self.stdout.write("Telegram:")
        client = TelegramBotClient()
        relay_enabled = bool(client.relay_url)
        self.stdout.write(f"  relay_configured={relay_enabled}")
        try:
            response = client.get_me()
            result = response.get("result") or {}
            self.stdout.write(
                self.style.SUCCESS(
                    f"  getMe=OK username=@{result.get('username') or '?'} id={result.get('id') or '?'}"
                )
            )
        except TelegramBotApiError as exc:
            self.stdout.write(
                self.style.ERROR(
                    f"  getMe=FAILED error={exc} response={exc.response}"
                )
            )
            return False
        except Exception as exc:
            self.stdout.write(
                self.style.ERROR(f"  getMe=FAILED error_type={type(exc).__name__}")
            )
            return False

        if chat_id:
            try:
                response = client.request(
                    "sendMessage", {"chat_id": chat_id, "text": text}
                )
                message_id = (response.get("result") or {}).get("message_id")
                self.stdout.write(
                    self.style.SUCCESS(f"  sendMessage=OK message_id={message_id or '?'}")
                )
            except TelegramBotApiError as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"  sendMessage=FAILED error={exc} response={exc.response}"
                    )
                )
                return False
        return True

    def handle(self, *args, **options):
        provider = options["provider"]
        chat_id = str(options.get("chat_id") or "").strip()
        text = str(options.get("text") or "Loomera provider probe")

        self.stdout.write("=== Loomera Messaging Provider Probe ===")
        self.stdout.write(
            "Secrets are never printed; getMe validates the configured outbound credential."
        )
        self.stdout.write(
            f"MESSAGING_ENABLED={bool(getattr(settings, 'MESSAGING_ENABLED', False))}"
        )
        self.stdout.write(
            f"MESSAGING_OUTBOUND_ENABLED={bool(getattr(settings, 'MESSAGING_OUTBOUND_ENABLED', False))}"
        )
        self.stdout.write("")

        ok = True
        if provider in {"bale", "all"}:
            ok = self._probe_bale(chat_id, text) and ok
            self.stdout.write("")
        if provider in {"telegram", "all"}:
            ok = self._probe_telegram(chat_id, text) and ok

        if not ok:
            raise SystemExit(1)
