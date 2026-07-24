from __future__ import annotations

import json
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from apps.notifications.models import NotificationChannel, NotificationDeliveryStatus

from ...management.commands.bale_account_link_check import run_bale_account_link_check
from ...management.commands.bale_delivery_queue_check import (
    run_bale_delivery_queue_check,
)
from ...management.commands.bale_webhook_admin import run_bale_webhook_admin
from ...management.commands.bale_webhook_event_check import run_bale_webhook_event_check
from ...management.commands.messaging_qa_check import run_messaging_qa_check


@dataclass(frozen=True)
class BaleFinalReadinessIssue:
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


def _add_issue(issues, *, code: str, severity: str, message: str, hint: str = ""):
    issues.append(
        BaleFinalReadinessIssue(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
        )
    )


def _collect_command_issues(command_name: str, result: dict):
    issues = []
    for issue in result.get("issues", []):
        issues.append(
            {
                "source": command_name,
                "code": issue.get("code", ""),
                "severity": issue.get("severity", "warning"),
                "message": issue.get("message", ""),
                "hint": issue.get("hint", ""),
            }
        )
    return issues


def _summary_from_result(result: dict):
    return result.get("summary", {}) or {}


def _is_queue_dirty(delivery_result: dict) -> bool:
    counts = (delivery_result.get("counts") or {}).get("deliveries") or {}
    return bool(
        counts.get(NotificationDeliveryStatus.FAILED)
        or counts.get(NotificationDeliveryStatus.PENDING_SETUP)
    )


def run_bale_final_readiness_check(*, strict: bool = False):
    issues: list[BaleFinalReadinessIssue] = []

    messaging_qa = run_messaging_qa_check(strict=False)
    delivery_queue = run_bale_delivery_queue_check(
        statuses=[
            NotificationDeliveryStatus.QUEUED,
            NotificationDeliveryStatus.FAILED,
            NotificationDeliveryStatus.PENDING_SETUP,
        ],
        limit=25,
        strict=False,
    )
    webhook_events = run_bale_webhook_event_check(limit=25, strict=False)
    account_links = run_bale_account_link_check(limit=25, strict=False)
    webhook_admin = run_bale_webhook_admin(strict=False)

    command_results = {
        "messaging_qa_check": messaging_qa,
        "bale_delivery_queue_check": delivery_queue,
        "bale_webhook_event_check": webhook_events,
        "bale_account_link_check": account_links,
        "bale_webhook_admin": webhook_admin,
    }

    command_issues = []
    for name, result in command_results.items():
        command_issues.extend(_collect_command_issues(name, result))

    for issue in command_issues:
        _add_issue(
            issues,
            code=f"{issue['source']}::{issue['code']}",
            severity=issue["severity"],
            message=issue["message"],
            hint=issue["hint"],
        )

    if _is_queue_dirty(delivery_queue):
        _add_issue(
            issues,
            code="BALE_QUEUE_HAS_RETRYABLE_PROBLEMS",
            severity="warning",
            message="صف بله دارای delivery failed یا pending_setup است.",
            hint="قبل از Staging/Production، bale_delivery_queue_check را بررسی و در صورت نیاز requeue امن انجام بده.",
        )

    messaging_summary = _summary_from_result(messaging_qa)
    queue_ready = bool(
        ((messaging_qa.get("queue") or {}).get("bale") or {}).get(
            "bale_outbound_queue_ready"
        )
    )

    if messaging_summary.get("error_count", 0):
        _add_issue(
            issues,
            code="MESSAGING_QA_HAS_ERRORS",
            severity="error",
            message="Messaging/Bale QA دارای error است.",
            hint="اول messaging_qa_check --strict را اصلاح کن.",
        )

    readiness = {
        "local_development_safe": True,
        "staging_ready": not issues and bool(queue_ready),
        "production_ready": False,
        "queue_ready": bool(queue_ready),
    }

    summary = {
        "ok": not issues,
        "strict": bool(strict),
        "issue_count": len(issues),
        "warning_count": len(
            [issue for issue in issues if issue.severity == "warning"]
        ),
        "error_count": len([issue for issue in issues if issue.severity == "error"]),
        "staging_ready": readiness["staging_ready"],
        "production_ready": readiness["production_ready"],
    }

    return {
        "summary": summary,
        "readiness": readiness,
        "command_summaries": {
            name: _summary_from_result(result)
            for name, result in command_results.items()
        },
        "recommended_order": [
            "python manage.py messaging_qa_check",
            "python manage.py bale_account_link_check",
            "python manage.py bale_delivery_queue_check",
            "python manage.py bale_webhook_event_check",
            "python manage.py bale_webhook_admin",
            "python manage.py bale_final_readiness_check --strict",
        ],
        "staging_runbook": [
            "Set MESSAGING_PUBLIC_BASE_URL to the staging HTTPS domain.",
            "Set BALE_BOT_TOKEN and BALE_WEBHOOK_SECRET only in env.",
            "Set MESSAGING_ENABLED=True and BALE_BOT_ENABLED=True.",
            "Keep MESSAGING_OUTBOUND_ENABLED=False until webhook/admin checks pass.",
            "Run python manage.py messaging_qa_check --strict.",
            "Run python manage.py bale_account_link_check --strict.",
            "Run python manage.py bale_delivery_queue_check --strict.",
            "Run python manage.py bale_webhook_event_check --strict.",
            "Run python manage.py bale_webhook_admin --set first as dry-run.",
            "Run python manage.py bale_webhook_admin --set --apply only on staging.",
            "Enable MESSAGING_OUTBOUND_ENABLED=True only after queue/provider checks are clean.",
            "Run python manage.py bale_final_readiness_check --strict.",
        ],
        "production_policy": [
            "Do not enable Bale production before staging passes strict checks.",
            "Do not enable provider webhook on production before domain, HTTPS, and secret header are verified.",
            "Do not run queue processing with MESSAGING_OUTBOUND_ENABLED=True while unexpected queued test data exists.",
            "Do not expose BALE_BOT_TOKEN or BALE_WEBHOOK_SECRET in logs, reports, ZIP files, or commit messages.",
        ],
        "issues": [issue.as_dict() for issue in issues],
    }


class Command(BaseCommand):
    help = "Run final Bale readiness checks and print a safe local/staging runbook."

    def add_arguments(self, parser):
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
        strict = bool(options.get("strict"))
        result = run_bale_final_readiness_check(strict=strict)

        if options.get("json"):
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            summary = result["summary"]
            readiness = result["readiness"]

            self.stdout.write("=== Bale Final Readiness Check ===")
            self.stdout.write(f"strict={summary['strict']}")
            self.stdout.write(f"issues={summary['issue_count']}")
            self.stdout.write(f"errors={summary['error_count']}")
            self.stdout.write(f"warnings={summary['warning_count']}")
            self.stdout.write(f"staging_ready={summary['staging_ready']}")
            self.stdout.write(f"production_ready={summary['production_ready']}")
            self.stdout.write("")

            self.stdout.write("Readiness:")
            for key, value in readiness.items():
                self.stdout.write(f"  {key}={value}")
            self.stdout.write("")

            self.stdout.write("Command summaries:")
            for name, command_summary in result["command_summaries"].items():
                self.stdout.write(f"  {name}: {command_summary}")
            self.stdout.write("")

            self.stdout.write("Recommended order:")
            for item in result["recommended_order"]:
                self.stdout.write(f"  - {item}")
            self.stdout.write("")

            self.stdout.write("Staging runbook:")
            for item in result["staging_runbook"]:
                self.stdout.write(f"  - {item}")
            self.stdout.write("")

            self.stdout.write("Production policy:")
            for item in result["production_policy"]:
                self.stdout.write(f"  - {item}")
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
                    self.style.SUCCESS("Bale is ready for staging checks.")
                )

        if result["issues"] and strict:
            raise CommandError(
                "Bale final readiness check failed because --strict treats warnings as blocking issues."
            )
