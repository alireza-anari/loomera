from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from loomera.logging_utils import mask_email, mask_mobile

from .models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryStatus,
)

logger = logging.getLogger(__name__)


def _normalize_mobile(mobile: str) -> str:
    value = (
        str(mobile or "")
        .strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if value.startswith("+98"):
        value = "0" + value[3:]
    if value.startswith("0098"):
        value = "0" + value[4:]
    if value.startswith("98") and len(value) == 12:
        value = "0" + value[2:]
    return value


def _record_attempt(
    delivery: NotificationDelivery,
    *,
    status: str,
    provider: str = "",
    response: dict | None = None,
    error: str = "",
):
    delivery.attempt_count = int(delivery.attempt_count or 0) + 1
    delivery.status = status
    delivery.provider = provider or delivery.provider
    if status == NotificationDeliveryStatus.SENT:
        delivery.sent_at = timezone.now()
        delivery.failed_at = None
        delivery.last_error = ""
    elif status == NotificationDeliveryStatus.FAILED:
        delivery.failed_at = timezone.now()
        delivery.last_error = error or "failed"
    delivery.save(
        update_fields=[
            "attempt_count",
            "status",
            "provider",
            "sent_at",
            "failed_at",
            "last_error",
            "updated_at",
        ]
    )
    NotificationDeliveryAttempt.objects.create(
        delivery=delivery,
        attempt_number=delivery.attempt_count,
        status=status,
        provider=provider or delivery.provider,
        provider_response=response or {},
        error_message=error or "",
    )
    return delivery


def deliver_email(delivery: NotificationDelivery):
    recipient = delivery.recipient
    user = recipient.user
    email = str(getattr(user, "email", "") or "").strip()
    if not email:
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.PENDING_SETUP,
            error="missing_email",
        )
    from_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if not from_email:
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.PENDING_SETUP,
            error="missing_default_from_email",
        )
    try:
        send_mail(
            subject=recipient.notification.title,
            message=recipient.notification.body,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info(
            "Notification email sent | delivery=%s | email=%s",
            delivery.pk,
            mask_email(email),
        )
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.SENT,
            provider="email",
            response={"email": mask_email(email)},
        )
    except Exception as exc:
        logger.exception(
            "Notification email failed | delivery=%s | email=%s",
            delivery.pk,
            mask_email(email),
        )
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.FAILED,
            provider="email",
            error=str(exc),
        )


def _send_smsir(*, mobile: str, message: str):
    api_key = str(getattr(settings, "SMSIR_API_KEY", "") or "").strip()
    if getattr(settings, "SMSIR_USE_SANDBOX", True):
        api_key = (
            str(getattr(settings, "SMSIR_SANDBOX_API_KEY", "") or "").strip() or api_key
        )
    line_number = str(getattr(settings, "SMSIR_LINE_NUMBER", "") or "").strip()
    url = str(getattr(settings, "SMSIR_BULK_URL", "") or "").strip()
    timeout = int(getattr(settings, "SMSIR_TIMEOUT_SECONDS", 10) or 10)
    if not api_key:
        return (
            NotificationDeliveryStatus.PENDING_SETUP,
            {"reason": "missing_smsir_api_key"},
            "",
        )
    if not line_number:
        return (
            NotificationDeliveryStatus.PENDING_SETUP,
            {"reason": "missing_smsir_line_number"},
            "",
        )
    if not url:
        return (
            NotificationDeliveryStatus.PENDING_SETUP,
            {"reason": "missing_smsir_bulk_url"},
            "",
        )

    payload = {"lineNumber": line_number, "messageText": message, "mobiles": [mobile]}
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-KEY": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        status = (
            NotificationDeliveryStatus.SENT
            if 200 <= status_code < 300
            else NotificationDeliveryStatus.FAILED
        )
        return (
            status,
            {
                "provider_status_code": status_code,
                "provider_response": data,
                "mobile": mask_mobile(mobile),
            },
            "",
        )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        return (
            NotificationDeliveryStatus.FAILED,
            {
                "provider_status_code": exc.code,
                "provider_response": data,
                "mobile": mask_mobile(mobile),
            },
            str(exc),
        )
    except Exception as exc:
        logger.exception("SMS.ir notification failed | mobile=%s", mask_mobile(mobile))
        return (
            NotificationDeliveryStatus.FAILED,
            {"mobile": mask_mobile(mobile)},
            str(exc),
        )


def deliver_sms(delivery: NotificationDelivery):
    provider = (
        str(getattr(settings, "SMS_PROVIDER", "disabled") or "disabled").strip().lower()
    )
    if provider == "disabled":
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.PENDING_SETUP,
            provider="disabled",
            error="provider_disabled",
        )
    mobile = _normalize_mobile(getattr(delivery.recipient.user, "mobile_number", ""))
    if not mobile:
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.PENDING_SETUP,
            provider=provider,
            error="missing_mobile",
        )
    if provider == "smsir":
        status, response, error = _send_smsir(
            mobile=mobile, message=delivery.recipient.notification.body
        )
        return _record_attempt(
            delivery, status=status, provider="smsir", response=response, error=error
        )
    return _record_attempt(
        delivery,
        status=NotificationDeliveryStatus.PENDING_SETUP,
        provider=provider,
        error="unsupported_sms_provider",
    )


def deliver_messaging(delivery: NotificationDelivery):
    try:
        from apps.messaging.notification_delivery import deliver_simple_notification
    except (
        Exception
    ) as exc:  # defensive: notifications must not crash if adapter code is unavailable
        logger.exception(
            "Messaging notification adapter import failed | delivery=%s", delivery.pk
        )
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.FAILED,
            provider=delivery.channel,
            error=f"messaging_adapter_import_failed: {exc}",
        )

    try:
        result = deliver_simple_notification(delivery)
        return _record_attempt(
            delivery,
            status=result.status,
            provider=result.provider,
            response=result.response,
            error=result.error,
        )
    except Exception as exc:
        logger.exception(
            "Messaging notification delivery failed | delivery=%s | channel=%s",
            delivery.pk,
            delivery.channel,
        )
        return _record_attempt(
            delivery,
            status=NotificationDeliveryStatus.FAILED,
            provider=delivery.channel,
            error=str(exc),
        )


def _is_messaging_channel(channel: str) -> bool:
    try:
        from apps.messaging.notification_delivery import messaging_notification_channels
    except Exception:
        return channel in {
            NotificationChannel.BALE,
            NotificationChannel.TELEGRAM,
            NotificationChannel.RUBIKA,
        }
    return channel in messaging_notification_channels()


def _queued_delivery_channels() -> list[str]:
    channels = [NotificationChannel.EMAIL, NotificationChannel.SMS]
    try:
        from apps.messaging.notification_delivery import (
            queue_processable_messaging_channels,
        )
    except Exception:
        return channels
    channels.extend(queue_processable_messaging_channels())
    return channels


def deliver(delivery: NotificationDelivery):
    if delivery.channel == NotificationChannel.EMAIL:
        return deliver_email(delivery)
    if delivery.channel == NotificationChannel.SMS:
        return deliver_sms(delivery)
    if delivery.channel in {NotificationChannel.DASHBOARD, NotificationChannel.SYSTEM}:
        delivery.status = NotificationDeliveryStatus.SENT
        delivery.sent_at = delivery.sent_at or timezone.now()
        delivery.save(update_fields=["status", "sent_at", "updated_at"])
        return delivery
    if _is_messaging_channel(delivery.channel):
        return deliver_messaging(delivery)
    return _record_attempt(
        delivery,
        status=NotificationDeliveryStatus.PENDING_SETUP,
        error="unsupported_channel",
    )


def deliver_queued_delivery_by_id(
    delivery_id: int,
):
    max_attempts = int(
        getattr(
            settings,
            "LOOMERA_NOTIFICATION_MAX_ATTEMPTS",
            3,
        )
        or 3
    )

    with transaction.atomic():
        delivery = (
            NotificationDelivery.objects.select_for_update(skip_locked=True)
            .select_related(
                "recipient__user",
                "recipient__notification",
            )
            .filter(
                pk=delivery_id,
                status=NotificationDeliveryStatus.QUEUED,
            )
            .first()
        )

        if delivery is None:
            return None

        if int(delivery.attempt_count or 0) >= max_attempts:
            return delivery

        return deliver(delivery)


def process_queued_deliveries(*, limit: int = 50, include_failed: bool = False):
    statuses = [NotificationDeliveryStatus.QUEUED]
    if include_failed:
        statuses.append(NotificationDeliveryStatus.FAILED)
    max_attempts = int(getattr(settings, "LOOMERA_NOTIFICATION_MAX_ATTEMPTS", 3) or 3)
    qs = (
        NotificationDelivery.objects.filter(
            channel__in=_queued_delivery_channels(), status__in=statuses
        )
        .select_related("recipient__user", "recipient__notification")
        .order_by("created_at", "id")[:limit]
    )
    result = {"processed": 0, "sent": 0, "failed": 0, "pending_setup": 0, "skipped": 0}
    for delivery in list(qs):
        if int(delivery.attempt_count or 0) >= max_attempts:
            continue
        with transaction.atomic():
            locked = (
                NotificationDelivery.objects.select_for_update(skip_locked=True)
                .select_related(
                    "recipient__user",
                    "recipient__notification",
                )
                .filter(
                    pk=delivery.pk,
                    status__in=statuses,
                )
                .first()
            )

            if locked is None:
                continue

            if int(locked.attempt_count or 0) >= max_attempts:
                continue

            delivered = deliver(locked)
        result["processed"] += 1
        if delivered.status in result:
            result[delivered.status] += 1
    return result
