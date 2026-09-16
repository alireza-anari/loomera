from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import FinancialAccount, LedgerEntry, OrderDetailFinancialSnapshot, StaffEarning


@dataclass(frozen=True)
class LedgerLine:
    account: FinancialAccount
    direction: str
    amount: int
    description: str = ""
    metadata: dict | None = None


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def get_or_create_financial_account(owner, account_type: str, *, currency: str = "IRR") -> FinancialAccount:
    """حساب مالی داخلی را برای مالک داده‌شده می‌سازد/برمی‌گرداند."""
    if owner is None:
        content_type = None
        object_id = None
    else:
        content_type = ContentType.objects.get_for_model(owner, for_concrete_model=False)
        object_id = owner.pk

    account, _ = FinancialAccount.objects.get_or_create(
        owner_content_type=content_type,
        owner_object_id=object_id,
        account_type=account_type,
        defaults={"currency": currency},
    )
    return account


@transaction.atomic
def post_balanced_ledger_entries(
    *,
    entry_type: str,
    lines: list[LedgerLine],
    order=None,
    order_detail=None,
    created_by=None,
    group_id=None,
    metadata: dict | None = None,
) -> list[LedgerEntry]:
    debit_total = sum(_safe_int(line.amount) for line in lines if line.direction == LedgerEntry.Direction.DEBIT)
    credit_total = sum(_safe_int(line.amount) for line in lines if line.direction == LedgerEntry.Direction.CREDIT)

    if debit_total != credit_total:
        raise ValidationError("سند دفتر مالی تراز نیست؛ جمع بدهکار و بستانکار باید برابر باشد.")

    if debit_total <= 0:
        return []

    group_id = group_id or uuid.uuid4()
    base_metadata = metadata or {}
    entries = []

    for line in lines:
        amount = _safe_int(line.amount)
        if amount <= 0:
            continue
        entry = LedgerEntry.objects.create(
            account=line.account,
            order=order,
            order_detail=order_detail,
            group_id=group_id,
            entry_type=entry_type,
            direction=line.direction,
            amount=amount,
            description=line.description,
            metadata={**base_metadata, **(line.metadata or {})},
            created_by=created_by,
        )
        entries.append(entry)

    return entries


def sync_staff_earning_from_snapshot(snapshot: OrderDetailFinancialSnapshot) -> StaffEarning:
    status = StaffEarning.Status.PAYABLE if snapshot.status == snapshot.Status.FINALIZED else StaffEarning.Status.PENDING
    earning, _ = StaffEarning.objects.update_or_create(
        order_detail=snapshot.order_detail,
        defaults={
            "financial_snapshot": snapshot,
            "salon": snapshot.salon,
            "stylist": snapshot.stylist,
            "gross_share": int(snapshot.stylist_gross_share or 0),
            "material_deduction": int(snapshot.stylist_material_deduction or 0),
            "net_profit": int(snapshot.stylist_net_share or 0),
            "status": status,
            "calculated_at": snapshot.finalized_at or snapshot.updated_at,
        },
    )
    return earning


@transaction.atomic
def sync_ledger_for_snapshot(snapshot: OrderDetailFinancialSnapshot, *, created_by=None, force: bool = False):
    """
    برای هر سند مالی نهایی‌شده یک سند Ledger تراز ایجاد می‌کند.
    اگر قبلاً برای snapshot ثبت شده باشد، به‌صورت پیش‌فرض تکرار نمی‌کند.
    """
    if snapshot.status != snapshot.Status.FINALIZED:
        return []

    existing_qs = LedgerEntry.objects.filter(
        entry_type="appointment_financial_snapshot",
        order_detail=snapshot.order_detail,
        metadata__snapshot_id=snapshot.pk,
        status=LedgerEntry.Status.POSTED,
    )
    if existing_qs.exists() and not force:
        return list(existing_qs)

    if force and existing_qs.exists():
        existing_qs.update(status=LedgerEntry.Status.VOIDED)

    total_paid = int(snapshot.total_customer_paid or snapshot.paid_amount_allocated or 0)
    platform_commission = int(snapshot.platform_commission_allocated or 0)
    staff_share = int(snapshot.stylist_net_share or 0)
    salon_share = int(snapshot.salon_net_share or 0)

    credit_total = platform_commission + staff_share + salon_share
    if credit_total <= 0:
        return []

    clearing_account = get_or_create_financial_account(
        snapshot.salon,
        FinancialAccount.AccountType.PROVIDER_CLEARING,
    )
    salon_account = get_or_create_financial_account(
        snapshot.salon,
        FinancialAccount.AccountType.SALON,
    )
    staff_account = get_or_create_financial_account(
        snapshot.stylist,
        FinancialAccount.AccountType.STAFF_RECEIVABLE,
    )
    platform_account = get_or_create_financial_account(
        None,
        FinancialAccount.AccountType.PLATFORM_COMMISSION,
    )

    lines = [
        LedgerLine(
            account=clearing_account,
            direction=LedgerEntry.Direction.DEBIT,
            amount=max(total_paid, credit_total),
            description="ثبت دریافت/مطالبه مشتری برای نوبت",
        ),
        LedgerLine(
            account=salon_account,
            direction=LedgerEntry.Direction.CREDIT,
            amount=salon_share,
            description="ثبت سهم خالص سالن از نوبت",
        ),
        LedgerLine(
            account=staff_account,
            direction=LedgerEntry.Direction.CREDIT,
            amount=staff_share,
            description="ثبت مطالبه آرایشگر از سالن",
        ),
        LedgerLine(
            account=platform_account,
            direction=LedgerEntry.Direction.CREDIT,
            amount=platform_commission,
            description="ثبت کمیسیون پلتفرم",
        ),
    ]

    # اگر total_paid بیشتر از جمع سهم‌ها باشد، اختلاف به حساب تعدیلات می‌رود تا سند تراز بماند.
    delta = max(total_paid, credit_total) - credit_total
    if delta > 0:
        adjustment_account = get_or_create_financial_account(
            snapshot.salon,
            FinancialAccount.AccountType.ADJUSTMENT,
        )
        lines.append(
            LedgerLine(
                account=adjustment_account,
                direction=LedgerEntry.Direction.CREDIT,
                amount=delta,
                description="اختلاف/کسورات مالی ثبت‌شده برای تراز سند",
            )
        )

    return post_balanced_ledger_entries(
        entry_type="appointment_financial_snapshot",
        lines=lines,
        order=snapshot.order,
        order_detail=snapshot.order_detail,
        created_by=created_by,
        metadata={
            "snapshot_id": snapshot.pk,
            "payment_method": snapshot.payment_method,
            "gross_amount": int(snapshot.gross_amount or 0),
            "discount_allocated": int(snapshot.discount_allocated or 0),
            "material_cost_total": int(snapshot.material_cost_total or 0),
        },
    )
