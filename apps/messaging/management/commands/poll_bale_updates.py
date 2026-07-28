from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.bale_bot.polling import BalePollingError, poll_bale_updates


class Command(BaseCommand):
    help = "Poll pending Bale updates safely when webhook delivery is unavailable."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum updates to fetch in one run (1-100).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=None,
            help="Provider long-poll timeout in seconds. Cron should normally use 0.",
        )

    def handle(self, *args, **options):
        try:
            result = poll_bale_updates(
                limit=options.get("limit"),
                timeout=options.get("timeout"),
            )
        except BalePollingError as exc:
            raise CommandError(str(exc)) from exc

        payload = result.as_dict()
        self.stdout.write(
            "Bale polling | "
            f"status={payload['status']} | "
            f"fetched={payload['fetched']} | "
            f"processed={payload['processed']} | "
            f"duplicates={payload['duplicates']} | "
            f"next_offset={payload['next_offset']} | "
            f"failed_update_id={payload['failed_update_id']}"
        )

        if result.status in {"failed", "provider_error"}:
            raise CommandError(
                "Bale polling did not complete successfully: "
                f"status={result.status} error={result.error or 'unknown'}"
            )
