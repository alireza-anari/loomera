from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.messaging.models import MessagingProvider

from .client import BaleBotApiError, BaleBotClient
from .services import (
    BaleWebhookDisabled,
    get_bale_provider_for_webhook,
    record_bale_webhook_update,
)


BALE_POLLING_OFFSET_METADATA_KEY = "bale_polling_next_offset"
BALE_POLLING_LOCK_KEY = "loomera:bale:polling:lock:v1"


class BalePollingError(RuntimeError):
    pass


class BalePollingProtocolError(BalePollingError):
    pass


@dataclass(frozen=True)
class BalePollingResult:
    status: str
    fetched: int = 0
    processed: int = 0
    duplicates: int = 0
    next_offset: int | None = None
    failed_update_id: int | None = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "fetched": self.fetched,
            "processed": self.processed,
            "duplicates": self.duplicates,
            "next_offset": self.next_offset,
            "failed_update_id": self.failed_update_id,
            "error": self.error,
        }


def bale_polling_enabled() -> bool:
    return bool(getattr(settings, "BALE_POLLING_ENABLED", False))


def _coerce_update_id(value: Any) -> int:
    if isinstance(value, bool):
        raise BalePollingProtocolError("invalid_bale_update_id")

    try:
        update_id = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise BalePollingProtocolError("invalid_bale_update_id") from exc

    if update_id < 0:
        raise BalePollingProtocolError("invalid_bale_update_id")

    return update_id


def _read_next_offset(provider: MessagingProvider) -> int | None:
    metadata = provider.metadata if isinstance(provider.metadata, dict) else {}
    value = metadata.get(BALE_POLLING_OFFSET_METADATA_KEY)
    if value is None or value == "":
        return None
    return _coerce_update_id(value)


@transaction.atomic
def _persist_next_offset(*, provider_id: int, next_offset: int) -> int:
    provider = MessagingProvider.objects.select_for_update().get(pk=provider_id)
    metadata = dict(provider.metadata or {})
    current_value = metadata.get(BALE_POLLING_OFFSET_METADATA_KEY)
    current_offset = None
    if current_value is not None and current_value != "":
        current_offset = _coerce_update_id(current_value)

    persisted_offset = max(current_offset or 0, next_offset)
    if current_offset != persisted_offset:
        metadata[BALE_POLLING_OFFSET_METADATA_KEY] = persisted_offset
        provider.metadata = metadata
        provider.save(update_fields=["metadata", "updated_at"])

    return persisted_offset


def _acquire_lock(*, timeout: int) -> str:
    token = uuid4().hex
    try:
        acquired = cache.add(BALE_POLLING_LOCK_KEY, token, timeout=timeout)
    except Exception as exc:
        raise BalePollingError("bale_polling_lock_unavailable") from exc

    return token if acquired else ""


def _release_lock(token: str) -> None:
    if not token:
        return
    try:
        if cache.get(BALE_POLLING_LOCK_KEY) == token:
            cache.delete(BALE_POLLING_LOCK_KEY)
    except Exception:
        # The lock TTL is the final safety boundary when cache cleanup fails.
        return


def poll_bale_updates(
    *,
    client: BaleBotClient | None = None,
    limit: int | None = None,
    timeout: int | None = None,
    lock_ttl: int | None = None,
    base_url: str | None = None,
) -> BalePollingResult:
    if not bale_polling_enabled():
        return BalePollingResult(status="disabled")

    resolved_limit = int(
        limit if limit is not None else getattr(settings, "BALE_POLLING_LIMIT", 100)
    )
    resolved_timeout = int(
        timeout
        if timeout is not None
        else getattr(settings, "BALE_POLLING_TIMEOUT_SECONDS", 0)
    )
    resolved_lock_ttl = int(
        lock_ttl
        if lock_ttl is not None
        else getattr(settings, "BALE_POLLING_LOCK_TTL_SECONDS", 120)
    )

    if not 1 <= resolved_limit <= 100:
        raise BalePollingError("bale_polling_limit_out_of_range")
    if resolved_timeout < 0:
        raise BalePollingError("bale_polling_timeout_out_of_range")
    if resolved_lock_ttl < 30:
        raise BalePollingError("bale_polling_lock_ttl_too_small")

    lock_token = _acquire_lock(timeout=resolved_lock_ttl)
    if not lock_token:
        return BalePollingResult(status="locked")

    try:
        provider = get_bale_provider_for_webhook()
        next_offset = _read_next_offset(provider)
        api_client = client or BaleBotClient()
        response = api_client.get_updates(
            offset=next_offset,
            limit=resolved_limit,
            timeout=resolved_timeout,
        )

        updates = response.get("result")
        if not isinstance(updates, list):
            raise BalePollingProtocolError("invalid_bale_get_updates_result")

        normalized_updates: list[tuple[int, dict[str, Any]]] = []
        for update in updates:
            if not isinstance(update, dict):
                raise BalePollingProtocolError("invalid_bale_update_payload")
            normalized_updates.append(
                (_coerce_update_id(update.get("update_id")), update)
            )

        normalized_updates.sort(key=lambda item: item[0])

        processed = 0
        duplicates = 0
        resolved_base_url = (
            str(
                base_url
                if base_url is not None
                else getattr(settings, "MESSAGING_PUBLIC_BASE_URL", "")
            )
            .strip()
            .rstrip("/")
        )

        for update_id, update in normalized_updates:
            try:
                result = record_bale_webhook_update(
                    payload=update,
                    headers={"transport": "polling"},
                    base_url=(f"{resolved_base_url}/" if resolved_base_url else ""),
                )
            except Exception as exc:
                return BalePollingResult(
                    status="failed",
                    fetched=len(normalized_updates),
                    processed=processed,
                    duplicates=duplicates,
                    next_offset=next_offset,
                    failed_update_id=update_id,
                    error=exc.__class__.__name__,
                )

            if result.get("duplicate"):
                duplicates += 1
            else:
                processed += 1

            next_offset = _persist_next_offset(
                provider_id=provider.pk,
                next_offset=update_id + 1,
            )

        return BalePollingResult(
            status="ok",
            fetched=len(normalized_updates),
            processed=processed,
            duplicates=duplicates,
            next_offset=next_offset,
        )
    except BaleWebhookDisabled as exc:
        return BalePollingResult(status="disabled", error=str(exc))
    except (BaleBotApiError, ImproperlyConfigured) as exc:
        return BalePollingResult(
            status="provider_error",
            error=str(exc),
        )
    finally:
        _release_lock(lock_token)
