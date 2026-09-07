from __future__ import annotations

import logging
from threading import Thread
from typing import Any

from django.conf import settings
from django.db import close_old_connections, transaction

from apps.bale_bot.handlers import handle_bale_update_stage11
from apps.bale_bot.parser import ParsedBaleUpdate, parse_bale_update
from apps.messaging.constants import MessagingMessageDirection, MessagingProviderKey
from apps.messaging.models import MessagingProvider, MessagingWebhookEvent
from apps.messaging.services import (
    ensure_default_providers, get_or_create_identity, log_message,
    provider_allowed, record_webhook_event,
)
from .client import TelegramBotClient

logger = logging.getLogger(__name__)


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


def _process_telegram_webhook_event(*, event_id: int, base_url: str) -> None:
    """Process a stored Telegram event outside the webhook request lifecycle."""
    close_old_connections()
    try:
        event = MessagingWebhookEvent.objects.select_related("provider", "identity").get(
            id=event_id
        )
        provider = event.provider
        payload = event.payload or {}
        parsed: ParsedBaleUpdate = parse_bale_update(payload)
        identity = event.identity

        if identity is not None:
            handler_result = handle_bale_update_stage11(
                parsed=parsed,
                identity=identity,
                provider=provider,
                base_url=base_url,
                client=TelegramBotClient(),
            )
            logger.info(
                "Telegram webhook event processed | event_id=%s result=%s",
                event_id,
                handler_result,
            )
        event.mark_processed()
    except Exception as exc:
        logger.exception("Telegram webhook event processing failed | event_id=%s", event_id)
        try:
            event = MessagingWebhookEvent.objects.get(id=event_id)
            event.mark_failed(type(exc).__name__)
        except Exception:
            logger.exception("Failed to mark Telegram webhook event failed | event_id=%s", event_id)
    finally:
        close_old_connections()


def _start_telegram_event_processing(*, event_id: int, base_url: str) -> None:
    """Start processing after commit so the webhook can return immediately.

    Celery remains optional for this deployment. When no worker is available,
    the lightweight daemon thread keeps webhook delivery independent from the
    slower Loomi/Telegram outbound work.
    """
    worker = Thread(
        target=_process_telegram_webhook_event,
        kwargs={"event_id": event_id, "base_url": base_url},
        name=f"telegram-webhook-{event_id}",
        daemon=True,
    )
    worker.start()


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

    # Do not run Loomi or outbound Telegram calls inside the webhook request.
    # Telegram needs a fast 2xx response; processing continues after commit.
    if identity is not None:
        transaction.on_commit(
            lambda event_id=event.id, url=base_url: _start_telegram_event_processing(
                event_id=event_id, base_url=url
            )
        )
    else:
        event.mark_processed()

    return {
        "event": event, "created": True, "duplicate": False,
        "identity": identity, "parsed": parsed, "handler_result": "queued",
    }
