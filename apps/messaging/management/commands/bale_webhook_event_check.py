from __future__ import annotations

import json
from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.bale_bot.services import (
    BaleWebhookIgnored,
    reprocess_bale_webhook_event,
)

from ...constants import MessagingProviderKey, MessagingWebhookEventStatus
from ...models import MessagingProvider, MessagingWebhookEvent
from ...services import ensure_default_providers

DEFAULT_STATUSES = [
    MessagingWebhookEventStatus.FAILED,
    MessagingWebhookEventStatus.RECEIVED,
]

REPROCESSABLE_STATUSES = {
    MessagingWebhookEventStatus.FAILED,
    MessagingWebhookEventStatus.RECEIVED,
}


@dataclass(frozen=True)
class BaleWebhookEventIssue:
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


def _safe_text(value: str, *, max_length: int = 180) -> str:
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


def _parse_statuses(values):
    if not values:
        return list(DEFAULT_STATUSES)

    allowed = {choice for choice, _label in MessagingWebhookEventStatus.choices}
    statuses = []
    for value in values:
        value = str(value or "").strip()
        if value not in allowed:
            raise CommandError(f"Invalid webhook event status: {value}")
        statuses.append(value)
    return statuses


def _bale_provider():
    ensure_default_providers()
    return MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()


def _public_base_url() -> str:
    return str(getattr(settings, "MESSAGING_PUBLIC_BASE_URL", "") or "").rstrip("/")


def _event_counts(provider):
    if provider is None:
        return {}

    rows = (
        MessagingWebhookEvent.objects.filter(provider=provider)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    return {row["status"]: row["count"] for row in rows}


def _base_event_queryset(*, provider, statuses, event_ids=None):
    queryset = (
        MessagingWebhookEvent.objects.none()
        if provider is None
        else MessagingWebhookEvent.objects.filter(
            provider=provider, status__in=statuses
        )
    )

    if event_ids:
        queryset = queryset.filter(pk__in=event_ids)

    return queryset.select_related("identity").order_by("received_at", "id")


def _event_snapshot(event: MessagingWebhookEvent):
    return {
        "id": event.pk,
        "status": event.status,
        "event_type": event.event_type,
        "event_id": event.event_id,
        "update_id": event.update_id,
        "identity_id": event.identity_id,
        "received_at": event.received_at.isoformat() if event.received_at else "",
        "processed_at": event.processed_at.isoformat() if event.processed_at else "",
        "error_message": _safe_text(event.error_message),
    }


def _add_issue(issues, *, code: str, severity: str, message: str, hint: str = ""):
    issues.append(
        BaleWebhookEventIssue(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
        )
    )


def run_bale_webhook_event_check(
    *,
    statuses=None,
    event_ids=None,
    limit: int = 50,
    apply: bool = False,
    reprocess_failed: bool = False,
    reprocess_received: bool = False,
    strict: bool = False,
    base_url: str = "",
):
    issues: list[BaleWebhookEventIssue] = []

    limit = max(1, min(int(limit or 50), 500))
    statuses = _parse_statuses(statuses)
    event_ids = [int(item) for item in (event_ids or []) if int(item) > 0]

    provider = _bale_provider()
    queryset = _base_event_queryset(
        provider=provider,
        statuses=statuses,
        event_ids=event_ids,
    )

    selected_ids = list(queryset.values_list("id", flat=True)[:limit])
    selected_events = list(
        _base_event_queryset(
            provider=provider,
            statuses=statuses,
            event_ids=selected_ids,
        )
    )

    counts = _event_counts(provider)
    failed_count = int(counts.get(MessagingWebhookEventStatus.FAILED, 0) or 0)
    received_count = int(counts.get(MessagingWebhookEventStatus.RECEIVED, 0) or 0)

    if failed_count:
        _add_issue(
            issues,
            code="BALE_FAILED_WEBHOOK_EVENTS_EXIST",
            severity="warning",
            message="وبهوک ناموفق بله وجود دارد.",
            hint="بعد از بررسی علت خطا، با --reprocess-failed --apply می‌توان reprocess کنترل‌شده انجام داد.",
        )

    if received_count:
        _add_issue(
            issues,
            code="BALE_UNPROCESSED_WEBHOOK_EVENTS_EXIST",
            severity="warning",
            message="وبهوک دریافت‌شده ولی پردازش‌نشده بله وجود دارد.",
            hint="اگر handler امن است، با --reprocess-received --apply قابل پردازش دوباره است.",
        )

    reprocessed = []
    skipped = []

    wants_reprocess = bool(reprocess_failed or reprocess_received)
    if wants_reprocess:
        target_statuses = []
        if reprocess_failed:
            target_statuses.append(MessagingWebhookEventStatus.FAILED)
        if reprocess_received:
            target_statuses.append(MessagingWebhookEventStatus.RECEIVED)

        target_ids = list(
            _base_event_queryset(
                provider=provider,
                statuses=target_statuses,
                event_ids=selected_ids,
            ).values_list("id", flat=True)[:limit]
        )

        if not apply:
            skipped.append(
                {
                    "reason": "dry_run",
                    "message": "برای reprocess واقعی باید --apply اضافه شود.",
                    "candidate_ids": target_ids,
                }
            )
        else:
            effective_base_url = base_url or _public_base_url()
            for event_id in target_ids:
                before = MessagingWebhookEvent.objects.get(pk=event_id)
                if before.status not in REPROCESSABLE_STATUSES:
                    skipped.append(
                        {
                            "id": before.pk,
                            "status": before.status,
                            "reason": "not_reprocessable",
                        }
                    )
                    continue

                if (
                    before.status == MessagingWebhookEventStatus.FAILED
                    and not reprocess_failed
                ):
                    skipped.append(
                        {
                            "id": before.pk,
                            "status": before.status,
                            "reason": "failed_reprocess_not_requested",
                        }
                    )
                    continue

                if (
                    before.status == MessagingWebhookEventStatus.RECEIVED
                    and not reprocess_received
                ):
                    skipped.append(
                        {
                            "id": before.pk,
                            "status": before.status,
                            "reason": "received_reprocess_not_requested",
                        }
                    )
                    continue

                try:
                    result = reprocess_bale_webhook_event(
                        event_id=before.pk,
                        base_url=effective_base_url,
                    )
                except BaleWebhookIgnored as exc:
                    skipped.append(
                        {
                            "id": before.pk,
                            "status": before.status,
                            "reason": _safe_text(str(exc)),
                        }
                    )
                    continue

                event = result["event"]
                reprocessed.append(
                    {
                        "id": event.pk,
                        "from_status": before.status,
                        "to_status": event.status,
                        "ok": bool(result["ok"]),
                        "handler_result": _safe_text(result.get("handler_result", "")),
                        "error": _safe_text(result.get("error", "")),
                    }
                )

    summary = {
        "ok": not issues,
        "strict": bool(strict),
        "dry_run": not apply,
        "selected_count": len(selected_events),
        "reprocessed_count": len(reprocessed),
        "skipped_count": len(skipped),
        "issue_count": len(issues),
        "warning_count": len(
            [issue for issue in issues if issue.severity == "warning"]
        ),
        "error_count": len([issue for issue in issues if issue.severity == "error"]),
    }

    return {
        "summary": summary,
        "filters": {
            "statuses": statuses,
            "event_ids": event_ids,
            "limit": limit,
            "apply": bool(apply),
            "reprocess_failed": bool(reprocess_failed),
            "reprocess_received": bool(reprocess_received),
        },
        "provider": {
            "exists": provider is not None,
            "key": provider.key if provider else "",
        },
        "counts": {
            "events": counts,
        },
        "selected_events": [_event_snapshot(event) for event in selected_events],
        "reprocessed": reprocessed,
        "skipped": skipped,
        "issues": [issue.as_dict() for issue in issues],
    }


class Command(BaseCommand):
    help = "Inspect and safely reprocess stored Bale webhook events without printing secrets or payloads."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="append",
            dest="statuses",
            choices=[choice for choice, _label in MessagingWebhookEventStatus.choices],
            help="Filter webhook event status. Can be passed multiple times.",
        )
        parser.add_argument(
            "--event-id",
            action="append",
            type=int,
            dest="event_ids",
            help="Limit to a specific MessagingWebhookEvent id. Can be passed multiple times.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of webhook events to inspect. Max: 500.",
        )
        parser.add_argument(
            "--reprocess-failed",
            action="store_true",
            help="Reprocess failed Bale webhook events.",
        )
        parser.add_argument(
            "--reprocess-received",
            action="store_true",
            help="Reprocess received/unprocessed Bale webhook events.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply reprocess changes. Without this flag the command is dry-run.",
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
        result = run_bale_webhook_event_check(
            statuses=options.get("statuses"),
            event_ids=options.get("event_ids"),
            limit=options.get("limit"),
            apply=bool(options.get("apply")),
            reprocess_failed=bool(options.get("reprocess_failed")),
            reprocess_received=bool(options.get("reprocess_received")),
            strict=bool(options.get("strict")),
        )

        if options.get("json"):
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            summary = result["summary"]
            filters = result["filters"]

            self.stdout.write("=== Bale Webhook Event Check ===")
            self.stdout.write(f"dry_run={summary['dry_run']}")
            self.stdout.write(f"strict={summary['strict']}")
            self.stdout.write(f"statuses={filters['statuses']}")
            self.stdout.write(f"limit={filters['limit']}")
            self.stdout.write(f"selected={summary['selected_count']}")
            self.stdout.write(f"reprocessed={summary['reprocessed_count']}")
            self.stdout.write(f"skipped={summary['skipped_count']}")
            self.stdout.write(f"issues={summary['issue_count']}")
            self.stdout.write("")

            self.stdout.write("Counts:")
            self.stdout.write(f"  events={result['counts']['events']}")
            self.stdout.write("")

            if result["selected_events"]:
                self.stdout.write("Selected events:")
                for item in result["selected_events"]:
                    self.stdout.write(
                        "  "
                        f"id={item['id']} "
                        f"status={item['status']} "
                        f"type={item['event_type']} "
                        f"event_id={item['event_id']} "
                        f"update_id={item['update_id']} "
                        f"identity={item['identity_id']} "
                        f"error={item['error_message']}"
                    )
                self.stdout.write("")

            if result["reprocessed"]:
                self.stdout.write("Reprocessed:")
                for item in result["reprocessed"]:
                    self.stdout.write(
                        "  "
                        f"id={item['id']} "
                        f"{item['from_status']} -> {item['to_status']} "
                        f"ok={item['ok']} "
                        f"handler={item['handler_result']} "
                        f"error={item['error']}"
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
                    self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(
                    self.style.SUCCESS("No Bale webhook event issues found.")
                )

        if result["issues"] and options.get("strict"):
            raise CommandError(
                "Bale webhook event check failed because --strict treats warnings as blocking issues."
            )
