from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Callable

from ..context import LumiContext
from ..policy import ToolPolicy, ToolPolicyError
from ..schemas.results import ToolResult


logger = logging.getLogger(__name__)


ToolHandler = Callable[[LumiContext, dict[str, Any], Any], dict[str, Any]]


class ToolValidationError(ValueError):
    code = "invalid_arguments"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    policy: ToolPolicy
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    category: str = "read"
    beta_priority: str = "A"

    def public_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "beta_priority": self.beta_priority,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "policy": {
                "allowed_roles": sorted(self.policy.allowed_roles),
                "requires_auth": self.policy.requires_auth,
                "requires_confirmation": self.policy.requires_confirmation,
                "mutates_state": self.policy.mutates_state,
                "writes_database": self.policy.writes_database,
                "idempotent": self.policy.idempotent,
                "beta_enabled": self.policy.beta_enabled,
            },
        }


class ToolRegistry:
    def __init__(self, *, domain: Any):
        self.domain = domain
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        name = str(spec.name or "").strip()
        if not name:
            raise ValueError("Tool name is required.")
        if name in self._tools:
            raise ValueError(f"Duplicate tool: {name}")
        self._tools[name] = spec
        return spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[str(name)]
        except KeyError as exc:
            raise KeyError(f"Unknown Lumi tool: {name}") from exc

    def list_for_context(self, context: LumiContext) -> list[dict[str, Any]]:
        rows = []
        for spec in self._tools.values():
            try:
                # Confirmation is intentionally ignored when merely advertising
                # capabilities. It is enforced at execution time.
                spec.policy.check(context, confirmed=spec.policy.requires_confirmation)
            except ToolPolicyError:
                continue
            rows.append(spec.public_metadata())
        return sorted(rows, key=lambda item: item["name"])

    @staticmethod
    def _validate(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolValidationError("ورودی ابزار باید یک JSON object باشد.")
        required = schema.get("required") or []
        missing = [key for key in required if arguments.get(key) in (None, "")]
        if missing:
            raise ToolValidationError(f"ورودی‌های الزامی ناقص‌اند: {', '.join(missing)}")

        python_types = {"integer": int, "number": (int, float), "string": str, "boolean": bool, "object": dict, "array": list}
        for key, prop in (schema.get("properties") or {}).items():
            if key not in arguments or arguments[key] is None:
                continue
            value = arguments[key]
            allowed = prop.get("type")
            allowed_types = allowed if isinstance(allowed, list) else [allowed] if allowed else []
            allowed_types = [item for item in allowed_types if item != "null"]
            def _matches(type_name: str) -> bool:
                if type_name == "integer":
                    return isinstance(value, int) and not isinstance(value, bool)
                if type_name == "number":
                    return isinstance(value, (int, float)) and not isinstance(value, bool)
                expected = python_types.get(type_name)
                return bool(expected) and isinstance(value, expected)

            if allowed_types and not any(_matches(item) for item in allowed_types):
                raise ToolValidationError(f"نوع ورودی «{key}» معتبر نیست.")
            if "enum" in prop and value not in prop["enum"]:
                raise ToolValidationError(f"مقدار ورودی «{key}» معتبر نیست.")

    def execute(
        self,
        *,
        name: str,
        context: LumiContext,
        arguments: dict[str, Any] | None = None,
        confirmed: bool = False,
    ) -> ToolResult:
        try:
            spec = self.get(name)
        except KeyError:
            return ToolResult.failure(str(name or ""), code="unknown_tool", error="این ابزار در Lumi ثبت نشده است.")

        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return ToolResult.failure(spec.name, code="invalid_arguments", error="ورودی ابزار باید یک JSON object باشد.")
        arguments = dict(arguments)
        try:
            spec.policy.check(context, confirmed=confirmed)
            self._validate(spec.input_schema, arguments)
            data = spec.handler(context, arguments, self.domain)
            if not isinstance(data, dict):
                raise TypeError("Tool handlers must return dict results.")
            return ToolResult.success(spec.name, data)
        except ToolPolicyError as exc:
            return ToolResult.failure(spec.name, code=getattr(exc, "code", "tool_not_allowed"), error=str(exc))
        except ToolValidationError as exc:
            return ToolResult.failure(spec.name, code=exc.code, error=str(exc))
        except Exception:
            # Never expose raw ORM/database/internal exceptions to the model.
            # Validation-specific UX should be returned as structured domain data.
            logger.exception("Lumi tool failed", extra={"tool": spec.name})
            return ToolResult.failure(
                spec.name,
                code="domain_error",
                error="در حال حاضر انجام این درخواست ممکن نیست. دوباره تلاش کن.",
            )
