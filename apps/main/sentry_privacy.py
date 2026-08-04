import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

_SAFE_REQUEST_HEADERS = {
    "accept",
    "content-type",
    "host",
    "user-agent",
}

_SENSITIVE_KEY_MARKERS = (
    "password",
    "passwd",
    "pwd",
    "otp",
    "token",
    "secret",
    "authorization",
    "cookie",
    "csrf",
    "session",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "database_url",
    "redis_url",
    "cache_location",
    "dsn",
    "webhook",
    "phone",
    "mobile",
    "email",
    "iban",
    "sheba",
    "card_number",
    "national_id",
    "first_name",
    "last_name",
    "full_name",
    "customer_name",
)

_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    flags=re.IGNORECASE,
)

_IR_PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+98|0098|98|0)?9\d{9})(?!\d)")

_SENSITIVE_ASSIGNMENT_RE = re.compile(r"""(?ix)
    \b(
        password
        |passwd
        |pwd
        |otp
        |token
        |secret
        |api[_-]?key
        |authorization
        |cookie
        |session(?:id|_key)?
    )\b
    \s*[:=]\s*
    ([^\s,;&]+)
    """)


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _scrub_text(value: str) -> str:
    value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    value = _IR_PHONE_RE.sub("[REDACTED_PHONE]", value)

    value = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED}",
        value,
    )

    return value


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_text(value)

    if isinstance(value, Mapping):
        cleaned = {}

        for key, item in value.items():
            if _is_sensitive_key(key):
                cleaned[key] = REDACTED
            else:
                cleaned[key] = _scrub_value(item)

        return cleaned

    if isinstance(value, list):
        return [_scrub_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)

    return value


def _sanitize_request(event: dict) -> None:
    request = event.get("request")

    if not isinstance(request, dict):
        return

    # Never send raw request bodies or URL/query data to external monitoring.
    for key in (
        "data",
        "cookies",
        "query_string",
        "env",
        "url",
    ):
        request.pop(key, None)

    headers = request.get("headers")

    if isinstance(headers, Mapping):
        safe_headers = {}

        for key, value in headers.items():
            normalized = str(key).strip().lower()

            if normalized in _SAFE_REQUEST_HEADERS:
                safe_headers[key] = _scrub_value(value)

        request["headers"] = safe_headers
    else:
        request.pop("headers", None)


def _drop_stack_local_variables(event: dict) -> None:
    exception = event.get("exception")

    if not isinstance(exception, dict):
        return

    values = exception.get("values")

    if not isinstance(values, list):
        return

    for exception_value in values:
        if not isinstance(exception_value, dict):
            continue

        stacktrace = exception_value.get("stacktrace")

        if not isinstance(stacktrace, dict):
            continue

        frames = stacktrace.get("frames")

        if not isinstance(frames, list):
            continue

        for frame in frames:
            if isinstance(frame, dict):
                frame.pop("vars", None)


def sentry_before_send(event: dict, hint: dict | None) -> dict:
    """
    Final fail-safe privacy boundary before an error leaves Loomera.

    Direct user identity, raw request data, cookies, query strings,
    authorization material and stack-frame local variables must not be
    exported to the external error-monitoring provider.
    """

    event.pop("user", None)

    _sanitize_request(event)
    _drop_stack_local_variables(event)

    return _scrub_value(event)


def sentry_before_send_transaction(
    event: dict,
    hint: dict | None,
) -> dict:
    # Tracing is currently disabled, but keep the same privacy boundary
    # ready before tracing is enabled later.
    return sentry_before_send(event, hint)


def sentry_before_breadcrumb(
    breadcrumb: dict,
    hint: dict | None,
) -> dict:
    return _scrub_value(breadcrumb)
