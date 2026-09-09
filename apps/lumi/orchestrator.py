from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from .context import LumiContext
from .providers.base import ModelProviderError
from .schemas.results import ToolResult
from .tools import ToolRegistry, build_default_registry


DEFAULT_MODEL_ROUTABLE_TOOLS = frozenset(
    {
        "get_services",
        "get_service_price",
        "get_contact",
        "get_availability",
        "search_booking_options",
    }
)

_PERIOD_ALIASES = {
    "": "",
    "morning": "morning",
    "صبح": "morning",
    "noon": "noon",
    "ظهر": "noon",
    "ظهرها": "noon",
    "evening": "evening",
    "عصر": "evening",
    "عصرها": "evening",
    "night": "night",
    "شب": "night",
    "شبها": "night",
    "شب‌ها": "night",
}


class LumiOrchestrator:
    """Policy-first orchestration boundary.

    Phase C lets an LLM *suggest* one read/search intent. The orchestrator then
    enriches authoritative scope IDs, resolves service names through Loomera,
    normalizes date/period entities and finally sends the request through the
    normal ToolRegistry policy/validation path. Model failure returns ``None`` so
    callers can preserve their deterministic legacy fallback unchanged.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        model: Any = None,
        model_allowed_tools: Iterable[str] | None = None,
        min_confidence: float = 0.65,
    ):
        self.registry = registry or build_default_registry()
        self.model = model
        self.model_allowed_tools = frozenset(model_allowed_tools or DEFAULT_MODEL_ROUTABLE_TOOLS)
        self.min_confidence = max(0.0, min(float(min_confidence), 1.0))

    def available_tools(self, context: LumiContext) -> list[dict[str, Any]]:
        return self.registry.list_for_context(context)

    def model_tools(self, context: LumiContext) -> list[dict[str, Any]]:
        return [
            item
            for item in self.available_tools(context)
            if item.get("name") in self.model_allowed_tools
            and not bool((item.get("policy") or {}).get("writes_database"))
            and not bool((item.get("policy") or {}).get("requires_confirmation"))
        ]

    def execute_tool(
        self,
        *,
        context: LumiContext,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        confirmed: bool = False,
    ) -> ToolResult:
        return self.registry.execute(
            name=tool_name,
            context=context,
            arguments=arguments,
            confirmed=confirmed,
        )

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            parsed = int(str(value or "").strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _reference_date(context: LumiContext) -> date:
        raw = str((context.metadata or {}).get("reference_date") or "").strip()
        if raw:
            try:
                return date.fromisoformat(raw)
            except ValueError:
                pass
        return date.today()

    @classmethod
    def _normalize_date(cls, value: Any, *, context: LumiContext) -> str:
        raw = str(value or "").strip().lower().replace("‌", " ")
        if not raw:
            return ""
        today = cls._reference_date(context)
        aliases = {
            "today": today,
            "امروز": today,
            "tomorrow": today + timedelta(days=1),
            "فردا": today + timedelta(days=1),
            "day_after_tomorrow": today + timedelta(days=2),
            "day after tomorrow": today + timedelta(days=2),
            "پس فردا": today + timedelta(days=2),
        }
        if raw in aliases:
            return aliases[raw].isoformat()
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            return ""
        return parsed.isoformat() if parsed >= today else ""

    @staticmethod
    def _normalize_period(value: Any) -> str:
        raw = str(value or "").strip().lower().replace("‌", "")
        return _PERIOD_ALIASES.get(raw, "")

    @staticmethod
    def _service_query(arguments: dict[str, Any]) -> str:
        for key in ("service_query", "service", "service_name", "query"):
            value = str(arguments.get(key) or "").strip()
            if value:
                return value[:160]
        return ""

    def _resolve_service(
        self,
        *,
        context: LumiContext,
        salon_id: int,
        arguments: dict[str, Any],
        tool_name: str,
    ) -> tuple[int | None, ToolResult | None]:
        explicit = self._positive_int(arguments.get("service_id"))
        # Model-supplied IDs are deliberately ignored unless the caller explicitly
        # marks them as trusted backend arguments. Messaging Phase C never does.
        if explicit and bool(arguments.get("_trusted_service_id")):
            return explicit, None

        query = self._service_query(arguments)
        if not query:
            return None, ToolResult.success(
                tool_name,
                {
                    "needs_clarification": True,
                    "reason": "service_required",
                    "services": [],
                },
            )
        lookup = self.execute_tool(
            context=context,
            tool_name="get_services",
            arguments={"salon_id": salon_id, "query": query, "limit": 6},
        )
        if not lookup.ok:
            return None, lookup
        services = list((lookup.data or {}).get("services") or [])
        if len(services) == 1:
            return self._positive_int(services[0].get("id")), None
        if not services:
            return None, ToolResult.success(
                tool_name,
                {
                    "not_found": True,
                    "reason": "service_not_found",
                    "service_query": query,
                    "services": [],
                },
            )
        return None, ToolResult.success(
            tool_name,
            {
                "needs_clarification": True,
                "reason": "service_ambiguous",
                "service_query": query,
                "services": services[:6],
            },
        )

    def _authoritative_arguments(
        self,
        *,
        context: LumiContext,
        tool_name: str,
        suggested: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, ToolResult | None]:
        args = dict(suggested or {})
        salon_id = self._positive_int((context.metadata or {}).get("salon_id"))

        if tool_name in {
            "get_services",
            "get_service_price",
            "get_contact",
            "get_availability",
            "search_booking_options",
        }:
            if salon_id is None:
                return None, None
            args["salon_id"] = salon_id

        if tool_name == "get_services":
            return {
                "salon_id": salon_id,
                "query": self._service_query(args),
                "limit": 12,
            }, None

        if tool_name == "get_contact":
            return {"salon_id": salon_id}, None

        if tool_name in {"get_service_price", "get_availability", "search_booking_options"}:
            service_id, resolution = self._resolve_service(
                context=context,
                salon_id=int(salon_id),
                arguments=args,
                tool_name=tool_name,
            )
            if resolution is not None:
                return None, resolution
            if service_id is None:
                return None, None
            clean: dict[str, Any] = {
                "salon_id": salon_id,
                "service_id": service_id,
            }
            # Stylist IDs are not accepted from the model in Phase C. Searching
            # all currently eligible specialists is safer than guessing identity.
            date_value = self._normalize_date(args.get("date"), context=context)
            period_value = self._normalize_period(
                args.get("time_preference") or args.get("period")
            )
            if date_value:
                clean["date"] = date_value
            if tool_name == "search_booking_options":
                clean["time_preference"] = period_value
                clean["limit"] = 8
            elif tool_name == "get_availability":
                clean["period"] = period_value
                clean["limit"] = 8
            return clean, None

        return None, None

    def route_message(self, *, context: LumiContext, message: str) -> ToolResult | None:
        if self.model is None or not bool(getattr(self.model, "enabled", False)):
            return None
        tools = self.model_tools(context)
        if not tools:
            return None
        try:
            intent = self.model.extract_intent(
                message=str(message or "")[:1200],
                context=context.model_dict(),
                tools=tools,
            )
        except ModelProviderError:
            return None
        except Exception:
            # An optional model must never break the legacy assistant path.
            return None

        tool_name = str(getattr(intent, "intent", "") or "").strip()
        if not tool_name or tool_name == "fallback" or tool_name not in self.model_allowed_tools:
            return None
        if tool_name not in {item.get("name") for item in tools}:
            return None
        confidence = getattr(intent, "confidence", None)
        if confidence is not None and float(confidence) < self.min_confidence:
            return None
        suggested = getattr(intent, "arguments", {}) or {}
        if not isinstance(suggested, dict):
            return None

        arguments, resolution = self._authoritative_arguments(
            context=context,
            tool_name=tool_name,
            suggested=suggested,
        )
        if resolution is not None:
            return resolution
        if arguments is None:
            return None
        return self.execute_tool(
            context=context,
            tool_name=tool_name,
            arguments=arguments,
            confirmed=False,
        )
