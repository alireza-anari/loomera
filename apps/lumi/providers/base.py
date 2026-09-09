from __future__ import annotations

from typing import Any, Protocol

from ..schemas.intents import StructuredIntent


class ModelProviderError(RuntimeError):
    pass



class ModelProvider(Protocol):
    """LLM interface. Providers receive tool metadata/results, never ORM objects."""

    @property
    def enabled(self) -> bool: ...

    def complete(self, messages: list[dict[str, Any]]) -> str: ...

    def extract_intent(
        self,
        *,
        message: str,
        context: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> StructuredIntent: ...
