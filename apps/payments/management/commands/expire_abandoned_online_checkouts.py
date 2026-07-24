from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.orders.lifecycle import cancel_order_reminder
from apps.orders.models import Order
from apps.payments.finance import cancel_order_with_financials
from apps.payments.models import Payment


logger = logging.getLogger(__name__)


ABANDONED_REASON = "مهلت پرداخت آنلاین به پایان رسید و رزرو آزاد شد."


def _is_abandoned_checkout_candidate(payment: Payment) -> bool:
    if payment.purpose != Payment.Purpose.APPOINTMENT:
        return False

    if payment.state not in {
        Payment.State.INITIATED,
        Payment.State.PENDING,
    }:
        return False

    if payment.is_finally:
        return False

    if not payment.order_id:
        return False

    if not payment.gateway_track_id:
        return False

    meta = payment.meta or {}

    if meta.get("verify_pending"):
        return False

    order = payment.order

    if order.selected_payment_method != "online":
        return False

    if order.is_paid or order.is_finally:
        return False

    if order.status == "cancelled":
        return False

    if order.status not in {"pending", "confirmed"}:
        return False

    return True


def _expire_payment(payment: Payment, *, reason: str) -> str:
    if not _is_abandoned_checkout_candidate(payment):
        return "skipped_not_candidate"

    now = timezone.now()

    payment.mark_failure(
        state=Payment.State.CANCELLED,
        status_code=-30,
        meta={
            "abandoned_checkout": {
                "expired": True,
                "reason": reason,
                "expired_at": now.isoformat(),
            }
        },
    )

    cancel_order_with_financials(
        order=payment.order,
        reason=reason,
        refund_reason=reason,
        payment=payment,
    )

    cancel_order_reminder(payment.order)

    return "expired"


class Command(BaseCommand):
    help = (
        "آزادسازی رزروهای پرداخت آنلاین که کاربر آن‌ها را "
        "در درگاه رها کرده و callback موفق/لغو/شکست دریافت نشده است."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="اعمال تغییر واقعی. بدون این گزینه فقط dry-run انجام می‌شود.",
        )
        parser.add_argument(
            "--max-age-minutes",
            type=int,
            default=30,
            help="حداقل سن پرداخت آنلاین رهاشده بر حسب دقیقه.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="حداکثر تعداد پرداخت برای بررسی.",
        )
        parser.add_argument(
            "--payment-id",
            type=int,
            action="append",
            default=[],
            help="فقط Paymentهای مشخص بررسی شوند. قابل تکرار است.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        max_age_minutes = int(options["max_age_minutes"])

        if max_age_minutes < 0:
            raise SystemExit("--max-age-minutes cannot be negative")
        limit = max(
            int(options["limit"] or 50),
            1,
        )
        payment_ids = options["payment_id"] or []

        cutoff = timezone.now() - timedelta(
            minutes=max_age_minutes
        )

        queryset = (
            Payment.objects.select_related(
                "order",
                "order__customer",
                "order__salon",
                "customer",
                "customer__user",
            )
            .filter(
                purpose=Payment.Purpose.APPOINTMENT,
                state__in=[
                    Payment.State.INITIATED,
                    Payment.State.PENDING,
                ],
                is_finally=False,
                provider__in=[
                    Payment.Provider.ZIBAL,
                    Payment.Provider.MOCK,
                ],
                order__isnull=False,
                order__selected_payment_method="online",
                order__is_paid=False,
                order__is_finally=False,
                order__status__in=[
                    "pending",
                    "confirmed",
                ],
                gateway_track_id__isnull=False,
                update_date__lte=cutoff,
            )
            .exclude(gateway_track_id="")
            .exclude(meta__verify_pending__isnull=False)
            .order_by("update_date", "id")
        )

        if payment_ids:
            queryset = queryset.filter(pk__in=payment_ids)

        payments = list(queryset[:limit])

        mode_label = "APPLY" if apply_changes else "DRY-RUN"

        counters = {
            "checked": 0,
            "expired": 0,
            "skipped": 0,
            "errors": 0,
        }

        self.stdout.write(
            self.style.NOTICE(
                f"=== Expire abandoned online checkouts | {mode_label} ==="
            )
        )
        self.stdout.write(
            f"max_age_minutes={max_age_minutes}"
        )
        self.stdout.write(
            f"candidates={len(payments)}"
        )

        for payment in payments:
            counters["checked"] += 1

            try:
                if not _is_abandoned_checkout_candidate(payment):
                    action = "skipped_not_candidate"
                    counters["skipped"] += 1

                elif not apply_changes:
                    action = "expire_candidate"

                else:
                    with transaction.atomic():
                        locked_payment = (
                            Payment.objects.select_for_update(
                                of=("self",)
                            )
                            .select_related(
                                "order",
                                "order__customer",
                                "order__salon",
                                "customer",
                                "customer__user",
                            )
                            .get(pk=payment.pk)
                        )

                        action = _expire_payment(
                            locked_payment,
                            reason=ABANDONED_REASON,
                        )

                    if action == "expired":
                        counters["expired"] += 1
                    else:
                        counters["skipped"] += 1

                self.stdout.write(
                    "payment={payment_id} order={order_id} "
                    "amount={amount} state={state} "
                    "age_since_update={updated} action={action}".format(
                        payment_id=payment.pk,
                        order_id=payment.order_id,
                        amount=int(payment.amount or 0),
                        state=payment.state,
                        updated=payment.update_date.isoformat(),
                        action=action,
                    )
                )

            except Exception as exc:
                counters["errors"] += 1

                logger.error(
                    "Expire abandoned online checkout failed | "
                    "payment=%s | error_type=%s",
                    payment.pk,
                    type(exc).__name__,
                )

                self.stderr.write(
                    self.style.ERROR(
                        f"payment={payment.pk} "
                        "error=processing_failed"
                    )
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.NOTICE("=== Summary ===")
        )

        for key, value in counters.items():
            self.stdout.write(f"{key}={value}")

        if counters["errors"]:
            raise SystemExit(1)