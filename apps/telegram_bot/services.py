from __future__ import annotations

from typing import Any
from django.conf import settings
from django.db import transaction

from apps.bale_bot.handlers import handle_bale_update_stage11
from apps.bale_bot.parser import ParsedBaleUpdate, parse_bale_update
from apps.messaging.constants import MessagingMessageDirection, MessagingProviderKey
from apps.messaging.models import MessagingProvider
from apps.messaging.services import (
    ensure_default_providers, get_or_create_identity, log_message,
    provider_allowed, record_webhook_event,
)
from .client import TelegramBotClient


class TelegramWebhookDisabled(PermissionError):
    pass


def telegram_webhook_enabled():
    return bool(getattr(settings, "MESSAGING_ENABLED", False)) and bool(
        getattr(settings, "TELEGRAM_BOT_ENABLED", False)
    )


def get_telegram_provider_for_webhook():
    ensure_default_providers()
    provider = MessagingProvider.objects.get(key=MessagingProviderKey.TELEGRAM)
    if not telegram_webhook_enabled():
        raise TelegramWebhookDisabled("telegram_webhook_disabled")
    if not provider.is_active or not provider_allowed(MessagingProviderKey.TELEGRAM):
        raise TelegramWebhookDisabled("telegram_provider_disabled")
    return provider


def sanitize_webhook_headers(meta: dict[str, Any]):
    # Never persist HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN.
    allowed = [
        "CONTENT_TYPE", "CONTENT_LENGTH", "HTTP_USER_AGENT",
        "HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP", "HTTP_X_REQUEST_ID",
    ]
    return {key: str(meta.get(key, "")) for key in allowed if meta.get(key)}


@transaction.atomic
def record_telegram_webhook_update(*, payload, headers=None, base_url=""):
    provider = get_telegram_provider_for_webhook()
    parsed: ParsedBaleUpdate = parse_bale_update(payload)
    identity = None
    if parsed.user_id:
        identity, _ = get_or_create_identity(
            provider=provider, provider_user_id=parsed.user_id,
            chat_id=parsed.chat_id, username=parsed.username,
            display_name=parsed.display_name, language_code=parsed.language_code,
            raw_profile=parsed.raw_user,
        )
    event, created = record_webhook_event(
        provider=provider, identity=identity, payload=payload, headers=headers or {},
        event_id=parsed.event_id, update_id=parsed.update_id, event_type=parsed.event_type,
    )
    if not created:
        return {"event": event, "created": False, "duplicate": True, "identity": identity or event.identity, "parsed": parsed}
    if parsed.inbound_text or parsed.event_type:
        log_message(
            provider=provider, identity=identity,
            direction=MessagingMessageDirection.INBOUND,
            text=parsed.inbound_text, payload=payload,
        )
    handler_result = "ignored_missing_identity"
    if identity is not None:
        try:
            handler_result = handle_bale_update_stage11(
                parsed=parsed, identity=identity, provider=provider, base_url=base_url,
                client=TelegramBotClient(),
            )
        except Exception as exc:
            event.mark_failed(type(exc).__name__)
            raise
    event.mark_processed()
    return {
        "event": event, "created": True, "duplicate": False,
        "identity": identity, "parsed": parsed, "handler_result": handler_result,
    }
