from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionState(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass(slots=True)
class ActionProposal:
    tool_name: str
    target: str = ""
    effect: str = ""
    requires_confirmation: bool = False
    state: ActionState = ActionState.PROPOSED
    arguments: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def explain(self) -> dict[str, Any]:
        """Structured, user-displayable explanation before an important action."""
        return {
            "action": self.tool_name,
            "target": self.target,
            "effect": self.effect,
            "requires_confirmation": self.requires_confirmation,
            "state": self.state.value,
            "preview": dict(self.preview),
        }

    def confirm(self) -> None:
        if not self.requires_confirmation:
            self.state = ActionState.CONFIRMED
            return
        if self.state is not ActionState.PROPOSED:
            raise ValueError("Only proposed actions can be confirmed.")
        self.state = ActionState.CONFIRMED

    def mark_executed(self) -> None:
        if self.requires_confirmation and self.state is not ActionState.CONFIRMED:
            raise ValueError("Confirmed state is required before execution.")
        self.state = ActionState.EXECUTED
        self.error = ""

    def mark_failed(self, error: str) -> None:
        self.state = ActionState.FAILED
        self.error = str(error or "")[:500]
