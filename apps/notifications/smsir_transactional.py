from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, time
from typing import Any

import requests
from django.conf import settings

from apps.accounts.services.sms import (
    SMSConfigurationError,
    format_smsir_mobile,
    mask_mobile_number,
)
from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    format_time_fa,
)


logger = logging.getLogger(__name__)

MAX_PARAMETER_LENGTH = 50


@dataclass(frozen=True, slots=True)
class SMSIRTransactionalResult:
    status: str
    response: dict[str, Any]
    error: str = ""


_TEMPLATE_SETTINGS = {
    ("booking_created", "customer"): "SMSIR_BOOKING_CREATED_TEMPLATE_ID",
    ("booking_created", "stylist"): "SMSIR_STYLIST_NEW_BOOKING_TEMPLATE_ID",
    ("booking_paid", "stylist"): "SMSIR_STYLIST_NEW_BOOKING_TEMPLATE_ID",
    ("stylist_confirmed", "customer"): "SMSIR_BOOKING_CONFIRMED_TEMPLATE_ID",
    ("stylist_rejected", "customer"): "SMSIR_BOOKING_CANCELLED_TEMPLATE_ID",
    ("stylist_rejected_cancelled", "customer"): "SMSIR_BOOKING_CANCELLED_TEMPLATE_ID",
    ("booking_cancelled", "customer"): "SMSIR_BOOKING_CANCELLED_TEMPLATE_ID",
    ("order_cancelled", "customer"): "SMSIR_BOOKING_CANCELLED_TEMPLATE_ID",
    ("reminder_due", "customer"): "SMSIR_BOOKING_REMINDER_TEMPLATE_ID",
    ("booking_rescheduled", "customer"): "SMSIR_BOOKING_RESCHEDULED_TEMPLATE_ID",
    ("appointment_rescheduled", "customer"): "SMSIR_BOOKING_RESCHEDULED_TEMPLATE_ID",
}


def template_setting_name(*, event_type: str, audience_role: str) -> str:
    key = (
        str(event_type or "").strip().lower(),
        str(audience_role or "").strip().lower(),
    )
    return _TEMPLATE_SETTINGS.get(key, "")


def _clean_parameter(value: Any) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized[:MAX_PARAMETER_LENGTH]


def _order_details(order) -> list:
    if order is None:
        return []

    manager = getattr(order, "order_details1", None)
    if manager is None:
        return []

    try:
        return list(
            manager.select_related("service", "salon")
            .order_by("date", "time", "id")
        )
    except AttributeError:
        try:
            return list(manager.all())
        except AttributeError:
            return []


def _service_label(*, order_detail=None, details: list | None = None) -> str:
    if order_detail is not None:
        service = getattr(order_detail, "service", None)
        return _clean_parameter(getattr(service, "service_name", ""))

    names: list[str] = []
    for detail in details or []:
        service = getattr(detail, "service", None)
        name = _clean_parameter(getattr(service, "service_name", ""))
        if name and name not in names:
            names.append(name)

    if not names:
        return ""
    if len(names) == 1:
        return names[0]

    return _clean_parameter(f"{names[0]} و {len(names) - 1} خدمت دیگر")


def build_booking_parameters(
    *,
    order=None,
    order_detail=None,
    salon=None,
) -> list[dict[str, str]]:
    details = _order_details(order)
    primary_detail = order_detail or (details[0] if details else None)

    resolved_salon = (
        salon
        or getattr(primary_detail, "salon", None)
        or getattr(order, "salon", None)
    )
    salon_name = _clean_parameter(
        getattr(resolved_salon, "salon_name", "")
    )
    service_name = _service_label(
        order_detail=order_detail,
        details=details,
    )

    appointment_date = getattr(primary_detail, "date", None)
    appointment_time = getattr(primary_detail, "time", None)

    date_label = ""
    if isinstance(appointment_date, date):
        date_label = _clean_parameter(
            format_jalali_numeric(appointment_date)
        )

    time_label = ""
    if isinstance(appointment_time, time):
        time_label = _clean_parameter(
            format_time_fa(appointment_time)
        )

    values = {
        "SALON": salon_name,
        "SERVICE": service_name,
        "DATE": date_label,
        "TIME": time_label,
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SMSConfigurationError(
            "پارامترهای پیامک رزرو ناقص‌اند: " + ", ".join(missing)
        )

    return [
        {"name": name, "value": value}
        for name, value in values.items()
    ]


def _template_id(setting_name: str) -> int:
    raw_value = str(getattr(settings, setting_name, "") or "").strip()
    if not raw_value:
        raise SMSConfigurationError(
            f"متغیر {setting_name} تنظیم نشده است."
        )
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise SMSConfigurationError(
            f"مقدار {setting_name} عددی نیست."
        ) from exc


def _extract_message_id(payload: object) -> str:
    if isinstance(payload, dict):
        value = payload.get("messageId")
        return str(value) if value is not None else ""
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            value = first.get("messageId")
            return str(value) if value is not None else ""
    return ""


def send_smsir_transactional(
    *,
    event_type: str,
    audience_role: str,
    mobile: str,
    order=None,
    order_detail=None,
    salon=None,
) -> SMSIRTransactionalResult | None:
    if not getattr(
        settings,
        "SMSIR_TRANSACTIONAL_TEMPLATES_ENABLED",
        False,
    ):
        return None

    setting_name = template_setting_name(
        event_type=event_type,
        audience_role=audience_role,
    )
    if not setting_name:
        return None

    if getattr(settings, "SMSIR_USE_SANDBOX", True):
        return SMSIRTransactionalResult(
            status="pending_setup",
            response={
                "reason": "transactional_templates_require_live_smsir",
                "template_setting": setting_name,
            },
            error="transactional_templates_require_live_smsir",
        )

    api_key = str(getattr(settings, "SMSIR_API_KEY", "") or "").strip()
    if not api_key:
        return SMSIRTransactionalResult(
            status="pending_setup",
            response={"reason": "missing_smsir_api_key"},
            error="missing_smsir_api_key",
        )

    try:
        payload = {
            "mobile": format_smsir_mobile(mobile),
            "templateId": _template_id(setting_name),
            "parameters": build_booking_parameters(
                order=order,
                order_detail=order_detail,
                salon=salon,
            ),
        }
    except SMSConfigurationError as exc:
        return SMSIRTransactionalResult(
            status="pending_setup",
            response={
                "reason": "invalid_transactional_sms_configuration",
                "template_setting": setting_name,
            },
            error=str(exc),
        )

    url = str(
        getattr(
            settings,
            "SMSIR_VERIFY_URL",
            "https://api.sms.ir/v1/send/verify",
        )
        or ""
    ).strip()
    timeout = max(
        int(getattr(settings, "SMSIR_TIMEOUT_SECONDS", 10) or 10),
        3,
    )
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-API-KEY": api_key,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    except requests.Timeout:
        return SMSIRTransactionalResult(
            status="failed",
            response={
                "provider": "smsir",
                "mode": "transactional_verify",
                "template_id": payload["templateId"],
                "mobile": mask_mobile_number(mobile),
            },
            error="smsir_verify_timeout",
        )
    except requests.RequestException as exc:
        logger.exception(
            "SMS.ir transactional request failed | event=%s | role=%s | mobile=%s",
            event_type,
            audience_role,
            mask_mobile_number(mobile),
        )
        return SMSIRTransactionalResult(
            status="failed",
            response={
                "provider": "smsir",
                "mode": "transactional_verify",
                "template_id": payload["templateId"],
                "mobile": mask_mobile_number(mobile),
            },
            error=f"smsir_verify_request_error:{type(exc).__name__}",
        )

    try:
        response_json = response.json()
    except ValueError:
        return SMSIRTransactionalResult(
            status="failed",
            response={
                "provider": "smsir",
                "mode": "transactional_verify",
                "provider_status_code": response.status_code,
                "template_id": payload["templateId"],
                "mobile": mask_mobile_number(mobile),
            },
            error="smsir_verify_invalid_response",
        )

    provider_status = response_json.get("status")
    accepted = response.ok and str(provider_status) == "1"
    message_id = _extract_message_id(response_json.get("data"))
    result_response = {
        "provider": "smsir",
        "mode": "transactional_verify",
        "provider_status_code": response.status_code,
        "provider_status": provider_status,
        "provider_message": str(response_json.get("message") or "")[:200],
        "template_id": payload["templateId"],
        "template_setting": setting_name,
        "parameter_names": [
            item["name"] for item in payload["parameters"]
        ],
        "message_id": message_id,
        "mobile": mask_mobile_number(mobile),
    }

    if accepted:
        logger.info(
            "SMS.ir transactional notification sent | event=%s | role=%s | template_id=%s | mobile=%s | message_id=%s",
            event_type,
            audience_role,
            payload["templateId"],
            mask_mobile_number(mobile),
            message_id or "-",
        )
        return SMSIRTransactionalResult(
            status="sent",
            response=result_response,
        )

    return SMSIRTransactionalResult(
        status="failed",
        response=result_response,
        error="smsir_verify_rejected",
    )
