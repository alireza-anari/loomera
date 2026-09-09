from __future__ import annotations

from typing import Any

from .context import LumiContext
from .schemas.results import ToolResult
from .tools import ToolRegistry, build_default_registry


class LumiOrchestrator:
    """Small orchestration boundary for Phase A/B.

    It deliberately does *not* auto-execute model-selected actions yet. A later
    phase may plug a free LLM into `providers.ModelProvider` for intent/entity
    extraction while keeping this tool/policy boundary unchanged.
    """

    def __init__(self, *, registry: ToolRegistry | None = None, model: Any = None):
        self.registry = registry or build_default_registry()
        self.model = model

    def available_tools(self, context: LumiContext) -> list[dict[str, Any]]:
        return self.registry.list_for_context(context)

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
