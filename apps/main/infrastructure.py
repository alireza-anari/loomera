from __future__ import annotations

import logging
from contextlib import contextmanager

from django.core.management import call_command
from django.utils import timezone

from .models import OperationalJobRun

logger = logging.getLogger(__name__)


@contextmanager
def operational_job(name: str, metadata: dict | None = None):
    run = OperationalJobRun.objects.create(
        job_name=name,
        status=OperationalJobRun.Status.STARTED,
        metadata=metadata or {},
    )
    try:
        yield run
    except Exception as exc:
        logger.exception("Operational job failed: %s", name)
        run.mark_finished(
            status=OperationalJobRun.Status.FAILED,
            summary="failed",
            error_message=f"{exc.__class__.__name__}: {exc}",
        )
        raise
    else:
        run.mark_finished(status=OperationalJobRun.Status.SUCCESS, summary="completed")


def run_management_job(command_name: str, *args, job_name: str | None = None, **options):
    with operational_job(job_name or command_name, {"command": command_name, "options": options}) as run:
        call_command(command_name, *args, **options)
        return run


def run_scheduled_tasks(
    *,
    daily_metrics=True,
    dry_run=False,
    limit=100,
):
    """Run the cron-safe scheduled task bundle.

    Normal execution keeps the existing cron behavior and records an
    OperationalJobRun for every child command.

    ``dry_run=True`` is strictly side-effect free at the scheduler boundary:
    commands with native dry-run support are executed in that mode, while
    commands without native dry-run support are reported as skipped. No
    OperationalJobRun records are created during a dry-run.
    """
    results = []
    today = timezone.localdate()

    task_specs = [
        (
            "dispatch_appointment_notifications",
            [],
            {"limit": limit},
            False,
        ),
        (
            "process_notification_deliveries",
            [],
            {"limit": limit},
            False,
        ),
        (
            "confirm_no_show_after_window",
            [],
            {},
            True,
        ),
        (
            "expire_salon_stories",
            [],
            {},
            True,
        ),
        (
            "process_report_exports",
            [],
            {"limit": min(limit, 25)},
            False,
        ),
    ]

    if daily_metrics:
        task_specs.append(
            (
                "build_daily_metrics",
                [],
                {"date": today.isoformat()},
                False,
            )
        )

    for (
        command_name,
        args,
        base_options,
        supports_native_dry_run,
    ) in task_specs:
        options = dict(base_options)

        if dry_run:
            if not supports_native_dry_run:
                results.append(
                    {
                        "command": command_name,
                        "status": (
                            "skipped_no_native_dry_run"
                        ),
                    }
                )
                continue

            options["dry_run"] = True
            call_command(
                command_name,
                *args,
                **options,
            )
            results.append(
                {
                    "command": command_name,
                    "status": "dry_run",
                }
            )
            continue

        if supports_native_dry_run:
            options["dry_run"] = False

        with operational_job(
            f"scheduled.{command_name}",
            {"dry_run": False},
        ) as run:
            call_command(
                command_name,
                *args,
                **options,
            )
            results.append(
                {
                    "command": command_name,
                    "run_id": run.pk,
                }
            )

    return results
