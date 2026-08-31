from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from .models import (
    InstagramAccountConnection,
    InstagramConnectionStatus,
    InstagramInboundMessage,
)


def _messaging_runtime_enabled():
    return bool(
        getattr(settings, "INSTAGRAM_ENABLED", False)
        and getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)
    )


def _verify_signature(raw_body, signature_header):
    secret = str(getattr(settings, "INSTAGRAM_APP_SECRET", "") or "").strip()
    header = str(signature_header or "").strip()

    if not secret or not header.startswith("sha256="):
        return False

    supplied = header.split("=", 1)[1].strip().lower()
    if not supplied:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, supplied)


def _safe_timestamp(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_connection(*, entry_account_id, recipient_account_id):
    account_id = str(recipient_account_id or entry_account_id or "").strip()
    if not account_id:
        return None

    entry_id = str(entry_account_id or "").strip()
    recipient_id = str(recipient_account_id or "").strip()

    # Meta's messaging payload identifies the connected Professional Account in
    # entry.id and recipient.id. If both are present but disagree, do not guess.
    if entry_id and recipient_id and entry_id != recipient_id:
        return None

    connection = (
        InstagramAccountConnection.objects.select_related("salon", "stylist")
        .filter(
            instagram_account_id=account_id,
            status=InstagramConnectionStatus.CONNECTED,
        )
        .first()
    )
    if connection is None or not connection.is_context_active():
        return None

    return connection


def _ingest_message_event(*, entry_account_id, event):
    if not isinstance(event, dict):
        return False

    message = event.get("message")
    if not isinstance(message, dict):
        # Reactions/read receipts/postbacks/etc. are intentionally ignored in
        # the current Lumi-DM Beta scope.
        return False

    # Instagram message webhooks may include echoes/self events. Lumi must only
    # respond to customer-initiated inbound messages.
    if message.get("is_echo") or message.get("is_self"):
        return False

    if message.get("is_deleted") or message.get("is_unsupported"):
        return False

    provider_message_id = str(message.get("mid") or "").strip()
    sender_id = str((event.get("sender") or {}).get("id") or "").strip()
    recipient_id = str((event.get("recipient") or {}).get("id") or "").strip()

    if not provider_message_id or not sender_id or not recipient_id:
        return False

    # If sender and recipient are equal, this is not a customer->business DM.
    if sender_id == recipient_id:
        return False

    connection = _find_connection(
        entry_account_id=entry_account_id,
        recipient_account_id=recipient_id,
    )
    if connection is None:
        return False

    text = message.get("text")
    if text is None:
        # Attachments/shares are outside the current text-first Lumi Beta scope.
        return False

    text = str(text).strip()
    if not text:
        return False

    # Bound persisted customer text. No raw webhook payload is retained.
    text = text[:4000]

    try:
        with transaction.atomic():
            _, created = InstagramInboundMessage.objects.get_or_create(
                provider_message_id=provider_message_id,
                defaults={
                    "connection": connection,
                    "sender_igsid": sender_id,
                    "recipient_instagram_account_id": recipient_id,
                    "message_text": text,
                    "provider_timestamp_ms": _safe_timestamp(
                        event.get("timestamp")
                    ),
                },
            )
    except IntegrityError:
        # Concurrent duplicate delivery: the unique provider_message_id is the
        # final idempotency boundary.
        return False

    return created


def ingest_payload(payload):
    if not isinstance(payload, dict) or payload.get("object") != "instagram":
        return 0

    created_count = 0

    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue

        entry_account_id = str(entry.get("id") or "").strip()

        for event in entry.get("messaging") or []:
            if _ingest_message_event(
                entry_account_id=entry_account_id,
                event=event,
            ):
                created_count += 1

    return created_count


@csrf_exempt
def instagram_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        expected = str(
            getattr(settings, "INSTAGRAM_WEBHOOK_VERIFY_TOKEN", "") or ""
        )

        if (
            mode == "subscribe"
            and expected
            and token
            and hmac.compare_digest(str(token), expected)
            and challenge is not None
        ):
            return HttpResponse(str(challenge), content_type="text/plain")

        return HttpResponseForbidden("Webhook verification failed.")

    if request.method != "POST":
        return HttpResponse(status=405)

    # Disabled mode is deliberately a no-op 200. Meta should not keep retrying
    # while Loomera has Instagram switched off.
    if not _messaging_runtime_enabled():
        return HttpResponse("EVENT_RECEIVED", content_type="text/plain")

    raw_body = request.body
    max_bytes = int(
        getattr(settings, "INSTAGRAM_WEBHOOK_MAX_BYTES", 256 * 1024)
    )
    if len(raw_body) > max_bytes:
        return HttpResponse(status=413)

    if not _verify_signature(
        raw_body,
        request.headers.get("X-Hub-Signature-256"),
    ):
        return HttpResponseForbidden("Invalid webhook signature.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("Invalid webhook payload.")

    ingest_payload(payload)

    # Do not expose processing details. Meta only needs a quick successful ACK.
    return HttpResponse("EVENT_RECEIVED", content_type="text/plain")
