from django.core.management.base import BaseCommand

from apps.accounts.models import CustomerNotification
from apps.notifications.services import sync_legacy_appointment_notification, sync_legacy_customer_notification
from apps.orders.models import AppointmentNotification


class Command(BaseCommand):
    help = "Sync legacy CustomerNotification and AppointmentNotification records into the unified notification layer."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]
        customer_count = 0
        appointment_count = 0

        for item in CustomerNotification.objects.order_by("-created_at", "-id")[:limit]:
            customer_count += 1
            if not dry_run:
                sync_legacy_customer_notification(item)

        for item in AppointmentNotification.objects.order_by("-created_at", "-id")[:limit]:
            appointment_count += 1
            if not dry_run:
                sync_legacy_appointment_notification(item)

        self.stdout.write(
            self.style.SUCCESS(
                f"Legacy notifications inspected: customer={customer_count}, appointment={appointment_count}, dry_run={dry_run}"
            )
        )
