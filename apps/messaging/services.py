from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .constants import (
    MessagingActionStatus,
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
    MessagingTokenPurpose,
    MessagingWebhookEventStatus,
)
from .models import (
    MessagingAccountConnection,
    MessagingActionExecution,
    MessagingIdentity,
    MessagingMessageLog,
    MessagingProvider,
    MessagingToken,
    MessagingWebhookEvent,
)

DEFAULT_PROVIDER_TITLES = {
    MessagingProviderKey.BALE: "بله",
    MessagingProviderKey.TELEGRAM: "تلگرام",
    MessagingProviderKey.WHATSAPP: "واتس‌اپ",
    MessagingProviderKey.RUBIKA: "روبیکا",
}


def messaging_enabled() -> bool:
    return bool(getattr(settings, "MESSAGING_ENABLED", False))


def messaging_outbound_enabled() -> bool:
    return bool(getattr(settings, "MESSAGING_OUTBOUND_ENABLED", False))


def provider_allowed(provider_key: str) -> bool:
    allowed = getattr(settings, "MESSAGING_ALLOWED_PROVIDERS", []) or []
    return str(provider_key or "") in set(allowed)


def _should_auto_activate_provider(provider_key: str) -> bool:
    return (
        str(provider_key or "") == str(MessagingProviderKey.BALE)
        and messaging_enabled()
        and bool(getattr(settings, "BALE_BOT_ENABLED", False))
        and provider_allowed(provider_key)
    )


def ensure_default_providers() -> dict[str, MessagingProvider]:
    providers: dict[str, MessagingProvider] = {}
    for key, title in DEFAULT_PROVIDER_TITLES.items():
        should_activate = _should_auto_activate_provider(key)
        provider, created = MessagingProvider.objects.get_or_create(
            key=key,
            defaults={
                "title": title,
                "is_active": should_activate,
                "supports_webhook": True,
                "supports_callback": True,
                "supports_outbound": True,
            },
        )
        changed = []
        if not provider.title:
            provider.title = title
            changed.append("title")
        if should_activate and not provider.is_active:
            provider.is_active = True
            changed.append("is_active")
        if changed and not created:
            provider.save(update_fields=changed)
        providers[key] = provider
    return providers


def get_provider(provider_key: str) -> MessagingProvider:
    provider = MessagingProvider.objects.get(key=provider_key)
    if not provider.is_active or not provider_allowed(provider.key):
        raise PermissionError("messaging_provider_disabled")
    return provider


def make_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()


def _related_content_type(related_object):
    if related_object is None:
        return None, None
    return (
        ContentType.objects.get_for_model(related_object, for_concrete_model=False),
        related_object.pk,
    )


def issue_messaging_token(
    *,
    purpose: str,
    expires_in: timedelta,
    provider: MessagingProvider | None = None,
    identity: MessagingIdentity | None = None,
    user=None,
    notification_delivery=None,
    related_object=None,
    action_key: str = "",
    audience_role: str = "",
    salon_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, MessagingToken]:
    raw_token = make_raw_token()
    related_ct, related_id = _related_content_type(related_object)
    token = MessagingToken.objects.create(
        purpose=purpose,
        token_hash=hash_token(raw_token),
        token_prefix=raw_token[:12],
        provider=provider,
        identity=identity,
        user=user,
        notification_delivery=notification_delivery,
        related_content_type=related_ct,
        related_object_id=related_id,
        action_key=action_key or "",
        audience_role=audience_role or "",
        salon_id=salon_id,
        expires_at=timezone.now() + expires_in,
        metadata=metadata or {},
    )
    return raw_token, token


def get_token(raw_token: str, *, purpose: str | None = None) -> MessagingToken | None:
    token_hash = hash_token(raw_token)
    qs = MessagingToken.objects.select_related("provider", "identity", "user")
    if purpose:
        qs = qs.filter(purpose=purpose)
    return qs.filter(token_hash=token_hash).first()


@transaction.atomic
def consume_token(raw_token: str, *, purpose: str | None = None) -> MessagingToken:
    token_hash = hash_token(raw_token)
    qs = MessagingToken.objects.select_for_update()
    if purpose:
        qs = qs.filter(purpose=purpose)

    token = qs.filter(token_hash=token_hash).first()
    if token is None:
        raise ValueError("token_not_found")
    if token.is_revoked:
        raise ValueError("token_revoked")
    if token.is_used:
        raise ValueError("token_already_used")
    if token.is_expired:
        raise ValueError("token_expired")

    token.mark_used()
    return token


@transaction.atomic
def connect_identity_with_raw_token(
    *,
    identity: MessagingIdentity,
    raw_token: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[MessagingAccountConnection, MessagingToken]:
    """
    Consume one account-link token and connect the messaging identity atomically.
    
    Only a hashed lookup value is stored; the raw token is supplied by the caller.
    The token row is locked and must be unused, unrevoked, unexpired, assigned to a
    user, and compatible with the identity provider. An identity already linked to
    a different user is rejected. The token is marked used in the same transaction
    before the active connection is created or refreshed. This operation links an
    account but does not authenticate a web session.
    """
    token_hash = hash_token(raw_token)
    token = (
        MessagingToken.objects.select_for_update()
        .filter(token_hash=token_hash, purpose=MessagingTokenPurpose.CONNECT_ACCOUNT)
        .first()
    )

    if token is None:
        raise ValueError("token_not_found")
    if token.is_revoked:
        raise ValueError("token_revoked")
    if token.is_used:
        raise ValueError("token_already_used")
    if token.is_expired:
        raise ValueError("token_expired")
    if token.user_id is None:
        raise ValueError("token_missing_user")
    if token.provider_id and token.provider_id != identity.provider_id:
        raise ValueError("token_provider_mismatch")
    if identity.user_id and identity.user_id != token.user_id:
        raise ValueError("identity_already_linked_to_another_user")

    token.mark_used()

    connection = connect_identity_to_user(
        identity,
        token.user,
        metadata={
            "source": "bot_connect_token",
            **(metadata or {}),
        },
    )
    return connection, token


def get_or_create_identity(
    *,
    provider: MessagingProvider,
    provider_user_id: str,
    chat_id: str = "",
    phone_number: str = "",
    username: str = "",
    display_name: str = "",
    language_code: str = "",
    raw_profile: dict[str, Any] | None = None,
) -> tuple[MessagingIdentity, bool]:
    defaults = {
        "chat_id": chat_id or "",
        "phone_number": phone_number or "",
        "username": username or "",
        "display_name": display_name or "",
        "language_code": language_code or "",
        "raw_profile": raw_profile or {},
        "last_seen_at": timezone.now(),
    }
    identity, created = MessagingIdentity.objects.get_or_create(
        provider=provider,
        provider_user_id=str(provider_user_id),
        defaults=defaults,
    )
    if not created:
        changed_fields = []
        for field in [
            "chat_id",
            "phone_number",
            "username",
            "display_name",
            "language_code",
        ]:
            value = defaults[field]
            if value and getattr(identity, field) != value:
                setattr(identity, field, value)
                changed_fields.append(field)
        if raw_profile:
            identity.raw_profile = raw_profile
            changed_fields.append("raw_profile")
        identity.last_seen_at = timezone.now()
        changed_fields.extend(["last_seen_at", "updated_at"])
        identity.save(update_fields=sorted(set(changed_fields)))
    return identity, created


def identity_has_active_connection(identity: MessagingIdentity, *, user=None) -> bool:
    if identity is None:
        return False

    if identity.status != MessagingIdentityStatus.LINKED:
        return False

    user_id = getattr(user, "pk", None) or identity.user_id
    if not user_id:
        return False

    return MessagingAccountConnection.objects.filter(
        provider_id=identity.provider_id,
        identity_id=identity.pk,
        user_id=user_id,
        status=MessagingConnectionStatus.ACTIVE,
    ).exists()


def revoke_active_tokens_for_identity(identity: MessagingIdentity) -> int:
    if identity is None or not identity.pk:
        return 0

    return MessagingToken.objects.filter(
        identity_id=identity.pk,
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).update(revoked_at=timezone.now())


@transaction.atomic
def connect_identity_to_user(
    identity: MessagingIdentity, user, *, metadata: dict[str, Any] | None = None
) -> MessagingAccountConnection:
    identity.link_to_user(user)
    connection, _ = MessagingAccountConnection.objects.update_or_create(
        identity=identity,
        status=MessagingConnectionStatus.ACTIVE,
        defaults={
            "provider": identity.provider,
            "user": user,
            "connected_at": timezone.now(),
            "disconnected_at": None,
            "metadata": metadata or {},
        },
    )
    return connection


@transaction.atomic
def disconnect_identity(identity: MessagingIdentity) -> dict[str, int]:
    identity = MessagingIdentity.objects.select_for_update().get(pk=identity.pk)

    identity.disconnect()

    disconnected_connections = MessagingAccountConnection.objects.filter(
        identity=identity,
        status=MessagingConnectionStatus.ACTIVE,
    ).update(
        status=MessagingConnectionStatus.DISCONNECTED,
        disconnected_at=timezone.now(),
    )

    revoked_tokens = revoke_active_tokens_for_identity(identity)

    return {
        "disconnected_connections": disconnected_connections,
        "revoked_tokens": revoked_tokens,
    }


def record_webhook_event(
    *,
    provider: MessagingProvider,
    payload: dict[str, Any],
    headers: dict[str, Any] | None = None,
    event_id: str = "",
    update_id: str = "",
    event_type: str = "",
    identity: MessagingIdentity | None = None,
) -> tuple[MessagingWebhookEvent, bool]:
    """
    Create or find one provider-scoped webhook event idempotently.
    
    When neither event_id nor update_id is available, a new audit row is always
    created because no stable deduplication key exists. Otherwise either identifier
    may match an existing event for the same provider. The initial lookup avoids
    unnecessary writes, while ``IntegrityError`` recovery handles concurrent
    inserts safely. The returned ``created`` flag is the authority for whether
    inbound logging and dispatch may run.
    """
    defaults = {
        "payload": payload or {},
        "headers": headers or {},
        "event_type": event_type or "",
        "identity": identity,
        "status": MessagingWebhookEventStatus.RECEIVED,
    }
    if not event_id and not update_id:
        return (
            MessagingWebhookEvent.objects.create(
                provider=provider,
                event_id="",
                update_id="",
                **defaults,
            ),
            True,
        )

    lookup = Q()
    if event_id:
        lookup |= Q(event_id=event_id)
    if update_id:
        lookup |= Q(update_id=update_id)

    existing = (
        MessagingWebhookEvent.objects.filter(provider=provider).filter(lookup).first()
    )
    if existing:
        return existing, False

    try:
        return (
            MessagingWebhookEvent.objects.create(
                provider=provider,
                event_id=event_id or "",
                update_id=update_id or "",
                **defaults,
            ),
            True,
        )
    except IntegrityError:
        existing = (
            MessagingWebhookEvent.objects.filter(provider=provider)
            .filter(lookup)
            .first()
        )
        if existing is None:
            raise
        return existing, False


def log_message(
    *,
    provider: MessagingProvider,
    direction: str,
    identity: MessagingIdentity | None = None,
    notification_delivery=None,
    status: str | None = None,
    text: str = "",
    payload: dict[str, Any] | None = None,
    provider_response: dict[str, Any] | None = None,
    external_message_id: str = "",
    error_message: str = "",
) -> MessagingMessageLog:
    """
    Persist one inbound or outbound messaging audit record.
    
    Inbound messages default to received and outbound messages default to queued
    unless the caller supplies a terminal status. Sent and received timestamps are
    derived from that resolved status and direction. This helper records provider
    payloads and responses but does not perform network I/O, retry delivery, update
    a NotificationDelivery row, or execute a messaging action.
    """
    resolved_status = status
    if not resolved_status:
        resolved_status = (
            MessagingMessageStatus.RECEIVED
            if direction == MessagingMessageDirection.INBOUND
            else MessagingMessageStatus.QUEUED
        )
    now = timezone.now()
    return MessagingMessageLog.objects.create(
        provider=provider,
        identity=identity,
        notification_delivery=notification_delivery,
        direction=direction,
        status=resolved_status,
        external_message_id=external_message_id or "",
        text=text or "",
        payload=payload or {},
        provider_response=provider_response or {},
        error_message=error_message or "",
        sent_at=now if resolved_status == MessagingMessageStatus.SENT else None,
        received_at=now if direction == MessagingMessageDirection.INBOUND else None,
    )


def create_action_execution(
    *,
    token: MessagingToken | None = None,
    provider: MessagingProvider | None = None,
    identity: MessagingIdentity | None = None,
    user=None,
    action_key: str = "",
    related_object=None,
    status: str = MessagingActionStatus.STARTED,
    result: dict[str, Any] | None = None,
    error_message: str = "",
) -> MessagingActionExecution:
    related_ct, related_id = _related_content_type(related_object)
    return MessagingActionExecution.objects.create(
        token=token,
        provider=provider or getattr(token, "provider", None),
        identity=identity or getattr(token, "identity", None),
        user=user or getattr(token, "user", None),
        action_key=action_key or getattr(token, "action_key", ""),
        related_content_type=related_ct,
        related_object_id=related_id,
        status=status,
        result=result or {},
        error_message=error_message or "",
        finished_at=timezone.now() if status != MessagingActionStatus.STARTED else None,
    )
