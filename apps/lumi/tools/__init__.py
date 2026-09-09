from __future__ import annotations

from typing import Any

from ..domain import StagingLoomeraGateway
from .base import ToolRegistry, ToolSpec
from .booking import register_booking_tools
from .read import register_read_tools


def build_default_registry(*, domain: Any | None = None) -> ToolRegistry:
    registry = ToolRegistry(domain=domain or StagingLoomeraGateway())
    register_read_tools(registry)
    register_booking_tools(registry)
    return registry


__all__ = ["ToolRegistry", "ToolSpec", "build_default_registry"]
