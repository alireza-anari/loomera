from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils.crypto import salted_hmac

from .auth_serializers import normalize_iran_mobile, validate_mobile_for_auth

logger = logging.getLogger(__name__)

API_AUTH_OTP_PURPOSE_LOGIN = "app_login"


class ApiOtpPayloadTooLarge(Exception):
    pass


class ApiOtpPayloadInvalid(Exception):
    pass


class ApiOtpRateLimitUnavailable(Exception):
    pass


class ApiOtpRateLimited(Exception):
    def __init__(self, *, retry_after: int, scope: str):
        self.retry_after = max(int(retry_after or 0), 0)
        self.scope = scope
        super().__init__(scope)


@dataclass(frozen=True)
class ApiOtpRequestResult:
    mobile_number: str
    masked_mobile_number: str
    ttl_seconds: int
    resend_seconds: int
    length: int
    mode: str = "simulated"
    sent: bool = False


class ApiOtpNotFound(Exception):
    pass


class ApiOtpExpired(Exception):
    pass


class ApiOtpInvalidCode(Exception):
    def __init__(self, *, attempts_remaining: int):
        self.attempts_remaining = max(int(attempts_remaining or 0), 0)
        super().__init__("invalid_code")


class ApiOtpMaxAttemptsExceeded(Exception):
    pass


def api_otp_now_ts() -> int:
    return int(time.time())


def api_otp_cache_prefix() -> str:
    return str(
        getattr(settings, "LOOMERA_API_AUTH_OTP_CACHE_PREFIX", "loomera:api-auth-otp")
        or "loomera:api-auth-otp"
    ).strip()


def api_otp_length() -> int:
    return max(int(getattr(settings, "LOOMERA_API_AUTH_OTP_LENGTH", 6) or 6), 4)


def api_otp_ttl_seconds() -> int:
    return max(
        int(getattr(settings, "LOOMERA_API_AUTH_OTP_TTL_SECONDS", 120) or 120), 60
    )


def api_otp_resend_seconds() -> int:
    return max(
        int(getattr(settings, "LOOMERA_API_AUTH_OTP_RESEND_SECONDS", 60) or 60),
        30,
    )


def api_otp_max_verify_attempts() -> int:
    return max(
        int(getattr(settings, "LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS", 5) or 5),
        1,
    )


def api_otp_fail_closed() -> bool:
    """
    Return the configured cache-failure policy for the OTP subsystem.
    
    When true, an unavailable cache blocks OTP request or verification because
    rate-limit state, attempt counters, and replay prevention cannot be trusted.
    The false setting is a local compatibility policy and must not be interpreted
    as equivalent security.
    """
    return bool(getattr(settings, "LOOMERA_API_AUTH_OTP_FAIL_CLOSED", True))


def api_otp_mobile_hour_limit() -> int:
    return max(
        int(
            getattr(
                settings,
                "LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR",
                5,
            )
            or 5
        ),
        1,
    )


def api_otp_ip_hour_limit() -> int:
    return max(
        int(
            getattr(settings, "LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR", 30) or 30
        ),
        1,
    )


def mask_mobile_for_api(mobile_number: str | None) -> str:
    mobile = normalize_iran_mobile(mobile_number)
    if len(mobile) != 11:
        return "شماره نامعتبر"
    return f"{mobile[:4]}***{mobile[-3:]}"


def generate_numeric_otp(length: int | None = None) -> str:
    length = api_otp_length() if length is None else max(int(length or 0), 4)
    upper_bound = 10**length
    return str(secrets.randbelow(upper_bound)).zfill(length)


def normalize_otp_code(value: str | None) -> str:
    return str(value or "").strip()


def hash_otp_code(*, mobile_number: str, code: str, purpose: str) -> str:
    return salted_hmac(
        "loomera.api.auth.otp",
        f"{purpose}:{mobile_number}:{code}",
    ).hexdigest()


def _safe_cache_key_part(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value or ""))


def otp_record_cache_key(*, purpose: str, mobile_number: str) -> str:
    return (
        f"{api_otp_cache_prefix()}:record:"
        f"{_safe_cache_key_part(purpose)}:{_safe_cache_key_part(mobile_number)}"
    )


def otp_resend_cache_key(*, purpose: str, mobile_number: str) -> str:
    return (
        f"{api_otp_cache_prefix()}:resend:"
        f"{_safe_cache_key_part(purpose)}:{_safe_cache_key_part(mobile_number)}"
    )


def otp_hour_rate_cache_key(*, scope: str, value: str) -> str:
    current_hour = api_otp_now_ts() // 3600
    return (
        f"{api_otp_cache_prefix()}:rate:"
        f"{_safe_cache_key_part(scope)}:{_safe_cache_key_part(value)}:{current_hour}"
    )


def client_ip_from_request(request) -> str:
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR") or "").strip() or "unknown"


def _cache_get(key: str, default=None):
    """
    Read OTP or rate-limit state through the configured failure policy.
    
    Cache backend failures are converted to ``ApiOtpRateLimitUnavailable`` when
    fail-closed is enabled. Under the explicit open policy, the supplied default
    is returned. Secret codes, hashes, and complete mobile numbers must not be
    logged by this boundary.
    """
    try:
        return cache.get(key, default)
    except Exception as exc:
        logger.warning("API OTP cache get failed | key_scope=%s", key.split(":")[-3:-1])
        if api_otp_fail_closed():
            raise ApiOtpRateLimitUnavailable from exc
        return default


def _cache_set(key: str, value, *, timeout: int):
    """
    Persist OTP or rate-limit state through the configured failure policy.
    
    Cache backend failures are converted to ``ApiOtpRateLimitUnavailable`` when
    fail-closed is enabled. Under the explicit open policy, the write may be
    skipped. Callers must not assume a skipped write created replay protection or
    an enforceable rate-limit record.
    """
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as exc:
        logger.warning("API OTP cache set failed | key_scope=%s", key.split(":")[-3:-1])
        if api_otp_fail_closed():
            raise ApiOtpRateLimitUnavailable from exc


def _cache_delete(
    key: str,
    *,
    context: str,
    required: bool = False,
) -> bool:
    """
    Delete OTP state with an explicit replay-prevention requirement.
    
    ``required=False`` is best-effort cleanup for expired or exhausted records.
    ``required=True`` is used after a correct OTP comparison; with fail-closed
    enabled, deletion failure raises ``ApiOtpRateLimitUnavailable`` so the caller
    cannot authenticate while the valid record may still be replayable. This
    helper never exposes the stored OTP payload.
    """
    try:
        cache.delete(key)
        return True
    except Exception as exc:
        logger.warning(
            "API OTP cache delete failed | context=%s | key_scope=%s",
            context,
            key.split(":")[-3:-1],
        )

        if required and api_otp_fail_closed():
            raise ApiOtpRateLimitUnavailable from exc

        return False


def _increment_hour_rate(*, scope: str, value: str, limit: int):
    """
    Increment and enforce one current-hour OTP request counter.
    
    The caller supplies either the mobile or IP scope. Cache failures follow the
    OTP fail-closed policy, and a count strictly greater than the configured limit
    raises ``ApiOtpRateLimited``. This function does not create or deliver an OTP.
    """
    key = otp_hour_rate_cache_key(scope=scope, value=value)
    try:
        current = cache.get(key, 0)
        current = int(current or 0) + 1
        cache.set(key, current, timeout=3600)
    except Exception as exc:
        logger.warning("API OTP rate cache failed | scope=%s", scope)
        if api_otp_fail_closed():
            raise ApiOtpRateLimitUnavailable from exc
        return

    if current > limit:
        raise ApiOtpRateLimited(retry_after=3600, scope=scope)


def _check_resend_cooldown(*, purpose: str, mobile_number: str):
    """
    Reject a repeated OTP request while the mobile resend cooldown is active.
    
    The cooldown is scoped by purpose and normalized mobile number. Missing state
    allows the request; a positive remaining interval raises ``ApiOtpRateLimited``
    with the ``mobile_resend`` scope. This check does not mutate the OTP record.
    """
    key = otp_resend_cache_key(purpose=purpose, mobile_number=mobile_number)
    last_sent_at = _cache_get(key)
    if not last_sent_at:
        return

    remaining = api_otp_resend_seconds() - (api_otp_now_ts() - int(last_sent_at))
    if remaining > 0:
        raise ApiOtpRateLimited(retry_after=remaining, scope="mobile_resend")


def create_api_otp_request(
    *,
    mobile_number: str,
    request=None,
    purpose: str = API_AUTH_OTP_PURPOSE_LOGIN,
) -> ApiOtpRequestResult:
    """
    Create the server-side OTP challenge after all request limits pass.
    
    The mobile number is normalized and validated before cooldown, per-mobile, and
    per-IP limits are enforced. Only a salted code hash is stored; the plaintext
    code is never placed in cache or returned by this function. The current
    delivery mode is simulated and this function does not create a user, verify a
    challenge, or authenticate a session.
    """
    valid, normalized_mobile, error = validate_mobile_for_auth(mobile_number)
    if not valid:
        raise ValueError(error or "شماره موبایل معتبر نیست.")

    ip_address = client_ip_from_request(request) if request is not None else "unknown"

    _check_resend_cooldown(purpose=purpose, mobile_number=normalized_mobile)
    _increment_hour_rate(
        scope="mobile",
        value=f"{purpose}:{normalized_mobile}",
        limit=api_otp_mobile_hour_limit(),
    )
    _increment_hour_rate(
        scope="ip",
        value=f"{purpose}:{ip_address}",
        limit=api_otp_ip_hour_limit(),
    )

    code = generate_numeric_otp()
    now_ts = api_otp_now_ts()
    ttl_seconds = api_otp_ttl_seconds()

    record: dict[str, Any] = {
        "purpose": purpose,
        "mobile_number": normalized_mobile,
        "code_hash": hash_otp_code(
            mobile_number=normalized_mobile,
            code=code,
            purpose=purpose,
        ),
        "created_at": now_ts,
        "expires_at": now_ts + ttl_seconds,
        "attempts": 0,
        "max_attempts": api_otp_max_verify_attempts(),
        "verified": False,
        "delivery": {
            "channel": "sms",
            "mode": "simulated",
            "sent": False,
            "provider": "none",
        },
    }

    _cache_set(
        otp_record_cache_key(purpose=purpose, mobile_number=normalized_mobile),
        record,
        timeout=ttl_seconds,
    )
    _cache_set(
        otp_resend_cache_key(purpose=purpose, mobile_number=normalized_mobile),
        now_ts,
        timeout=api_otp_resend_seconds(),
    )

    logger.info(
        "API OTP request accepted | purpose=%s | mobile=%s | mode=simulated",
        purpose,
        mask_mobile_for_api(normalized_mobile),
    )

    return ApiOtpRequestResult(
        mobile_number=normalized_mobile,
        masked_mobile_number=mask_mobile_for_api(normalized_mobile),
        ttl_seconds=ttl_seconds,
        resend_seconds=api_otp_resend_seconds(),
        length=api_otp_length(),
    )


def load_api_otp_record(
    *, mobile_number: str, purpose: str = API_AUTH_OTP_PURPOSE_LOGIN
):
    normalized_mobile = normalize_iran_mobile(mobile_number)
    return _cache_get(
        otp_record_cache_key(purpose=purpose, mobile_number=normalized_mobile)
    )


def verify_api_otp_code(
    *,
    mobile_number: str,
    code: str,
    purpose: str = API_AUTH_OTP_PURPOSE_LOGIN,
) -> dict[str, Any]:
    """
    Verify one OTP challenge without authenticating a Django user session.
    
    The submitted code must have the configured numeric length and is compared to
    the stored hash with ``secrets.compare_digest``. Expired and exhausted records
    are cleaned up, invalid attempts preserve the remaining TTL, and successful
    verification requires deletion of the cache record before returning. This function does not authenticate a Django user session. User lookup and
    ``login`` belong to the API view after this function succeeds.
    """
    valid, normalized_mobile, error = validate_mobile_for_auth(mobile_number)
    if not valid:
        raise ValueError(error or "شماره موبایل معتبر نیست.")

    normalized_code = normalize_otp_code(code)
    if not normalized_code.isdigit() or len(normalized_code) != api_otp_length():
        raise ApiOtpInvalidCode(attempts_remaining=0)

    key = otp_record_cache_key(purpose=purpose, mobile_number=normalized_mobile)
    record = _cache_get(key)

    if not record:
        raise ApiOtpNotFound

    now_ts = api_otp_now_ts()
    if int(record.get("expires_at") or 0) < now_ts:
        _cache_delete(
            key,
            context="expired",
        )
        raise ApiOtpExpired

    attempts = int(record.get("attempts") or 0)
    max_attempts = int(record.get("max_attempts") or api_otp_max_verify_attempts())

    if attempts >= max_attempts:
        _cache_delete(
            key,
            context="max_attempts",
        )
        raise ApiOtpMaxAttemptsExceeded

    expected_hash = str(record.get("code_hash") or "")
    submitted_hash = hash_otp_code(
        mobile_number=normalized_mobile,
        code=normalized_code,
        purpose=purpose,
    )

    if not secrets.compare_digest(expected_hash, submitted_hash):
        attempts += 1
        attempts_remaining = max(max_attempts - attempts, 0)

        if attempts_remaining <= 0:
            _cache_delete(
                key,
                context="invalid_max_attempts",
            )
            raise ApiOtpMaxAttemptsExceeded

        record["attempts"] = attempts
        ttl_remaining = max(int(record.get("expires_at") or now_ts) - now_ts, 1)
        _cache_set(key, record, timeout=ttl_remaining)

        raise ApiOtpInvalidCode(attempts_remaining=attempts_remaining)

    record["verified"] = True
    record["verified_at"] = now_ts

    _cache_delete(
        key,
        context="verified",
        required=True,
    )

    logger.info(
        "API OTP verified | purpose=%s | mobile=%s",
        purpose,
        mask_mobile_for_api(normalized_mobile),
    )

    return record
