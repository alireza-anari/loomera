from django.core.management.base import BaseCommand

from apps.orders.models import OrderDetail
from apps.orders.appointment_lifecycle import apply_no_show_refund_policy
from apps.payments.models import Payment, PaymentTransaction, WalletTransaction, RefundRequest


class Command(BaseCommand):
    help = "Repair wallet refunds for paid no-show order details, with verbose diagnostics."

    def add_arguments(self, parser):
        parser.add_argument("--detail-id", type=int, default=None, help="Repair a single OrderDetail id")
        parser.add_argument("--order-id", type=int, default=None, help="Repair all details for one Order id")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without writing")
        parser.add_argument("--limit", type=int, default=100, help="Maximum number of details to inspect")
        parser.add_argument(
            "--force-full-refund",
            action="store_true",
            help="Ignore no-show penalty rules and refund the successful digital payment amount. Use only for repairing QA/test data.",
        )

    def _candidate_qs(self, options):
        qs = OrderDetail.objects.select_related(
            "order", "order__customer__user", "salon", "service"
        )
        if options["detail_id"]:
            return qs.filter(pk=options["detail_id"])
        if options["order_id"]:
            return qs.filter(order_id=options["order_id"]).order_by("id")
        return qs.filter(no_show_confirmed_at__isnull=False).order_by("-no_show_confirmed_at", "-id")[: int(options["limit"] or 100)]

    def _diagnose(self, detail):
        order = detail.order
        user = getattr(getattr(order, "customer", None), "user", None)
        return {
            "detail": detail.pk,
            "order": order.pk,
            "method": getattr(order, "selected_payment_method", ""),
            "is_paid": getattr(order, "is_paid", None),
            "order_total": int(getattr(order, "total_amount", 0) or 0),
            "detail_price": int(getattr(detail, "price", 0) or 0),
            "confirmed": bool(getattr(detail, "no_show_confirmed_at", None)),
            "order_refunded": int(getattr(order, "refunded_to_wallet_amount", 0) or 0),
            "payments": list(Payment.objects.filter(order=order).values("id", "provider", "state", "is_finally", "amount")[:5]),
            "payment_transactions": list(PaymentTransaction.objects.filter(order=order).values("id", "method", "status", "amount")[:5]),
            "wallet_refunds": list(WalletTransaction.objects.filter(wallet__user=user, order=order, transaction_type="REFUND").values("id", "amount", "description")[:5]) if user else [],
            "refund_requests": list(RefundRequest.objects.filter(order=order).values("id", "amount", "status", "reason")[:5]),
        }

    def handle(self, *args, **options):
        qs = self._candidate_qs(options)
        processed = refunded = skipped = failed = 0

        for detail in qs:
            processed += 1
            diag = self._diagnose(detail)
            self.stdout.write(f"DIAG {diag}")
            if options["dry_run"]:
                skipped += 1
                continue
            try:
                result = apply_no_show_refund_policy(
                    detail=detail,
                    actor=None,
                    force_full_refund=bool(options["force_full_refund"]),
                )
                amount = int(result.get("refund_amount") or 0)
                credited = int(result.get("credited") or 0)
                if result.get("eligible") and (amount > 0 or credited > 0):
                    refunded += 1
                    self.stdout.write(self.style.SUCCESS(f"REPAIRED detail={detail.pk} order={detail.order_id} result={result}"))
                elif result.get("eligible"):
                    skipped += 1
                    self.stdout.write(f"ELIGIBLE_ZERO detail={detail.pk} order={detail.order_id} result={result}")
                else:
                    skipped += 1
                    self.stdout.write(f"SKIPPED detail={detail.pk} order={detail.order_id} result={result}")
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"FAILED detail={detail.pk} order={detail.order_id} {exc.__class__.__name__}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"No-show refund repair completed: processed={processed}, refunded={refunded}, skipped={skipped}, failed={failed}, dry_run={options['dry_run']}"
        ))
