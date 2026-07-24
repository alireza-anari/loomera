from django.core.management.base import BaseCommand

from apps.discounts.models import DiscountSnapshot
from apps.orders.models import Order


class Command(BaseCommand):
    help = "Build lightweight discount snapshot records for existing discounted orders."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = int(options.get("limit") or 0)
        qs = Order.objects.filter(discount_amount__gt=0).order_by("id")
        if limit:
            qs = qs[:limit]
        count = 0
        for order in qs:
            snapshot = {
                "version": 0,
                "legacy": True,
                "coupon_code": order.coupon_code,
                "basket_discount_title": order.basket_discount_title,
                "subtotal": int(order.subtotal_amount or 0),
                "service_discount_amount": int(order.basket_discount_amount or 0),
                "coupon_discount_amount": int(order.coupon_discount_amount or 0),
                "total_discount_amount": int(order.discount_amount or 0),
                "final_amount": int(order.total_amount or 0),
            }
            if dry_run:
                count += 1
                continue
            DiscountSnapshot.objects.update_or_create(
                order=order,
                defaults={
                    "subtotal_amount": int(order.subtotal_amount or 0),
                    "service_discount_amount": int(order.basket_discount_amount or 0),
                    "coupon_discount_amount": int(order.coupon_discount_amount or 0),
                    "total_discount_amount": int(order.discount_amount or 0),
                    "final_amount": int(order.total_amount or 0),
                    "rules_snapshot": snapshot,
                },
            )
            order.discount_rules_snapshot = snapshot
            order.save(update_fields=["discount_rules_snapshot"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Discount snapshots {'would be synced' if dry_run else 'synced'}: {count}"))
