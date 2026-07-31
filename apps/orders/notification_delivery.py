from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from loomera.logging_utils import mask_email, mask_mobile

from apps.notifications.smsir_transactional import (
    send_smsir_transactional,
)

from .models import AppointmentNotification


logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    status: str
    meta: dict


def normalize_mobile(mobile: str) -> str:
    value = str(mobile or "").strip()
    value = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    if value.startswith("+98"):
        value = "0" + value[3:]

    if value.startswith("0098"):
        value = "0" + value[4:]

    if value.startswith("98") and len(value) == 12:
        value = "0" + value[2:]

    return value


def _merge_meta(notification: AppointmentNotification, extra: dict) -> dict:
    meta = dict(notification.meta or {})
    meta.update(extra or {})
    return meta


def _save_delivery_result(
    notification: AppointmentNotification, result: DeliveryResult
):
    notification.delivery_status = result.status
    notification.meta = _merge_meta(notification, result.meta)
    notification.save(update_fields=["delivery_status", "meta"])
    return notification


def _increment_attempt(notification: AppointmentNotification) -> int:
    meta = dict(notification.meta or {})
    attempts = int(meta.get("attempt_count") or 0) + 1
    meta["attempt_count"] = attempts
    meta["last_attempt_at"] = timezone.now().isoformat()
    notification.meta = meta
    notification.save(update_fields=["meta"])
    return attempts


def _target_user(notification: AppointmentNotification):
    if notification.target_user_id:
        return notification.target_user

    if notification.customer_id and getattr(notification.customer, "user", None):
        return notification.customer.user

    if notification.stylist_id and getattr(notification.stylist, "user", None):
        return notification.stylist.user

    return None


def _customer_opted_out_email(notification: AppointmentNotification) -> bool:
    if notification.audience_role != "customer":
        return False

    customer = notification.customer
    if not customer:
        return False

    return not getattr(customer, "notify_appointment_email", True)


def _customer_opted_out_sms(notification: AppointmentNotification) -> bool:
    if notification.audience_role != "customer":
        return False

    customer = notification.customer
    if not customer:
        return False

    return not getattr(customer, "notify_appointment_sms", True)


def _stylist_opted_out_email(notification: AppointmentNotification) -> bool:
    if notification.audience_role != "stylist":
        return False

    stylist = notification.stylist
    if not stylist:
        return False

    return not getattr(stylist, "notify_booking_email", True)


def _stylist_opted_out_sms(notification: AppointmentNotification) -> bool:
    if notification.audience_role != "stylist":
        return False

    stylist = notification.stylist
    if not stylist:
        return False

    return not getattr(stylist, "notify_booking_sms", False)


def deliver_email_notification(
    notification: AppointmentNotification,
) -> AppointmentNotification:
    notification = AppointmentNotification.objects.select_related(
        "customer", "stylist", "target_user"
    ).get(pk=notification.pk)

    if _customer_opted_out_email(notification):
        return _save_delivery_result(
            notification,
            DeliveryResult("skipped", {"reason": "customer_email_opt_out"}),
        )

    if _stylist_opted_out_email(notification):
        return _save_delivery_result(
            notification,
            DeliveryResult("skipped", {"reason": "stylist_email_opt_out"}),
        )

    user = _target_user(notification)
    email = str(getattr(user, "email", "") or "").strip()

    if not email:
        return _save_delivery_result(
            notification,
            DeliveryResult("pending_setup", {"reason": "missing_email"}),
        )

    from_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()

    if not from_email:
        return _save_delivery_result(
            notification,
            DeliveryResult(
                "pending_setup",
                {"reason": "missing_default_from_email", "email": mask_email(email)},
            ),
        )

    attempts = _increment_attempt(notification)

    try:
        send_mail(
            subject=notification.title,
            message=notification.body,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=False,
        )

        logger.info(
            "Appointment email sent | notification=%s | order=%s | email=%s",
            notification.pk,
            notification.order_id,
            mask_email(email),
        )

        return _save_delivery_result(
            notification,
            DeliveryResult(
                "sent",
                {
                    "email": mask_email(email),
                    "attempt_count": attempts,
                    "sent_at": timezone.now().isoformat(),
                },
            ),
        )

    except Exception as exc:
        logger.exception(
            "Appointment email failed | notification=%s | order=%s | email=%s",
            notification.pk,
            notification.order_id,
            mask_email(email),
        )

        return _save_delivery_result(
            notification,
            DeliveryResult(
                "failed",
                {
                    "email": mask_email(email),
                    "attempt_count": attempts,
                    "error": str(exc),
                    "failed_at": timezone.now().isoformat(),
                },
            ),
        )


def _get_smsir_api_key() -> str:
    if getattr(settings, "SMSIR_USE_SANDBOX", True):
        return (
            str(getattr(settings, "SMSIR_SANDBOX_API_KEY", "") or "").strip()
            or str(getattr(settings, "SMSIR_API_KEY", "") or "").strip()
        )

    return str(getattr(settings, "SMSIR_API_KEY", "") or "").strip()


def _send_smsir_bulk(*, mobile: str, message: str) -> DeliveryResult:
    api_key = _get_smsir_api_key()
    line_number = str(getattr(settings, "SMSIR_LINE_NUMBER", "") or "").strip()
    url = str(getattr(settings, "SMSIR_BULK_URL", "") or "").strip()
    timeout = int(getattr(settings, "SMSIR_TIMEOUT_SECONDS", 10) or 10)

    if not api_key:
        return DeliveryResult("pending_setup", {"reason": "missing_smsir_api_key"})

    if not line_number:
        return DeliveryResult("pending_setup", {"reason": "missing_smsir_line_number"})

    if not url:
        return DeliveryResult("pending_setup", {"reason": "missing_smsir_bulk_url"})

    payload = {
        "lineNumber": line_number,
        "messageText": message,
        "mobiles": [mobile],
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-KEY": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)

        try:
            response_json = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            response_json = {"raw": raw_body}

        if 200 <= status_code < 300:
            return DeliveryResult(
                "sent",
                {
                    "provider": "smsir",
                    "provider_status_code": status_code,
                    "provider_response": response_json,
                    "mobile": mask_mobile(mobile),
                    "sent_at": timezone.now().isoformat(),
                },
            )

        return DeliveryResult(
            "failed",
            {
                "provider": "smsir",
                "provider_status_code": status_code,
                "provider_response": response_json,
                "mobile": mask_mobile(mobile),
            },
        )

    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            response_json = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            response_json = {"raw": raw_body}

        return DeliveryResult(
            "failed",
            {
                "provider": "smsir",
                "provider_status_code": exc.code,
                "provider_response": response_json,
                "mobile": mask_mobile(mobile),
                "error": str(exc),
                "failed_at": timezone.now().isoformat(),
            },
        )

    except Exception as exc:
        logger.exception("SMS.ir request failed | mobile=%s", mask_mobile(mobile))
        return DeliveryResult(
            "failed",
            {
                "provider": "smsir",
                "mobile": mask_mobile(mobile),
                "error": str(exc),
                "failed_at": timezone.now().isoformat(),
            },
        )


def deliver_sms_notification(
    notification: AppointmentNotification,
) -> AppointmentNotification:
    notification = AppointmentNotification.objects.select_related(
        "customer__user",
        "stylist__user",
        "target_user",
        "order",
        "order__salon",
        "order_detail__service",
        "order_detail__salon",
        "salon",
    ).get(pk=notification.pk)

    if _customer_opted_out_sms(notification):
        return _save_delivery_result(
            notification,
            DeliveryResult("skipped", {"reason": "customer_sms_opt_out"}),
        )

    if _stylist_opted_out_sms(notification):
        return _save_delivery_result(
            notification,
            DeliveryResult("skipped", {"reason": "stylist_sms_opt_out"}),
        )

    user = _target_user(notification)
    mobile = normalize_mobile(getattr(user, "mobile_number", ""))

    if not mobile:
        return _save_delivery_result(
            notification,
            DeliveryResult("pending_setup", {"reason": "missing_mobile"}),
        )

    provider = (
        str(getattr(settings, "SMS_PROVIDER", "disabled") or "disabled").strip().lower()
    )

    if provider == "disabled":
        return _save_delivery_result(
            notification,
            DeliveryResult(
                "pending_setup",
                {"reason": "provider_disabled", "mobile": mask_mobile(mobile)},
            ),
        )

    attempts = _increment_attempt(notification)

    if provider == "smsir":
        transactional = send_smsir_transactional(
            event_type=notification.event_type,
            audience_role=notification.audience_role,
            mobile=mobile,
            order=notification.order,
            order_detail=notification.order_detail,
            salon=notification.salon,
        )
        if transactional is not None:
            meta = dict(transactional.response or {})
            if transactional.error:
                meta["error"] = transactional.error
            meta["attempt_count"] = attempts
            return _save_delivery_result(
                notification,
                DeliveryResult(transactional.status, meta),
            )

        result = _send_smsir_bulk(
            mobile=mobile,
            message=notification.body,
        )
        result.meta["attempt_count"] = attempts
        return _save_delivery_result(notification, result)

    return _save_delivery_result(
        notification,
        DeliveryResult(
            "pending_setup",
            {
                "reason": "unsupported_sms_provider",
                "provider": provider,
                "mobile": mask_mobile(mobile),
                "attempt_count": attempts,
            },
        ),
    )


def deliver_notification(
    notification: AppointmentNotification,
) -> AppointmentNotification:
    if notification.channel == "email":
        return deliver_email_notification(notification)

    if notification.channel == "sms":
        return deliver_sms_notification(notification)

    if notification.channel in {"dashboard", "system"}:
        if notification.delivery_status != "sent":
            notification.delivery_status = "sent"
            notification.save(update_fields=["delivery_status"])
        return notification

    notification.delivery_status = "pending_setup"
    notification.meta = _merge_meta(notification, {"reason": "unsupported_channel"})
    notification.save(update_fields=["delivery_status", "meta"])
    return notification


def maybe_deliver_immediately(
    notification: AppointmentNotification,
) -> AppointmentNotification:
    if not getattr(settings, "LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY", True):
        return notification

    if notification.delivery_status not in {"queued", "failed"}:
        return notification

    return deliver_notification(notification)


def process_queued_notifications(
    *, limit: int = 50, include_failed: bool = False
) -> dict:
    statuses = ["queued"]
    if include_failed:
        statuses.append("failed")

    max_attempts = int(getattr(settings, "LOOMERA_NOTIFICATION_MAX_ATTEMPTS", 3) or 3)

    qs = (
        AppointmentNotification.objects.filter(
            channel__in=["email", "sms"], delivery_status__in=statuses
        )
        .select_related("customer__user", "stylist__user", "target_user", "order")
        .order_by("created_at", "id")[:limit]
    )

    processed = 0
    sent = 0
    failed = 0
    skipped = 0
    pending_setup = 0

    for notification in list(qs):
        attempts = int((notification.meta or {}).get("attempt_count") or 0)

        if attempts >= max_attempts:
            continue

        with transaction.atomic():
            locked = AppointmentNotification.objects.select_for_update().get(
                pk=notification.pk
            )

            result = deliver_notification(locked)

        processed += 1

        if result.delivery_status == "sent":
            sent += 1
        elif result.delivery_status == "failed":
            failed += 1
        elif result.delivery_status == "skipped":
            skipped += 1
        elif result.delivery_status == "pending_setup":
            pending_setup += 1

    return {
        "processed": processed,
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "pending_setup": pending_setup,
    }
