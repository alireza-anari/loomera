from __future__ import annotations

from typing import Any

from ..context import LumiContext
from ..policy import ToolPolicy
from .base import ToolRegistry, ToolSpec


def _search(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    result = domain.get_availability(
        salon_id=int(arguments["salon_id"]),
        service_id=int(arguments["service_id"]),
        stylist_id=int(arguments["stylist_id"]) if arguments.get("stylist_id") else None,
        date=str(arguments.get("date") or ""),
        period=str(arguments.get("time_preference") or arguments.get("period") or ""),
        limit=int(arguments.get("limit") or 12),
    )
    # Keep the contract stable for the future LLM. The adapter can change while
    # the model continues to see a simple `options` array.
    return {"options": list(result.get("options") or [])}


def _prepare(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    result = domain.prepare_booking(context=context, arguments=arguments)
    if result.get("kind") == "booking_preview":
        return {
            "booking_preview": result.get("preview") or {},
            "payment_methods": result.get("payment_methods") or [],
            "checkout_url": result.get("checkout_url") or "",
            "confirmation_required": True,
            "execution_mode": "existing_checkout_handoff",
            "action_state": result.get("action_state") or {},
        }
    return result


def register_booking_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="search_booking_options",
            description="Search real bookable options. This tool never creates an order.",
            handler=_search,
            policy=ToolPolicy.read_public(),
            input_schema={
                "type": "object",
                "required": ["salon_id", "service_id"],
                "properties": {
                    "salon_id": {"type": "integer"},
                    "service_id": {"type": "integer"},
                    "stylist_id": {"type": ["integer", "null"]},
                    "date": {"type": "string"},
                    "time_preference": {"enum": ["", "morning", "noon", "evening", "night"]},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={"type": "object", "properties": {"options": {"type": "array"}}},
            category="booking",
            beta_priority="B",
        )
    )
    registry.register(
        ToolSpec(
            name="prepare_booking",
            description="Validate a selected option and build the existing checkout preview; never creates an Order.",
            handler=_prepare,
            policy=ToolPolicy(
                allowed_roles=frozenset({"customer", "admin"}),
                requires_auth=True,
                requires_confirmation=False,
                mutates_state=True,  # request session only
                writes_database=False,
                idempotent=False,
                beta_enabled=True,
            ),
            input_schema={
                "type": "object",
                "required": ["salon_id", "service_id", "stylist_id", "date", "time"],
                "properties": {
                    "salon_id": {"type": "integer"},
                    "service_id": {"type": "integer"},
                    "stylist_id": {"type": "integer"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "period": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "booking_preview": {"type": "object"},
                    "confirmation_required": {"const": True},
                    "execution_mode": {"const": "existing_checkout_handoff"},
                },
            },
            category="booking",
            beta_priority="D",
        )
    )
