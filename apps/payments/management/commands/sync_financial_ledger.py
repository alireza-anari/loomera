from django.core.management.base import BaseCommand

from apps.payments.ledger import sync_ledger_for_snapshot, sync_staff_earning_from_snapshot
from apps.payments.models import OrderDetailFinancialSnapshot


class Command(BaseCommand):
    help = "Sync StaffEarning and LedgerEntry rows for finalized financial snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Void old ledger entries and recreate them.")
        parser.add_argument("--limit", type=int, default=0, help="Optional max number of snapshots to process.")
        parser.add_argument("--dry-run", action="store_true", help="Only count snapshots without writing.")

    def handle(self, *args, **options):
        qs = (
            OrderDetailFinancialSnapshot.objects.filter(
                status=OrderDetailFinancialSnapshot.Status.FINALIZED
            )
            .select_related("order", "order_detail", "salon", "stylist")
            .order_by("id")
        )
        if options["limit"]:
            qs = qs[: options["limit"]]

        processed = 0
        ledger_entries = 0
        for snapshot in qs:
            processed += 1
            if options["dry_run"]:
                continue
            sync_staff_earning_from_snapshot(snapshot)
            entries = sync_ledger_for_snapshot(snapshot, force=options["force"])
            ledger_entries += len(entries)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"{processed} finalized snapshots would be processed."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Processed {processed} snapshots and synced {ledger_entries} ledger entries."))
