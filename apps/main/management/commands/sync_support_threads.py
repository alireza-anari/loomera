from django.core.management.base import BaseCommand

from apps.main.models import SupportTicket
from apps.main.support_services import initialize_support_ticket


class Command(BaseCommand):
    help = "Create thread messages/events for legacy support tickets."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        qs = SupportTicket.objects.order_by("id")
        if options["limit"]:
            qs = qs[: options["limit"]]
        total = 0
        for ticket in qs:
            total += 1
            if options["dry_run"]:
                self.stdout.write(f"would sync ticket #{ticket.pk}")
                continue
            initialize_support_ticket(ticket, actor=ticket.user, attachment_file=None, request=None)
            self.stdout.write(f"synced ticket #{ticket.pk}")
        self.stdout.write(self.style.SUCCESS(f"processed {total} ticket(s)"))
