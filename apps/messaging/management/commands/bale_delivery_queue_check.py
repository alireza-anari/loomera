from __future__ import annotations

import json
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
)

from ...constants import (
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
)
from ...models import MessagingMessageLog, MessagingProvider
from ...services import ensure_default_providers

DEFAULT_STATUSES = [
    NotificationDeliveryStatus.QUEUED,
    NotificationDeliveryStatus.FAILED,
    NotificationDeliveryStatus.PENDING_SETUP,
]

REQUEUEABLE_STATUSES = {
    NotificationDeliveryStatus.FAILED,
    NotificationDeliveryStatus.PENDING_SETUP,
}


@dataclass(frozen=True)
class BaleQueueIssue:
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

    allowed = {choice for choice, _label in NotificationDeliveryStatus.choices}
    statuses = []
    for value in values:
        value = str(value or "").strip()
        if value not in allowed:
            raise CommandError(f"Invalid delivery status: {value}")
        statuses.append(value)

    return statuses


def _bale_provider():
    ensure_default_providers()
    return MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()


def _base_delivery_queryset(*, statuses, delivery_ids=None):
    queryset = (
        NotificationDelivery.objects.filter(
            channel=NotificationChannel.BALE,
            status__in=statuses,
        )
        .select_related("recipient__user", "recipient__notification")
        .order_by("created_at", "id")
    )

    if delivery_ids:
        queryset = queryset.filter(pk__in=delivery_ids)

    return queryset


def _delivery_counts():
    rows = (
        NotificationDelivery.objects.filter(channel=NotificationChannel.BALE)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )
    return {row["status"]: row["count"] for row in rows}


def _delivery_snapshot(delivery: NotificationDelivery):
    recipient = delivery.recipient
    notification = recipient.notification

    return {
        "id": delivery.pk,
        "status": delivery.status,
        "attempt_count": int(delivery.attempt_count or 0),
        "recipient_user_id": recipient.user_id,
        "notification_id": notification.pk,
        "event_type": notification.event_type,
        "created_at": delivery.created_at.isoformat() if delivery.created_at else "",
        "updated_at": delivery.updated_at.isoformat() if delivery.updated_at else "",
        "failed_at": delivery.failed_at.isoformat() if delivery.failed_at else "",
        "last_error": _safe_text(delivery.last_error),
    }


def _failed_log_queryset(provider):
    if provider is None:
        return MessagingMessageLog.objects.none()

    return (
        MessagingMessageLog.objects.filter(
            provider=provider,
            direction=MessagingMessageDirection.OUTBOUND,
            status=MessagingMessageStatus.FAILED,
        )
        .select_related("notification_delivery")
        .order_by("-created_at", "-id")
    )


def _failed_log_snapshot(log: MessagingMessageLog):
    return {
        "id": log.pk,
        "notification_delivery_id": log.notification_delivery_id,
        "created_at": log.created_at.isoformat() if log.created_at else "",
        "error_message": _safe_text(log.error_message),
    }


def _add_issue(issues, *, code: str, severity: str, message: str, hint: str = ""):
    issues.append(
        BaleQueueIssue(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
        )
    )


def _requeue_delivery(delivery: NotificationDelivery, *, reason: str):
    previous_status = delivery.status
    metadata = dict(delivery.metadata or {})
    history = list(metadata.get("bale_requeue_history") or [])
    history.append(
        {
            "at": timezone.now().isoformat(),
            "from_status": previous_status,
            "reason": reason,
            "command": "bale_delivery_queue_check",
        }
    )
    metadata["bale_requeue_history"] = history[-10:]

    delivery.status = NotificationDeliveryStatus.QUEUED
    delivery.attempt_count = 0
    delivery.failed_at = None
    delivery.sent_at = None
    delivery.last_error = ""
    delivery.metadata = metadata
    delivery.save(
        update_fields=[
            "status",
            "attempt_count",
            "failed_at",
            "sent_at",
            "last_error",
            "metadata",
            "updated_at",
        ]
    )

    return previous_status


def run_bale_delivery_queue_check(
    *,
    statuses=None,
    delivery_ids=None,
    limit: int = 50,
    apply: bool = False,
    requeue_failed: bool = False,
    requeue_pending_setup: bool = False,
    strict: bool = False,
):
    issues: list[BaleQueueIssue] = []

    limit = max(1, min(int(limit or 50), 500))
    statuses = _parse_statuses(statuses)
    delivery_ids = [int(item) for item in (delivery_ids or []) if int(item) > 0]

    provider = _bale_provider()
    queryset = _base_delivery_queryset(statuses=statuses, delivery_ids=delivery_ids)
    selected_ids = list(queryset.values_list("id", flat=True)[:limit])

    selected_deliveries = list(
        _base_delivery_queryset(statuses=statuses, delivery_ids=selected_ids)
    )

    failed_logs = _failed_log_queryset(provider)
    failed_log_samples = list(failed_logs[: min(limit, 50)])

    counts = _delivery_counts()
    failed_delivery_count = int(counts.get(NotificationDeliveryStatus.FAILED, 0) or 0)
    pending_setup_count = int(
        counts.get(NotificationDeliveryStatus.PENDING_SETUP, 0) or 0
    )
    failed_log_count = failed_logs.count()

    if failed_delivery_count:
        _add_issue(
            issues,
            code="BALE_FAILED_DELIVERIES_EXIST",
            severity="warning",
            message="ارسال ناموفق بله در NotificationDelivery وجود دارد.",
            hint="بعد از بررسی علت خطا، با --requeue-failed --apply می‌توان retry امن را آماده کرد.",
        )

    if pending_setup_count:
        _add_issue(
            issues,
            code="BALE_PENDING_SETUP_DELIVERIES_EXIST",
            severity="warning",
            message="ارسال بله در وضعیت pending_setup وجود دارد.",
            hint="ابتدا اتصال حساب/identity کاربر را بررسی کن؛ سپس در صورت نیاز با --requeue-pending-setup --apply آماده retry کن.",
        )

    if failed_log_count:
        _add_issue(
            issues,
            code="BALE_FAILED_OUTBOUND_MESSAGE_LOGS_EXIST",
            severity="warning",
            message="لاگ پیام خروجی ناموفق بله وجود دارد.",
            hint="این command متن پیام یا secret چاپ نمی‌کند؛ فقط خطای خلاصه را برای بررسی نشان می‌دهد.",
        )

    requeued = []
    skipped = []

    wants_requeue = bool(requeue_failed or requeue_pending_setup)
    if wants_requeue:
        target_statuses = []
        if requeue_failed:
            target_statuses.append(NotificationDeliveryStatus.FAILED)
        if requeue_pending_setup:
            target_statuses.append(NotificationDeliveryStatus.PENDING_SETUP)

        target_ids = list(
            NotificationDelivery.objects.filter(
                channel=NotificationChannel.BALE,
                status__in=target_statuses,
            )
            .filter(pk__in=selected_ids)
            .order_by("created_at", "id")
            .values_list("id", flat=True)[:limit]
        )

        if not apply:
            skipped.append(
                {
                    "reason": "dry_run",
                    "message": "برای requeue واقعی باید --apply اضافه شود.",
                    "candidate_ids": target_ids,
                }
            )
        else:
            with transaction.atomic():
                locked_deliveries = (
                    NotificationDelivery.objects.select_for_update()
                    .filter(
                        pk__in=target_ids,
                        channel=NotificationChannel.BALE,
                    )
                    .select_related("recipient__notification")
                    .order_by("created_at", "id")
                )

                for delivery in locked_deliveries:
                    if delivery.status not in REQUEUEABLE_STATUSES:
                        skipped.append(
                            {
                                "id": delivery.pk,
                                "status": delivery.status,
                                "reason": "not_requeueable",
                            }
                        )
                        continue

                    if (
                        delivery.status == NotificationDeliveryStatus.FAILED
                        and not requeue_failed
                    ):
                        skipped.append(
                            {
                                "id": delivery.pk,
                                "status": delivery.status,
                                "reason": "failed_requeue_not_requested",
                            }
                        )
                        continue

                    if (
                        delivery.status == NotificationDeliveryStatus.PENDING_SETUP
                        and not requeue_pending_setup
                    ):
                        skipped.append(
                            {
                                "id": delivery.pk,
                                "status": delivery.status,
                                "reason": "pending_setup_requeue_not_requested",
                            }
                        )
                        continue

                    previous_status = _requeue_delivery(
                        delivery,
                        reason="manual_bale_queue_requeue",
                    )
                    requeued.append(
                        {
                            "id": delivery.pk,
                            "from_status": previous_status,
                            "to_status": NotificationDeliveryStatus.QUEUED,
                        }
                    )

    summary = {
        "ok": not issues,
        "strict": bool(strict),
        "dry_run": not apply,
        "selected_count": len(selected_deliveries),
        "requeued_count": len(requeued),
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
            "delivery_ids": delivery_ids,
            "limit": limit,
            "apply": bool(apply),
            "requeue_failed": bool(requeue_failed),
            "requeue_pending_setup": bool(requeue_pending_setup),
        },
        "provider": {
            "exists": provider is not None,
            "key": provider.key if provider else "",
        },
        "counts": {
            "deliveries": counts,
            "failed_outbound_message_logs": failed_log_count,
        },
        "selected_deliveries": [
            _delivery_snapshot(delivery) for delivery in selected_deliveries
        ],
        "failed_outbound_message_logs": [
            _failed_log_snapshot(log) for log in failed_log_samples
        ],
        "requeued": requeued,
        "skipped": skipped,
        "issues": [issue.as_dict() for issue in issues],
    }


class Command(BaseCommand):
    help = "Inspect and safely requeue Bale notification deliveries without sending messages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="append",
            dest="statuses",
            choices=[choice for choice, _label in NotificationDeliveryStatus.choices],
            help="Filter delivery status. Can be passed multiple times.",
        )
        parser.add_argument(
            "--delivery-id",
            action="append",
            type=int,
            dest="delivery_ids",
            help="Limit to a specific NotificationDelivery id. Can be passed multiple times.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of deliveries/log samples to inspect. Max: 500.",
        )
        parser.add_argument(
            "--requeue-failed",
            action="store_true",
            help="Prepare failed Bale deliveries for retry by moving them back to queued.",
        )
        parser.add_argument(
            "--requeue-pending-setup",
            action="store_true",
            help="Prepare pending_setup Bale deliveries for retry after identity/setup has been fixed.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply requeue changes. Without this flag the command is dry-run.",
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
        result = run_bale_delivery_queue_check(
            statuses=options.get("statuses"),
            delivery_ids=options.get("delivery_ids"),
            limit=options.get("limit"),
            apply=bool(options.get("apply")),
            requeue_failed=bool(options.get("requeue_failed")),
            requeue_pending_setup=bool(options.get("requeue_pending_setup")),
            strict=bool(options.get("strict")),
        )

        if options.get("json"):
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            summary = result["summary"]
            filters = result["filters"]

            self.stdout.write("=== Bale Delivery Queue Check ===")
            self.stdout.write(f"dry_run={summary['dry_run']}")
            self.stdout.write(f"strict={summary['strict']}")
            self.stdout.write(f"statuses={filters['statuses']}")
            self.stdout.write(f"limit={filters['limit']}")
            self.stdout.write(f"selected={summary['selected_count']}")
            self.stdout.write(f"requeued={summary['requeued_count']}")
            self.stdout.write(f"skipped={summary['skipped_count']}")
            self.stdout.write(f"issues={summary['issue_count']}")
            self.stdout.write("")

            self.stdout.write("Counts:")
            self.stdout.write(f"  deliveries={result['counts']['deliveries']}")
            self.stdout.write(
                f"  failed_outbound_message_logs={result['counts']['failed_outbound_message_logs']}"
            )
            self.stdout.write("")

            if result["selected_deliveries"]:
                self.stdout.write("Selected deliveries:")
                for item in result["selected_deliveries"]:
                    self.stdout.write(
                        "  "
                        f"id={item['id']} "
                        f"status={item['status']} "
                        f"attempts={item['attempt_count']} "
                        f"user={item['recipient_user_id']} "
                        f"notification={item['notification_id']} "
                        f"event={item['event_type']} "
                        f"error={item['last_error']}"
                    )
                self.stdout.write("")

            if result["failed_outbound_message_logs"]:
                self.stdout.write("Failed outbound message logs:")
                for item in result["failed_outbound_message_logs"]:
                    self.stdout.write(
                        "  "
                        f"id={item['id']} "
                        f"delivery={item['notification_delivery_id']} "
                        f"error={item['error_message']}"
                    )
                self.stdout.write("")

            if result["requeued"]:
                self.stdout.write("Requeued:")
                for item in result["requeued"]:
                    self.stdout.write(
                        f"  id={item['id']} {item['from_status']} -> {item['to_status']}"
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
                    self.style.SUCCESS("No Bale delivery queue issues found.")
                )

        if result["issues"] and options.get("strict"):
            raise CommandError(
                "Bale delivery queue check failed because --strict treats warnings as blocking issues."
            )
