import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.notifications import (
    notify_booking_created,
    notify_payment_failed,
    notify_payment_success,
    notify_wallet_charge,
    notify_wallet_charge_failed,
)
from apps.orders.lifecycle import (
    cancel_order_reminder,
    mark_review_requested,
    notify_manager_and_stylists_for_booking,
    notify_operational_milestone,
    schedule_order_reminder,
)
from apps.payments.finance import (
    cancel_order_with_financials,
    sync_settlement_for_order,
)
from apps.payments.gateways import verify_payment
from apps.payments.models import Payment, Wallet


logger = logging.getLogger(__name__)


def _find_finalized_booking_conflict(order):
    if not order or not getattr(order, "pk", None):
        return None

    from apps.orders.booking_utils import BLOCKING_STATUSES
    from apps.orders.models import OrderDetail

    details = list(
        order.order_details1.select_related(
            "service",
            "stylist",
            "salon",
        ).order_by("date", "time", "id")
    )

    for detail in details:
        if not detail.stylist_id or not detail.date or not detail.time:
            continue

        booking_end = detail.occupied_until or detail.end_time

        if not booking_end:
            detail.recompute_schedule_snapshots(save=False)
            booking_end = detail.occupied_until or detail.end_time

        if not booking_end:
            continue

        conflict = (
            OrderDetail.objects.select_for_update()
            .filter(
                stylist=detail.stylist,
                date=detail.date,
                time__lt=booking_end,
                end_time__gt=detail.time,
                order__status__in=BLOCKING_STATUSES,
            )
            .filter(Q(order__is_finally=True) | Q(order__is_paid=True))
            .exclude(order=order)
            .select_related("order", "service", "stylist__user")
            .order_by("time", "id")
            .first()
        )

        if conflict:
            return conflict

    return None


def _can_update_pending_payment(payment):
    return (
        payment.state
        in {
            Payment.State.INITIATED,
            Payment.State.PENDING,
        }
        and not payment.is_finally
    )


def _pending_meta_from_result(result, *, source):
    return {
        "verify": result.raw or {},
        "verify_pending": {
            "source": source,
            "retryable": bool(result.retryable),
            "requires_review": bool(result.requires_review),
            "integrity_errors": list(result.integrity_errors),
            "message": result.message or "",
            "checked_at": timezone.now().isoformat(),
        },
    }


def _apply_pending_result(payment, result):
    if not _can_update_pending_payment(payment):
        return "skipped_not_pending"

    payment.mark_pending(
        status_code=result.code,
        meta=_pending_meta_from_result(
            result,
            source="reconcile_command",
        ),
    )

    return "kept_pending"


def _apply_wallet_success(payment, result, *, notify):
    if not _can_update_pending_payment(payment):
        return "skipped_not_pending"

    payment.mark_success(
        ref_id=result.ref_id or payment.ref_id or payment.gateway_track_id,
        track_id=result.track_id or payment.gateway_track_id,
        status_code=result.code or 100,
        meta={
            "card_number": result.card_number,
            "verify": result.raw or {},
            "source": "wallet_charge",
            "reconciled_by_command": True,
            "reconciled_at": timezone.now().isoformat(),
        },
    )

    wallet, _ = Wallet.objects.select_for_update().get_or_create(
        user=payment.customer.user
    )

    wallet.deposit(
        amount=int(payment.amount),
        description=(
            "شارژ کیف پول پس از بازیابی پرداخت نامشخص "
            f"- کد پرداخت: {payment.id}"
        ),
    )

    if notify:
        transaction.on_commit(
            lambda payment=payment: notify_wallet_charge(
                customer=payment.customer,
                payment=payment,
                amount=int(payment.amount),
            )
        )

    return "wallet_success"


def _apply_appointment_success(payment, result, *, notify):
    if not _can_update_pending_payment(payment):
        return "skipped_not_pending"

    payment.mark_success(
        ref_id=result.ref_id or payment.ref_id or payment.gateway_track_id,
        track_id=result.track_id or payment.gateway_track_id,
        status_code=result.code or 100,
        meta={
            "card_number": result.card_number,
            "verify": result.raw or {},
            "reconciled_by_command": True,
            "reconciled_at": timezone.now().isoformat(),
        },
    )

    if not payment.order_id:
        return "appointment_success_without_order"

    order = payment.order
    conflict = _find_finalized_booking_conflict(order)

    if conflict:
        order.is_paid = True
        order.checkout_locked_at = timezone.now()
        order.save(
            update_fields=[
                "is_paid",
                "checkout_locked_at",
                "update_date",
            ]
        )

        cancel_order_with_financials(
            order=order,
            reason=(
                "زمان رزرو قبل از بازیابی پرداخت "
                "توسط کاربر دیگری نهایی شد"
            ),
            refund_reason="عدم دسترسی زمان انتخاب‌شده",
            payment=payment,
        )

        cancel_order_reminder(order)

        if notify:
            transaction.on_commit(
                lambda order=order, payment=payment: notify_payment_failed(
                    customer=order.customer,
                    payment=payment,
                    order=order,
                    action_url="",
                    title="زمان رزرو دیگر آزاد نیست",
                )
            )

        return "appointment_conflict_cancelled"

    order.is_paid = True
    order.is_finally = True
    order.status = (
        "completed"
        if order.service_completed_at or order.status == "completed"
        else "paid"
    )
    order.checkout_locked_at = timezone.now()
    order.save(
        update_fields=[
            "is_paid",
            "is_finally",
            "status",
            "checkout_locked_at",
            "update_date",
        ]
    )

    sync_settlement_for_order(order, payment=payment)

    if order.service_completed_at or order.status == "completed":
        notify_operational_milestone(
            order,
            event_type="payment_completed",
            title="پرداخت رزرو نهایی شد",
            body=(
                "پرداخت رزرو ثبت شد و مسیر ثبت دیدگاه "
                "برای مشتری فعال است."
            ),
        )
        mark_review_requested(order)
    else:
        schedule_order_reminder(order)
        notify_manager_and_stylists_for_booking(
            order,
            event_type="booking_paid",
        )

    if notify:
        transaction.on_commit(
            lambda order=order: notify_booking_created(
                customer=order.customer,
                order=order,
            )
        )
        transaction.on_commit(
            lambda order=order, payment=payment: notify_payment_success(
                customer=order.customer,
                payment=payment,
                order=order,
            )
        )

    return "appointment_success"


def _apply_definitive_failure(payment, result, *, notify):
    if not _can_update_pending_payment(payment):
        return "skipped_not_pending"

    payment.mark_failure(
        status_code=result.code or -2,
        meta={
            "verify": result.raw or {},
            "reconciled_by_command": True,
            "reconciled_failure_at": timezone.now().isoformat(),
        },
    )

    if payment.purpose == Payment.Purpose.WALLET:
        if notify:
            transaction.on_commit(
                lambda payment=payment: notify_wallet_charge_failed(
                    customer=payment.customer,
                    payment=payment,
                    title="تأیید شارژ کیف پول ناموفق بود",
                )
            )

        return "wallet_failed"

    if payment.order_id:
        if (payment.meta or {}).get("source") == "pay_in_salon_online":
            order = payment.order
            order.selected_payment_method = "pay_in_salon"
            order.status = (
                "completed"
                if order.service_completed_at or order.status == "completed"
                else order.status
            )
            order.save(
                update_fields=[
                    "selected_payment_method",
                    "status",
                    "update_date",
                ]
            )
            sync_settlement_for_order(order, payment=payment)

            return "appointment_fallback_pay_in_salon"

        cancel_order_with_financials(
            order=payment.order,
            reason="تایید پرداخت پس از بازیابی ناموفق بود",
            refund_reason="تایید ناموفق پرداخت",
            payment=payment,
        )

        if notify:
            transaction.on_commit(
                lambda payment=payment: notify_payment_failed(
                    customer=payment.customer,
                    payment=payment,
                    order=payment.order,
                    action_url="",
                    title="تأیید پرداخت ناموفق بود",
                )
            )

    return "appointment_failed"


class Command(BaseCommand):
    help = (
        "بازبینی و تعیین‌تکلیف Paymentهای درگاهی که در وضعیت "
        "pending مانده‌اند."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="اعمال تغییر واقعی. بدون این گزینه فقط dry-run انجام می‌شود.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="حداکثر تعداد پرداخت برای بررسی.",
        )
        parser.add_argument(
            "--min-age-minutes",
            type=int,
            default=10,
            help=(
                "فقط پرداخت‌هایی بررسی شوند که حداقل این تعداد "
                "دقیقه از آخرین تغییرشان گذشته است."
            ),
        )
        parser.add_argument(
            "--payment-id",
            type=int,
            action="append",
            default=[],
            help=(
                "فقط یک یا چند Payment مشخص بررسی شود. "
                "قابل تکرار است."
            ),
        )
        parser.add_argument(
            "--notify",
            action="store_true",
            help="ارسال اعلان بعد از apply موفق یا شکست قطعی.",
        )
        parser.add_argument(
            "--finalize-failures",
            action="store_true",
            help=(
                "شکست قطعی درگاه را هم نهایی کند. "
                "در اجرای اولیه توصیه نمی‌شود."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        limit = max(int(options["limit"] or 50), 1)
        min_age_minutes = max(int(options["min_age_minutes"] or 0), 0)
        payment_ids = options["payment_id"] or []
        notify = bool(options["notify"])
        finalize_failures = bool(options["finalize_failures"])

        cutoff = timezone.now() - timedelta(minutes=min_age_minutes)

        queryset = (
            Payment.objects.select_related(
                "customer",
                "customer__user",
                "order",
                "order__customer",
                "order__salon",
            )
            .filter(
                state__in=[
                    Payment.State.INITIATED,
                    Payment.State.PENDING,
                ],
                is_finally=False,
                provider__in=[
                    Payment.Provider.ZIBAL,
                    Payment.Provider.MOCK,
                ],
                update_date__lte=cutoff,
            )
            .exclude(gateway_track_id__isnull=True)
            .exclude(gateway_track_id="")
            .order_by("update_date", "id")
        )

        if payment_ids:
            queryset = queryset.filter(pk__in=payment_ids)

        payments = list(queryset[:limit])

        counters = {
            "checked": 0,
            "success": 0,
            "pending": 0,
            "requires_review": 0,
            "failure": 0,
            "skipped": 0,
            "errors": 0,
        }

        mode_label = "APPLY" if apply_changes else "DRY-RUN"

        self.stdout.write(
            self.style.NOTICE(
                f"=== Reconcile pending gateway payments | {mode_label} ==="
            )
        )
        self.stdout.write(f"candidates={len(payments)}")

        for payment in payments:
            counters["checked"] += 1

            try:
                result = verify_payment(
                    payment=payment,
                    track_id=payment.gateway_track_id,
                )

                if result.success:
                    if not apply_changes:
                        action = "success_candidate"
                    else:
                        with transaction.atomic():
                            locked_payment = (
                                Payment.objects.select_for_update(of=("self",))
                                .select_related(
                                    "customer",
                                    "customer__user",
                                    "order",
                                    "order__customer",
                                    "order__salon",
                                )
                                .get(pk=payment.pk)
                            )

                            if locked_payment.purpose == Payment.Purpose.WALLET:
                                action = _apply_wallet_success(
                                    locked_payment,
                                    result,
                                    notify=notify,
                                )
                            else:
                                action = _apply_appointment_success(
                                    locked_payment,
                                    result,
                                    notify=notify,
                                )

                    counters["success"] += 1

                elif result.retryable or result.requires_review:
                    if result.requires_review:
                        counters["requires_review"] += 1
                    else:
                        counters["pending"] += 1

                    if not apply_changes:
                        action = "pending_candidate"
                    else:
                        with transaction.atomic():
                            locked_payment = (
                                Payment.objects.select_for_update(of=("self",))
                                .get(pk=payment.pk)
                            )
                            action = _apply_pending_result(
                                locked_payment,
                                result,
                            )

                else:
                    counters["failure"] += 1

                    if not apply_changes:
                        action = "failure_candidate"
                    elif finalize_failures:
                        with transaction.atomic():
                            locked_payment = (
                                Payment.objects.select_for_update(of=("self",))
                                .select_related(
                                    "customer",
                                    "customer__user",
                                    "order",
                                    "order__customer",
                                    "order__salon",
                                )
                                .get(pk=payment.pk)
                            )
                            action = _apply_definitive_failure(
                                locked_payment,
                                result,
                                notify=notify,
                            )
                    else:
                        action = "failure_not_finalized"

                self.stdout.write(
                    "payment={id} purpose={purpose} amount={amount} "
                    "result_success={success} retryable={retryable} "
                    "requires_review={requires_review} code={code} "
                    "action={action}".format(
                        id=payment.pk,
                        purpose=payment.purpose,
                        amount=int(payment.amount or 0),
                        success=result.success,
                        retryable=result.retryable,
                        requires_review=result.requires_review,
                        code=result.code,
                        action=action,
                    )
                )

            except Exception as exc:
                counters["errors"] += 1

                logger.error(
                    "Pending gateway payment reconciliation failed | "
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
        self.stdout.write(self.style.NOTICE("=== Summary ==="))

        for key, value in counters.items():
            self.stdout.write(f"{key}={value}")

        if counters["errors"]:
            raise SystemExit(1)