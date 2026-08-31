from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .lumi_bridge import process_inbound_with_lumi
from .models import (
    InstagramAccountConnection,
    InstagramConnectionStatus,
    InstagramInboundMessage,
    InstagramInboundMessageStatus,
    InstagramReplySendStatus,
)


MANAGE_MESSAGES_SCOPE = "instagram_business_manage_messages"


@dataclass(frozen=True)
class InstagramSendResult:
    status: str
    provider_message_id: str = ""
    error_code: str = ""


def _send_runtime_enabled():
    return bool(
        getattr(settings, "INSTAGRAM_ENABLED", False)
        and getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)
        and getattr(settings, "INSTAGRAM_SEND_ENABLED", False)
    )


def _messages_endpoint(connection):
    base = str(settings.INSTAGRAM_GRAPH_BASE_URL).rstrip("/")
    version = str(
        getattr(settings, "INSTAGRAM_GRAPH_API_VERSION", "v24.0") or "v24.0"
    ).strip().strip("/")
    return f"{base}/{version}/{connection.instagram_account_id}/messages"


def _mark_connection_needs_reauth(connection):
    if connection.status != InstagramConnectionStatus.NEEDS_REAUTH:
        connection.status = InstagramConnectionStatus.NEEDS_REAUTH
        connection.save(update_fields=["status", "updated_at"])


def _safe_failure(inbound, code):
    inbound.reply_send_status = InstagramReplySendStatus.FAILED
    inbound.reply_last_error_code = str(code or "send_failed")[:64]
    inbound.save(
        update_fields=["reply_send_status", "reply_last_error_code"]
    )
    return InstagramSendResult(
        status=InstagramReplySendStatus.FAILED,
        error_code=inbound.reply_last_error_code,
    )


def _safe_suppress(inbound, code):
    inbound.reply_send_status = InstagramReplySendStatus.SUPPRESSED
    inbound.reply_last_error_code = str(code or "suppressed")[:64]
    inbound.save(
        update_fields=["reply_send_status", "reply_last_error_code"]
    )
    return InstagramSendResult(
        status=InstagramReplySendStatus.SUPPRESSED,
        error_code=inbound.reply_last_error_code,
    )


@transaction.atomic
def dispatch_lumi_reply(inbound_message_id):
    inbound = InstagramInboundMessage.objects.select_for_update().get(
        pk=inbound_message_id
    )

    if inbound.reply_send_status == InstagramReplySendStatus.SENT:
        return InstagramSendResult(
            status=InstagramReplySendStatus.SENT,
            provider_message_id=inbound.reply_provider_message_id,
        )

    if not _send_runtime_enabled():
        return _safe_suppress(inbound, "send_disabled")

    if inbound.status != InstagramInboundMessageStatus.PROCESSED:
        return _safe_failure(inbound, "lumi_not_processed")

    if inbound.requires_human or inbound.lumi_disposition == "human_handoff":
        return _safe_suppress(inbound, "human_handoff")

    reply_text = str(inbound.lumi_reply_text or "").strip()
    if not reply_text:
        return _safe_suppress(inbound, "empty_reply")

    connection = (
        InstagramAccountConnection.objects.select_related("salon", "stylist")
        .get(pk=inbound.connection_id)
    )

    if not connection.is_context_active():
        return _safe_failure(inbound, "inactive_context")

    if MANAGE_MESSAGES_SCOPE not in set(connection.granted_scopes or []):
        return _safe_failure(inbound, "missing_manage_messages_scope")

    if (
        connection.token_expires_at is not None
        and connection.token_expires_at <= timezone.now()
    ):
        _mark_connection_needs_reauth(connection)
        return _safe_failure(inbound, "token_expired")

    try:
        access_token = connection.get_access_token()
    except Exception:
        _mark_connection_needs_reauth(connection)
        return _safe_failure(inbound, "token_unavailable")

    if not access_token:
        _mark_connection_needs_reauth(connection)
        return _safe_failure(inbound, "token_missing")

    inbound.reply_send_status = InstagramReplySendStatus.SENDING
    inbound.reply_send_attempts += 1
    inbound.reply_last_error_code = ""
    inbound.save(
        update_fields=[
            "reply_send_status",
            "reply_send_attempts",
            "reply_last_error_code",
        ]
    )

    timeout = int(getattr(settings, "INSTAGRAM_REQUEST_TIMEOUT", 10))

    try:
        response = requests.post(
            _messages_endpoint(connection),
            json={
                "recipient": {"id": inbound.sender_igsid},
                "message": {"text": reply_text[:4000]},
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException:
        return _safe_failure(inbound, "network_error")

    if not response.ok:
        if response.status_code in (401, 403):
            _mark_connection_needs_reauth(connection)
        family = (
            f"http_{response.status_code // 100}xx"
            if 100 <= response.status_code <= 599
            else "http_error"
        )
        return _safe_failure(inbound, family)

    try:
        payload = response.json()
    except ValueError:
        return _safe_failure(inbound, "invalid_provider_response")

    provider_message_id = str(payload.get("message_id") or "").strip()
    if not provider_message_id:
        return _safe_failure(inbound, "missing_provider_message_id")

    inbound.reply_send_status = InstagramReplySendStatus.SENT
    inbound.reply_provider_message_id = provider_message_id[:255]
    inbound.reply_last_error_code = ""
    inbound.reply_sent_at = timezone.now()
    inbound.save(
        update_fields=[
            "reply_send_status",
            "reply_provider_message_id",
            "reply_last_error_code",
            "reply_sent_at",
        ]
    )

    return InstagramSendResult(
        status=InstagramReplySendStatus.SENT,
        provider_message_id=inbound.reply_provider_message_id,
    )


def process_and_dispatch_lumi_reply(inbound_message_id):
    process_inbound_with_lumi(inbound_message_id)
    return dispatch_lumi_reply(inbound_message_id)
