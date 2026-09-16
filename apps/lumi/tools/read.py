from __future__ import annotations

from typing import Any

from ..context import LumiContext
from ..policy import ToolPolicy
from .base import ToolRegistry, ToolSpec


PUBLIC_ROLES = frozenset({"guest", "user", "customer", "stylist", "manager", "admin"})


def _profile(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    return domain.get_my_profile(context=context)


def _services(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    return domain.get_services(
        salon_id=arguments.get("salon_id"),
        query=str(arguments.get("query") or ""),
        limit=int(arguments.get("limit") or 20),
    )


def _price(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    return domain.get_service_price(
        salon_id=int(arguments["salon_id"]),
        service_id=int(arguments["service_id"]),
        stylist_id=int(arguments["stylist_id"]) if arguments.get("stylist_id") else None,
    )


def _contact(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    return domain.get_contact(salon_id=int(arguments["salon_id"]))


def _availability(context: LumiContext, arguments: dict[str, Any], domain: Any) -> dict[str, Any]:
    return domain.get_availability(
        salon_id=int(arguments["salon_id"]),
        service_id=int(arguments["service_id"]),
        stylist_id=int(arguments["stylist_id"]) if arguments.get("stylist_id") else None,
        date=str(arguments.get("date") or ""),
        period=str(arguments.get("period") or ""),
        limit=int(arguments.get("limit") or 18),
    )


def register_read_tools(registry: ToolRegistry) -> None:
    public_read = ToolPolicy(
        allowed_roles=PUBLIC_ROLES,
        requires_auth=False,
        requires_confirmation=False,
        mutates_state=False,
        writes_database=False,
        idempotent=True,
    )
    registry.register(
        ToolSpec(
            name="get_my_profile",
            description="Return the minimal identity/role profile Lumi is allowed to use.",
            handler=_profile,
            policy=ToolPolicy(
                allowed_roles=frozenset({"user", "customer", "stylist", "manager", "admin"}),
                requires_auth=True,
                requires_confirmation=False,
                mutates_state=False,
                writes_database=False,
                idempotent=True,
            ),
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}}},
            category="customer",
            beta_priority="A",
        )
    )
    registry.register(
        ToolSpec(
            name="get_services",
            description="List active platform or salon services without exposing Django model objects.",
            handler=_services,
            policy=public_read,
            input_schema={
                "type": "object",
                "properties": {
                    "salon_id": {"type": ["integer", "null"]},
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={"type": "object", "properties": {"services": {"type": "array"}}},
            category="salon",
            beta_priority="B",
        )
    )
    registry.register(
        ToolSpec(
            name="get_service_price",
            description="Resolve current bookable price range using Loomera booking truth and specialist overrides.",
            handler=_price,
            policy=public_read,
            input_schema={
                "type": "object",
                "required": ["salon_id", "service_id"],
                "properties": {
                    "salon_id": {"type": "integer"},
                    "service_id": {"type": "integer"},
                    "stylist_id": {"type": ["integer", "null"]},
                },
            },
            output_schema={"type": "object", "properties": {"min_price": {}, "max_price": {}, "prices": {"type": "array"}}},
            category="salon",
            beta_priority="B",
        )
    )
    registry.register(
        ToolSpec(
            name="get_contact",
            description="Return public salon contact information only.",
            handler=_contact,
            policy=public_read,
            input_schema={"type": "object", "required": ["salon_id"], "properties": {"salon_id": {"type": "integer"}}},
            output_schema={"type": "object", "properties": {"name": {}, "address": {}, "phone": {}}},
            category="salon",
            beta_priority="B",
        )
    )
    registry.register(
        ToolSpec(
            name="get_availability",
            description="Read actual bookable slots from Loomera's existing booking engine.",
            handler=_availability,
            policy=public_read,
            input_schema={
                "type": "object",
                "required": ["salon_id", "service_id"],
                "properties": {
                    "salon_id": {"type": "integer"},
                    "service_id": {"type": "integer"},
                    "stylist_id": {"type": ["integer", "null"]},
                    "date": {"type": "string"},
                    "period": {"enum": ["", "morning", "noon", "evening", "night"]},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={"type": "object", "properties": {"options": {"type": "array"}}},
            category="booking",
            beta_priority="B",
        )
    )
