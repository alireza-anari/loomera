from __future__ import annotations

import logging
import re
from typing import Any

EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
MOBILE_RE = re.compile(r"\b(09\d{9})\b")
PAYMENT_TOKEN_PATH_RE = re.compile(
    r"(/payments/(?:charge/verify|appointment/(?:verify|result|mock))/\d+/)([A-Za-z0-9_-]{16,})"
)
QUERY_SECRET_RE = re.compile(r"((?:token|callback_token|idempotency_key|Authority)=)([^&\s]+)", re.IGNORECASE)


def mask_email(value: str | None) -> str:
    text = str(value or "").strip()
    if not text or "@" not in text:
        return text
    local, domain = text.split("@", 1)
    if len(local) <= 2:
        local_masked = local[:1] + "***"
    else:
        local_masked = local[:2] + "***"
    domain_parts = domain.split(".")
    if not domain_parts:
        return f"{local_masked}@***"
    domain_head = domain_parts[0]
    domain_masked = (domain_head[:1] + "***") if domain_head else "***"
    if len(domain_parts) > 1:
        return f"{local_masked}@{domain_masked}." + ".".join(domain_parts[1:])
    return f"{local_masked}@{domain_masked}"


def mask_mobile(value: str | None) -> str:
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 11 and digits.startswith("09"):
        return f"{digits[:4]}***{digits[-3:]}"
    return text


def mask_token(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) <= 8:
        return "<redacted>" if text else ""
    return f"{text[:4]}...{text[-4:]}"


def sanitize_text(value: str | None) -> str:
    text = str(value or "")
    text = EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    text = MOBILE_RE.sub(lambda m: mask_mobile(m.group(0)), text)
    text = PAYMENT_TOKEN_PATH_RE.sub(lambda m: f"{m.group(1)}<redacted>", text)
    text = QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}<redacted>", text)
    return text


def sanitize_value(value: Any):
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {key: sanitize_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        sanitized_items = [sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(sanitized_items)
        if isinstance(value, set):
            return set(sanitized_items)
        return sanitized_items
    return value


class SensitiveDataMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_value(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: sanitize_value(val) for key, val in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(sanitize_value(val) for val in record.args)
        elif record.args:
            record.args = sanitize_value(record.args)
        return True
