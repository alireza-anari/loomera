from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .actions import (
    is_customer_discovery_candidate,
    run_customer_booking_action,
    run_customer_discovery,
)


def _consume_action_limit(request) -> bool:
    limit = max(int(getattr(settings, "HELP_ACTION_USER_LIMIT", 80) or 80), 1)
    if not getattr(request.user, "is_authenticated", False):
        limit = max(int(getattr(settings, "HELP_ACTION_GUEST_LIMIT", 30) or 30), 1)
    window = max(int(getattr(settings, "HELP_ACTION_RATE_WINDOW_SECONDS", 3600) or 3600), 60)
    if getattr(request.user, "is_authenticated", False):
        identity = f"user:{request.user.pk}"
    else:
        raw_ip = request.META.get("REMOTE_ADDR", "") or "unknown"
        identity = "guest:" + hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()[:20]
    key = f"loomera:lumi-action:{identity}"
    try:
        count = int(cache.get(key, 0) or 0)
        if count >= limit:
            return False
        if count == 0:
            cache.set(key, 1, timeout=window)
        else:
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=window)
        return True
    except Exception:
        return True


@require_POST
def customer_discovery_api(request):
    if len(request.body or b"") > 16 * 1024:
        return JsonResponse({"error": "درخواست بیش از حد بزرگ است."}, status=413)

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    message = str(payload.get("message") or "").strip()
    if not message or len(message) > 1200:
        return JsonResponse({"error": "پیام معتبر نیست."}, status=400)

    action_state = payload.get("action_state") if isinstance(payload.get("action_state"), dict) else None
    if not is_customer_discovery_candidate(message, action_state):
        return JsonResponse({"handled": False})

    if not _consume_action_limit(request):
        return JsonResponse(
            {"error": "تعداد جستجوهای این بازه به حد مجاز رسیده. کمی بعد دوباره امتحان کن."},
            status=429,
        )

    result = run_customer_discovery(
        message,
        state=action_state,
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
    )
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})


@require_POST
def customer_booking_api(request):
    if len(request.body or b"") > 16 * 1024:
        return JsonResponse({"error": "درخواست بیش از حد بزرگ است."}, status=413)

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    action = str(payload.get("action") or "").strip()
    if action not in {"select_salon", "select_stylist", "relax_slots", "select_slot", "cancel"}:
        return JsonResponse({"error": "عملیات رزرو معتبر نیست."}, status=400)

    if not _consume_action_limit(request):
        return JsonResponse(
            {"error": "تعداد عملیات این بازه به حد مجاز رسیده. کمی بعد دوباره امتحان کن."},
            status=429,
        )

    try:
        result = run_customer_booking_action(request, payload)
    except Exception as exc:
        from django.core.exceptions import ValidationError

        if isinstance(exc, ValidationError):
            messages = getattr(exc, "messages", None) or [str(exc)]
            return JsonResponse({"error": messages[0]}, status=400, json_dumps_params={"ensure_ascii": False})
        raise
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})
