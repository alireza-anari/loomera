from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.orders.appointment_lifecycle import confirm_no_show
from apps.orders.models import OrderDetail


class Command(BaseCommand):
    help = "Confirm pending no-show records whose review/dispute window has expired."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        now = timezone.now()
        limit = max(int(options.get("limit") or 100), 1)
        ids = list(
            OrderDetail.objects.filter(
                no_show_pending_at__isnull=False,
                no_show_confirmed_at__isnull=True,
                no_show_dispute_until__isnull=False,
                no_show_dispute_until__lte=now,
            ).order_by("no_show_dispute_until", "id").values_list("id", flat=True)[:limit]
        )
        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING(f"{len(ids)} pending no-show records are ready to confirm."))
            return
        count = 0
        for detail_id in ids:
            with transaction.atomic():
                detail = OrderDetail.objects.select_for_update().get(pk=detail_id)
                confirm_no_show(detail=detail, actor=None, note="تایید خودکار پس از پایان مهلت بررسی")
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Confirmed {count} no-show records."))
