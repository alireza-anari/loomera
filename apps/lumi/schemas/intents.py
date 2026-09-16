from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StructuredIntent:
    """Provider-neutral intent envelope.

    The model can suggest only a tool name + JSON arguments. It cannot grant
    authorization, confirmation, or database authority through this object.
    """

    intent: str
    arguments: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
