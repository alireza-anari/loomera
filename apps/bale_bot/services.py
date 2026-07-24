from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction

from apps.messaging.constants import (
    MessagingMessageDirection,
    MessagingProviderKey,
    MessagingWebhookEventStatus,
)
from apps.messaging.models import MessagingProvider, MessagingWebhookEvent
from apps.messaging.services import (
    ensure_default_providers,
    get_or_create_identity,
    log_message,
    provider_allowed,
    record_webhook_event,
)

from .handlers import handle_bale_update_stage11
from .parser import ParsedBaleUpdate, parse_bale_update


class BaleWebhookDisabled(PermissionError):
    pass


class BaleWebhookIgnored(ValueError):
    pass


def bale_webhook_enabled() -> bool:
    return bool(getattr(settings, "MESSAGING_ENABLED", False)) and bool(
        getattr(settings, "BALE_BOT_ENABLED", False)
    )


def get_bale_provider_for_webhook() -> MessagingProvider:
    ensure_default_providers()
    provider = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
    if not bale_webhook_enabled():
        raise BaleWebhookDisabled("bale_webhook_disabled")
    if not provider.is_active or not provider_allowed(MessagingProviderKey.BALE):
        raise BaleWebhookDisabled("bale_provider_disabled")
    return provider


def sanitize_webhook_headers(meta: dict[str, Any]) -> dict[str, str]:
    allowed = [
        "CONTENT_TYPE",
        "CONTENT_LENGTH",
        "HTTP_USER_AGENT",
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_REAL_IP",
        "HTTP_X_REQUEST_ID",
    ]
    return {key: str(meta.get(key, "")) for key in allowed if meta.get(key)}


@transaction.atomic
def record_bale_webhook_update(
    *,
    payload: dict[str, Any],
    headers: dict[str, Any] | None = None,
    base_url: str = "",
):
    """
    Atomically ingest, deduplicate, and dispatch one parsed Bale update.
    
    The active provider is resolved first, the sender identity is created or
    refreshed, and the webhook event is recorded using provider-scoped event or
    update identifiers. A duplicate returns immediately without a second inbound
    message log or handler execution. A new event is logged as inbound, dispatched
    only when an identity exists, and marked processed after successful handling.
    Handler exceptions are marked on the event boundary and re-raised so the
    webhook view can return a controlled failure instead of reporting success.
    """
    provider = get_bale_provider_for_webhook()
    parsed: ParsedBaleUpdate = parse_bale_update(payload)

    identity = None
    if parsed.user_id:
        identity, _ = get_or_create_identity(
            provider=provider,
            provider_user_id=parsed.user_id,
            chat_id=parsed.chat_id,
            username=parsed.username,
            display_name=parsed.display_name,
            language_code=parsed.language_code,
            raw_profile=parsed.raw_user,
        )

    event, created = record_webhook_event(
        provider=provider,
        identity=identity,
        payload=payload,
        headers=headers or {},
        event_id=parsed.event_id,
        update_id=parsed.update_id,
        event_type=parsed.event_type,
    )

    if not created:
        return {
            "event": event,
            "created": False,
            "duplicate": True,
            "identity": identity or event.identity,
            "parsed": parsed,
        }

    if parsed.inbound_text or parsed.event_type:
        log_message(
            provider=provider,
            identity=identity,
            direction=MessagingMessageDirection.INBOUND,
            text=parsed.inbound_text,
            payload=payload,
        )

    handler_result = "not_processed"
    if identity is not None:
        try:
            handler_result = handle_bale_update_stage11(
                parsed=parsed,
                identity=identity,
                provider=provider,
                base_url=base_url,
            )
        except Exception as exc:
            event.mark_failed(str(exc))
            raise

    event.mark_processed()

    return {
        "event": event,
        "created": True,
        "duplicate": False,
        "identity": identity,
        "parsed": parsed,
        "handler_result": handler_result,
    }


@transaction.atomic
def reprocess_bale_webhook_event(*, event_id: int, base_url: str = ""):
    """
    Reprocess one explicitly selected stored Bale webhook event.
    
    The event row is locked and must belong to the active Bale provider with a
    received or failed status. Reprocessing intentionally bypasses duplicate
    detection and does not create a second inbound message log. Identity metadata
    may be refreshed from the stored payload. Handler failure is converted to a
    failed result instead of being re-raised so the failed event state can commit;
    success marks the event processed. This boundary is intended for explicit
    administrative recovery, not normal webhook delivery.
    """

    event = MessagingWebhookEvent.objects.select_for_update().get(pk=event_id)

    provider = get_bale_provider_for_webhook()
    if event.provider_id != provider.pk:
        raise BaleWebhookIgnored("event_provider_mismatch")

    if event.status not in {
        MessagingWebhookEventStatus.FAILED,
        MessagingWebhookEventStatus.RECEIVED,
    }:
        raise BaleWebhookIgnored("event_status_not_reprocessable")

    parsed: ParsedBaleUpdate = parse_bale_update(event.payload or {})

    identity = event.identity
    if parsed.user_id:
        identity, _created = get_or_create_identity(
            provider=provider,
            provider_user_id=parsed.user_id,
            chat_id=parsed.chat_id,
            username=parsed.username,
            display_name=parsed.display_name,
            language_code=parsed.language_code,
            raw_profile=parsed.raw_user,
        )

        if event.identity_id != identity.pk:
            event.identity = identity
            event.save(update_fields=["identity"])

    handler_result = "not_processed"
    if identity is not None:
        try:
            handler_result = handle_bale_update_stage11(
                parsed=parsed,
                identity=identity,
                provider=provider,
                base_url=base_url,
            )
        except Exception as exc:
            event.mark_failed(str(exc))
            return {
                "ok": False,
                "event": event,
                "identity": identity,
                "parsed": parsed,
                "handler_result": "failed",
                "error": str(exc),
            }

    event.mark_processed()

    return {
        "ok": True,
        "event": event,
        "identity": identity,
        "parsed": parsed,
        "handler_result": handler_result,
        "error": "",
    }
