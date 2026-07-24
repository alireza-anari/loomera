from django.core.management.base import BaseCommand
from apps.main.infrastructure import run_scheduled_tasks


class Command(BaseCommand):
    help = "Run Loomera cron-safe scheduled tasks bundle."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Run tasks in dry-run mode where supported.")
        parser.add_argument("--skip-daily-metrics", action="store_true", help="Skip DailyMetric snapshot build.")
        parser.add_argument("--limit", type=int, default=100, help="Processing limit for queue-like tasks.")

    def handle(self, *args, **options):
        results = run_scheduled_tasks(
            daily_metrics=not options[
                "skip_daily_metrics"
            ],
            dry_run=options["dry_run"],
            limit=options["limit"],
        )

        if options["dry_run"]:
            native_dry_runs = sum(
                result.get("status") == "dry_run"
                for result in results
            )
            skipped = sum(
                result.get("status")
                == "skipped_no_native_dry_run"
                for result in results
            )

            self.stdout.write(
                self.style.WARNING(
                    "Scheduled task bundle dry-run "
                    "completed | "
                    f"native_dry_runs={native_dry_runs} | "
                    "skipped_without_native_dry_run="
                    f"{skipped} | "
                    f"total={len(results)}"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Scheduled task bundle completed: "
                f"{len(results)} tasks"
            )
        )
