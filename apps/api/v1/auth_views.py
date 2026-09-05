from __future__ import annotations
from apps.main.ui_feedback import user_error_message

import json

from django.conf import settings
from django.contrib.auth import get_user, get_user_model, login, logout
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from .auth_otp import (
    ApiOtpExpired,
    ApiOtpInvalidCode,
    ApiOtpMaxAttemptsExceeded,
    ApiOtpNotFound,
    ApiOtpPayloadInvalid,
    ApiOtpPayloadTooLarge,
    ApiOtpRateLimited,
    ApiOtpRateLimitUnavailable,
    create_api_otp_request,
    verify_api_otp_code,
)
from .auth_serializers import (
    public_auth_policy,
    serialize_auth_user,
    validate_mobile_for_auth,
)
from .responses import api_error, api_success


def _django_request(request):
    return getattr(request, "_request", request)


def _django_session_user(request):
    django_request = _django_request(request)
    user = get_user(django_request)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _session_is_authenticated(request) -> bool:
    return _django_session_user(request) is not None


def _auth_otp_payload_max_bytes() -> int:
    return int(
        getattr(
            settings,
            "LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES",
            2 * 1024,
        )
        or 2 * 1024
    )


def _parse_content_length(value) -> int | None:
    """
    Parse an optional HTTP Content-Length value for OTP payload validation.
    
    A missing value remains unknown. Present values must be non-negative integers;
    invalid, non-numeric, or negative values raise ``ApiOtpPayloadInvalid``. This
    helper does not trust the header as the sole body-size check.
    """
    if value in (None, ""):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiOtpPayloadInvalid from exc

    if parsed < 0:
        raise ApiOtpPayloadInvalid

    return parsed


def _load_auth_json_object_payload(
    request,
    *,
    max_bytes: int,
) -> dict:
    """
    Load a bounded UTF-8 JSON object for OTP request and verification views.
    
    Both the declared Content-Length and the actual request body are checked
    against ``max_bytes``. Malformed UTF-8, malformed JSON, and non-object JSON are
    rejected with ``ApiOtpPayloadInvalid``. Unexpected request-body failures are
    not swallowed, and the returned dictionary remains untrusted input.
    """
    content_length = _parse_content_length(
        request.META.get("CONTENT_LENGTH")
    )

    if (
        content_length is not None
        and content_length > max_bytes
    ):
        raise ApiOtpPayloadTooLarge

    raw_body = request.body or b"{}"

    if len(raw_body) > max_bytes:
        raise ApiOtpPayloadTooLarge

    try:
        payload = json.loads(
            raw_body.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ApiOtpPayloadInvalid from exc

    if not isinstance(payload, dict):
        raise ApiOtpPayloadInvalid

    return payload


class ApiAuthStatusAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        user = _django_session_user(request)
        is_authenticated = user is not None

        return api_success(
            {
                "authenticated": is_authenticated,
                "user": (
                    serialize_auth_user(user, include_private=False)
                    if is_authenticated
                    else None
                ),
                "session": {
                    "type": "django_session",
                    "active": is_authenticated,
                },
            }
        )


class ApiAuthMeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return api_success(
            {
                "authenticated": True,
                "user": serialize_auth_user(request.user, include_private=True),
            }
        )


class ApiAuthPolicyAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return api_success(public_auth_policy())


class ApiOtpRequestAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _load_payload(self, request):
        return _load_auth_json_object_payload(
            request,
            max_bytes=_auth_otp_payload_max_bytes(),
        )

    def post(self, request, *args, **kwargs):
        """
        Map an OTP request into the public API contract without exposing secrets.
        
        The bounded shared parser and mobile validation run before challenge creation.
        Rate-limit and cache-policy exceptions are translated to stable HTTP errors.
        A successful response contains only the masked mobile number and delivery,
        TTL, resend, and length metadata; it never returns the OTP code or stored hash
        and does not authenticate a session.
        """
        try:
            payload = self._load_payload(request)
        except ApiOtpPayloadTooLarge:
            return api_error(
                "payload_too_large",
                "حجم درخواست بیش از حد مجاز است.",
                status=413,
            )
        except ApiOtpPayloadInvalid:
            return api_error(
                "invalid_payload",
                "ساختار درخواست معتبر نیست.",
                status=400,
            )

        mobile_number = payload.get("mobile_number")
        valid, normalized_mobile, error = validate_mobile_for_auth(mobile_number)
        if not valid:
            return api_error(
                "invalid_mobile_number",
                error or "شماره موبایل معتبر نیست.",
                status=400,
            )

        try:
            result = create_api_otp_request(
                mobile_number=normalized_mobile,
                request=request,
            )
        except ApiOtpRateLimited as exc:
            return api_error(
                "otp_rate_limited",
                "درخواست کد بیش از حد مجاز است. لطفاً کمی بعد دوباره تلاش کنید.",
                status=429,
                details={
                    "retry_after_seconds": exc.retry_after,
                    "scope": exc.scope,
                },
            )
        except ApiOtpRateLimitUnavailable:
            return api_error(
                "otp_rate_limit_unavailable",
                "در حال حاضر امکان درخواست کد وجود ندارد. لطفاً کمی بعد دوباره تلاش کنید.",
                status=503,
            )
        except ValueError as exc:
            return api_error(
                "invalid_mobile_number",
                user_error_message(exc, "شماره موبایل معتبر نیست."),
                status=400,
            )

        return api_success(
            {
                "accepted": True,
                "mobile_number": result.masked_mobile_number,
                "delivery": {
                    "channel": "sms",
                    "mode": result.mode,
                    "sent": result.sent,
                },
                "otp": {
                    "ttl_seconds": result.ttl_seconds,
                    "resend_seconds": result.resend_seconds,
                    "length": result.length,
                },
            }
        )


class ApiOtpVerifyAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def _load_payload(self, request):
        return _load_auth_json_object_payload(
            request,
            max_bytes=_auth_otp_payload_max_bytes(),
        )

    def _get_active_user_by_mobile(self, mobile_number: str):
        UserModel = get_user_model()
        return (
            UserModel.objects.filter(
                mobile_number=mobile_number,
                is_active=True,
            )
            .order_by("pk")
            .first()
        )

    def post(self, request, *args, **kwargs):
        """
        Verify an OTP and establish a session only after replay-safe success.
        
        The bounded shared parser, mobile validation, and non-empty code check run
        before ``verify_api_otp_code``. Verification errors are translated to stable
        API responses. Only after the challenge succeeds and its required cache delete
        completes does the view resolve an active user and call Django login; a missing user is
        not created automatically.
        """
        try:
            payload = self._load_payload(request)
        except ApiOtpPayloadTooLarge:
            return api_error(
                "payload_too_large",
                "حجم درخواست بیش از حد مجاز است.",
                status=413,
            )
        except ApiOtpPayloadInvalid:
            return api_error(
                "invalid_payload",
                "ساختار درخواست معتبر نیست.",
                status=400,
            )

        mobile_number = payload.get("mobile_number")
        code = str(payload.get("code") or "").strip()

        valid, normalized_mobile, error = validate_mobile_for_auth(mobile_number)
        if not valid:
            return api_error(
                "invalid_mobile_number",
                error or "شماره موبایل معتبر نیست.",
                status=400,
            )

        if not code:
            return api_error(
                "invalid_otp_code",
                "کد تایید الزامی است.",
                status=400,
            )

        try:
            verify_api_otp_code(
                mobile_number=normalized_mobile,
                code=code,
            )
        except ApiOtpNotFound:
            return api_error(
                "otp_not_found",
                "کد تایید معتبر یا فعالی برای این شماره وجود ندارد.",
                status=400,
            )
        except ApiOtpExpired:
            return api_error(
                "otp_expired",
                "کد تایید منقضی شده است.",
                status=400,
            )
        except ApiOtpInvalidCode as exc:
            return api_error(
                "invalid_otp_code",
                "کد تایید صحیح نیست.",
                status=400,
                details={
                    "attempts_remaining": exc.attempts_remaining,
                },
            )
        except ApiOtpMaxAttemptsExceeded:
            return api_error(
                "otp_max_attempts_exceeded",
                "تعداد تلاش‌ها بیش از حد مجاز است. لطفاً دوباره درخواست کد بدهید.",
                status=429,
            )
        except ApiOtpRateLimitUnavailable:
            return api_error(
                "otp_rate_limit_unavailable",
                "در حال حاضر امکان تایید کد وجود ندارد. لطفاً کمی بعد دوباره تلاش کنید.",
                status=503,
            )
        except ValueError as exc:
            return api_error(
                "invalid_mobile_number",
                user_error_message(exc, "شماره موبایل معتبر نیست."),
                status=400,
            )

        user = self._get_active_user_by_mobile(normalized_mobile)
        if user is None:
            return api_error(
                "auth_user_not_found",
                "کاربری با این شماره موبایل پیدا نشد.",
                status=404,
            )

        login(_django_request(request), user)

        return api_success(
            {
                "verified": True,
                "authenticated": True,
                "user": serialize_auth_user(user, include_private=True),
                "session": {
                    "type": "django_session",
                },
            }
        )


class ApiAuthLogoutAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        django_request = _django_request(request)
        was_authenticated = _session_is_authenticated(request)
        logout(django_request)

        return api_success(
            {
                "logged_out": True,
                "was_authenticated": was_authenticated,
                "session": {
                    "type": "django_session",
                    "active": False,
                },
            }
        )
