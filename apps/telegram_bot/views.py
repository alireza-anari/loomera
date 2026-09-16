from __future__ import annotations

import json
from hmac import compare_digest
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from .services import TelegramWebhookDisabled, record_telegram_webhook_update, sanitize_webhook_headers

TELEGRAM_SECRET_HEADER = "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"


def _json_error(message, *, status):
    return JsonResponse({"ok": False, "error": message}, status=status)


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, *args, **kwargs):
        if not bool(getattr(settings, "MESSAGING_ENABLED", False)) or not bool(
            getattr(settings, "TELEGRAM_BOT_ENABLED", False)
        ):
            return _json_error("telegram_webhook_disabled", status=404)
        configured_secret = str(getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
        if not configured_secret:
            return _json_error("webhook_secret_not_configured", status=503)
        provided_secret = str(request.META.get(TELEGRAM_SECRET_HEADER) or "").strip()
        if not provided_secret or not compare_digest(provided_secret, configured_secret):
            return _json_error("invalid_webhook_secret", status=403)
        max_bytes = int(getattr(settings, "TELEGRAM_WEBHOOK_MAX_BYTES", 256 * 1024))
        if len(request.body or b"") > max_bytes:
            return _json_error("payload_too_large", status=413)
        try:
            payload = json.loads((request.body or b"{}").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_error("invalid_json", status=400)
        if not isinstance(payload, dict):
            return _json_error("invalid_payload", status=400)
        update_id = payload.get("update_id")
        if isinstance(update_id, bool) or not isinstance(update_id, int):
            return _json_error("invalid_update_id", status=400)
        try:
            result = record_telegram_webhook_update(
                payload=payload, headers=sanitize_webhook_headers(request.META),
                base_url=request.build_absolute_uri("/"),
            )
        except TelegramWebhookDisabled as exc:
            return _json_error(str(exc), status=404)
        except Exception:
            return _json_error("webhook_record_failed", status=500)
        return JsonResponse({
            "ok": True, "stored": bool(result["created"]),
            "duplicate": bool(result["duplicate"]),
        })
