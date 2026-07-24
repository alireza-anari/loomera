from __future__ import annotations

import json
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from ...constants import (
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingProviderKey,
)
from ...models import (
    MessagingAccountConnection,
    MessagingIdentity,
    MessagingProvider,
)
from ...services import ensure_default_providers


@dataclass(frozen=True)
class BaleAccountLinkIssue:
    code: str
    severity: str
    message: str
    hint: str = ""

    def as_dict(self):
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
        }


def _safe_text(value: str, *, max_length: int = 80) -> str:
    cleaned = (
        str(value or "")
        .replace("\x00", "")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )
    if len(cleaned) > max_length:
        return f"{cleaned[:max_length]}..."
    return cleaned


def _mask_identifier(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


def _add_issue(issues, *, code: str, severity: str, message: str, hint: str = ""):
    issues.append(
        BaleAccountLinkIssue(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
        )
    )


def _bale_provider():
    ensure_default_providers()
    return MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()


def _identity_counts(provider):
    if provider is None:
        return {}

    rows = (
        MessagingIdentity.objects.filter(provider=provider)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    return {row["status"]: row["count"] for row in rows}


def _connection_counts(provider):
    if provider is None:
        return {}

    rows = (
        MessagingAccountConnection.objects.filter(provider=provider)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    return {row["status"]: row["count"] for row in rows}


def _identity_snapshot(identity: MessagingIdentity):
    return {
        "id": identity.pk,
        "status": identity.status,
        "user_id": identity.user_id,
        "provider_user_id": _mask_identifier(identity.provider_user_id),
        "chat_id_configured": bool(identity.chat_id),
        "chat_id": _mask_identifier(identity.chat_id),
        "last_seen_at": (
            identity.last_seen_at.isoformat() if identity.last_seen_at else ""
        ),
        "connected_at": (
            identity.connected_at.isoformat() if identity.connected_at else ""
        ),
        "disconnected_at": (
            identity.disconnected_at.isoformat() if identity.disconnected_at else ""
        ),
    }


def _connection_snapshot(connection: MessagingAccountConnection):
    return {
        "id": connection.pk,
        "status": connection.status,
        "user_id": connection.user_id,
        "identity_id": connection.identity_id,
        "connected_at": (
            connection.connected_at.isoformat() if connection.connected_at else ""
        ),
        "disconnected_at": (
            connection.disconnected_at.isoformat() if connection.disconnected_at else ""
        ),
    }


def _active_connections(provider):
    if provider is None:
        return MessagingAccountConnection.objects.none()

    return (
        MessagingAccountConnection.objects.filter(
            provider=provider,
            status=MessagingConnectionStatus.ACTIVE,
        )
        .select_related("identity", "user")
        .order_by("connected_at", "id")
    )


def _linked_identities(provider):
    if provider is None:
        return MessagingIdentity.objects.none()

    return (
        MessagingIdentity.objects.filter(
            provider=provider,
            status=MessagingIdentityStatus.LINKED,
        )
        .select_related("user")
        .order_by("updated_at", "id")
    )


def _find_problem_connections(provider, *, limit: int):
    items = []
    for connection in _active_connections(provider)[:limit]:
        identity = connection.identity

        codes = []
        if connection.provider_id != identity.provider_id:
            codes.append("provider_mismatch")
        if identity.user_id != connection.user_id:
            codes.append("user_mismatch")
        if identity.status != MessagingIdentityStatus.LINKED:
            codes.append("identity_not_linked")
        if not identity.chat_id:
            codes.append("missing_chat_id")

        if codes:
            items.append(
                {
                    "connection": _connection_snapshot(connection),
                    "identity": _identity_snapshot(identity),
                    "codes": codes,
                }
            )

    return items


def _find_linked_identities_without_active_connection(provider, *, limit: int):
    if provider is None:
        return []

    active_identity_ids = MessagingAccountConnection.objects.filter(
        provider=provider,
        status=MessagingConnectionStatus.ACTIVE,
    ).values_list("identity_id", flat=True)

    identities = (
        _linked_identities(provider)
        .exclude(pk__in=active_identity_ids)
        .order_by("updated_at", "id")[:limit]
    )

    return [_identity_snapshot(identity) for identity in identities]


def _find_active_connections_without_chat_id(provider, *, limit: int):
    if provider is None:
        return []

    connections = (
        _active_connections(provider)
        .filter(identity__chat_id="")
        .order_by("connected_at", "id")[:limit]
    )

    return [_connection_snapshot(connection) for connection in connections]


def _repair_active_identity_states(provider, *, limit: int):
    repaired = []
    skipped = []

    if provider is None:
        return repaired, skipped

    candidates = (
        MessagingAccountConnection.objects.select_for_update()
        .filter(
            provider=provider,
            status=MessagingConnectionStatus.ACTIVE,
        )
        .select_related("identity")
        .order_by("connected_at", "id")[:limit]
    )

    for connection in candidates:
        identity = connection.identity

        if connection.provider_id != identity.provider_id:
            skipped.append(
                {
                    "connection_id": connection.pk,
                    "identity_id": identity.pk,
                    "reason": "provider_mismatch",
                }
            )
            continue

        if identity.user_id != connection.user_id:
            skipped.append(
                {
                    "connection_id": connection.pk,
                    "identity_id": identity.pk,
                    "reason": "user_mismatch",
                }
            )
            continue

        if not identity.chat_id:
            skipped.append(
                {
                    "connection_id": connection.pk,
                    "identity_id": identity.pk,
                    "reason": "missing_chat_id",
                }
            )
            continue

        if identity.status == MessagingIdentityStatus.LINKED:
            continue

        previous_status = identity.status
        identity.status = MessagingIdentityStatus.LINKED
        identity.connected_at = (
            identity.connected_at or connection.connected_at or timezone.now()
        )
        identity.disconnected_at = None
        identity.save(
            update_fields=["status", "connected_at", "disconnected_at", "updated_at"]
        )

        repaired.append(
            {
                "connection_id": connection.pk,
                "identity_id": identity.pk,
                "from_status": previous_status,
                "to_status": MessagingIdentityStatus.LINKED,
            }
        )

    return repaired, skipped


def run_bale_account_link_check(
    *,
    limit: int = 50,
    repair_active_identities: bool = False,
    apply: bool = False,
    strict: bool = False,
):
    issues: list[BaleAccountLinkIssue] = []

    limit = max(1, min(int(limit or 50), 500))
    provider = _bale_provider()

    identity_counts = _identity_counts(provider)
    connection_counts = _connection_counts(provider)

    problem_connections = _find_problem_connections(provider, limit=limit)
    linked_without_connection = _find_linked_identities_without_active_connection(
        provider,
        limit=limit,
    )
    active_without_chat_id = _find_active_connections_without_chat_id(
        provider, limit=limit
    )

    if provider is None:
        _add_issue(
            issues,
            code="BALE_PROVIDER_MISSING",
            severity="error",
            message="provider بله در دیتابیس وجود ندارد.",
        )

    if problem_connections:
        _add_issue(
            issues,
            code="BALE_ACTIVE_CONNECTION_INCONSISTENCY",
            severity="warning",
            message="active connection بله با identity متناظر ناسازگار است.",
            hint="موارد user/provider/status/chat_id را بررسی کن.",
        )

    if linked_without_connection:
        _add_issue(
            issues,
            code="BALE_LINKED_IDENTITY_WITHOUT_ACTIVE_CONNECTION",
            severity="warning",
            message="identity بله در وضعیت linked است اما active connection ندارد.",
            hint="این مورد می‌تواند باعث pending_setup شدن ارسال اعلان شود؛ به‌صورت خودکار connection ساخته نمی‌شود.",
        )

    if active_without_chat_id:
        _add_issue(
            issues,
            code="BALE_ACTIVE_CONNECTION_MISSING_CHAT_ID",
            severity="warning",
            message="active connection بله وجود دارد اما identity chat_id ندارد.",
            hint="بدون chat_id ارسال پیام ممکن نیست.",
        )

    repaired = []
    skipped = []

    if repair_active_identities:
        if not apply:
            skipped.append(
                {
                    "reason": "dry_run",
                    "message": "برای repair واقعی باید --apply اضافه شود.",
                }
            )
        else:
            with transaction.atomic():
                repaired, skipped = _repair_active_identity_states(
                    provider, limit=limit
                )

    summary = {
        "ok": not issues,
        "strict": bool(strict),
        "dry_run": not apply,
        "issue_count": len(issues),
        "warning_count": len(
            [issue for issue in issues if issue.severity == "warning"]
        ),
        "error_count": len([issue for issue in issues if issue.severity == "error"]),
        "problem_connection_count": len(problem_connections),
        "linked_without_connection_count": len(linked_without_connection),
        "active_without_chat_id_count": len(active_without_chat_id),
        "repaired_count": len(repaired),
        "skipped_count": len(skipped),
    }

    return {
        "summary": summary,
        "filters": {
            "limit": limit,
            "repair_active_identities": bool(repair_active_identities),
            "apply": bool(apply),
        },
        "provider": {
            "exists": provider is not None,
            "key": provider.key if provider else "",
        },
        "counts": {
            "identities": identity_counts,
            "connections": connection_counts,
        },
        "problem_connections": problem_connections,
        "linked_identities_without_active_connection": linked_without_connection,
        "active_connections_without_chat_id": active_without_chat_id,
        "repaired": repaired,
        "skipped": skipped,
        "issues": [issue.as_dict() for issue in issues],
    }


class Command(BaseCommand):
    help = "Inspect and safely repair Bale account identity/connection consistency."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of records to inspect. Max: 500.",
        )
        parser.add_argument(
            "--repair-active-identities",
            action="store_true",
            help="Repair active connection identities whose user matches but status is not linked.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply safe repairs. Without this flag the command is dry-run.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when any issue is found.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output.",
        )

    def handle(self, *args, **options):
        result = run_bale_account_link_check(
            limit=options.get("limit"),
            repair_active_identities=bool(options.get("repair_active_identities")),
            apply=bool(options.get("apply")),
            strict=bool(options.get("strict")),
        )

        if options.get("json"):
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            summary = result["summary"]

            self.stdout.write("=== Bale Account Link Check ===")
            self.stdout.write(f"dry_run={summary['dry_run']}")
            self.stdout.write(f"strict={summary['strict']}")
            self.stdout.write(f"issues={summary['issue_count']}")
            self.stdout.write(f"warnings={summary['warning_count']}")
            self.stdout.write(f"errors={summary['error_count']}")
            self.stdout.write(
                f"problem_connections={summary['problem_connection_count']}"
            )
            self.stdout.write(
                f"linked_without_connection={summary['linked_without_connection_count']}"
            )
            self.stdout.write(
                f"active_without_chat_id={summary['active_without_chat_id_count']}"
            )
            self.stdout.write(f"repaired={summary['repaired_count']}")
            self.stdout.write(f"skipped={summary['skipped_count']}")
            self.stdout.write("")

            self.stdout.write("Counts:")
            self.stdout.write(f"  identities={result['counts']['identities']}")
            self.stdout.write(f"  connections={result['counts']['connections']}")
            self.stdout.write("")

            if result["problem_connections"]:
                self.stdout.write("Problem connections:")
                for item in result["problem_connections"]:
                    connection = item["connection"]
                    identity = item["identity"]
                    self.stdout.write(
                        "  "
                        f"connection={connection['id']} "
                        f"identity={identity['id']} "
                        f"user={connection['user_id']} "
                        f"identity_user={identity['user_id']} "
                        f"identity_status={identity['status']} "
                        f"chat_id_configured={identity['chat_id_configured']} "
                        f"codes={item['codes']}"
                    )
                self.stdout.write("")

            if result["linked_identities_without_active_connection"]:
                self.stdout.write("Linked identities without active connection:")
                for identity in result["linked_identities_without_active_connection"]:
                    self.stdout.write(
                        "  "
                        f"identity={identity['id']} "
                        f"user={identity['user_id']} "
                        f"chat_id_configured={identity['chat_id_configured']} "
                        f"last_seen_at={identity['last_seen_at']}"
                    )
                self.stdout.write("")

            if result["active_connections_without_chat_id"]:
                self.stdout.write("Active connections without chat_id:")
                for connection in result["active_connections_without_chat_id"]:
                    self.stdout.write(
                        "  "
                        f"connection={connection['id']} "
                        f"identity={connection['identity_id']} "
                        f"user={connection['user_id']}"
                    )
                self.stdout.write("")

            if result["repaired"]:
                self.stdout.write("Repaired:")
                for item in result["repaired"]:
                    self.stdout.write(
                        f"  identity={item['identity_id']} {item['from_status']} -> {item['to_status']}"
                    )
                self.stdout.write("")

            if result["skipped"]:
                self.stdout.write("Skipped:")
                for item in result["skipped"]:
                    self.stdout.write(f"  {item}")
                self.stdout.write("")

            if result["issues"]:
                self.stdout.write("Issues:")
                for issue in result["issues"]:
                    line = f"[{issue['severity']}] {issue['code']}: {issue['message']}"
                    if issue.get("hint"):
                        line += f"\n  hint: {issue['hint']}"
                    if issue["severity"] == "error":
                        self.stdout.write(self.style.ERROR(line))
                    else:
                        self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(
                    self.style.SUCCESS("No Bale account link issues found.")
                )

        if result["issues"] and options.get("strict"):
            raise CommandError(
                "Bale account link check failed because --strict treats warnings as blocking issues."
            )
