from django.core.management.base import BaseCommand

from apps.notifications.delivery import process_queued_deliveries


class Command(BaseCommand):
    help = "Process queued unified notification deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--include-failed", action="store_true")

    def handle(self, *args, **options):
        result = process_queued_deliveries(limit=options["limit"], include_failed=options["include_failed"])
        self.stdout.write(self.style.SUCCESS(f"Processed notification deliveries: {result}"))
