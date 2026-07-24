from __future__ import annotations

import re
from typing import Any

from django.conf import settings

_IRAN_MOBILE_RE = re.compile(r"^09\d{9}$")


def normalize_iran_mobile(value: str | None) -> str:
    raw_value = str(value or "").strip()
    raw_value = raw_value.replace(" ", "").replace("-", "")

    if raw_value.startswith("+98"):
        raw_value = "0" + raw_value[3:]
    elif raw_value.startswith("0098"):
        raw_value = "0" + raw_value[4:]
    elif raw_value.startswith("98") and len(raw_value) == 12:
        raw_value = "0" + raw_value[2:]

    return raw_value


def validate_mobile_for_auth(value: str | None) -> tuple[bool, str, str]:
    mobile = normalize_iran_mobile(value)

    if not mobile:
        return False, "", "شماره موبایل الزامی است."

    if not _IRAN_MOBILE_RE.match(mobile):
        return False, mobile, "شماره موبایل معتبر نیست."

    return True, mobile, ""


def user_display_name(user) -> str:
    name_parts = [
        str(getattr(user, "name", "") or "").strip(),
        str(getattr(user, "family", "") or "").strip(),
    ]
    full_name = " ".join(part for part in name_parts if part).strip()
    return full_name or str(getattr(user, "mobile_number", "") or "").strip()


def user_role_flags(user) -> dict[str, bool]:
    return {
        "is_customer": hasattr(user, "customer_profile"),
        "is_stylist": hasattr(user, "stylist_profile"),
        "is_salon_manager": hasattr(user, "salon_manager_profile"),
        "is_staff": bool(getattr(user, "is_staff", False)),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
    }


def serialize_auth_user(user, *, include_private: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": user.pk,
        "display_name": user_display_name(user),
        "roles": user_role_flags(user),
    }

    if include_private:
        data["mobile_number"] = str(getattr(user, "mobile_number", "") or "")
        data["email"] = str(getattr(user, "email", "") or "")

    return data


def public_auth_policy() -> dict[str, Any]:
    return {
        "method": "mobile_otp",
        "phone_region": str(getattr(settings, "LOOMERA_API_AUTH_PHONE_REGION", "IR")),
        "otp": {
            "length": int(getattr(settings, "LOOMERA_API_AUTH_OTP_LENGTH", 6) or 6),
            "ttl_seconds": int(
                getattr(settings, "LOOMERA_API_AUTH_OTP_TTL_SECONDS", 120) or 120
            ),
            "resend_seconds": int(
                getattr(settings, "LOOMERA_API_AUTH_OTP_RESEND_SECONDS", 60) or 60
            ),
            "max_verify_attempts": int(
                getattr(settings, "LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS", 5) or 5
            ),
        },
        "endpoints": {
            "status": "/api/v1/auth/status/",
            "me": "/api/v1/auth/me/",
            "policy": "/api/v1/auth/policy/",
            "otp_request": "/api/v1/auth/otp/request/",
            "otp_verify": "/api/v1/auth/otp/verify/",
            "logout": "/api/v1/auth/logout/",
        },
    }
