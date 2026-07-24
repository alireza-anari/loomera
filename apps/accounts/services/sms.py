from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

PERSIAN_DIGITS_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
SMSIR_VERIFY_URL = "https://api.sms.ir/v1/send/verify"
SMSIR_SANDBOX_TEMPLATE_ID = 123456

OTP_PURPOSE_SIGNUP = "signup"
OTP_PURPOSE_PASSWORD_RESET = "password_reset"


@dataclass(slots=True)
class SMSDeliveryResult:
    success: bool
    provider: str
    mode: str
    message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    simulated: bool = False


class SMSConfigurationError(Exception):
    pass



def _translate_digits(value: str | None) -> str:
    return (value or "").translate(PERSIAN_DIGITS_MAP).translate(ARABIC_DIGITS_MAP)



def normalize_mobile_number(mobile_number: str | None) -> str:
    digits = "".join(ch for ch in _translate_digits(mobile_number) if ch.isdigit())
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits



def format_smsir_mobile(mobile_number: str | None) -> str:
    digits = normalize_mobile_number(mobile_number)
    if len(digits) != 11 or not digits.startswith("09"):
        raise SMSConfigurationError("شماره موبایل برای ارسال پیامک معتبر نیست.")
    return digits[1:]



def mask_mobile_number(mobile_number: str | None) -> str:
    digits = normalize_mobile_number(mobile_number)
    if len(digits) != 11:
        return "شماره نامعتبر"
    return f"{digits[:4]}***{digits[-3:]}"



def create_random_code(count: int) -> int:
    count = max(int(count or 0), 1)
    if count == 1:
        return secrets.randbelow(10)
    lower_bound = 10 ** (count - 1)
    upper_delta = 9 * (10 ** (count - 1))
    return lower_bound + secrets.randbelow(upper_delta)



def create_state_token() -> str:
    return secrets.token_hex(16)



def _get_sms_provider() -> str:
    return str(getattr(settings, "SMS_PROVIDER", "disabled") or "disabled").strip().lower()



def _get_smsir_mode() -> str:
    return "sandbox" if getattr(settings, "SMSIR_USE_SANDBOX", True) else "live"



def _get_smsir_api_key(mode: str) -> str:
    if mode == "sandbox":
        return str(getattr(settings, "SMSIR_SANDBOX_API_KEY", "") or "").strip()
    return str(getattr(settings, "SMSIR_API_KEY", "") or "").strip()



def _get_smsir_template_id(purpose: str, mode: str) -> int:
    if mode == "sandbox":
        return SMSIR_SANDBOX_TEMPLATE_ID

    template_setting_name = {
        OTP_PURPOSE_SIGNUP: "SMSIR_SIGNUP_TEMPLATE_ID",
        OTP_PURPOSE_PASSWORD_RESET: "SMSIR_RESET_TEMPLATE_ID",
    }.get(purpose)

    if not template_setting_name:
        raise SMSConfigurationError("نوع OTP پشتیبانی نمی‌شود.")

    raw_template_id = getattr(settings, template_setting_name, "")
    if raw_template_id in (None, ""):
        raise SMSConfigurationError("شناسه قالب پیامکی تنظیم نشده است.")

    try:
        return int(raw_template_id)
    except (TypeError, ValueError) as exc:
        raise SMSConfigurationError("شناسه قالب پیامکی معتبر نیست.") from exc



def _build_smsir_payload(*, mobile_number: str, code: str, purpose: str, mode: str) -> dict:
    template_id = _get_smsir_template_id(purpose, mode)
    parameter_name = str(
        getattr(settings, "SMSIR_OTP_PARAMETER_NAME", "CODE") or "CODE"
    ).strip() or "CODE"
    return {
        "mobile": format_smsir_mobile(mobile_number),
        "templateId": template_id,
        "parameters": [{"name": parameter_name, "value": str(code)}],
    }



def _extract_message_id(data: object) -> str | None:
    if isinstance(data, dict):
        message_id = data.get("messageId")
        return str(message_id) if message_id is not None else None
    if isinstance(data, list) and data:
        first_item = data[0]
        if isinstance(first_item, dict):
            message_id = first_item.get("messageId")
            return str(message_id) if message_id is not None else None
    return None



def _send_smsir_verify(*, mobile_number: str, code: str, purpose: str) -> SMSDeliveryResult:
    mode = _get_smsir_mode()
    api_key = _get_smsir_api_key(mode)
    if not api_key:
        logger.error("SMS.ir API key is missing | mode=%s", mode)
        return SMSDeliveryResult(
            success=False,
            provider="smsir",
            mode=mode,
            error_code="missing_api_key",
            error_message="کلید API پیامک تنظیم نشده است.",
            simulated=(mode == "sandbox"),
        )

    try:
        payload = _build_smsir_payload(
            mobile_number=mobile_number,
            code=code,
            purpose=purpose,
            mode=mode,
        )
    except SMSConfigurationError as exc:
        logger.error("SMS.ir configuration error | mode=%s | error=%s", mode, exc)
        return SMSDeliveryResult(
            success=False,
            provider="smsir",
            mode=mode,
            error_code="invalid_configuration",
            error_message=str(exc),
            simulated=(mode == "sandbox"),
        )

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "x-api-key": api_key,
    }
    timeout = max(int(getattr(settings, "SMSIR_TIMEOUT_SECONDS", 10) or 10), 3)

    try:
        response = requests.post(
            SMSIR_VERIFY_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    except requests.Timeout:
        logger.warning(
            "SMS.ir verify timeout | mode=%s | purpose=%s | mobile=%s",
            mode,
            purpose,
            mask_mobile_number(mobile_number),
        )
        return SMSDeliveryResult(
            success=False,
            provider="smsir",
            mode=mode,
            error_code="timeout",
            error_message="درخواست ارسال پیامک timeout شد.",
            simulated=(mode == "sandbox"),
        )
    except requests.RequestException as exc:
        logger.exception(
            "SMS.ir verify request failed | mode=%s | purpose=%s | mobile=%s",
            mode,
            purpose,
            mask_mobile_number(mobile_number),
        )
        return SMSDeliveryResult(
            success=False,
            provider="smsir",
            mode=mode,
            error_code="request_error",
            error_message=str(exc),
            simulated=(mode == "sandbox"),
        )

    try:
        payload_response = response.json()
    except ValueError:
        logger.error(
            "SMS.ir returned non-JSON response | status=%s | mode=%s | mobile=%s",
            response.status_code,
            mode,
            mask_mobile_number(mobile_number),
        )
        return SMSDeliveryResult(
            success=False,
            provider="smsir",
            mode=mode,
            error_code="invalid_response",
            error_message="پاسخ نامعتبر از سرویس پیامک دریافت شد.",
            simulated=(mode == "sandbox"),
        )

    status_code = payload_response.get("status")
    message_text = payload_response.get("message")
    success = response.ok and str(status_code) == "1"
    message_id = _extract_message_id(payload_response.get("data"))

    if success:
        logger.info(
            "SMS.ir OTP sent | mode=%s | purpose=%s | mobile=%s | template_id=%s | message_id=%s",
            mode,
            purpose,
            mask_mobile_number(mobile_number),
            payload.get("templateId"),
            message_id or "-",
        )
        return SMSDeliveryResult(
            success=True,
            provider="smsir",
            mode=mode,
            message_id=message_id,
            simulated=(mode == "sandbox"),
        )

    logger.warning(
        "SMS.ir OTP failed | mode=%s | purpose=%s | mobile=%s | status=%s | message=%s",
        mode,
        purpose,
        mask_mobile_number(mobile_number),
        status_code,
        message_text,
    )
    return SMSDeliveryResult(
        success=False,
        provider="smsir",
        mode=mode,
        error_code=str(status_code) if status_code is not None else None,
        error_message=message_text,
        simulated=(mode == "sandbox"),
    )



def send_otp_sms(mobile_number: str, code: str, *, purpose: str) -> SMSDeliveryResult:
    provider = _get_sms_provider()
    if not getattr(settings, "SMS_OTP_ENABLED", False):
        logger.warning(
            "SMS delivery disabled by configuration | provider=%s | mobile=%s",
            provider,
            mask_mobile_number(mobile_number),
        )
        return SMSDeliveryResult(
            success=False,
            provider=provider,
            mode="disabled",
            error_code="disabled",
            error_message="ارسال پیامک غیرفعال است.",
            simulated=True,
        )

    if provider == "smsir":
        return _send_smsir_verify(
            mobile_number=mobile_number,
            code=str(code),
            purpose=purpose,
        )

    logger.error("Unsupported SMS provider configured: %s", provider)
    return SMSDeliveryResult(
        success=False,
        provider=provider,
        mode="invalid",
        error_code="unsupported_provider",
        error_message="provider پیامکی پشتیبانی نمی‌شود.",
        simulated=True,
    )
