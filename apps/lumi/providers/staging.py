from __future__ import annotations

import json
import re
from typing import Any, Callable

from .base import ModelProviderError
from ..schemas.intents import StructuredIntent


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class HelpCenterIntentProvider:
    """Adapter over Loomera's existing Help Center AI provider.

    The provider is deliberately limited to intent/entity extraction.  It never
    receives ORM objects or authoritative Loomera IDs and never executes tools.

    ``last_error_kind`` is intentionally coarse.  It lets the messaging
    integration distinguish an unavailable upstream from an ordinary model
    fallback without exposing HTTP bodies, API keys or provider internals to
    ``apps.lumi`` or the end user.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        provider_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._enabled_flag = bool(enabled)
        self._provider_factory = provider_factory
        self.last_error_kind: str | None = None

    def _provider(self):
        if self._provider_factory is not None:
            return self._provider_factory()
        from apps.help_center.ai import get_ai_provider

        return get_ai_provider()

    @property
    def enabled(self) -> bool:
        if not self._enabled_flag:
            return False
        try:
            return bool(getattr(self._provider(), "enabled", False))
        except Exception:
            self.last_error_kind = "provider_unavailable"
            return False

    @staticmethod
    def _parse_json_object(raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            raise ModelProviderError("Empty intent response.")
        text = _JSON_FENCE_RE.sub("", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ModelProviderError("Intent response is not a JSON object.")
        try:
            value = json.loads(text[start : end + 1])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelProviderError("Malformed intent JSON.") from exc
        if not isinstance(value, dict):
            raise ModelProviderError("Intent response must be a JSON object.")
        return value

    @staticmethod
    def _safe_tool_metadata(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        safe = []
        for item in tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            safe.append(
                {
                    "name": name,
                    "description": str(item.get("description") or "")[:500],
                    "input_schema": item.get("input_schema") or {},
                }
            )
        return safe

    @staticmethod
    def _classify_provider_error(exc: Exception) -> str:
        """Return a non-sensitive failure class for circuit-breaker decisions."""
        status = getattr(exc, "status", None)
        if status in {401, 403}:
            return "provider_auth"
        if status == 429:
            return "provider_rate_limited"
        if isinstance(status, int) and status >= 500:
            return "provider_upstream"

        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            name = type(current).__name__.lower()
            if "timeout" in name:
                return "provider_network"
            if "urlerror" in name or "connection" in name or "disconnect" in name:
                return "provider_network"
            reason = getattr(current, "reason", None)
            if isinstance(reason, BaseException):
                current = reason
                continue
            current = current.__cause__ or current.__context__
        return "provider_unavailable"

    def complete(self, messages: list[dict[str, Any]]) -> str:
        self.last_error_kind = None
        provider = self._provider()
        if not self._enabled_flag or not getattr(provider, "enabled", False):
            self.last_error_kind = "provider_disabled"
            raise ModelProviderError("Intent provider is disabled.")
        try:
            return str(provider.complete(messages) or "")
        except Exception as exc:
            self.last_error_kind = self._classify_provider_error(exc)
            # Do not leak provider HTTP details/API metadata across the Lumi port.
            raise ModelProviderError("Intent provider request failed.") from exc

    def extract_intent(
        self,
        *,
        message: str,
        context: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> StructuredIntent:
        self.last_error_kind = None
        tool_rows = self._safe_tool_metadata(tools)
        allowed_names = {item["name"] for item in tool_rows}
        if not allowed_names:
            raise ModelProviderError("No model-routable tools are available.")

        system = (
            "تو فقط intent router لومی هستی، نه پاسخ‌گوی کاربر. "
            "فقط یک JSON object معتبر خروجی بده و هیچ متن دیگری ننویس. "
            "فقط یکی از نام ابزارهای مجاز یا fallback را انتخاب کن. "
            "هرگز عملیات حساس، نوشتن در دیتابیس، لغو، refund، پرداخت، تغییر حساب یا confirm را پیشنهاد نده. "
            "شناسه salon/service/stylist را حدس نزن؛ شناسه‌های authoritative توسط backend اضافه می‌شوند. "
            "برای نام خدمت از service_query استفاده کن. عبارت محاوره‌ای را به کوتاه‌ترین نام خدمت قابل جستجو تبدیل کن؛ "
            "مثلاً «موهامو رنگ کنم» را service_query='رنگ مو' و «کوتاهی میخوام» را service_query='کوتاهی' در نظر بگیر. "
            "برای تاریخ می‌توانی date را به شکل ISO یا یکی از today/tomorrow/day_after_tomorrow/"
            "امروز/فردا/پس فردا بدهی. برای بازه زمانی از time_preference با morning/noon/evening/night "
            "یا معادل فارسی استفاده کن. "
            "سؤال درباره قیمت/هزینه یک خدمت = get_service_price. "
            "سؤال درباره وقت، جا، تایم، ساعت آزاد یا امکان انجام خدمت در تاریخ/بازه = get_availability. "
            "سؤال درباره آدرس/شماره/راه رسیدن = get_contact. سؤال درباره فهرست خدمات = get_services. "
            "اگر مطمئن نیستی intent=fallback بده. "
            "ساختار خروجی: "
            '{"intent":"tool-or-fallback","arguments":{},"confidence":0.0}'
        )
        payload = {
            "context": context,
            "available_tools": tool_rows,
            "user_message": str(message or "")[:1200],
        }
        raw = self.complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )
        try:
            value = self._parse_json_object(raw)
        except ModelProviderError:
            self.last_error_kind = "provider_invalid_response"
            raise
        intent = str(value.get("intent") or "").strip()
        arguments = value.get("arguments") or {}
        if not isinstance(arguments, dict):
            self.last_error_kind = "provider_invalid_response"
            raise ModelProviderError("Intent arguments must be a JSON object.")
        if intent != "fallback" and intent not in allowed_names:
            # Unknown/hallucinated tools never cross into the registry.
            return StructuredIntent(intent="fallback", arguments={}, confidence=0.0)

        confidence = value.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None:
            confidence = max(0.0, min(confidence, 1.0))

        return StructuredIntent(
            intent=intent or "fallback",
            arguments=dict(arguments),
            confidence=confidence,
        )
