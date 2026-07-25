from __future__ import annotations

import json

import ast
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

SENSITIVE_APPS = (
    "payments",
    "orders",
    "api",
    "messaging",
    "bale_bot",
)

ALLOWED_CATEGORIES = {
    "infrastructure_cache_boundary",
    "provider_webhook_boundary",
    "per_item_command_boundary",
    "notification_delivery_boundary",
    "domain_action_boundary",
    "readiness_probe_boundary",
    "signal_safety_boundary",
    "legacy_template_fallback",
    "user_facing_recovery",
    "legacy_financial_lifecycle_fallback",
    "legacy_lifecycle_fallback",
    "optional_data_compatibility_fallback",
}

ALLOWED_REVIEW_STATUSES = {
    "approved_boundary",
    "tracked_legacy",
}

CATEGORY_NOTES = {
    "infrastructure_cache_boundary": (
        "Cache backend boundary; provider-specific failures " "vary by backend."
    ),
    "provider_webhook_boundary": (
        "External provider or webhook boundary that must "
        "convert failures into a controlled domain result."
    ),
    "per_item_command_boundary": (
        "Per-record command isolation; one failed record " "must not stop the batch."
    ),
    "notification_delivery_boundary": (
        "Best-effort notification delivery must not roll " "back the primary action."
    ),
    "domain_action_boundary": (
        "Messaging action boundary converts domain failures " "into action results."
    ),
    "readiness_probe_boundary": (
        "Readiness probe records an unavailable dependency " "instead of crashing."
    ),
    "signal_safety_boundary": (
        "Signal side effect must not break the primary " "database operation."
    ),
    "legacy_template_fallback": (
        "Legacy display fallback retained for compatibility; " "narrowing is tracked."
    ),
    "user_facing_recovery": (
        "Legacy user-facing recovery boundary; narrowing " "is tracked."
    ),
    "legacy_financial_lifecycle_fallback": (
        "Legacy financial/lifecycle fallback; requires "
        "dedicated regression tests before further narrowing."
    ),
    "legacy_lifecycle_fallback": (
        "Legacy lifecycle compatibility fallback; narrowing " "is tracked."
    ),
    "optional_data_compatibility_fallback": (
        "Optional or legacy data compatibility fallback; " "narrowing is tracked."
    ),
}


def production_python_files(base_dir: Path):
    for app_name in SENSITIVE_APPS:
        app_root = base_dir / "apps" / app_name

        for path in app_root.rglob("*.py"):
            relative = path.relative_to(base_dir)
            parts = relative.parts

            if "migrations" in parts:
                continue
            if "__pycache__" in parts:
                continue
            if "tests" in parts:
                continue
            if path.name == "tests.py":
                continue
            if path.name.startswith("test_"):
                continue

            yield path


def exception_names(
    node: ast.expr | None,
) -> set[str]:
    if node is None:
        return {"<bare>"}

    if isinstance(node, ast.Name):
        return {node.id}

    if isinstance(node, ast.Attribute):
        return {node.attr}

    if isinstance(node, ast.Tuple):
        names: set[str] = set()

        for item in node.elts:
            names.update(exception_names(item))

        return names

    return {ast.unparse(node)}


def _owner_qualname(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> str:
    names: list[str] = []
    current = node

    while current in parents:
        current = parents[current]

        if isinstance(
            current,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            names.append(current.name)

    return ".".join(reversed(names)) or "<module>"


def _canonical_ast(value):
    """Return a Python-version-stable representation of an AST value."""

    if isinstance(value, ast.AST):
        fields = {}

        for field_name, field_value in ast.iter_fields(value):
            normalized = _canonical_ast(field_value)

            # Different Python versions may add optional AST fields.
            # Empty optional fields must not change the fingerprint.
            if normalized is None:
                continue

            if normalized == []:
                continue

            if normalized == {}:
                continue

            fields[field_name] = normalized

        return {
            "node": type(value).__name__,
            "fields": fields,
        }

    if isinstance(value, (list, tuple)):
        return [_canonical_ast(item) for item in value]

    if isinstance(value, bytes):
        return {
            "bytes": value.hex(),
        }

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return {
        "python_type": type(value).__name__,
        "repr": repr(value),
    }


def _ast_hash(value: ast.AST) -> str:
    payload = json.dumps(
        _canonical_ast(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return sha256(payload.encode("utf-8")).hexdigest()


def stable_ast_sha256(value: ast.AST) -> str:
    """Return a Python-version-stable SHA-256 fingerprint for an AST."""

    return _ast_hash(value)


def _category_for(
    path: str,
    qualname: str,
) -> tuple[str, str]:
    key = f"{path}::{qualname}"

    if path == "apps/api/v1/auth_otp.py":
        return (
            "infrastructure_cache_boundary",
            "approved_boundary",
        )

    if path.startswith("apps/bale_bot/"):
        return (
            "provider_webhook_boundary",
            "approved_boundary",
        )

    if path in {
        ("apps/payments/management/commands/" "expire_abandoned_online_checkouts.py"),
        ("apps/payments/management/commands/" "reconcile_pending_gateway_payments.py"),
        ("apps/orders/management/commands/" "repair_no_show_refunds.py"),
    }:
        return (
            "per_item_command_boundary",
            "approved_boundary",
        )

    if path in {
        "apps/messaging/actions.py",
        "apps/messaging/manager_actions.py",
        "apps/messaging/stylist_actions.py",
    }:
        return (
            "domain_action_boundary",
            "approved_boundary",
        )

    if path == ("apps/api/management/commands/" "app_api_readiness_check.py"):
        return (
            "readiness_probe_boundary",
            "approved_boundary",
        )

    if path == "apps/orders/signals.py":
        return (
            "signal_safety_boundary",
            "approved_boundary",
        )

    if (
        path == "apps/orders/notification_delivery.py"
        or "notification" in qualname.lower()
        or qualname.startswith("_notify_")
        or key.endswith("::dispatch_due_order_reminders")
        or key.endswith("::create_notification")
    ):
        return (
            "notification_delivery_boundary",
            "approved_boundary",
        )

    if path == ("apps/orders/templatetags/" "jalali_filters.py"):
        return (
            "legacy_template_fallback",
            "tracked_legacy",
        )

    if path.endswith("/views.py"):
        return (
            "user_facing_recovery",
            "tracked_legacy",
        )

    if path in {
        "apps/payments/finance.py",
        "apps/orders/appointment_lifecycle.py",
    }:
        return (
            "legacy_financial_lifecycle_fallback",
            "tracked_legacy",
        )

    if path == "apps/orders/lifecycle.py":
        return (
            "legacy_lifecycle_fallback",
            "tracked_legacy",
        )

    return (
        "optional_data_compatibility_fallback",
        "tracked_legacy",
    )


def collect_forbidden_exception_handlers(
    base_dir: Path,
) -> list[dict]:
    violations: list[dict] = []

    for path in production_python_files(base_dir):
        relative = path.relative_to(base_dir).as_posix()

        source = path.read_text(encoding="utf-8")
        tree = ast.parse(
            source,
            filename=str(path),
        )

        for node in ast.walk(tree):
            if not isinstance(
                node,
                ast.ExceptHandler,
            ):
                continue

            names = exception_names(node.type)
            forbidden = names.intersection(
                {
                    "<bare>",
                    "BaseException",
                }
            )

            if not forbidden:
                continue

            violations.append(
                {
                    "path": relative,
                    "line": node.lineno,
                    "exceptions": sorted(forbidden),
                }
            )

    return sorted(
        violations,
        key=lambda item: (
            item["path"],
            item["line"],
        ),
    )


def collect_broad_exception_inventory(
    base_dir: Path,
) -> list[dict]:
    pending: list[dict] = []

    for path in production_python_files(base_dir):
        relative = path.relative_to(base_dir).as_posix()

        source = path.read_text(encoding="utf-8")
        tree = ast.parse(
            source,
            filename=str(path),
        )

        parents: dict[
            ast.AST,
            ast.AST,
        ] = {}

        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            if not isinstance(
                node,
                ast.ExceptHandler,
            ):
                continue

            if "Exception" not in exception_names(node.type):
                continue

            try_node = parents.get(node)

            if not isinstance(
                try_node,
                (
                    ast.Try,
                    ast.TryStar,
                ),
            ):
                raise AssertionError(
                    f"{relative}:{node.lineno}: " "broad handler has no Try parent"
                )

            qualname = _owner_qualname(
                node,
                parents,
            )

            (
                category,
                review_status,
            ) = _category_for(
                relative,
                qualname,
            )

            pending.append(
                {
                    "path": relative,
                    "qualname": qualname,
                    "line": node.lineno,
                    "try_handler_index": (try_node.handlers.index(node)),
                    "try_sha256": _ast_hash(try_node),
                    "handler_sha256": _ast_hash(node),
                    "category": category,
                    "review_status": (review_status),
                    "note": CATEGORY_NOTES[category],
                }
            )

    grouped: dict[
        tuple[str, str],
        list[dict],
    ] = defaultdict(list)

    for item in pending:
        grouped[
            (
                item["path"],
                item["qualname"],
            )
        ].append(item)

    inventory: list[dict] = []

    for items in grouped.values():
        items.sort(key=lambda item: item["line"])

        for ordinal, item in enumerate(
            items,
            start=1,
        ):
            clean = dict(item)
            clean.pop("line")
            clean["ordinal"] = ordinal
            inventory.append(clean)

    return sorted(
        inventory,
        key=lambda item: (
            item["path"],
            item["qualname"],
            item["ordinal"],
        ),
    )
