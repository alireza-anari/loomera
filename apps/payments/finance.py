from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.orders.models import AppointmentNotification, Order, OrderDetail

from .ledger import sync_ledger_for_snapshot, sync_staff_earning_from_snapshot
from .models import (
    ExtraCharge,
    OrderDetailFinancialSnapshot,
    Payment,
    RefundRequest,
    SalonSettlement,
    SalonWallet,
    StylistWallet,
    Wallet,
    WalletTransaction,
)


DIGITAL_PAYMENT_METHODS = {"online", "wallet"}
logger = logging.getLogger(__name__)


def _lock_self(queryset):
    """
    در PostgreSQL وقتی select_related شامل FK nullable باشد،
    FOR UPDATE روی outer join خطا می‌دهد.
    با of=("self",) فقط جدول اصلی قفل می‌شود.
    """
    if connection.features.has_select_for_update_of:
        return queryset.select_for_update(of=("self",))
    return queryset.select_for_update()


@dataclass
class OrderCancellationResult:
    order: Order
    refund_amount: int = 0
    already_cancelled: bool = False


def _round_money(value) -> int:
    amount = Decimal(value or 0)
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def wallet_refund_amount_for_order(order: Order) -> int:
    """
    مبلغ واقعی بازگشت وجه ثبت‌شده در کیف پول مشتری برای این سفارش.
    این fallback باعث می‌شود اگر order.refunded_to_wallet_amount به هر دلیل sync نشده بود،
    گزارش‌های مالی همچنان مقدار درست را بخوانند.
    """
    try:
        total = (
            WalletTransaction.objects.filter(
                order=order,
                transaction_type=WalletTransaction.TransactionType.REFUND,
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        return max(_safe_int(total), 0)
    except Exception:
        return 0


def ensure_order_refund_fields_from_wallet(order: Order) -> int:
    """
    اگر refund در WalletTransaction وجود دارد اما روی خود Order ذخیره نشده،
    فیلدهای order را با کیف پول sync می‌کند.
    """
    wallet_refund_amount = wallet_refund_amount_for_order(order)

    if wallet_refund_amount <= 0:
        return max(_safe_int(getattr(order, "refunded_to_wallet_amount", 0)), 0)

    order_refund_amount = max(
        _safe_int(getattr(order, "refunded_to_wallet_amount", 0)), 0
    )

    if wallet_refund_amount > order_refund_amount:
        last_refund_tx = (
            WalletTransaction.objects.filter(
                order=order,
                transaction_type=WalletTransaction.TransactionType.REFUND,
            )
            .order_by("-created_at")
            .first()
        )

        order.refunded_to_wallet_amount = wallet_refund_amount
        order.refunded_to_wallet_at = (
            last_refund_tx.created_at if last_refund_tx else timezone.now()
        )
        order.save(update_fields=["refunded_to_wallet_amount", "refunded_to_wallet_at"])

    return max(wallet_refund_amount, order_refund_amount)


def _no_show_refund_amount_for_order(order: Order) -> int:
    """Return wallet refund amount that belongs to no-show compensation.

    No-show wallet refunds are paid back to the customer but should not be
    treated as salon/stylist costs.  They are tracked through RefundRequest and
    customer WalletTransaction only.
    """
    if not getattr(order, "pk", None):
        return 0
    try:
        total = (
            RefundRequest.objects.filter(
                order=order,
                reason__icontains="عدم حضور",
            )
            .exclude(status=RefundRequest.Status.REJECTED)
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        return max(int(total or 0), 0)
    except Exception:
        return 0


def _settlement_refund_amount_for_order(order: Order) -> int:
    """
    Refund amount that should affect salon settlement.

    Cancellation refunds reduce salon settlement.
    Confirmed no-show wallet refunds must not appear as salon/stylist cost lines,
    so they are excluded.
    """
    total_refund = max(
        ensure_order_refund_fields_from_wallet(order),
        _safe_int(getattr(order, "refunded_to_wallet_amount", 0)),
    )
    no_show_refund = _no_show_refund_amount_for_order(order)
    return max(total_refund - no_show_refund, 0)


def get_pay_in_salon_cash_payment(order: Order) -> Payment | None:
    """
    آخرین رکورد پرداخت نقدی/حضوری مربوط به سفارش را برمی‌گرداند.
    این رکورد تا قبل از تایید دوطرفه در state=pending می‌ماند.
    """
    return (
        order.payment_order.filter(
            purpose=Payment.Purpose.APPOINTMENT,
            provider=Payment.Provider.MANUAL,
            meta__source="pay_in_salon_cash",
        )
        .order_by("-id")
        .first()
    )


def get_pay_in_salon_cash_confirmation_state(order: Order) -> dict:
    payment = get_pay_in_salon_cash_payment(order)
    meta = payment.meta if payment and isinstance(payment.meta, dict) else {}
    customer_confirmed = bool(meta.get("customer_confirmed_at"))
    stylist_confirmed = bool(meta.get("stylist_confirmed_at"))
    finalized = bool(payment and payment.state == Payment.State.SUCCESS and payment.is_finally)
    return {
        "payment": payment,
        "customer_confirmed": customer_confirmed,
        "stylist_confirmed": stylist_confirmed,
        "finalized": finalized,
        "awaiting_customer": bool(payment and stylist_confirmed and not customer_confirmed and not finalized),
        "awaiting_stylist": bool(payment and customer_confirmed and not stylist_confirmed and not finalized),
    }


def _get_or_create_pay_in_salon_cash_payment(order: Order) -> Payment:
    payment = get_pay_in_salon_cash_payment(order)
    if payment:
        return payment

    return Payment.objects.create(
        order=order,
        customer=order.customer,
        amount=order.total_amount,
        description=f"تایید دوطرفه پرداخت نقدی در سالن - سفارش {order.order_number}",
        provider=Payment.Provider.MANUAL,
        purpose=Payment.Purpose.APPOINTMENT,
        state=Payment.State.PENDING,
        sandbox_mode=True,
        callback_token=secrets.token_urlsafe(24),
        idempotency_key=uuid.uuid4().hex,
        meta={"source": "pay_in_salon_cash"},
    )


@transaction.atomic
def confirm_pay_in_salon_cash_payment(order: Order, *, actor=None, role: str) -> dict:
    """
    پرداخت نقدی بعد از پایان خدمت فقط وقتی نهایی می‌شود که هم مشتری و هم متخصص
    آن را تایید کرده باشند. برای جلوگیری از migration جدید، وضعیت تاییدها در meta
    رکورد Payment نگهداری می‌شود.
    """
    if role not in {"customer", "stylist"}:
        raise ValidationError("نقش تاییدکننده پرداخت معتبر نیست.")

    locked_order = (
        _lock_self(Order.objects)
        .select_related("customer", "salon")
        .get(pk=order.pk)
    )

    if locked_order.status == "cancelled":
        raise ValidationError("این رزرو لغو شده و امکان تایید پرداخت ندارد.")

    if not (locked_order.service_completed_at or locked_order.status == "completed"):
        raise ValidationError("تایید پرداخت حضوری فقط بعد از پایان خدمت امکان‌پذیر است.")

    if locked_order.is_paid:
        return {"order": locked_order, "payment": get_pay_in_salon_cash_payment(locked_order), "already_paid": True, "finalized": True}

    payment = _get_or_create_pay_in_salon_cash_payment(locked_order)
    payment = _lock_self(Payment.objects).get(pk=payment.pk)
    meta = payment.meta if isinstance(payment.meta, dict) else {}
    now_iso = timezone.now().isoformat()
    actor_id = getattr(actor, "pk", None)

    if role == "customer":
        meta.setdefault("customer_confirmed_at", now_iso)
        if actor_id:
            meta.setdefault("customer_confirmed_by", actor_id)
    else:
        meta.setdefault("stylist_confirmed_at", now_iso)
        if actor_id:
            meta.setdefault("stylist_confirmed_by", actor_id)

    payment.meta = {**meta, "source": "pay_in_salon_cash"}
    payment.state = Payment.State.PENDING
    payment.is_finally = False
    payment.save(update_fields=["meta", "state", "is_finally", "update_date"])

    customer_confirmed = bool(payment.meta.get("customer_confirmed_at"))
    stylist_confirmed = bool(payment.meta.get("stylist_confirmed_at"))

    finalized = False
    if customer_confirmed and stylist_confirmed:
        payment.mark_success(
            ref_id=f"MANUAL-{payment.id}",
            track_id=f"manual-{payment.id}",
            status_code=100,
            meta={"source": "pay_in_salon_cash", "confirmed_at": timezone.now().isoformat()},
        )
        locked_order.is_paid = True
        locked_order.is_finally = True
        locked_order.selected_payment_method = "pay_in_salon"
        locked_order.status = "completed"
        locked_order.checkout_locked_at = timezone.now()
        locked_order.save(update_fields=["is_paid", "is_finally", "selected_payment_method", "status", "checkout_locked_at", "update_date"])
        sync_settlement_for_order(locked_order, payment=payment)

        from apps.orders.lifecycle import mark_review_requested, notify_operational_milestone

        notify_operational_milestone(
            locked_order,
            event_type="payment_completed",
            title="پرداخت نقدی رزرو تایید شد",
            body="پرداخت حضوری این رزرو توسط مشتری و متخصص تایید شد و مسیر ثبت دیدگاه فعال است.",
        )
        mark_review_requested(locked_order)
        finalized = True
    else:
        sync_settlement_for_order(locked_order, payment=payment)
        from apps.orders.lifecycle import notify_operational_milestone

        waiting_for = "متخصص" if role == "customer" else "مشتری"
        notify_operational_milestone(
            locked_order,
            event_type="pay_in_salon_pending",
            title="تایید پرداخت نقدی در انتظار تکمیل است",
            body=f"پرداخت نقدی توسط {('مشتری' if role == 'customer' else 'متخصص')} تایید شد و اکنون منتظر تایید {waiting_for} است.",
        )

    return {
        "order": locked_order,
        "payment": payment,
        "already_paid": False,
        "finalized": finalized,
        "customer_confirmed": customer_confirmed,
        "stylist_confirmed": stylist_confirmed,
    }


def _allocate_amount_to_details(
    amount: int, details: list[OrderDetail]
) -> dict[int, int]:
    """
    یک مبلغ کلی مثل تخفیف یا کارمزد پلتفرم را به نسبت قیمت هر آیتم رزرو تقسیم می‌کند.
    خروجی دقیقاً با مبلغ ورودی برابر می‌شود و اختلاف رند شدن روی آخرین آیتم می‌افتد.
    """
    amount = _safe_int(amount)
    result = {detail.pk: 0 for detail in details}

    if amount <= 0 or not details:
        return result

    total_weight = sum(max(_safe_int(detail.price), 0) for detail in details)
    if total_weight <= 0:
        return result

    running_weight = 0
    previous_cumulative = 0

    for detail in details:
        running_weight += max(_safe_int(detail.price), 0)
        cumulative = _round_money(
            Decimal(amount) * Decimal(running_weight) / Decimal(total_weight)
        )
        result[detail.pk] = max(cumulative - previous_cumulative, 0)
        previous_cumulative = cumulative

    diff = amount - sum(result.values())
    if diff and details:
        result[details[-1].pk] = max(result[details[-1].pk] + diff, 0)

    return result


def _get_detail_allocations(
    order: Order, details: list[OrderDetail]
) -> dict[str, dict[int, int]]:
    """
    تخفیف و کارمزد پلتفرم را بین آیتم‌های رزرو تقسیم می‌کند.
    """
    discount_amount = _safe_int(order.discount_amount or order.discount)
    platform_commission_amount = _safe_int(order.platform_commission_amount)

    return {
        "discount": _allocate_amount_to_details(discount_amount, details),
        "platform_commission": _allocate_amount_to_details(
            platform_commission_amount, details
        ),
    }


def _get_settlement_for_order(order: Order):
    try:
        return order.salon_settlement
    except SalonSettlement.DoesNotExist:
        return None


def _build_material_snapshot(detail: OrderDetail) -> list[dict]:
    usages = detail.material_usages.select_related(
        "material", "source_template"
    ).order_by("id")

    items = []

    for usage in usages:
        items.append(
            {
                "usage_id": usage.pk,
                "material_id": usage.material_id,
                "material_name": usage.material.name if usage.material_id else "",
                "source_template_id": usage.source_template_id,
                "quantity": str(usage.quantity),
                "unit_cost": _safe_int(usage.unit_cost),
                "total_cost": _safe_int(usage.total_cost),
                "paid_by": usage.paid_by,
            }
        )

    return items


def _split_material_costs(
    *, material_snapshot: list[dict], rule=None
) -> tuple[int, int]:
    """
    خروجی:
    material_cost_paid_by_salon, material_cost_paid_by_stylist

    اولویت با سیاست تعریف‌شده در StylistCommissionRule است.
    اگر قانون سهم وجود نداشته باشد، paid_by ثبت‌شده روی مواد مصرفی ملاک قرار می‌گیرد.
    """
    total = sum(_safe_int(item.get("total_cost")) for item in material_snapshot)

    if total <= 0:
        return 0, 0

    if rule:
        if rule.material_cost_policy == rule.MaterialCostPolicy.SALON_PAYS:
            return total, 0

        if rule.material_cost_policy == rule.MaterialCostPolicy.STYLIST_PAYS:
            return 0, total

        if rule.material_cost_policy == rule.MaterialCostPolicy.SPLIT:
            stylist_percent = Decimal(rule.stylist_material_cost_percent or 0)
            stylist_cost = _round_money(
                Decimal(total) * stylist_percent / Decimal("100")
            )
            stylist_cost = min(max(stylist_cost, 0), total)
            salon_cost = total - stylist_cost
            return salon_cost, stylist_cost

    salon_cost = 0
    stylist_cost = 0

    for item in material_snapshot:
        item_total = _safe_int(item.get("total_cost"))
        paid_by = item.get("paid_by")

        if paid_by == "stylist":
            stylist_cost += item_total
        elif paid_by == "shared":
            stylist_part = _round_money(Decimal(item_total) * Decimal("0.5"))
            stylist_cost += stylist_part
            salon_cost += item_total - stylist_part
        else:
            salon_cost += item_total

    return salon_cost, stylist_cost


def _build_rule_snapshot(rule) -> dict:
    if not rule:
        return {}

    return {
        "rule_id": rule.pk,
        "commission_type": rule.commission_type,
        "percent": str(rule.percent),
        "fixed_amount": _safe_int(rule.fixed_amount),
        "share_base": rule.share_base,
        "material_cost_policy": rule.material_cost_policy,
        "stylist_material_cost_percent": str(rule.stylist_material_cost_percent),
        "effective_from": (
            rule.effective_from.isoformat() if rule.effective_from else None
        ),
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
    }


def _calculate_stylist_gross_share(*, rule, share_base_amount: int) -> int:
    if not rule:
        return 0

    share_base_amount = max(_safe_int(share_base_amount), 0)

    if share_base_amount <= 0:
        return 0

    if rule.commission_type == rule.CommissionType.FIXED:
        return min(_safe_int(rule.fixed_amount), share_base_amount)

    percent = Decimal(rule.percent or 0)
    amount = _round_money(Decimal(share_base_amount) * percent / Decimal("100"))
    return min(max(amount, 0), share_base_amount)


@transaction.atomic
def calculate_order_detail_financials(
    order_detail: OrderDetail,
    *,
    settlement: SalonSettlement | None = None,
    force: bool = False,
) -> OrderDetailFinancialSnapshot:
    """
    محاسبه مالی یک آیتم رزرو را انجام می‌دهد و نتیجه را در OrderDetailFinancialSnapshot ذخیره می‌کند.
    این تابع فقط سند را می‌سازد/آپدیت می‌کند؛ واریز کیف پول در finalize انجام می‌شود.
    """
    from apps.services.models import StylistCommissionRule

    detail = (
        _lock_self(OrderDetail.objects)
        .select_related("order", "salon", "service", "stylist")
        .get(pk=order_detail.pk)
    )
    order = detail.order

    existing = getattr(detail, "financial_snapshot", None)
    if (
        existing
        and existing.status == OrderDetailFinancialSnapshot.Status.FINALIZED
        and not force
    ):
        return existing

    all_details = list(
        order.order_details1.select_related("salon", "service", "stylist").order_by(
            "id"
        )
    )

    allocations = _get_detail_allocations(order, all_details)

    gross_amount = max(_safe_int(detail.price), 0)
    approved_extra_charges = _safe_int(
        ExtraCharge.objects.filter(
            order_detail=detail,
            status__in=[
                ExtraCharge.Status.APPROVED,
                ExtraCharge.Status.MANAGER_APPROVED,
            ],
        ).aggregate(total=Sum("amount"))["total"]
    )

    discount_allocated = min(
        _safe_int(allocations["discount"].get(detail.pk)),
        gross_amount,
    )
    paid_amount_allocated = max(gross_amount - discount_allocated, 0) + approved_extra_charges

    platform_commission_allocated = min(
        _safe_int(allocations["platform_commission"].get(detail.pk)),
        paid_amount_allocated,
    )
    net_after_platform = max(paid_amount_allocated - platform_commission_allocated, 0)

    if settlement is None:
        settlement = _get_settlement_for_order(order)

    rule = StylistCommissionRule.get_active_for(
        salon=detail.salon,
        stylist=detail.stylist,
        service=detail.service,
        at_date=detail.date or timezone.localdate(),
    )

    material_snapshot = _build_material_snapshot(detail)
    material_cost_total = sum(
        _safe_int(item.get("total_cost")) for item in material_snapshot
    )
    material_cost_paid_by_salon, material_cost_paid_by_stylist = _split_material_costs(
        material_snapshot=material_snapshot,
        rule=rule,
    )


    if rule:
        if rule.share_base == rule.ShareBase.GROSS_AFTER_DISCOUNT:
            share_base_amount = paid_amount_allocated
        elif rule.share_base == rule.ShareBase.AFTER_PLATFORM_COMMISSION:
            share_base_amount = net_after_platform
        else:
            share_base_amount = max(net_after_platform - material_cost_total, 0)
    else:
        share_base_amount = net_after_platform

    stylist_gross_share = _calculate_stylist_gross_share(
        rule=rule,
        share_base_amount=share_base_amount,
    )

    if rule and rule.share_base == rule.ShareBase.NET_AFTER_MATERIALS:
        # وقتی مبنای سهم سود خالص است، هزینه مواد قبلاً از مبنای تقسیم کم شده است.
        stylist_material_deduction = material_cost_paid_by_stylist
        salon_material_deduction = material_cost_paid_by_salon

        stylist_net_share = stylist_gross_share
        salon_net_share = max(share_base_amount - stylist_gross_share, 0)
        salon_gross_share = salon_net_share
        salon_net_profit = salon_net_share
    else:
        stylist_material_deduction = material_cost_paid_by_stylist
        salon_material_deduction = material_cost_paid_by_salon

        stylist_net_share = max(stylist_gross_share - stylist_material_deduction, 0)
        salon_gross_share = max(net_after_platform - stylist_gross_share, 0)
        salon_net_share = max(salon_gross_share - salon_material_deduction, 0)
        salon_net_profit = salon_net_share

    calculation_snapshot = {
        "gross_amount": gross_amount,
        "discount_allocated": discount_allocated,
        "paid_amount_allocated": paid_amount_allocated,
        "platform_commission_allocated": platform_commission_allocated,
        "net_after_platform": net_after_platform,
        "material_cost_total": material_cost_total,
        "material_cost_paid_by_salon": material_cost_paid_by_salon,
        "material_cost_paid_by_stylist": material_cost_paid_by_stylist,
        "share_base_amount": share_base_amount,
        "stylist_gross_share": stylist_gross_share,
        "stylist_material_deduction": stylist_material_deduction,
        "stylist_net_share": stylist_net_share,
        "salon_gross_share": salon_gross_share,
        "salon_material_deduction": salon_material_deduction,
        "salon_net_share": salon_net_share,
        "salon_net_profit": salon_net_profit,
        "note": "در این نسخه، مبالغ کیف پول بر اساس سهم/سود خالص بعد از هزینه مواد محاسبه می‌شود.",
    }

    snapshot, _ = OrderDetailFinancialSnapshot.objects.update_or_create(
        order_detail=detail,
        defaults={
            "order": order,
            "settlement": settlement,
            "salon": detail.salon,
            "stylist": detail.stylist,
            "service": detail.service,
            "commission_rule": rule,
            "payment_method": order.selected_payment_method or "",
            "payment_provider": settlement.payment_provider if settlement else "",
            "gross_amount": gross_amount,
            "discount_allocated": discount_allocated,
            "paid_amount_allocated": paid_amount_allocated,
            "platform_commission_allocated": platform_commission_allocated,
            "net_after_platform": net_after_platform,
            "material_cost_total": material_cost_total,
            "material_cost_paid_by_salon": material_cost_paid_by_salon,
            "material_cost_paid_by_stylist": material_cost_paid_by_stylist,
            "share_base_amount": share_base_amount,
            "stylist_gross_share": stylist_gross_share,
            "stylist_material_deduction": stylist_material_deduction,
            "stylist_net_share": stylist_net_share,
            "salon_gross_share": salon_gross_share,
            "salon_material_deduction": salon_material_deduction,
            "salon_net_share": salon_net_share,
            "salon_net_profit": salon_net_profit,
            "extra_charges_amount": approved_extra_charges,
            "total_customer_paid": paid_amount_allocated + approved_extra_charges,
            "salon_customer_compensation": 0,
            # No-show refunds are customer wallet compensations and must not be
            # shown as salon/stylist costs in item-level finance.
            "salon_refund_amount": _settlement_refund_amount_for_order(order),
            "rule_snapshot": _build_rule_snapshot(rule),
            "material_snapshot": material_snapshot,
            "calculation_snapshot": calculation_snapshot,
        },
    )

    return snapshot


def _calculate_payout_state(order, salon, *, net_due: int):
    if order.selected_payment_method == "pay_in_salon":
        return (
            (
                SalonSettlement.PayoutState.MANUAL_COLLECTION
                if order.status != "cancelled"
                else SalonSettlement.PayoutState.CANCELLED
            ),
            "دریافت وجه در سالن انجام می‌شود.",
        )

    if not order.is_paid:
        return (
            (
                SalonSettlement.PayoutState.AWAITING_PAYMENT
                if order.status != "cancelled"
                else SalonSettlement.PayoutState.CANCELLED
            ),
            "پرداخت دیجیتال هنوز نهایی نشده است.",
        )

    if net_due <= 0 and order.status == "cancelled":
        return (
            SalonSettlement.PayoutState.CANCELLED,
            "پس از بازگشت وجه، مبلغی برای تسویه باقی نمانده است.",
        )

    if not getattr(salon, "payout_profile_complete", False):
        return SalonSettlement.PayoutState.HOLD, "اطلاعات امور مالی سالن ناقص است."

    return SalonSettlement.PayoutState.READY, ""


def _desired_salon_wallet_amount(settlement: SalonSettlement) -> int:
    if settlement.payout_state == SalonSettlement.PayoutState.CANCELLED:
        return 0

    if settlement.payment_method not in DIGITAL_PAYMENT_METHODS:
        return 0

    if int(settlement.paid_amount or 0) <= 0:
        return 0

    use_detail_finance = getattr(settings, "LOOMERA_USE_DETAIL_FINANCE", True)

    if use_detail_finance:
        total = settlement.detail_snapshots.filter(
            status=OrderDetailFinancialSnapshot.Status.FINALIZED,
        ).aggregate(total=Sum("salon_net_share"))["total"]

        return max(_safe_int(total), 0)

    return max(int(settlement.net_amount_due_to_salon or 0), 0)


@transaction.atomic
def sync_salon_wallet_for_settlement(settlement: SalonSettlement):
    if settlement.salon_id is None:
        return None

    locked_settlement = (
        _lock_self(SalonSettlement.objects)
        .select_related("order", "salon")
        .get(pk=settlement.pk)
    )

    wallet, _ = SalonWallet.objects.get_or_create(salon=locked_settlement.salon)
    wallet = SalonWallet.objects.select_for_update().get(pk=wallet.pk)

    aggregates = locked_settlement.wallet_transactions.aggregate(
        pending=Sum("pending_delta"),
        available=Sum("available_delta"),
    )

    pending_component = int(aggregates.get("pending") or 0)
    available_component = int(aggregates.get("available") or 0)
    current_total = pending_component + available_component
    desired_total = _desired_salon_wallet_amount(locked_settlement)

    if desired_total > current_total:
        wallet.add_pending(
            desired_total - current_total,
            
            description=f"ثبت سهم سالن از سفارش {locked_settlement.order.order_number}",
            order=locked_settlement.order,
            settlement=locked_settlement,
        )
        pending_component += desired_total - current_total

    elif desired_total < current_total:
        remaining = current_total - desired_total

        if pending_component > 0:
            pending_reduction = min(pending_component, remaining)
            wallet.reverse_pending(
                pending_reduction,
                description=f"کاهش سهم سالن از سفارش {locked_settlement.order.order_number}",
                order=locked_settlement.order,
                settlement=locked_settlement,
            )
            pending_component -= pending_reduction
            remaining -= pending_reduction

        if remaining > 0 and available_component > 0:
            available_reduction = min(available_component, remaining)
            wallet.reverse_available(
                available_reduction,
                description=f"اصلاح موجودی قابل برداشت سالن برای سفارش {locked_settlement.order.order_number}",
                order=locked_settlement.order,
                settlement=locked_settlement,
            )
            available_component -= available_reduction

    should_release = (
        locked_settlement.salon.payout_profile_complete
        and locked_settlement.payment_method in DIGITAL_PAYMENT_METHODS
        and desired_total > 0
        and locked_settlement.eligible_for_payout_at
        and timezone.now() >= locked_settlement.eligible_for_payout_at
        and pending_component > 0
    )

    if should_release:
        wallet.release_pending(
            pending_component,
            description=f"انتقال سهم سالن از سفارش {locked_settlement.order.order_number} به موجودی قابل برداشت",
            order=locked_settlement.order,
            settlement=locked_settlement,
        )

    return wallet


def _desired_stylist_wallet_amount(snapshot: OrderDetailFinancialSnapshot) -> int:
    if snapshot.status != OrderDetailFinancialSnapshot.Status.FINALIZED:
        return 0

    if snapshot.order.status == "cancelled":
        return 0

    if snapshot.order.selected_payment_method not in DIGITAL_PAYMENT_METHODS:
        return 0

    if not snapshot.order.is_paid:
        return 0

    return max(_safe_int(snapshot.stylist_net_share), 0)


@transaction.atomic
def sync_stylist_wallet_for_snapshot(snapshot: OrderDetailFinancialSnapshot):
    locked_snapshot = (
        _lock_self(OrderDetailFinancialSnapshot.objects)
        .select_related("order", "settlement", "stylist")
        .get(pk=snapshot.pk)
    )

    wallet, _ = StylistWallet.objects.get_or_create(stylist=locked_snapshot.stylist)
    wallet = StylistWallet.objects.select_for_update().get(pk=wallet.pk)

    aggregates = locked_snapshot.stylist_wallet_transactions.aggregate(
        pending=Sum("pending_delta"),
        available=Sum("available_delta"),
    )

    pending_component = int(aggregates.get("pending") or 0)
    available_component = int(aggregates.get("available") or 0)
    current_total = pending_component + available_component
    desired_total = _desired_stylist_wallet_amount(locked_snapshot)

    if desired_total > current_total:
        wallet.add_pending(
            desired_total - current_total,
            salon=locked_snapshot.salon,
            description=f"ثبت سهم متخصص از خدمت {locked_snapshot.service}",
            order=locked_snapshot.order,
            order_detail=locked_snapshot.order_detail,
            financial_snapshot=locked_snapshot,
        )
        pending_component += desired_total - current_total

    elif desired_total < current_total:
        remaining = current_total - desired_total

        if pending_component > 0:
            pending_reduction = min(pending_component, remaining)
            wallet.reverse_pending(
                pending_reduction,
                salon=locked_snapshot.salon,
                description=f"کاهش سهم متخصص از خدمت {locked_snapshot.service}",
                order=locked_snapshot.order,
                order_detail=locked_snapshot.order_detail,
                financial_snapshot=locked_snapshot,
            )
            pending_component -= pending_reduction
            remaining -= pending_reduction

        if remaining > 0 and available_component > 0:
            available_reduction = min(available_component, remaining)
            wallet.reverse_available(
                available_reduction,
                salon=locked_snapshot.salon,
                description=f"اصلاح موجودی قابل برداشت متخصص برای خدمت {locked_snapshot.service}",
                order=locked_snapshot.order,
                order_detail=locked_snapshot.order_detail,
                financial_snapshot=locked_snapshot,
            )
            available_component -= available_reduction

    settlement = locked_snapshot.settlement

    should_release = (
        settlement
        and settlement.payment_method in DIGITAL_PAYMENT_METHODS
        and settlement.eligible_for_payout_at
        and timezone.now() >= settlement.eligible_for_payout_at
        and pending_component > 0
    )

    if should_release:
        wallet.release_pending(
            pending_component,
            salon=locked_snapshot.salon,
            description=f"انتقال سهم متخصص از خدمت {locked_snapshot.service} به موجودی قابل برداشت",
            order=locked_snapshot.order,
            order_detail=locked_snapshot.order_detail,
            financial_snapshot=locked_snapshot,
        )

    return wallet


def release_eligible_salon_wallet_funds_for_salon(salon):
    settlements = SalonSettlement.objects.filter(
        salon=salon,
        payment_method__in=DIGITAL_PAYMENT_METHODS,
        paid_amount__gt=0,
        eligible_for_payout_at__isnull=False,
        eligible_for_payout_at__lte=timezone.now(),
    ).select_related("order", "salon")

    for settlement in settlements:
        sync_salon_wallet_for_settlement(settlement)


def release_eligible_stylist_wallet_funds_for_salon(salon):
    snapshots = OrderDetailFinancialSnapshot.objects.filter(
        salon=salon,
        status=OrderDetailFinancialSnapshot.Status.FINALIZED,
        settlement__payment_method__in=DIGITAL_PAYMENT_METHODS,
        settlement__eligible_for_payout_at__isnull=False,
        settlement__eligible_for_payout_at__lte=timezone.now(),
    ).select_related("order", "settlement", "stylist", "service")

    for snapshot in snapshots:
        sync_stylist_wallet_for_snapshot(snapshot)



def _is_order_ready_for_review_and_payment_notice(order: Order) -> bool:
    if not getattr(order, "is_paid", False):
        return False

    if getattr(order, "service_completed_at", None) or getattr(order, "status", "") == "completed":
        return True

    try:
        return not OrderDetail.objects.filter(
            order=order,
            service_completed_at__isnull=True,
        ).exists()
    except Exception:
        return False


def _ensure_customer_review_request_after_completed_payment(order: Order) -> None:
    if not _is_order_ready_for_review_and_payment_notice(order):
        return

    if getattr(order, "review_requested_at", None):
        return

    try:
        from apps.orders.lifecycle import mark_review_requested

        mark_review_requested(order)
    except Exception:
        logger.exception("Failed to mark review requested after payment. order=%s", getattr(order, "pk", None))


def _notify_stylists_payment_completed_for_order(order: Order, *, settlement: SalonSettlement | None = None) -> None:
    if not _is_order_ready_for_review_and_payment_notice(order):
        return

    details = (
        OrderDetail.objects.filter(order=order)
        .select_related("stylist__user", "service", "salon")
        .order_by("date", "time", "id")
    )

    for detail in details:
        stylist = detail.stylist
        stylist_user = getattr(stylist, "user", None) if stylist else None
        if not stylist or not stylist_user:
            continue

        already_sent = AppointmentNotification.objects.filter(
            order=order,
            order_detail=detail,
            stylist=stylist,
            target_user=stylist_user,
            audience_role="stylist",
            channel="dashboard",
            event_type="payment_completed",
        ).exists()
        if already_sent:
            continue

        service_name = detail.service.service_name if detail.service_id else "خدمت"
        notification = AppointmentNotification.objects.create(
            order=order,
            order_detail=detail,
            salon=detail.salon or order.salon,
            customer=order.customer,
            stylist=stylist,
            target_user=stylist_user,
            audience_role="stylist",
            channel="dashboard",
            event_type="payment_completed",
            title="پرداخت نوبت تکمیل شد",
            body=f"پرداخت رزرو مربوط به «{service_name}» نهایی شد و سهم مالی این خدمت در گزارش‌های مجموعه قابل پیگیری است.",
            delivery_status="sent",
            meta={
                "source": "phase11_payment_completed_to_stylist",
                "settlement_id": getattr(settlement, "pk", None),
                "detail_id": detail.pk,
                "order_id": order.pk,
            },
        )
        try:
            from apps.notifications.services import sync_legacy_appointment_notification

            sync_legacy_appointment_notification(notification)
        except Exception:
            logger.exception(
                "Failed to sync stylist payment notification. notification=%s",
                notification.pk,
            )

@transaction.atomic
def sync_settlement_for_order(order, payment: Payment | None = None):
    locked_order = (
        _lock_self(Order.objects)
        .select_related("customer", "salon")
        .get(pk=order.pk)
    )

    salon = locked_order.salon

    if salon is None:
        return None

    existing_settlement = (
        _lock_self(SalonSettlement.objects).filter(order=locked_order).first()
    )

    linked_payment = payment

    if (
        linked_payment is None
        and existing_settlement
        and existing_settlement.payment_id
    ):
        linked_payment = existing_settlement.payment

    if linked_payment is None:
        linked_payment = locked_order.payment_order.order_by("-id").first()

    # Only settlement-affecting refunds should reduce salon payout.
    # Confirmed no-show wallet refunds are customer compensations and are
    # intentionally excluded from salon/stylist cost accounting.
    refund_amount = _settlement_refund_amount_for_order(locked_order)
    paid_amount = int(locked_order.total_amount or 0) if locked_order.is_paid else 0
    net_due = max(int(locked_order.salon_payout_amount or 0) - refund_amount, 0)

    payout_state, hold_reason = _calculate_payout_state(
        locked_order,
        salon,
        net_due=net_due,
    )

    eligible_for_payout_at = None

    is_digital_paid_order = (
        locked_order.selected_payment_method in DIGITAL_PAYMENT_METHODS
        and paid_amount > 0
    )

    if (
        payout_state
        in {
            SalonSettlement.PayoutState.READY,
            SalonSettlement.PayoutState.HOLD,
        }
        and is_digital_paid_order
    ):
        if (
            existing_settlement
            and existing_settlement.eligible_for_payout_at
            and existing_settlement.payment_method in DIGITAL_PAYMENT_METHODS
            and int(existing_settlement.paid_amount or 0) > 0
            and existing_settlement.payout_state
            in {
                SalonSettlement.PayoutState.READY,
                SalonSettlement.PayoutState.HOLD,
            }
        ):
            eligible_for_payout_at = existing_settlement.eligible_for_payout_at
        else:
            eligible_for_payout_at = timezone.now() + timedelta(
                days=int(getattr(salon, "payout_delay_days", 2) or 0)
            )

    settlement, _ = SalonSettlement.objects.update_or_create(
        order=locked_order,
        defaults={
            "salon": salon,
            "customer": locked_order.customer,
            "payment": linked_payment,
            "payment_method": locked_order.selected_payment_method
            or (existing_settlement.payment_method if existing_settlement else ""),
            "payment_provider": (
                getattr(linked_payment, "provider", "")
                if linked_payment
                else (
                    existing_settlement.payment_provider if existing_settlement else ""
                )
            ),
            "gross_services_amount": int(locked_order.subtotal_amount or 0),
            "discount_amount": int(locked_order.discount_amount or 0),
            "tax_amount": 0,
            "paid_amount": paid_amount,
            "refund_amount": refund_amount,
            "first_visit_commission_applies": bool(
                locked_order.platform_commission_applies
            ),
            "platform_commission_percent": int(
                locked_order.platform_commission_percent or 0
            ),
            "platform_commission_amount": int(
                locked_order.platform_commission_amount or 0
            ),
            "net_amount_due_to_salon": net_due,
            "payout_state": payout_state,
            "payout_hold_reason": hold_reason,
            "eligible_for_payout_at": eligible_for_payout_at,
            "policy_snapshot": {
                "cancellation_window_hours": int(
                    getattr(salon, "cancellation_window_hours", 24) or 24
                ),
                "cancellation_refund_percent": int(
                    getattr(salon, "cancellation_refund_percent", 100) or 0
                ),
                "payout_delay_days": int(getattr(salon, "payout_delay_days", 2) or 0),
                "payout_profile_complete": bool(
                    getattr(salon, "payout_profile_complete", False)
                ),
                "detail_finance_enabled": bool(
                    getattr(settings, "LOOMERA_USE_DETAIL_FINANCE", True)
                ),
            },
        },
    )

    sync_salon_wallet_for_settlement(settlement)

    _ensure_customer_review_request_after_completed_payment(locked_order)
    _notify_stylists_payment_completed_for_order(locked_order, settlement=settlement)

    if (
        locked_order.booking_quick_link_id
        and locked_order.is_finally
        and locked_order.status != "cancelled"
    ):
        from apps.orders.quick_links import (
            mark_booking_quick_link_converted,
        )

        mark_booking_quick_link_converted(locked_order)

    logger.info(
        "Settlement synced | order=%s | payment=%s | method=%s | paid=%s | refund=%s | net_due=%s | payout_state=%s",
        locked_order.pk,
        getattr(linked_payment, "pk", None),
        locked_order.selected_payment_method,
        paid_amount,
        refund_amount,
        net_due,
        payout_state,
    )

    return settlement


@transaction.atomic
def finalize_order_detail_financials(
    order_detail: OrderDetail,
    *,
    payment: Payment | None = None,
    recorded_by=None,
    require_completed: bool = True,
    force: bool = False,
) -> OrderDetailFinancialSnapshot:
    """
    سند مالی یک خدمت رزروشده را نهایی می‌کند و سهم‌ها را با کیف پول‌ها sync می‌کند.
    """
    detail = (
        _lock_self(OrderDetail.objects)
        .select_related("order", "salon", "service", "stylist")
        .get(pk=order_detail.pk)
    )

    if detail.order.status == "cancelled":
        raise ValidationError("رزرو لغو شده است و نمی‌توان سند مالی آن را نهایی کرد.")

    if require_completed and not detail.service_completed_at:
        raise ValidationError("برای نهایی‌سازی مالی، ابتدا باید پایان خدمت ثبت شود.")

    existing = getattr(detail, "financial_snapshot", None)
    if (
        existing
        and existing.status == OrderDetailFinancialSnapshot.Status.FINALIZED
        and not force
    ):
        sync_staff_earning_from_snapshot(existing)
        sync_ledger_for_snapshot(existing, created_by=recorded_by)
        sync_stylist_wallet_for_snapshot(existing)
        if existing.settlement_id:
            sync_salon_wallet_for_settlement(existing.settlement)
        return existing

    # اگر قالب مواد برای خدمت تعریف شده باشد، در زمان نهایی‌سازی به مصرف واقعی تبدیل می‌شود.
    detail.ensure_material_usage_from_template(recorded_by=recorded_by)

    settlement = sync_settlement_for_order(detail.order, payment=payment)

    snapshot = calculate_order_detail_financials(
        detail,
        settlement=settlement,
        force=True,
    )

    if snapshot.status != OrderDetailFinancialSnapshot.Status.FINALIZED:
        snapshot.mark_finalized()
    elif not snapshot.finalized_at:
        snapshot.finalized_at = timezone.now()
        snapshot.save(update_fields=["finalized_at", "updated_at"])

    detail.financial_finalized_at = snapshot.finalized_at or timezone.now()
    detail.save(update_fields=["financial_finalized_at"])

    sync_staff_earning_from_snapshot(snapshot)
    sync_ledger_for_snapshot(snapshot, created_by=recorded_by, force=force)
    sync_stylist_wallet_for_snapshot(snapshot)

    if settlement:
        sync_salon_wallet_for_settlement(settlement)

    return snapshot


@transaction.atomic
def finalize_order_financials(
    order: Order,
    *,
    payment: Payment | None = None,
    recorded_by=None,
    require_all_completed: bool = True,
    force: bool = False,
) -> list[OrderDetailFinancialSnapshot]:
    """
    همه آیتم‌های رزرو را نهایی مالی می‌کند.
    اگر require_all_completed=True باشد، تا وقتی همه خدمات تمام نشده‌اند اجرا نمی‌شود.
    """
    locked_order = (
        _lock_self(Order.objects)
        .select_related("customer", "salon")
        .get(pk=order.pk)
    )

    if locked_order.status == "cancelled":
        raise ValidationError("رزرو لغو شده است و نمی‌توان سند مالی آن را نهایی کرد.")

    details = list(
        locked_order.order_details1.select_related(
            "salon", "service", "stylist"
        ).order_by("id")
    )

    if not details:
        return []

    if require_all_completed:
        incomplete = [detail for detail in details if not detail.service_completed_at]
        if incomplete:
            raise ValidationError("هنوز همه خدمات این رزرو به پایان نرسیده‌اند.")

    snapshots = []

    for detail in details:
        if not detail.service_completed_at:
            continue

        snapshot = finalize_order_detail_financials(
            detail,
            payment=payment,
            recorded_by=recorded_by,
            require_completed=True,
            force=force,
        )
        snapshots.append(snapshot)

    settlement = sync_settlement_for_order(locked_order, payment=payment)

    if settlement:
        sync_salon_wallet_for_settlement(settlement)

    return snapshots


@transaction.atomic
def reverse_financial_snapshots_for_order(order: Order):
    """
    در صورت لغو رزرو، اسناد مالی نهایی‌شده را برگشت می‌زند و کیف پول‌ها را sync می‌کند.
    """
    locked_order = _lock_self(Order.objects).get(pk=order.pk)

    snapshots = list(
        _lock_self(OrderDetailFinancialSnapshot.objects)
        .filter(order=locked_order)
        .select_related("order", "settlement", "stylist", "service", "order_detail")
        .order_by("id")
    )

    for snapshot in snapshots:
        snapshot.mark_reversed()

        if snapshot.order_detail_id:
            OrderDetail.objects.filter(pk=snapshot.order_detail_id).update(
                financial_finalized_at=None
            )

        sync_stylist_wallet_for_snapshot(snapshot)

    settlement = _get_settlement_for_order(locked_order)
    if settlement:
        sync_salon_wallet_for_settlement(settlement)

    return snapshots


@transaction.atomic
def refund_order_to_wallet(*, order, reason: str = "لغو رزرو دیجیتال") -> int:
    locked_order = (
        _lock_self(Order.objects)
        .select_related("customer__user", "salon")
        .get(pk=order.pk)
    )

    if (
        not locked_order.is_paid
        or locked_order.selected_payment_method not in DIGITAL_PAYMENT_METHODS
    ):
        return 0

    if int(locked_order.refunded_to_wallet_amount or 0) > 0:
        return int(locked_order.refunded_to_wallet_amount or 0)

    refund_percent = int(
        getattr(locked_order.salon, "cancellation_refund_percent", 100) or 0
    )
    refund_amount = int((int(locked_order.total_amount or 0) * refund_percent) / 100)

    if refund_amount <= 0:
        return 0

    wallet, _ = Wallet.objects.select_for_update().get_or_create(
        user=locked_order.customer.user
    )

    wallet.deposit(
        amount=refund_amount,
        description=f"بازگشت وجه رزرو {locked_order.order_number} به کیف پول - {reason}",
        transaction_type=WalletTransaction.TransactionType.REFUND,
        order=locked_order,
    )

    locked_order.refunded_to_wallet_amount = refund_amount
    locked_order.refunded_to_wallet_at = timezone.now()
    locked_order.save(
        update_fields=["refunded_to_wallet_amount", "refunded_to_wallet_at"]
    )

    logger.info(
        "Wallet refund created | order=%s | amount=%s | payment_method=%s",
        locked_order.pk,
        refund_amount,
        locked_order.selected_payment_method,
    )

    return refund_amount


@transaction.atomic
def cancel_order_with_financials(
    *,
    order,
    reason: str = "لغو رزرو",
    refund_reason: str | None = None,
    payment: Payment | None = None,
) -> OrderCancellationResult:
    locked_order = _lock_self(Order.objects).get(pk=order.pk)

    if locked_order.status == "cancelled":
        latest_payment = payment or locked_order.payment_order.order_by("-id").first()

        refund_amount = ensure_order_refund_fields_from_wallet(locked_order)

        settlement = sync_settlement_for_order(locked_order, payment=latest_payment)
        reverse_financial_snapshots_for_order(locked_order)
        settlement = sync_settlement_for_order(locked_order, payment=latest_payment)

        logger.info(
            "Already-cancelled order financials re-synced | order=%s | refund=%s | settlement=%s",
            locked_order.pk,
            refund_amount,
            getattr(settlement, "pk", None),
        )

        locked_order.refresh_from_db()

        return OrderCancellationResult(
            order=locked_order,
            refund_amount=refund_amount,
            already_cancelled=True,
        )

    locked_order.status = "cancelled"
    locked_order.is_finally = False
    locked_order.cancellation_reason = (
        reason or locked_order.cancellation_reason or "لغو رزرو"
    )[:255]
    locked_order.save(update_fields=["status", "is_finally", "cancellation_reason"])

    latest_payment = payment or locked_order.payment_order.order_by("-id").first()

    refund_amount = 0

    if (
        locked_order.is_paid
        and locked_order.selected_payment_method in DIGITAL_PAYMENT_METHODS
    ):
        refund_amount = refund_order_to_wallet(
            order=locked_order,
            reason=refund_reason or reason or "لغو رزرو",
        )
    
    locked_order.refresh_from_db()
    refund_amount = ensure_order_refund_fields_from_wallet(locked_order)

    sync_settlement_for_order(locked_order, payment=latest_payment)
    reverse_financial_snapshots_for_order(locked_order)
    sync_settlement_for_order(locked_order, payment=latest_payment)

    logger.info(
        "Order cancelled with financials | order=%s | refund=%s | payment=%s | reason=%s",
        locked_order.pk,
        refund_amount,
        getattr(latest_payment, "pk", None),
        reason,
    )

    return OrderCancellationResult(order=locked_order, refund_amount=refund_amount)
