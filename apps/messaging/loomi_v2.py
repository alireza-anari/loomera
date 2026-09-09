from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.lumi.context import build_lumi_context
from apps.lumi.orchestrator import DEFAULT_MODEL_ROUTABLE_TOOLS, LumiOrchestrator
from apps.lumi.providers import HelpCenterIntentProvider
from apps.lumi.schemas.results import ToolResult


logger = logging.getLogger(__name__)
_PROVIDER_COOLDOWN_KEY = "loomera:loomi-v2:intent-provider-cooldown:v1"
_PROVIDER_FAILURE_KINDS = {
    "provider_network",
    "provider_unavailable",
    "provider_upstream",
    "provider_rate_limited",
    "provider_auth",
    "provider_invalid_response",
}


def _format_price(value: Any) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,} تومان" if amount > 0 else "قیمت ثبت نشده"


def _render_services(data: dict[str, Any]) -> str:
    services = list(data.get("services") or [])
    if not services:
        return "فعلاً خدمت فعالی با این مشخصات پیدا نکردم."
    lines = [f"• {str(item.get('name') or '').strip()}" for item in services[:8] if str(item.get("name") or "").strip()]
    if not lines:
        return "فعلاً خدمت فعالی با این مشخصات پیدا نکردم."
    suffix = "\n\nاگر اسم یکی از خدمات رو بگی، قیمت یا زمان آزادش رو دقیق‌تر بررسی می‌کنم." if len(lines) > 1 else ""
    return "خدمات فعال ثبت‌شده:\n" + "\n".join(lines) + suffix


def _render_price(data: dict[str, Any]) -> str:
    if data.get("not_found"):
        query = str(data.get("service_query") or "خدمت موردنظر").strip()
        return f"برای «{query}» خدمت فعالی در این مجموعه پیدا نکردم."
    if data.get("needs_clarification"):
        return _render_service_clarification(data)
    name = str(data.get("service_name") or "این خدمت").strip()
    low = data.get("min_price")
    high = data.get("max_price")
    if low is None and high is None:
        return f"برای «{name}» فعلاً قیمت قابل رزروی ثبت نشده."
    if low == high:
        return f"قیمت فعلی «{name}»: {_format_price(low)}"
    return f"بازه قیمت فعلی «{name}»: از {_format_price(low)} تا {_format_price(high)}"


def _render_contact(data: dict[str, Any]) -> str:
    lines = []
    name = str(data.get("name") or "").strip()
    address = str(data.get("address") or "").strip()
    phone = str(data.get("phone") or "").strip()
    if name:
        lines.append(f"مجموعه: {name}")
    if address:
        lines.append(f"آدرس: {address}")
    if phone:
        lines.append(f"تماس: {phone}")
    if len(lines) <= 1:
        lines.append("آدرس یا شماره تماس عمومی هنوز ثبت نشده.")
    return "\n".join(lines)


def _render_service_clarification(data: dict[str, Any]) -> str:
    services = list(data.get("services") or [])
    if not services:
        return "اسم خدمتی که مدنظرت هست رو بفرست تا دقیق بررسی کنم."
    names = [str(item.get("name") or "").strip() for item in services[:6]]
    names = [name for name in names if name]
    if not names:
        return "اسم خدمتی که مدنظرت هست رو بفرست تا دقیق بررسی کنم."
    return "چند خدمت نزدیک پیدا کردم. کدوم مدنظرته؟\n" + "\n".join(f"• {name}" for name in names)


def _render_availability(data: dict[str, Any]) -> str:
    if data.get("not_found"):
        query = str(data.get("service_query") or "خدمت موردنظر").strip()
        return f"برای «{query}» خدمت قابل رزروی در این مجموعه پیدا نکردم."
    if data.get("needs_clarification"):
        return _render_service_clarification(data)
    options = list(data.get("options") or [])
    service_name = str(data.get("service_name") or "این خدمت").strip()
    if not options:
        return f"برای «{service_name}» در بازه‌ای که گفتی زمان آزادی پیدا نکردم."
    lines = []
    for option in options[:5]:
        date_label = str(option.get("date_label") or option.get("date") or "").strip()
        time_label = str(option.get("time") or option.get("start_time") or "").strip()
        stylist = str(option.get("stylist_name") or "").strip()
        price = option.get("price")
        parts = [part for part in (date_label, time_label) if part]
        line = "، ".join(parts)
        if stylist:
            line += f" — {stylist}"
        if price:
            line += f" — {_format_price(price)}"
        if line:
            lines.append(f"• {line}")
    if not lines:
        return f"برای «{service_name}» زمان آزادی پیدا کردم، اما جزئیات قابل نمایش نیست؛ از مسیر رزرو مجموعه بررسی کن."
    return (
        f"زمان‌های آزاد واقعی برای «{service_name}»:\n\n"
        + "\n".join(lines)
        + "\n\nبرای رزرو نهایی از مسیر لومرا ادامه بده."
    )


def render_tool_result(result: ToolResult) -> str | None:
    if not result.ok:
        return None
    data = result.data or {}
    if result.tool == "get_services":
        return _render_services(data)
    if result.tool == "get_service_price":
        return _render_price(data)
    if result.tool == "get_contact":
        return _render_contact(data)
    if result.tool in {"get_availability", "search_booking_options"}:
        return _render_availability(data)
    return None


def _intent_provider_factory():
    """Reuse the configured Help AI provider with a shorter Lumi intent timeout."""
    from apps.help_center.ai import get_ai_provider

    provider = get_ai_provider()
    requested = max(
        3,
        int(getattr(settings, "LOOMI_V2_INTENT_TIMEOUT_SECONDS", 6) or 6),
    )
    try:
        current = max(3, int(getattr(provider, "timeout", requested) or requested))
        provider.timeout = min(current, requested)
    except Exception:
        # Disabled/custom providers do not have to expose a writable timeout.
        pass
    return provider


def _provider_cooldown_active() -> bool:
    try:
        return bool(cache.get(_PROVIDER_COOLDOWN_KEY))
    except Exception:
        # Cache failure must never disable Lumi's deterministic fallback.
        return False


def _mark_provider_cooldown(error_kind: str | None) -> None:
    if error_kind not in _PROVIDER_FAILURE_KINDS:
        return
    seconds = max(
        0,
        int(getattr(settings, "LOOMI_V2_PROVIDER_COOLDOWN_SECONDS", 60) or 60),
    )
    if not seconds:
        return
    try:
        cache.set(_PROVIDER_COOLDOWN_KEY, str(error_kind), timeout=seconds)
    except Exception:
        logger.debug("Lumi v2 provider cooldown cache unavailable", exc_info=True)


def try_answer_with_lumi_v2(
    *,
    conversation_context: Any,
    target: Any,
    user: Any,
    provider: Any,
    question: str,
    reply_markup: dict | None,
) -> dict[str, Any] | None:
    """Try semantic read/search routing without weakening Loomera authority.

    The LLM is optional.  Any provider, parse, confidence or tool failure returns
    ``None`` so the caller can continue through Loomi's deterministic path.  A
    short provider cooldown prevents every message from paying a network timeout
    while the upstream is unavailable.
    """
    del target  # Authoritative scope comes from the stored conversation context.

    if not bool(getattr(settings, "LOOMI_V2_INTENT_ENABLED", False)):
        return None
    if str(getattr(conversation_context, "scope_type", "") or "") != "salon":
        return None
    if _provider_cooldown_active():
        return None
    try:
        salon_id = int(getattr(conversation_context, "scope_object_id", 0) or 0)
    except (TypeError, ValueError):
        return None
    if salon_id <= 0:
        return None

    provider_key = str(getattr(provider, "key", provider) or "messaging").strip().lower()
    lumi_context = build_lumi_context(
        user=user,
        channel=provider_key,
        metadata={
            "scope_type": "salon",
            "salon_id": salon_id,
            "reference_date": timezone.localdate().isoformat(),
        },
    )
    model = HelpCenterIntentProvider(
        enabled=True,
        provider_factory=_intent_provider_factory,
    )
    orchestrator = LumiOrchestrator(
        model=model,
        model_allowed_tools=DEFAULT_MODEL_ROUTABLE_TOOLS,
        min_confidence=float(getattr(settings, "LOOMI_V2_INTENT_MIN_CONFIDENCE", 0.65) or 0.65),
    )
    result = orchestrator.route_message(context=lumi_context, message=question)
    if result is None:
        _mark_provider_cooldown(model.last_error_kind)
        if model.last_error_kind in _PROVIDER_FAILURE_KINDS:
            logger.warning(
                "Lumi v2 intent provider unavailable; using deterministic fallback | kind=%s",
                model.last_error_kind,
            )
        return None
    text = render_tool_result(result)
    if not text:
        return None
    return {"text": text[:3500], "reply_markup": reply_markup}
