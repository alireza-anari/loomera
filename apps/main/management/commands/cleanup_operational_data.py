from datetime import timedelta

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.utils import timezone


class Command(BaseCommand):
    help = "Cleanup expired operational data such as report exports and old job runs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
        )
        parser.add_argument(
            "--job-run-days",
            type=int,
            default=30,
        )
        parser.add_argument(
            "--export-limit",
            type=int,
            default=100,
            help=("Maximum number of expired report exports " "to clean in this run."),
        )

    def _delete_queryset(self, qs, label, dry_run):
        count = qs.count()
        if not dry_run:
            qs.delete()
        self.stdout.write(
            f"{label}: {count} {'would be deleted' if dry_run else 'deleted'}"
        )
        return count

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()
        total = 0

        from apps.analytics.services import (
            cleanup_expired_report_exports,
        )
        from apps.main.models import OperationalJobRun

        export_stats = cleanup_expired_report_exports(
            now=now,
            dry_run=dry_run,
            limit=options["export_limit"],
        )

        export_total = export_stats["matched"] if dry_run else export_stats["deleted"]

        total += export_total

        self.stdout.write(
            "report_exports: "
            f"matched={export_stats['matched']} "
            f"deleted={export_stats['deleted']} "
            f"files_deleted="
            f"{export_stats['files_deleted']} "
            f"failed={export_stats['failed']} "
            f"dry_run={dry_run}"
        )

        job_cutoff = now - timedelta(days=options["job_run_days"])
        total += self._delete_queryset(
            OperationalJobRun.objects.filter(started_at__lt=job_cutoff).exclude(
                status="started"
            ),
            "operational_job_runs",
            dry_run,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Cleanup finished. total={total} dry_run={dry_run}")
        )
