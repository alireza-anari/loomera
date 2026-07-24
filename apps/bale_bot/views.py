from __future__ import annotations

import json
from hmac import compare_digest

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .constants import BALE_WEBHOOK_PROVIDER_SECRET_HEADER, BALE_WEBHOOK_SECRET_HEADER
from .services import (
    BaleWebhookDisabled,
    record_bale_webhook_update,
    sanitize_webhook_headers,
)


def _configured_webhook_secret() -> str:
    return str(getattr(settings, "BALE_WEBHOOK_SECRET", "") or "").strip()


def _provided_webhook_secret(request: HttpRequest) -> str:
    header_secret = str(request.META.get(BALE_WEBHOOK_SECRET_HEADER) or "").strip()
    if header_secret:
        return header_secret

    provider_secret = str(
        request.META.get(BALE_WEBHOOK_PROVIDER_SECRET_HEADER) or ""
    ).strip()
    if provider_secret:
        return provider_secret

    if bool(getattr(settings, "BALE_WEBHOOK_ALLOW_QUERY_SECRET", False)):
        return str(request.GET.get("secret") or "").strip()

    return ""


def _webhook_secret_required() -> bool:
    return bool(getattr(settings, "BALE_WEBHOOK_REQUIRE_SECRET", True))


def _json_error(message: str, *, status: int) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


@method_decorator(csrf_exempt, name="dispatch")
class BaleWebhookView(View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Accept one authenticated and bounded Bale webhook payload.
        
        Feature flags are checked before parsing. When a secret is configured it is
        compared with ``compare_digest``; required-but-missing configuration is a
        service error. The raw body size is enforced before UTF-8 JSON decoding, and
        only a JSON object is accepted. The view delegates idempotent storage and
        dispatch to ``record_bale_webhook_update``. Provider-facing failures use stable
        error codes and do not expose internal exception text. A duplicate response
        means the update was already stored and is not dispatched again.
        """
        if not bool(getattr(settings, "MESSAGING_ENABLED", False)) or not bool(
            getattr(settings, "BALE_BOT_ENABLED", False)
        ):
            return _json_error("bale_webhook_disabled", status=404)

        configured_secret = _configured_webhook_secret()
        if _webhook_secret_required() and not configured_secret:
            return _json_error("webhook_secret_not_configured", status=503)

        if configured_secret:
            provided_secret = _provided_webhook_secret(request)
            if not provided_secret or not compare_digest(
                provided_secret, configured_secret
            ):
                return _json_error("invalid_webhook_secret", status=403)

        max_bytes = int(getattr(settings, "BALE_WEBHOOK_MAX_BYTES", 256 * 1024))
        if len(request.body or b"") > max_bytes:
            return _json_error("payload_too_large", status=413)

        try:
            payload = json.loads((request.body or b"{}").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_error("invalid_json", status=400)

        if not isinstance(payload, dict):
            return _json_error("invalid_payload", status=400)

        try:
            result = record_bale_webhook_update(
                payload=payload,
                headers=sanitize_webhook_headers(request.META),
                base_url=request.build_absolute_uri("/"),
            )
        except BaleWebhookDisabled as exc:
            return _json_error(str(exc), status=404)
        except Exception as exc:
            # Do not expose internals to provider; stage 2 has no action side effects.
            return _json_error("webhook_record_failed", status=500)

        return JsonResponse(
            {
                "ok": True,
                "stored": bool(result["created"]),
                "duplicate": bool(result["duplicate"]),
            }
        )
