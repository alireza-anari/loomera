from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings

from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPreference,
    NotificationPriority,
)

from .constants import (
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingMessageStatus,
    MessagingProviderKey,
)
from .models import MessagingAccountConnection, MessagingProvider
from .services import (
    ensure_default_providers,
    messaging_enabled,
    messaging_outbound_enabled,
    provider_allowed,
)
from .actions import build_action_callback_data, issue_action_token

CHANNEL_PROVIDER_MAP = {
    NotificationChannel.BALE: MessagingProviderKey.BALE,
    NotificationChannel.TELEGRAM: MessagingProviderKey.TELEGRAM,
    NotificationChannel.WHATSAPP: MessagingProviderKey.WHATSAPP,
    NotificationChannel.RUBIKA: MessagingProviderKey.RUBIKA,
}


@dataclass(frozen=True)
class MessagingDeliveryResult:
    status: str
    provider: str
    response: dict
    error: str = ""


def messaging_notification_channels() -> set[str]:
    """Channels owned by apps.messaging.

    Stage 5 only wires Bale to a real adapter. The other provider channels are
    intentionally kept behind pending_setup responses until their adapters are
    added in later stages.
    """

    return set(CHANNEL_PROVIDER_MAP.keys())


def bale_outbound_queue_ready() -> bool:
    """Return True only when queued Bale deliveries may be consumed safely.

    This prevents the notification worker from turning queued Bale deliveries
    into SKIPPED/PENDING_SETUP before the bot is fully configured for real
    outbound delivery in local/staging/production.
    """

    if not messaging_enabled():
        return False
    if not bool(getattr(settings, "BALE_BOT_ENABLED", False)):
        return False
    if not messaging_outbound_enabled():
        return False
    if not str(getattr(settings, "BALE_BOT_TOKEN", "") or "").strip():
        return False
    if not provider_allowed(MessagingProviderKey.BALE):
        return False

    ensure_default_providers()
    provider = (
        MessagingProvider.objects.filter(key=MessagingProviderKey.BALE)
        .only("is_active", "supports_outbound")
        .first()
    )
    return bool(provider and provider.is_active and provider.supports_outbound)


def queue_processable_messaging_channels() -> list[str]:
    """Return messaging channels that the queue worker may touch now.

    Bale deliveries must stay queued until the bot is fully ready for outbound
    sending. This is important because the global notification cron may already
    be running in beta/staging while Bale is still being configured.
    """

    if not bale_outbound_queue_ready():
        return []
    return [NotificationChannel.BALE]


def notification_action_specs(delivery: NotificationDelivery) -> list[dict[str, Any]]:
    """Return optional messaging button specs from notification metadata.

    Supported metadata keys intentionally stay generic so later product stages can
    attach buttons without changing the notification model:
    - messaging_actions
    - bot_actions

    Action specs are ignored unless they are explicit dictionaries.
    """

    metadata = delivery.recipient.notification.metadata or {}
    specs = metadata.get("messaging_actions") or metadata.get("bot_actions") or []
    if not isinstance(specs, list):
        return []
    return [spec for spec in specs if isinstance(spec, dict)]


def _button_label(spec: dict[str, Any]) -> str:
    return str(spec.get("label") or spec.get("text") or "اقدام").strip()[:64] or "اقدام"


def _spec_salon_id(spec: dict[str, Any], fallback: int | None) -> int | None:
    raw = spec.get("salon_id")
    if raw in (None, ""):
        return fallback
    try:
        return int(raw)
    except (TypeError, ValueError):
        return fallback


def _spec_expires_in(spec: dict[str, Any]) -> timedelta | None:
    raw_minutes = spec.get("expires_minutes") or spec.get("ttl_minutes")
    if raw_minutes in (None, ""):
        return None
    try:
        minutes = int(raw_minutes)
    except (TypeError, ValueError):
        return None
    return timedelta(minutes=max(minutes, 1))


def build_actionable_reply_markup(
    delivery: NotificationDelivery, *, provider: MessagingProvider, identity
) -> dict | None:
    """
    Build safe inline buttons from explicit notification metadata.

    Invalid or incomplete specifications are ignored. URL buttons contain only the
    provided URL. Action and view buttons issue one-time action tokens bound to the
    provider, identity, recipient user, notification delivery, related object,
    audience role, and salon scope. Only the raw callback token is placed in
    callback_data; persistent storage keeps its hash. Buttons are grouped in rows
    of at most two, and no markup is returned when no valid button remains.
    """
    specs = notification_action_specs(delivery)
    if not specs:
        return None

    notification = delivery.recipient.notification
    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = []

    for spec in specs:
        button_type = str(spec.get("type") or "action").strip().lower()
        label = _button_label(spec)

        if button_type == "url":
            url = str(spec.get("url") or spec.get("action_url") or "").strip()
            if not url:
                continue
            current_row.append({"text": label, "url": url})
        elif button_type in {"action", "view"}:
            action_key = str(spec.get("key") or spec.get("action_key") or "").strip()
            if not action_key:
                continue
            raw_token, _ = issue_action_token(
                provider=provider,
                identity=identity,
                user=delivery.recipient.user,
                notification_delivery=delivery,
                related_object=notification.related_object,
                action_key=action_key,
                audience_role=str(
                    spec.get("audience_role") or delivery.recipient.audience_role or ""
                ),
                salon_id=_spec_salon_id(spec, notification.salon_id),
                expires_in=_spec_expires_in(spec),
                metadata={
                    "button_type": button_type,
                    "label": label,
                    "notification_id": notification.pk,
                    **(
                        spec.get("metadata")
                        if isinstance(spec.get("metadata"), dict)
                        else {}
                    ),
                },
            )
            current_row.append(
                {"text": label, "callback_data": build_action_callback_data(raw_token)}
            )
        else:
            continue

        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)
    if not rows:
        return None
    return {"inline_keyboard": rows}


def _decision_notification_text(delivery: NotificationDelivery) -> str:
    notification = delivery.recipient.notification
    role = str(delivery.recipient.audience_role or "")
    related = notification.related_object

    try:
        from apps.orders.models import OrderDetail
        from apps.salons.models import SalonMembership
        from apps.stylists.models import StaffLeaveRequest, StaffScheduleRequest
        from .bale_presenters import (
            appointment_block,
            leave_request_block,
            membership_request_block,
            schedule_request_block,
        )
    except Exception:
        return ""

    if isinstance(related, OrderDetail):
        if role == NotificationAudienceRole.STYLIST:
            if related.service_completed_at:
                heading = "خدمت انجام شد"
            elif related.service_started_at:
                heading = "خدمت در حال انجام"
            elif related.customer_arrived_at:
                heading = "مشتری رسیده"
            elif str(notification.event_type or "") in {"booking_created", "booking_paid"}:
                heading = "نوبت جدید برای شما ثبت شد"
            else:
                heading = str(notification.title or "نوبت").strip() or "نوبت"
            return appointment_block(
                related,
                heading=heading,
                include_salon=True,
                include_status=True,
            )
        if role == NotificationAudienceRole.MANAGER:
            heading = str(notification.title or "نوبت سالن").strip() or "نوبت سالن"
            return appointment_block(
                related,
                heading=heading,
                include_stylist=True,
                include_salon=False,
                include_status=True,
            )

    if role == NotificationAudienceRole.MANAGER:
        if isinstance(related, SalonMembership):
            return membership_request_block(related, heading="درخواست همکاری جدید")
        if isinstance(related, StaffLeaveRequest):
            return leave_request_block(related, heading="درخواست مرخصی")
        if isinstance(related, StaffScheduleRequest):
            return schedule_request_block(related, heading="درخواست برنامه کاری")
    return ""


def render_simple_notification_text(delivery: NotificationDelivery) -> str:
    notification = delivery.recipient.notification
    rich_text = _decision_notification_text(delivery).strip()
    action_url = str(notification.action_url or "").strip()

    if rich_text:
        parts = [rich_text]
        if action_url and not notification_action_specs(delivery):
            parts.append(f"جزئیات در سایت: {action_url}")
        text = "\n\n".join(parts)
    else:
        parts: list[str] = []
        title = str(notification.title or "").strip()
        body = str(notification.body or "").strip()
        if title:
            parts.append(title)
        if body:
            parts.append(body)
        if action_url:
            parts.append(f"جزئیات در سایت: {action_url}")
        text = "\n\n".join(parts).strip() or "اعلان جدید Loomera"

    max_chars = int(
        getattr(settings, "MESSAGING_NOTIFICATION_TEXT_MAX_CHARS", 3500) or 3500
    )
    if max_chars > 0 and len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def messaging_delivery_preference_enabled(delivery: NotificationDelivery) -> bool:
    """
    Re-check the recipient messaging preference when queued work is processed.

    Preferences may change after NotificationDelivery creation, and manually
    created rows must follow the same privacy policy. Critical notifications bypass
    opt-out consistently with the unified notification policy. Non-critical
    preferences are resolved from the most specific audience-role and event rule
    toward generic category defaults. Missing preference rows preserve the default
    enabled behavior.
    """

    recipient = delivery.recipient
    notification = recipient.notification
    if notification.priority == NotificationPriority.CRITICAL:
        return True

    qs = NotificationPreference.objects.filter(
        user=recipient.user, channel=delivery.channel
    )
    candidates = [
        {
            "audience_role": recipient.audience_role,
            "event_type": notification.event_type,
        },
        {
            "audience_role": recipient.audience_role,
            "category": notification.category,
            "event_type": "",
        },
        {"audience_role": recipient.audience_role, "category": "", "event_type": ""},
        {"audience_role": "", "category": notification.category, "event_type": ""},
        {"audience_role": "", "category": "", "event_type": ""},
    ]
    for filters in candidates:
        pref = qs.filter(**filters).order_by("-id").first()
        if pref is not None:
            return bool(pref.is_enabled)
    return True


def _get_provider_for_delivery(
    delivery: NotificationDelivery,
) -> MessagingProvider | None:
    provider_key = CHANNEL_PROVIDER_MAP.get(delivery.channel)
    if not provider_key:
        return None
    ensure_default_providers()
    return MessagingProvider.objects.filter(key=provider_key).first()


def _find_active_identity(delivery: NotificationDelivery, provider: MessagingProvider):
    user = delivery.recipient.user
    connection = (
        MessagingAccountConnection.objects.select_related("identity")
        .filter(
            provider=provider,
            user=user,
            status=MessagingConnectionStatus.ACTIVE,
            identity__status=MessagingIdentityStatus.LINKED,
        )
        .exclude(identity__chat_id="")
        .order_by("-connected_at", "-id")
        .first()
    )
    return connection.identity if connection else None


def _status_from_message_log(message_log) -> str:
    if message_log is None:
        return NotificationDeliveryStatus.FAILED
    if message_log.status == MessagingMessageStatus.SENT:
        return NotificationDeliveryStatus.SENT
    if message_log.status == MessagingMessageStatus.SKIPPED:
        return NotificationDeliveryStatus.SKIPPED
    if message_log.status == MessagingMessageStatus.FAILED:
        return NotificationDeliveryStatus.FAILED
    if message_log.status == MessagingMessageStatus.QUEUED:
        return NotificationDeliveryStatus.QUEUED
    return NotificationDeliveryStatus.FAILED


def deliver_simple_notification(
    delivery: NotificationDelivery,
) -> MessagingDeliveryResult:
    """
    Resolve and attempt one simple notification delivery through messaging.

    The provider, latest user preference, global feature flags, provider outbound
    capability, and an active linked identity are checked before any API call.
    Unavailable setup returns pending-setup, explicit opt-out or disabled messaging
    returns skipped, and an unsupported adapter also remains pending-setup. Bale
    messages use safe text rendering and optional tokenized reply markup; the
    resulting message-log status is mapped to the NotificationDelivery status
    returned to the queue processor. This function returns a delivery result but
    does not itself persist the queue row transition or retry policy.
    """

    provider = _get_provider_for_delivery(delivery)
    provider_key = CHANNEL_PROVIDER_MAP.get(delivery.channel, delivery.channel)
    provider_name = str(provider_key or delivery.channel or "")

    if provider is None:
        return MessagingDeliveryResult(
            status=NotificationDeliveryStatus.PENDING_SETUP,
            provider=provider_name,
            response={"reason": "messaging_provider_missing"},
            error="messaging_provider_missing",
        )

    provider_name = provider.key

    if not messaging_delivery_preference_enabled(delivery):
        return MessagingDeliveryResult(
            status=NotificationDeliveryStatus.SKIPPED,
            provider=provider_name,
            response={"reason": "messaging_user_preference_disabled"},
            error="messaging_user_preference_disabled",
        )

    if not messaging_enabled():
        return MessagingDeliveryResult(
            status=NotificationDeliveryStatus.SKIPPED,
            provider=provider_name,
            response={"reason": "messaging_disabled"},
            error="messaging_disabled",
        )

    if not provider.is_active or not provider_allowed(provider.key):
        return MessagingDeliveryResult(
            status=NotificationDeliveryStatus.PENDING_SETUP,
            provider=provider_name,
            response={
                "reason": "messaging_provider_disabled",
                "provider": provider.key,
            },
            error="messaging_provider_disabled",
        )

    if not provider.supports_outbound:
        return MessagingDeliveryResult(
            status=NotificationDeliveryStatus.PENDING_SETUP,
            provider=provider_name,
            response={
                "reason": "messaging_provider_outbound_unsupported",
                "provider": provider.key,
            },
            error="messaging_provider_outbound_unsupported",
        )

    identity = _find_active_identity(delivery, provider)
    if identity is None:
        return MessagingDeliveryResult(
            status=NotificationDeliveryStatus.PENDING_SETUP,
            provider=provider_name,
            response={
                "reason": "missing_linked_messaging_identity",
                "provider": provider.key,
            },
            error="missing_linked_messaging_identity",
        )

    text = render_simple_notification_text(delivery)

    if provider.key == MessagingProviderKey.BALE:
        from apps.bale_bot.client import BaleBotClient

        reply_markup = build_actionable_reply_markup(
            delivery, provider=provider, identity=identity
        )
        message_log = BaleBotClient().send_message(
            provider=provider,
            identity=identity,
            notification_delivery=delivery,
            chat_id=identity.chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        status = _status_from_message_log(message_log)
        response = {
            "provider": provider.key,
            "identity_id": identity.pk,
            "messaging_message_log_id": getattr(message_log, "pk", None),
            "external_message_id": getattr(message_log, "external_message_id", "")
            or "",
            "outbound_enabled": messaging_outbound_enabled(),
        }
        error = getattr(message_log, "error_message", "") or ""
        return MessagingDeliveryResult(
            status=status, provider=provider.key, response=response, error=error
        )

    return MessagingDeliveryResult(
        status=NotificationDeliveryStatus.PENDING_SETUP,
        provider=provider.key,
        response={
            "reason": "messaging_adapter_not_configured",
            "provider": provider.key,
        },
        error="messaging_adapter_not_configured",
    )
