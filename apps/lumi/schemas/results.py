from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolResult:
    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error: str = ""

    @classmethod
    def success(cls, tool: str, data: dict[str, Any] | None = None) -> "ToolResult":
        return cls(ok=True, tool=tool, data=dict(data or {}))

    @classmethod
    def failure(cls, tool: str, *, code: str, error: str) -> "ToolResult":
        return cls(ok=False, tool=tool, error_code=str(code or "tool_error"), error=str(error or ""))

    def as_dict(self) -> dict[str, Any]:
        payload = {"ok": self.ok, "tool": self.tool}
        if self.ok:
            payload["data"] = self.data
        else:
            payload.update({"error_code": self.error_code, "error": self.error})
        return payload
