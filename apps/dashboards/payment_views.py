from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    format_time_fa,
    parse_jalali_input,
    to_persian_digits,
)
from apps.dashboards.layout import build_dashboard_context
from apps.discounts.forms import (
    SalonCouponForm,
    SalonDiscountBasketForm,
    SalonDiscountCampaignForm,
)
from apps.discounts.models import Coupon, DiscountBasket, DiscountCampaign
from apps.payments.finance import release_eligible_salon_wallet_funds_for_salon
from apps.payments.forms import SalonWalletWithdrawalRequestForm
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
    SalonSettlement,
    SalonWallet,
    SalonWalletTransaction,
    SalonWalletWithdrawalRequest,
    StylistWallet,
    StylistWalletWithdrawalRequest,
    WalletWithdrawalRequest,
)
from apps.salons.forms import SalonPayoutSettingsForm
from apps.salons.models import Salon
import csv
from django.http import HttpResponse
from apps.orders.models import Order

from apps.discounts.activation_rules import (
    basket_conflict_message,
    basket_service_ids_from_cleaned_services,
    basket_service_ids_from_instance,
    campaign_conflict_message,
    campaign_service_ids_from_selection,
    campaign_service_ids_from_instance,
    find_basket_activation_conflicts,
    find_campaign_activation_conflicts,
)


def _to_int(value):
    return int(value or 0)


def _money(value):
    return f"{_to_int(value):,} تومان"

FINANCE_REPORT_PAYMENT_METHODS = {
    "",
    "online",
    "wallet",
    "pay_in_salon",
}

FINANCE_REPORT_PAYOUT_STATES = {
    "",
    "awaiting_payment",
    "manual_collection",
    "ready",
    "hold",
    "paid",
    "cancelled",
}


def _finance_report_query_max_chars():
    return max(
        int(getattr(settings, "FINANCE_REPORT_QUERY_MAX_CHARS", 2048) or 1),
        1,
    )


def _finance_report_max_range_days():
    return max(
        int(getattr(settings, "FINANCE_REPORT_MAX_RANGE_DAYS", 370) or 1),
        1,
    )


def _finance_report_export_max_rows():
    return max(
        int(getattr(settings, "FINANCE_REPORT_EXPORT_MAX_ROWS", 5000) or 1),
        1,
    )


def _finance_export_cell_max_chars():
    return max(
        int(getattr(settings, "FINANCE_EXPORT_CELL_MAX_CHARS", 500) or 1),
        1,
    )


def _validate_finance_report_query_size(request):
    query_string = request.META.get("QUERY_STRING") or ""
    if len(query_string.encode("utf-8")) > _finance_report_query_max_chars():
        raise ValidationError("حجم فیلترهای گزارش مالی بیش از حد مجاز است.")


def _clean_finance_report_choice(raw_value, allowed_values):
    value = str(raw_value or "").strip()
    return value if value in allowed_values else ""


def _normalize_finance_report_range(start_date, end_date):
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    if start_date and end_date:
        max_days = _finance_report_max_range_days()
        if (end_date - start_date).days > max_days:
            start_date = end_date - timedelta(days=max_days)

    return start_date, end_date


def _safe_finance_export_text(value):
    text = "" if value is None else str(value)
    text = text.replace("\x00", " ")
    text = text.replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split()).strip()

    max_chars = _finance_export_cell_max_chars()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()

    # جلوگیری از CSV/Excel formula injection
    if text.startswith(("=", "+", "-", "@")):
        text = "'" + text

    return text

def _dashboard_positive_int_or_none(value):
    text = str(value or "").strip()
    if not text.isdigit():
        return None

    parsed = int(text)
    return parsed if parsed > 0 else None


def _dashboard_request_body_too_large(request, max_bytes):
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        content_length = 0

    return content_length > max_bytes


def _finance_coupon_post_max_bytes():
    return max(
        int(getattr(settings, "FINANCE_COUPON_POST_MAX_BYTES", 8 * 1024) or 1),
        1,
    )


def _finance_coupon_code_max_chars():
    return max(
        int(getattr(settings, "FINANCE_COUPON_CODE_MAX_CHARS", 64) or 1),
        1,
    )


def _finance_coupon_description_max_chars():
    return max(
        int(getattr(settings, "FINANCE_COUPON_DESCRIPTION_MAX_CHARS", 1000) or 1),
        1,
    )


def _validate_finance_coupon_post_size(request):
    if _dashboard_request_body_too_large(request, _finance_coupon_post_max_bytes()):
        raise ValidationError("حجم اطلاعات ارسالی بیش از حد مجاز است.")


def _sanitize_finance_coupon_post_data(request):
    _validate_finance_coupon_post_size(request)

    data = request.POST.copy()

    coupon_code = str(data.get("coupon_code") or "").strip().upper()
    coupon_code = coupon_code.replace("\r", "").replace("\n", "").replace("\x00", "")

    if len(coupon_code) > _finance_coupon_code_max_chars():
        raise ValidationError("کد تخفیف بیش از حد مجاز است.")

    description = str(data.get("description") or "").strip()
    description = (
        description.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    )

    if len(description) > _finance_coupon_description_max_chars():
        raise ValidationError("توضیحات کد تخفیف بیش از حد مجاز است.")

    data["coupon_code"] = coupon_code
    data["description"] = description

    return data


def _payment_method_label(value):
    return {
        "online": "پرداخت آنلاین",
        "wallet": "کیف پول",
        "pay_in_salon": "پرداخت در مجموعه",
        "": "نامشخص",
    }.get(value or "", value or "نامشخص")


def _settlement_detail_totals(settlement):
    totals = settlement.detail_snapshots.filter(
        status=OrderDetailFinancialSnapshot.Status.FINALIZED,
    ).aggregate(
        gross=Sum("gross_amount"),
        discount=Sum("discount_allocated"),
        paid=Sum("paid_amount_allocated"),
        stylist_share=Sum("stylist_net_share"),
        salon_share=Sum("salon_net_share"),
        salon_profit=Sum("salon_net_profit"),
    )

    return {
        "gross": _to_int(totals.get("gross")),
        "discount": _to_int(totals.get("discount")),
        "paid": _to_int(totals.get("paid")),
        "stylist_share": _to_int(totals.get("stylist_share")),
        "salon_share": _to_int(totals.get("salon_share")),
        "salon_profit": _to_int(totals.get("salon_profit")),
    }


def _expected_salon_wallet_effect(settlement):
    """
    اثر مورد انتظار در کیف پول مجموعه فقط سهم خالص مجموعه است.
    سهم متخصص در StylistWallet ثبت می‌شود.
    """
    if settlement.payout_state == SalonSettlement.PayoutState.CANCELLED:
        return 0

    if settlement.payment_method not in {"online", "wallet"}:
        return 0

    if _to_int(settlement.paid_amount) <= 0:
        return 0

    detail_totals = _settlement_detail_totals(settlement)

    if detail_totals["salon_share"]:
        return max(detail_totals["salon_share"], 0)

    return max(_to_int(settlement.net_amount_due_to_salon), 0)


def _expected_salon_wallet_effect(settlement):
    """
    اثر مورد انتظار در کیف پول مجموعه فقط سهم خالص مجموعه است.
    سهم متخصص در StylistWallet ثبت می‌شود و نباید به عنوان اختلاف کیف پول مجموعه حساب شود.
    """
    if settlement.payout_state == SalonSettlement.PayoutState.CANCELLED:
        return 0

    if settlement.payment_method not in {"online", "wallet"}:
        return 0

    if _to_int(settlement.paid_amount) <= 0:
        return 0

    detail_total = settlement.detail_snapshots.filter(
        status=OrderDetailFinancialSnapshot.Status.FINALIZED,
    ).aggregate(total=Sum("salon_net_share"))["total"]

    if detail_total is not None:
        return max(_to_int(detail_total), 0)

    return max(_to_int(settlement.net_amount_due_to_salon), 0)


def _finance_date_label(value):
    if not value:
        return ""
    if hasattr(value, "date"):
        value = (
            timezone.localtime(value).date()
            if timezone.is_aware(value)
            else value.date()
        )
    return format_jalali_numeric(value)


def _finance_datetime_label(value):
    if not value:
        return ""
    local_value = timezone.localtime(value) if timezone.is_aware(value) else value
    return f"{format_jalali_numeric(local_value.date())} • {format_time_fa(local_value.time())}"


def _csv_text(value):
    """متن امن برای خروجی‌های CSV/Excel."""
    return _safe_finance_export_text(value)


def _payout_state_label(value):
    return {
        "awaiting_payment": "در انتظار پرداخت",
        "manual_collection": "پرداخت در مجموعه",
        "ready": "آماده تسویه",
        "hold": "نیازمند بررسی",
        "paid": "تسویه‌شده",
        "cancelled": "لغوشده",
        "": "همه وضعیت‌ها",
    }.get(value or "", value or "نامشخص")


class _SalonFinanceMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if hasattr(request.user, "salon_manager_profile"):
            return super().dispatch(request, *args, **kwargs)
        if hasattr(request.user, "stylist"):
            messages.info(
                request, "بخش‌های مالی فقط برای مدیر مجموعه در دسترس هستند.", "info"
            )
            return redirect("dashboards:stylist_dashboard")
        return redirect("accounts:login")

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

    def _base_context(self, request, *, title="امور مالی سالن", description=""):
        return build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="finance",
            page_title=title,
            request_path=request.path,
        )


class SalonFinanceHubView(_SalonFinanceMixin, View):
    template_name = "dashboards/finance_hub.html"

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)

        release_eligible_salon_wallet_funds_for_salon(salon)

        wallet, _ = SalonWallet.objects.get_or_create(salon=salon)

        settlements = SalonSettlement.objects.filter(salon=salon)
        snapshots = OrderDetailFinancialSnapshot.objects.filter(salon=salon)
        salon_withdrawals = wallet.withdrawal_requests.all()

        stylist_wallets = StylistWallet.objects.filter(
            stylist__stylists_of_salon=salon
        ).distinct()

        stylist_withdrawals = StylistWalletWithdrawalRequest.objects.filter(salon=salon)

        settlement_summary = settlements.aggregate(
            count=Count("id"),
            gross=Sum("gross_services_amount"),
            paid=Sum("paid_amount"),
            net_due=Sum("net_amount_due_to_salon"),
            refunds=Sum("refund_amount"),
        )

        snapshot_summary = snapshots.aggregate(
            count=Count("id"),
            materials=Sum("material_cost_total"),
            stylist_share=Sum("stylist_net_share"),
            salon_share=Sum("salon_net_share"),
            profit=Sum("salon_net_profit"),
        )

        pending_salon_withdrawals = salon_withdrawals.filter(
            status=SalonWalletWithdrawalRequest.Status.PENDING
        ).count()

        pending_stylist_withdrawals = stylist_withdrawals.filter(
            status=StylistWalletWithdrawalRequest.Status.PENDING
        ).count()

        discount_now = timezone.now()
        active_coupons = Coupon.objects.filter(
            salon=salon,
            is_active=True,
            is_archived=False,
            start_date__lte=discount_now,
            end_date__gte=discount_now,
        ).count()

        active_baskets = DiscountBasket.objects.filter(
            salon=salon,
            is_active=True,
            is_archived=False,
            start_date__lte=discount_now,
            end_date__gte=discount_now,
        ).count()

        active_campaigns = DiscountCampaign.objects.filter(
            salon=salon,
            is_active=True,
            is_archived=False,
            start_date__lte=discount_now,
            end_date__gte=discount_now,
        ).count()

        finance_alerts = []

        if not salon.payout_profile_complete:
            finance_alerts.append(
                {
                    "title": "اطلاعات پرداخت سالن کامل نیست",
                    "description": "برای برداشت وجه و تسویه دقیق، شماره شبا، نام صاحب حساب و اطلاعات مالی سالن را کامل کن.",
                    "url": reverse("dashboards:payout_settings"),
                    "icon": "fa-solid fa-circle-exclamation",
                    "tone": "warning",
                }
            )

        if pending_salon_withdrawals:
            finance_alerts.append(
                {
                    "title": "درخواست برداشت سالن در انتظار بررسی است",
                    "description": f"{pending_salon_withdrawals} درخواست برداشت سالن هنوز تعیین تکلیف نشده است.",
                    "url": reverse("dashboards:payout_settings"),
                    "icon": "fa-solid fa-hourglass-half",
                    "tone": "info",
                }
            )

        if pending_stylist_withdrawals:
            finance_alerts.append(
                {
                    "title": "درخواست برداشت متخصصان در انتظار بررسی است",
                    "description": f"{pending_stylist_withdrawals} درخواست برداشت متخصصان نیاز به تایید یا رد دارد.",
                    "url": reverse("dashboards:finance_stylist_withdrawals"),
                    "icon": "fa-solid fa-money-bill-transfer",
                    "tone": "warning",
                }
            )

        if not snapshot_summary.get("count"):
            finance_alerts.append(
                {
                    "title": "هنوز سند سود خالص ثبت نشده است",
                    "description": "برای گزارش دقیق سود، بعد از انجام نوبت‌ها مواد مصرفی و سهم متخصص را نهایی کن.",
                    "url": reverse("dashboards:finance_cost_center"),
                    "icon": "fa-solid fa-file-invoice-dollar",
                    "tone": "neutral",
                }
            )

        active_discount_count = active_coupons + active_baskets + active_campaigns

        finance_groups = [
            {
                "key": "money",
                "title": "پول مجموعه",
                "description": "ببین چه مبلغی قابل برداشت است، حساب بانکی را مدیریت کن و درخواست برداشت بده.",
                "icon": "finance_wallet",
                "meta": (
                    f"{pending_salon_withdrawals} برداشت در انتظار"
                    if pending_salon_withdrawals
                    else "آماده برداشت"
                ),
                "actions": [
                    {
                        "label": "موجودی و برداشت",
                        "description": "موجودی فعلی، حساب بانکی و درخواست برداشت",
                        "url": reverse("dashboards:payout_settings"),
                    },
                    {
                        "label": "سابقه پول",
                        "description": "ورود و خروج پول و مواردی که نیاز به بررسی دارند",
                        "url": reverse("dashboards:finance_reports"),
                    },
                ],
            },
            {
                "key": "profit",
                "title": "سود و هزینه",
                "description": "هزینه مواد و سهم متخصصان را تنظیم کن و نتیجه نهایی را در سود خالص ببین.",
                "icon": "finance_cost",
                "meta": f"{snapshot_summary.get('count') or 0} خدمت حساب‌شده",
                "actions": [
                    {
                        "label": "هزینه و سهم",
                        "description": "مواد هر خدمت و سهم هر متخصص را تنظیم کن",
                        "url": reverse("dashboards:finance_cost_center"),
                    },
                    {
                        "label": "سود خالص",
                        "description": "نتیجه هزینه‌ها و سهم‌ها را روی سود نهایی ببین",
                        "url": reverse("dashboards:finance_profit_report"),
                    },
                ],
            },
            {
                "key": "team",
                "title": "مالی متخصصان",
                "description": "درآمد و مانده هر متخصص را ببین و درخواست‌های برداشت را جداگانه بررسی کن.",
                "icon": "finance_team",
                "meta": (
                    f"{pending_stylist_withdrawals} برداشت در انتظار"
                    if pending_stylist_withdrawals
                    else f"{stylist_wallets.count()} عضو تیم"
                ),
                "actions": [
                    {
                        "label": "درآمد متخصصان",
                        "description": "درآمد قطعی، قابل دریافت و در انتظار هر متخصص",
                        "url": reverse("dashboards:finance_stylist_wallets"),
                    },
                    {
                        "label": "برداشت متخصصان",
                        "description": "درخواست‌های دریافت وجه را تأیید، رد یا پیگیری کن",
                        "url": reverse("dashboards:finance_stylist_withdrawals"),
                    },
                ],
            },
            {
                "key": "discounts",
                "title": "تخفیف‌ها",
                "description": "همه ابزارهای تخفیف را از یک جا پیدا کن؛ از کد ساده تا پیشنهاد دوره‌ای.",
                "icon": "finance_discount",
                "meta": f"{active_discount_count} مورد فعال",
                "actions": [
                    {
                        "label": "کدهای تخفیف",
                        "description": "کد تخفیف اختصاصی برای رزروهای مجموعه",
                        "url": reverse("dashboards:finance_coupons"),
                    },
                    {
                        "label": "پیشنهاد خدمات",
                        "description": "یک تخفیف مشترک را روی چند خدمت فعال کن",
                        "url": reverse("dashboards:finance_baskets"),
                    },
                    {
                        "label": "کمپین‌های تخفیف",
                        "description": "تخفیف‌های مناسبتی و دوره‌ای را مدیریت کن",
                        "url": reverse("dashboards:finance_campaigns"),
                    },
                ],
            },
        ]

        context = self._base_context(
            request,
            title="مالی",
            description="موجودی مجموعه، سود و هزینه، پرداخت تیم و تخفیف‌ها.",
        )

        context.update(
            {
                "salon": salon,
                "wallet": wallet,
                "finance_groups": finance_groups,
                "finance_summary_cards": [
                    {
                        "label": "موجودی قابل برداشت",
                        "value": _money(wallet.available_balance),
                        "icon": "finance_wallet",
                        "url": reverse("dashboards:payout_settings"),
                        "hint": "آماده برداشت",
                    },
                    {
                        "label": "در انتظار آزادشدن",
                        "value": _money(wallet.pending_balance),
                        "icon": "schedule",
                        "url": reverse("dashboards:payout_settings"),
                        "hint": "پس از مهلت نگه‌داری آزاد می‌شود",
                    },
                    {
                        "label": "فروش ثبت‌شده",
                        "value": _money(settlement_summary.get("gross")),
                        "icon": "reports",
                        "url": reverse("dashboards:finance_reports"),
                        "hint": f"{settlement_summary.get('count') or 0} نوبت ثبت‌شده",
                    },
                    {
                        "label": "سود مجموعه",
                        "value": _money(snapshot_summary.get("profit")),
                        "icon": "finance_cost",
                        "url": reverse("dashboards:finance_profit_report"),
                        "hint": f"{snapshot_summary.get('count') or 0} خدمت حساب‌شده",
                    },
                ],
            }
        )

        return render(request, self.template_name, context)


class _PlatformFinanceAdminMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(
                request, "دسترسی به گزارش مالی سراسری فقط برای مدیر سامانه مجاز است."
            )
            return redirect("dashboards:home")
        return super().dispatch(request, *args, **kwargs)

    def _base_context(self, request, *, title="گزارش مالی پلتفرم"):
        return build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title=title,
            request_path=request.path,
        )


class SalonPayoutSettingsView(_SalonFinanceMixin, View):
    template_name = "dashboards/payout_settings.html"

    def _build_context(self, request, form, salon, withdraw_form=None):
        release_eligible_salon_wallet_funds_for_salon(salon)
        wallet, _ = SalonWallet.objects.get_or_create(salon=salon)
        settlement_qs = SalonSettlement.objects.filter(salon=salon)
        recent_settlements = list(
            settlement_qs.select_related("order", "customer__user").order_by(
                "-created_at"
            )[:6]
        )
        recent_wallet_transactions = list(
            wallet.transactions.select_related("order").order_by("-created_at")[:8]
        )
        withdrawal_qs = wallet.withdrawal_requests.all()
        recent_withdrawals = list(withdrawal_qs.order_by("-created_at")[:5])
        pending_withdrawal_count = withdrawal_qs.filter(status="pending").count()

        context = self._base_context(
            request,
            title="پول مجموعه",
            description="موجودی، حساب مقصد برداشت و قوانین مالی مجموعه را از یک مسیر مدیریت کن.",
        )
        context.update(
            {
                "salon": salon,
                "form": form,
                "withdraw_form": withdraw_form
                or SalonWalletWithdrawalRequestForm(
                    initial={
                        "iban": salon.payout_iban,
                        "account_holder_name": salon.payout_account_holder_name,
                        "bank_name": salon.payout_bank_name,
                    }
                ),
                "page_meta": {
                    "title": "پول مجموعه",
                    "description": "موجودی قابل برداشت، حساب مقصد و قواعد آزادشدن یا بازگشت پول را مدیریت کن.",
                    "icon": "fa-solid fa-wallet",
                    "primary_action": None,
                    "badges": ["موجودی", "برداشت", "حساب پرداخت"],
                },
                "wallet": wallet,
                "recent_wallet_transactions": recent_wallet_transactions,
                "recent_withdrawals": recent_withdrawals,
                "recent_settlements": recent_settlements,
                "pending_withdrawal_count": pending_withdrawal_count,
                "payout_destination_ready": bool(
                    (salon.payout_iban or "").strip()
                    and (salon.payout_account_holder_name or "").strip()
                ),
                "min_amount": int(
                    getattr(settings, "SALON_WALLET_WITHDRAW_MIN_AMOUNT", 100000)
                    or 100000
                ),
                "max_amount": int(
                    getattr(settings, "SALON_WALLET_WITHDRAW_MAX_AMOUNT", 200000000)
                    or 200000000
                ),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        form = SalonPayoutSettingsForm(instance=salon)
        return render(
            request, self.template_name, self._build_context(request, form, salon)
        )

    def post(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        form = SalonPayoutSettingsForm(request.POST, instance=salon)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات امور مالی مجموعه با موفقیت ذخیره شد.")
            return redirect("dashboards:payout_settings")
        messages.error(request, "لطفاً خطاهای فرم امور مالی را بررسی کنید.")
        return render(
            request, self.template_name, self._build_context(request, form, salon)
        )


class SalonFinanceWithdrawView(_SalonFinanceMixin, View):
    def post(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        release_eligible_salon_wallet_funds_for_salon(salon)
        wallet, _ = SalonWallet.objects.get_or_create(salon=salon)
        withdraw_data = request.POST.copy()
        withdraw_data["iban"] = salon.payout_iban or ""
        withdraw_data["account_holder_name"] = salon.payout_account_holder_name or ""
        withdraw_data["bank_name"] = salon.payout_bank_name or ""
        form = SalonWalletWithdrawalRequestForm(withdraw_data)
        payout_form = SalonPayoutSettingsForm(instance=salon)
        if not form.is_valid():
            messages.error(request, "لطفاً خطاهای فرم برداشت را بررسی کنید.")
            return render(
                request,
                "dashboards/payout_settings.html",
                SalonPayoutSettingsView()._build_context(
                    request, payout_form, salon, withdraw_form=form
                ),
            )

        amount = int(form.cleaned_data["amount"])
        try:
            with transaction.atomic():
                wallet = SalonWallet.objects.select_for_update().get(pk=wallet.pk)
                wallet.request_withdraw(
                    amount,
                    description="ثبت درخواست برداشت از کیف پول مالی مجموعه",
                )
                SalonWalletWithdrawalRequest.objects.create(
                    wallet=wallet,
                    amount=amount,
                    iban=form.cleaned_data["iban"],
                    legacy_destination_iban=form.cleaned_data["iban"],
                    account_holder_name=form.cleaned_data["account_holder_name"],
                    legacy_destination_account_holder_name=form.cleaned_data[
                        "account_holder_name"
                    ],
                    bank_name=form.cleaned_data.get("bank_name", ""),
                    legacy_destination_bank_name=form.cleaned_data.get("bank_name", ""),
                    note="در انتظار بررسی تیم مالی پلتفرم",
                )
        except Exception as exc:
            form.add_error("amount", str(exc))
            messages.error(request, "ثبت درخواست برداشت ممکن نشد.")
            return render(
                request,
                "dashboards/payout_settings.html",
                SalonPayoutSettingsView()._build_context(
                    request, payout_form, salon, withdraw_form=form
                ),
            )

        messages.success(
            request, "درخواست برداشت مجموعه ثبت شد و پس از بررسی مالی پیگیری می‌شود."
        )
        return redirect("dashboards:payout_settings")


class SalonFinanceWithdrawCancelView(_SalonFinanceMixin, View):
    def post(self, request, withdrawal_id, *args, **kwargs):
        salon = self._get_salon(request)
        wallet, _ = SalonWallet.objects.get_or_create(salon=salon)
        withdraw_request = get_object_or_404(
            SalonWalletWithdrawalRequest.objects.select_related(
                "wallet", "wallet__salon"
            ),
            pk=withdrawal_id,
            wallet=wallet,
        )
        try:
            withdraw_request.cancel(
                note="درخواست برداشت توسط مدیر مجموعه لغو شد و مبلغ به موجودی قابل برداشت برگشت داده شد."
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                "درخواست برداشت مجموعه لغو شد و مبلغ به موجودی قابل برداشت برگشت داده شد.",
            )

        next_url = (request.POST.get("next") or "").strip()
        if next_url:
            return redirect(next_url)
        return redirect("dashboards:payout_settings")


class SalonFinanceReportsView(_SalonFinanceMixin, View):
    template_name = "dashboards/finance_reports.html"

    def _get_filters(self, request):
        _validate_finance_report_query_size(request)

        today = timezone.localdate()
        default_start = today - timedelta(days=29)

        start_date = parse_jalali_input(
            request.GET.get("start_date"),
            fallback=default_start,
        )
        end_date = parse_jalali_input(
            request.GET.get("end_date"),
            fallback=today,
        )

        start_date, end_date = _normalize_finance_report_range(start_date, end_date)

        payment_method = _clean_finance_report_choice(
            request.GET.get("payment_method"),
            FINANCE_REPORT_PAYMENT_METHODS,
        )
        payout_state = _clean_finance_report_choice(
            request.GET.get("payout_state"),
            FINANCE_REPORT_PAYOUT_STATES,
        )

        return {
            "start_date": start_date,
            "end_date": end_date,
            "payment_method": payment_method,
            "payout_state": payout_state,
        }

    def _build_settlement_queryset(self, salon, filters):
        qs = SalonSettlement.objects.filter(salon=salon).select_related(
            "order", "customer__user", "payment"
        )

        if filters["start_date"]:
            qs = qs.filter(created_at__date__gte=filters["start_date"])
        if filters["end_date"]:
            qs = qs.filter(created_at__date__lte=filters["end_date"])
        if filters["payment_method"]:
            qs = qs.filter(payment_method=filters["payment_method"])
        if filters["payout_state"]:
            qs = qs.filter(payout_state=filters["payout_state"])

        return qs

    def _build_wallet_queryset(self, wallet, filters):
        qs = wallet.transactions.select_related("order", "settlement")
        if filters["start_date"]:
            qs = qs.filter(created_at__date__gte=filters["start_date"])
        if filters["end_date"]:
            qs = qs.filter(created_at__date__lte=filters["end_date"])
        return qs

    def _build_withdrawals_queryset(self, wallet, filters):
        qs = wallet.withdrawal_requests.all()
        if filters["start_date"]:
            qs = qs.filter(created_at__date__gte=filters["start_date"])
        if filters["end_date"]:
            qs = qs.filter(created_at__date__lte=filters["end_date"])
        return qs

    def _build_orders_queryset(self, salon, filters):
        qs = Order.objects.filter(salon=salon)

        if filters["start_date"]:
            qs = qs.filter(register_date__gte=filters["start_date"])
        if filters["end_date"]:
            qs = qs.filter(register_date__lte=filters["end_date"])
        if filters["payment_method"]:
            qs = qs.filter(selected_payment_method=filters["payment_method"])

        return qs

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        release_eligible_salon_wallet_funds_for_salon(salon)
        wallet, _ = SalonWallet.objects.get_or_create(salon=salon)

        try:
            filters = self._get_filters(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:finance_reports")
        settlement_qs = self._build_settlement_queryset(salon, filters)
        wallet_tx_qs = self._build_wallet_queryset(wallet, filters)
        withdrawals_qs = self._build_withdrawals_queryset(wallet, filters)

        orders_qs = self._build_orders_queryset(salon, filters)

        campaign_summary = orders_qs.aggregate(
            coupon_uses=Count(
                "id", filter=Q(coupon_code__gt="") & Q(coupon_discount_amount__gt=0)
            ),
            coupon_discount_total=Sum("coupon_discount_amount"),
            basket_uses=Count(
                "id",
                filter=Q(basket_discount_title__gt="")
                & Q(basket_discount_amount__gt=0),
            ),
            basket_discount_total=Sum("basket_discount_amount"),
        )

        coupon_performance = []
        for row in (
            orders_qs.exclude(coupon_code="")
            .exclude(coupon_discount_amount__lte=0)
            .values("coupon_code")
            .annotate(
                uses=Count("id"),
                successful=Count(
                    "id", filter=Q(status__in=["confirmed", "paid", "completed"])
                ),
                cancelled=Count("id", filter=Q(status="cancelled")),
                sales=Sum("total_amount"),
                discount_total=Sum("coupon_discount_amount"),
                refunds=Sum("refunded_to_wallet_amount"),
            )
            .order_by("-discount_total", "-uses")[:12]
        ):
            uses = _to_int(row["uses"])
            successful = _to_int(row["successful"])
            row["success_rate"] = round((successful / uses) * 100, 1) if uses else 0
            coupon_performance.append(row)

        basket_performance = []
        for row in (
            orders_qs.exclude(basket_discount_title="")
            .exclude(basket_discount_amount__lte=0)
            .values("basket_discount_title")
            .annotate(
                uses=Count("id"),
                successful=Count(
                    "id", filter=Q(status__in=["confirmed", "paid", "completed"])
                ),
                cancelled=Count("id", filter=Q(status="cancelled")),
                sales=Sum("total_amount"),
                discount_total=Sum("basket_discount_amount"),
                refunds=Sum("refunded_to_wallet_amount"),
            )
            .order_by("-discount_total", "-uses")[:12]
        ):
            uses = _to_int(row["uses"])
            successful = _to_int(row["successful"])
            row["success_rate"] = round((successful / uses) * 100, 1) if uses else 0
            basket_performance.append(row)

        summary = settlement_qs.aggregate(
            total_orders=Count("id"),
            digital_orders=Count(
                "id", filter=Q(payment_method__in=["online", "wallet"])
            ),
            manual_orders=Count("id", filter=Q(payment_method="pay_in_salon")),
            gross=Sum("gross_services_amount"),
            discounts=Sum("discount_amount"),
            paid=Sum("paid_amount"),
            refunds=Sum("refund_amount"),
            commission=Sum("platform_commission_amount"),
            net_due=Sum("net_amount_due_to_salon"),
        )

        payment_breakdown = []
        for row in (
            settlement_qs.values("payment_method")
            .annotate(
                count=Count("id"),
                paid=Sum("paid_amount"),
                refunds=Sum("refund_amount"),
                commission=Sum("platform_commission_amount"),
                net_due=Sum("net_amount_due_to_salon"),
            )
            .order_by("payment_method")
        ):
            payment_breakdown.append(
                {
                    "label": _payment_method_label(row["payment_method"]),
                    "count": _to_int(row["count"]),
                    "paid": _to_int(row["paid"]),
                    "refunds": _to_int(row["refunds"]),
                    "commission": _to_int(row["commission"]),
                    "net_due": _to_int(row["net_due"]),
                }
            )

        wallet_transactions = list(wallet_tx_qs.order_by("-created_at", "-id")[:30])

        wallet_transaction_rows = [
            {
                "object": tx,
                "created_label": _finance_datetime_label(tx.created_at),
                "order_number": tx.order.order_number if tx.order else "",
                "transaction_type_label": tx.get_transaction_type_display(),
                "pending_delta": _to_int(tx.pending_delta),
                "available_delta": _to_int(tx.available_delta),
                "description": tx.description,
            }
            for tx in wallet_transactions
        ]

        settlement_totals = {}
        for tx in wallet_tx_qs.exclude(settlement_id__isnull=True):
            bucket = settlement_totals.setdefault(
                tx.settlement_id, {"pending": 0, "available": 0}
            )
            bucket["pending"] += _to_int(tx.pending_delta)
            bucket["available"] += _to_int(tx.available_delta)

        reconciliation_rows = []
        discrepancy_total = 0

        for settlement in settlement_qs.order_by("-created_at", "-id")[:40]:
            tx_bucket = settlement_totals.get(
                settlement.id, {"pending": 0, "available": 0}
            )
            actual_wallet_effect = _to_int(tx_bucket["pending"]) + _to_int(
                tx_bucket["available"]
            )
            detail_totals = _settlement_detail_totals(settlement)

            expected_wallet_effect = _expected_salon_wallet_effect(settlement)

            delta = actual_wallet_effect - expected_wallet_effect
            discrepancy_total += abs(delta)

            if delta == 0:
                reconciliation_status = "ok"
                reconciliation_note = "سند تسویه و گردش کیف پول با هم هم‌خوان هستند."
            elif settlement.payout_state == SalonSettlement.PayoutState.HOLD:
                reconciliation_status = "review"
                reconciliation_note = (
                    settlement.payout_hold_reason
                    or "سند در وضعیت نگه‌داری است و نیاز به بررسی دارد."
                )
            else:
                reconciliation_status = "mismatch"
                reconciliation_note = (
                    "مبلغ ثبت‌شده در کیف پول مجموعه با سند تسویه این رزرو یکسان نیست."
                )

            reconciliation_rows.append(
                {
                    "settlement": settlement,
                    "payment_method_label": _payment_method_label(
                        settlement.payment_method
                    ),
                    "payout_state_label": _payout_state_label(settlement.payout_state),
                    "created_label": _finance_date_label(settlement.created_at),
                    "customer_mobile": (
                        settlement.customer.user.mobile_number
                        if settlement.customer and settlement.customer.user
                        else ""
                    ),
                    "expected_wallet_effect": expected_wallet_effect,
                    "actual_wallet_effect": actual_wallet_effect,
                    "delta": delta,
                    "status": reconciliation_status,
                    "note": reconciliation_note,
                    "tone": (
                        "bg-emerald-100 text-emerald-700"
                        if reconciliation_status == "ok"
                        else (
                            "bg-amber-100 text-amber-700"
                            if reconciliation_status == "review"
                            else "bg-rose-100 text-rose-700"
                        )
                    ),
                    "label": (
                        "سالم"
                        if reconciliation_status == "ok"
                        else (
                            "نیازمند بررسی"
                            if reconciliation_status == "review"
                            else "عدم تطابق"
                        )
                    ),
                    "gross_services_amount": detail_totals["gross"]
                    or _to_int(settlement.gross_services_amount),
                    "discount_amount": detail_totals["discount"]
                    or _to_int(settlement.discount_amount),
                    "paid_amount": detail_totals["paid"]
                    or _to_int(settlement.paid_amount),
                    "stylist_share": detail_totals["stylist_share"],
                    "salon_share": detail_totals["salon_share"]
                    or expected_wallet_effect,
                    "salon_profit": detail_totals["salon_profit"],
                    "refund_amount": _to_int(settlement.refund_amount),
                    "platform_commission_amount": _to_int(
                        settlement.platform_commission_amount
                    ),
                }
            )

        wallet_summary = {
            "sales_pending": sum(
                max(_to_int(tx.pending_delta), 0)
                for tx in wallet_transactions
                if tx.transaction_type == "sale_pending"
            ),
            "released_to_available": sum(
                max(_to_int(tx.available_delta), 0)
                for tx in wallet_transactions
                if tx.transaction_type == "pending_release"
            ),
            "refund_debits": sum(
                abs(min(_to_int(tx.pending_delta), 0))
                + abs(min(_to_int(tx.available_delta), 0))
                for tx in wallet_transactions
                if tx.transaction_type == "refund_debit"
            ),
            "withdraw_requests": sum(
                abs(min(_to_int(tx.available_delta), 0))
                for tx in wallet_transactions
                if tx.transaction_type == "withdraw_request"
            ),
            "withdraw_restores": sum(
                max(_to_int(tx.available_delta), 0)
                for tx in wallet_transactions
                if tx.transaction_type == "withdraw_restore"
            ),
        }

        withdrawal_summary = withdrawals_qs.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            approved=Count("id", filter=Q(status="approved")),
            rejected=Count("id", filter=Q(status__in=["rejected", "cancelled"])),
            requested_amount=Sum("amount"),
            approved_amount=Sum("amount", filter=Q(status="approved")),
            pending_amount=Sum("amount", filter=Q(status="pending")),
        )

        finance_alerts = []
        if not salon.payout_profile_complete:
            finance_alerts.append(
                "پروفایل امور مالی مجموعه هنوز کامل نیست و بعضی تسویه‌ها در حالت نگه‌داری باقی می‌مانند."
            )
        if discrepancy_total:
            finance_alerts.append(
                f"در این بازه {discrepancy_total:,} تومان اختلاف بین اسناد تسویه و کیف پول مالی دیده شده است و باید سفارش‌های flagged را بررسی کنی."
            )
        if _to_int(withdrawal_summary.get("pending")):
            finance_alerts.append(
                f"{_to_int(withdrawal_summary.get('pending'))} درخواست برداشت هنوز در انتظار بررسی مالی است."
            )
        if not finance_alerts:
            finance_alerts.append(
                "در این بازه اختلاف مهمی دیده نشد و گردش کیف پول با اسناد تسویه هم‌راستا است."
            )

        reconciliation_attention_rows = [
            row for row in reconciliation_rows if row["status"] != "ok"
        ]

        default_start = timezone.localdate() - timedelta(days=29)
        default_end = timezone.localdate()
        active_filter_count = sum(
            [
                bool(filters["payment_method"]),
                bool(filters["payout_state"]),
                filters["start_date"] != default_start,
                filters["end_date"] != default_end,
            ]
        )
        if filters["start_date"] == default_start and filters["end_date"] == default_end:
            report_period_label = "۳۰ روز اخیر"
        elif filters["start_date"] and filters["end_date"]:
            report_period_label = (
                f"{format_jalali_numeric(filters['start_date'])} تا "
                f"{format_jalali_numeric(filters['end_date'])}"
            )
        else:
            report_period_label = "بازه انتخاب‌شده"

        export_query = request.GET.copy()
        export_url = reverse("dashboards:finance_reports_export")
        if export_query:
            export_url = f"{export_url}?{export_query.urlencode()}"

        context = self._base_context(request, title="گزارش تراکنش‌ها")
        context.update(
            {
                "salon": salon,
                "wallet": wallet,
                "page_meta": {
                    "title": "گزارش تراکنش‌ها",
                    "description": "ورود و خروج پول، روش‌های دریافت و سندهایی که نیاز به بررسی دارند را در یک صفحه ببین.",
                    "icon": "fa-solid fa-chart-line",
                    "primary_action": {
                        "label": "بازگشت به پول مجموعه",
                        "url": reverse("dashboards:payout_settings"),
                    },
                    "badges": ["تراکنش‌ها", "روش پرداخت", "بررسی اختلاف"],
                },
                "filters": {
                    "start_date": format_jalali_numeric(filters["start_date"]),
                    "end_date": format_jalali_numeric(filters["end_date"]),
                    "payment_method": filters["payment_method"],
                    "payout_state": filters["payout_state"],
                },
                "payment_method_options": [
                    ("", "همه روش‌ها"),
                    ("online", "پرداخت آنلاین"),
                    ("wallet", "کیف پول"),
                    ("pay_in_salon", "پرداخت در مجموعه"),
                ],
                "payout_state_options": [
                    ("", "همه وضعیت‌ها"),
                    ("awaiting_payment", "در انتظار پرداخت"),
                    ("manual_collection", "پرداخت در مجموعه"),
                    ("ready", "آماده تسویه"),
                    ("hold", "نیازمند بررسی"),
                    ("paid", "تسویه‌شده"),
                    ("cancelled", "لغوشده"),
                ],
                "export_url": export_url,
                "clear_filters_url": reverse("dashboards:finance_reports"),
                "active_filter_count": active_filter_count,
                "report_period_label": report_period_label,
                "transaction_summary_cards": [
                    {
                        "label": "دریافتی ثبت‌شده",
                        "value": _money(summary.get("paid")),
                        "hint": "پرداخت‌های ثبت‌شده در این بازه",
                        "tone": "primary",
                    },
                    {
                        "label": "بازپرداخت",
                        "value": _money(summary.get("refunds")),
                        "hint": "مبالغ برگشتی به مشتری",
                        "tone": "danger",
                    },
                    {
                        "label": "سهم مجموعه",
                        "value": _money(summary.get("net_due")),
                        "hint": "سهم مجموعه از اسناد این بازه",
                        "tone": "success",
                    },
                    {
                        "label": "نیازمند بررسی",
                        "value": f"{len(reconciliation_attention_rows)} مورد",
                        "hint": "اختلاف یا سند نگه‌داری‌شده",
                        "tone": "warning" if reconciliation_attention_rows else "success",
                    },
                ],
                "reconciliation_attention_rows": reconciliation_attention_rows,
                "summary_cards": [
                    {
                        "label": "جمع پرداخت دیجیتال",
                        "value": _money(summary.get("paid")),
                        "tone": "primary",
                    },
                    {
                        "label": "جمع تخفیف‌ها",
                        "value": _money(summary.get("discounts")),
                        "tone": "neutral",
                    },
                    {
                        "label": "جمع بازگشت وجه",
                        "value": _money(summary.get("refunds")),
                        "tone": "danger",
                    },
                    {
                        "label": "خالص سهم مجموعه",
                        "value": _money(summary.get("net_due")),
                        "tone": "success",
                    },
                    {
                        "label": "کارمزد پلتفرم",
                        "value": _money(summary.get("commission")),
                        "tone": "warning",
                    },
                    {
                        "label": "اختلاف شناسایی‌شده",
                        "value": _money(discrepancy_total),
                        "tone": "danger" if discrepancy_total else "success",
                    },
                ],
                "kpis": {
                    "total_orders": _to_int(summary.get("total_orders")),
                    "digital_orders": _to_int(summary.get("digital_orders")),
                    "manual_orders": _to_int(summary.get("manual_orders")),
                    "wallet_available": _money(wallet.available_balance),
                    "wallet_pending": _money(wallet.pending_balance),
                },
                "payment_breakdown": payment_breakdown,
                "wallet_summary": wallet_summary,
                "withdrawal_summary": {
                    k: _to_int(v) for k, v in withdrawal_summary.items()
                },
                "campaign_cards": [
                    {
                        "label": "استفاده از کد تخفیف",
                        "value": _to_int(campaign_summary.get("coupon_uses")),
                        "tone": "primary",
                    },
                    {
                        "label": "جمع تخفیف کدها",
                        "value": _money(campaign_summary.get("coupon_discount_total")),
                        "tone": "success",
                    },
                    {
                        "label": "استفاده از سبدهای تخفیف",
                        "value": _to_int(campaign_summary.get("basket_uses")),
                        "tone": "primary",
                    },
                    {
                        "label": "جمع تخفیف خدمات",
                        "value": _money(campaign_summary.get("basket_discount_total")),
                        "tone": "success",
                    },
                ],
                "coupon_performance": coupon_performance,
                "basket_performance": basket_performance,
                "reconciliation_rows": reconciliation_rows,
                "wallet_transactions": wallet_transactions,
                "wallet_transaction_rows": wallet_transaction_rows,
                "finance_alerts": finance_alerts,
            },
        )
        return render(request, self.template_name, context)


class SalonFinanceReportsExportCsvView(_SalonFinanceMixin, View):
    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        report_view = SalonFinanceReportsView()

        try:
            filters = report_view._get_filters(request)
        except ValidationError as exc:
            return HttpResponse(
                str(exc),
                status=400,
                content_type="text/plain; charset=utf-8",
            )

        settlement_qs = report_view._build_settlement_queryset(salon, filters)

        wallet, _ = SalonWallet.objects.get_or_create(salon=salon)
        wallet_tx_qs = wallet.transactions.select_related("settlement")

        if filters["start_date"]:
            wallet_tx_qs = wallet_tx_qs.filter(
                created_at__date__gte=filters["start_date"]
            )
        if filters["end_date"]:
            wallet_tx_qs = wallet_tx_qs.filter(
                created_at__date__lte=filters["end_date"]
            )

        settlement_totals = {}
        for tx in wallet_tx_qs.exclude(settlement_id__isnull=True):
            bucket = settlement_totals.setdefault(
                tx.settlement_id, {"pending": 0, "available": 0}
            )
            bucket["pending"] += _to_int(tx.pending_delta)
            bucket["available"] += _to_int(tx.available_delta)

        # CSV cannot reliably preserve Persian text, RTL direction, and column
        # presentation when opened by double-clicking in Excel on Windows. Return
        # an Excel-compatible HTML workbook instead: it needs no extra dependency,
        # opens correctly in Excel, keeps Persian text intact, and allows RTL
        # layout/alignment.
        response = HttpResponse(content_type="application/vnd.ms-excel; charset=utf-8")
        response["Content-Disposition"] = (
            'attachment; filename="loomera-finance-reconciliation-report.xls"'
        )

        def html_escape(value):
            value = _csv_text(value)
            return (
                str(value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
            )

        def money_cell(value):
            return f'<td class="num">{_to_int(value)}</td>'

        rows = []
        for settlement in settlement_qs.order_by("-created_at", "-id")[
            : _finance_report_export_max_rows()
        ]:
            tx_bucket = settlement_totals.get(
                settlement.id, {"pending": 0, "available": 0}
            )
            actual_wallet_effect = _to_int(tx_bucket["pending"]) + _to_int(
                tx_bucket["available"]
            )
            detail_totals = _settlement_detail_totals(settlement)

            expected_wallet_effect = _expected_salon_wallet_effect(settlement)

            delta = actual_wallet_effect - expected_wallet_effect
            note = (
                "سالم"
                if delta == 0
                else settlement.payout_hold_reason or "نیازمند بررسی"
            )

            row_class = "ok" if delta == 0 else "warn"
            rows.append(f"""
                <tr class="{row_class}">
                    <td class="text">{html_escape(settlement.order.order_number)}</td>
                    <td class="text">{html_escape(_finance_datetime_label(settlement.created_at))}</td>
                    <td class="text">{html_escape(_payment_method_label(settlement.payment_method))}</td>
                    <td class="text">{html_escape(_payout_state_label(settlement.payout_state))}</td>
                    {money_cell(detail_totals["gross"] or settlement.gross_services_amount)}
                    {money_cell(detail_totals["discount"] or settlement.discount_amount)}
                    {money_cell(detail_totals["paid"] or settlement.paid_amount)}
                    {money_cell(settlement.refund_amount)}
                    {money_cell(settlement.platform_commission_amount)}
                    {money_cell(detail_totals["stylist_share"])}
                    {money_cell(detail_totals["salon_share"] or expected_wallet_effect)}
                    {money_cell(detail_totals["salon_profit"])}
                    {money_cell(actual_wallet_effect)}
                    {money_cell(delta)}
                    <td class="text note">{html_escape(note)}</td>
                </tr>
                """)

        generated_at = _finance_datetime_label(timezone.now())
        title = "گزارش تطبیق اسناد و کیف پول لومرا"
        period_label = "همه بازه‌ها"
        if filters["start_date"] or filters["end_date"]:
            start_label = (
                _finance_date_label(filters["start_date"])
                if filters["start_date"]
                else "ابتدای داده‌ها"
            )
            end_label = (
                _finance_date_label(filters["end_date"])
                if filters["end_date"]
                else "امروز"
            )
            period_label = f"از {start_label} تا {end_label}"

        html = f"""\ufeff<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <style>
    body {{
      direction: rtl;
      unicode-bidi: embed;
      font-family: Tahoma, Arial, sans-serif;
      color: #1f2937;
    }}
    .meta {{
      margin-bottom: 14px;
      font-size: 12px;
      color: #4b5563;
    }}
    table {{
      direction: rtl;
      border-collapse: collapse;
      width: 100%;
      mso-table-lspace: 0pt;
      mso-table-rspace: 0pt;
    }}
    th {{
      background: #f3efff;
      color: #35285f;
      font-weight: 700;
      text-align: right;
      border: 1px solid #d7cdee;
      padding: 8px;
      white-space: nowrap;
    }}
    td {{
      border: 1px solid #e7e0f3;
      padding: 7px;
      text-align: right;
      vertical-align: top;
      white-space: nowrap;
    }}
    .text {{ mso-number-format: "\\@"; }}
    .num {{ mso-number-format: "0"; text-align: left; direction: ltr; }}
    .note {{ white-space: normal; min-width: 220px; }}
    .ok td {{ background: #f7fff9; }}
    .warn td {{ background: #fff8ed; }}
  </style>
</head>
<body>
  <h2>{html_escape(title)}</h2>
  <div class="meta">بازه گزارش: {html_escape(period_label)}</div>
  <div class="meta">زمان خروجی: {html_escape(generated_at)}</div>
  <table>
    <thead>
      <tr>
        <th>شماره سفارش</th>
        <th>تاریخ ثبت سند</th>
        <th>روش پرداخت</th>
        <th>وضعیت تسویه</th>
        <th>جمع خدمات</th>
        <th>تخفیف</th>
        <th>مبلغ پرداخت‌شده</th>
        <th>بازگشت وجه</th>
        <th>کارمزد پلتفرم</th>
        <th>سهم متخصص</th>
        <th>سهم مجموعه</th>
        <th>سود خالص مجموعه</th>
        <th>اثر واقعی کیف پول مجموعه</th>
        <th>اختلاف</th>
        <th>یادداشت تطبیق</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows) if rows else '<tr><td colspan="15">داده‌ای برای این گزارش وجود ندارد.</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""
        response.write(html)
        return response


class PlatformFinanceAdminReportView(_PlatformFinanceAdminMixin, View):
    template_name = "dashboards/platform_finance_report.html"

    def _get_filters(self, request):
        _validate_finance_report_query_size(request)

        today = timezone.localdate()
        default_start = today - timedelta(days=29)

        start_date = parse_jalali_input(
            request.GET.get("start_date"),
            fallback=default_start,
        )
        end_date = parse_jalali_input(
            request.GET.get("end_date"),
            fallback=today,
        )

        start_date, end_date = _normalize_finance_report_range(start_date, end_date)

        payment_method = _clean_finance_report_choice(
            request.GET.get("payment_method"),
            FINANCE_REPORT_PAYMENT_METHODS,
        )
        payout_state = _clean_finance_report_choice(
            request.GET.get("payout_state"),
            FINANCE_REPORT_PAYOUT_STATES,
        )

        salon_id = _dashboard_positive_int_or_none(request.GET.get("salon_id"))

        if salon_id and not Salon.objects.filter(pk=salon_id).exists():
            salon_id = None

        return {
            "start_date": start_date,
            "end_date": end_date,
            "payment_method": payment_method,
            "payout_state": payout_state,
            "salon_id": salon_id,
        }

    def _build_settlement_queryset(self, filters):
        qs = SalonSettlement.objects.select_related(
            "salon", "order", "customer__user", "payment"
        )

        if filters["start_date"]:
            qs = qs.filter(created_at__date__gte=filters["start_date"])
        if filters["end_date"]:
            qs = qs.filter(created_at__date__lte=filters["end_date"])
        if filters["payment_method"]:
            qs = qs.filter(payment_method=filters["payment_method"])
        if filters["payout_state"]:
            qs = qs.filter(payout_state=filters["payout_state"])
        if filters["salon_id"]:
            qs = qs.filter(salon_id=filters["salon_id"])

        return qs

    def get(self, request, *args, **kwargs):
        try:
            filters = self._get_filters(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:platform_finance")
        settlement_qs = self._build_settlement_queryset(filters)

        wallet_tx_qs = SalonWalletTransaction.objects.select_related(
            "wallet__salon", "order", "settlement"
        )
        if filters["start_date"]:
            wallet_tx_qs = wallet_tx_qs.filter(
                created_at__date__gte=filters["start_date"]
            )
        if filters["end_date"]:
            wallet_tx_qs = wallet_tx_qs.filter(
                created_at__date__lte=filters["end_date"]
            )
        if filters["salon_id"]:
            wallet_tx_qs = wallet_tx_qs.filter(wallet__salon_id=filters["salon_id"])

        pending_salon_withdrawals = SalonWalletWithdrawalRequest.objects.select_related(
            "wallet__salon"
        ).filter(status="pending")
        if filters["start_date"]:
            pending_salon_withdrawals = pending_salon_withdrawals.filter(
                created_at__date__gte=filters["start_date"]
            )
        if filters["end_date"]:
            pending_salon_withdrawals = pending_salon_withdrawals.filter(
                created_at__date__lte=filters["end_date"]
            )
        if filters["salon_id"]:
            pending_salon_withdrawals = pending_salon_withdrawals.filter(
                wallet__salon_id=filters["salon_id"]
            )

        pending_customer_withdrawals = WalletWithdrawalRequest.objects.select_related(
            "wallet__user"
        ).filter(status="pending")
        if filters["start_date"]:
            pending_customer_withdrawals = pending_customer_withdrawals.filter(
                created_at__date__gte=filters["start_date"]
            )
        if filters["end_date"]:
            pending_customer_withdrawals = pending_customer_withdrawals.filter(
                created_at__date__lte=filters["end_date"]
            )

        summary = settlement_qs.aggregate(
            total_orders=Count("id"),
            total_salons=Count("salon_id", distinct=True),
            digital_orders=Count(
                "id", filter=Q(payment_method__in=["online", "wallet"])
            ),
            gross=Sum("gross_services_amount"),
            discounts=Sum("discount_amount"),
            paid=Sum("paid_amount"),
            refunds=Sum("refund_amount"),
            commission=Sum("platform_commission_amount"),
            net_due=Sum("net_amount_due_to_salon"),
        )

        top_salons = list(
            settlement_qs.values("salon__salon_name")
            .annotate(
                orders=Count("id"),
                paid=Sum("paid_amount"),
                refunds=Sum("refund_amount"),
                net_due=Sum("net_amount_due_to_salon"),
            )
            .order_by("-net_due", "-paid")[:12]
        )

        settlement_totals = {}
        for tx in wallet_tx_qs.exclude(settlement_id__isnull=True):
            bucket = settlement_totals.setdefault(
                tx.settlement_id, {"pending": 0, "available": 0}
            )
            bucket["pending"] += _to_int(tx.pending_delta)
            bucket["available"] += _to_int(tx.available_delta)

        reconciliation_rows = []
        discrepancy_total = 0

        for settlement in settlement_qs.order_by("-created_at", "-id")[:80]:
            tx_bucket = settlement_totals.get(
                settlement.id, {"pending": 0, "available": 0}
            )
            actual_wallet_effect = _to_int(tx_bucket["pending"]) + _to_int(
                tx_bucket["available"]
            )

            expected_wallet_effect = _expected_salon_wallet_effect(settlement)

            delta = actual_wallet_effect - expected_wallet_effect
            discrepancy_total += abs(delta)

            if delta == 0:
                label = "سالم"
                tone = "bg-emerald-100 text-emerald-700"
                note = "اثر کیف پول و سند تسویه هم‌راستا هستند."
            elif settlement.payout_state == SalonSettlement.PayoutState.HOLD:
                label = "نیازمند بررسی"
                tone = "bg-amber-100 text-amber-700"
                note = settlement.payout_hold_reason or "سند در وضعیت نگه‌داری است."
            else:
                label = "عدم تطابق"
                tone = "bg-rose-100 text-rose-700"
                note = "گردش کیف پول این سفارش با خالص سند تسویه برابر نیست."

            reconciliation_rows.append(
                {
                    "settlement": settlement,
                    "payment_method_label": _payment_method_label(
                        settlement.payment_method
                    ),
                    "payout_state_label": _payout_state_label(settlement.payout_state),
                    "expected_wallet_effect": expected_wallet_effect,
                    "actual_wallet_effect": actual_wallet_effect,
                    "delta": delta,
                    "label": label,
                    "tone": tone,
                    "note": note,
                }
            )

        finance_alerts = []
        if discrepancy_total:
            finance_alerts.append(
                f"در این بازه {discrepancy_total:,} تومان اختلاف سراسری بین اسناد تسویه و گردش کیف پول مجموعه‌ها دیده شده است."
            )
        if pending_salon_withdrawals.count():
            finance_alerts.append(
                f"{pending_salon_withdrawals.count()} درخواست برداشت مجموعه هنوز در انتظار بررسی مالی است."
            )
        if pending_customer_withdrawals.count():
            finance_alerts.append(
                f"{pending_customer_withdrawals.count()} درخواست برداشت مشتری هنوز در انتظار بررسی است."
            )
        if not finance_alerts:
            finance_alerts.append(
                "در این بازه هشدار مهمی ثبت نشده و گزارش سراسری وضعیت پایداری دارد."
            )

        export_query = request.GET.copy()
        export_url = reverse("dashboards:platform_finance_export")
        if export_query:
            export_url = f"{export_url}?{export_query.urlencode()}"

        context = self._base_context(request, title="گزارش مالی سراسری")
        context.update(
            {
                "page_meta": {
                    "title": "گزارش مالی سراسری پلتفرم",
                    "description": "برای کنترل عملیاتی، فروش‌ها، برداشت‌ها، بازگشت وجه و اختلاف‌های مالی همه مجموعه‌ها را یک‌جا ببین.",
                    "icon": "fa-solid fa-building-columns",
                    "primary_action": {
                        "label": "بازگشت به خانه داشبورد",
                        "url": reverse("dashboards:home"),
                    },
                    "badges": [
                        "Platform Finance",
                        "Admin",
                        "Reconciliation",
                        "Withdrawals",
                    ],
                },
                "filters": {
                    "start_date": format_jalali_numeric(filters["start_date"]),
                    "end_date": format_jalali_numeric(filters["end_date"]),
                    "payment_method": filters["payment_method"],
                    "payout_state": filters["payout_state"],
                    "salon_id": filters["salon_id"],
                },
                "payment_method_options": [
                    ("", "همه روش‌ها"),
                    ("online", "پرداخت آنلاین"),
                    ("wallet", "کیف پول"),
                    ("pay_in_salon", "پرداخت در مجموعه"),
                ],
                "payout_state_options": [
                    ("", "همه وضعیت‌ها"),
                    ("awaiting_payment", "در انتظار پرداخت"),
                    ("manual_collection", "پرداخت در مجموعه"),
                    ("ready", "آماده تسویه"),
                    ("hold", "نیازمند بررسی"),
                    ("paid", "تسویه‌شده"),
                    ("cancelled", "لغوشده"),
                ],
                "salon_options": Salon.objects.order_by("salon_name").only(
                    "id", "salon_name"
                ),
                "export_url": export_url,
                "summary_cards": [
                    {
                        "label": "کل مجموعه‌های درگیر",
                        "value": _to_int(summary.get("total_salons")),
                    },
                    {
                        "label": "کل سفارش‌ها",
                        "value": _to_int(summary.get("total_orders")),
                    },
                    {
                        "label": "جمع پرداخت دیجیتال",
                        "value": _money(summary.get("paid")),
                    },
                    {
                        "label": "جمع تخفیف‌ها",
                        "value": _money(summary.get("discounts")),
                    },
                    {
                        "label": "جمع بازگشت وجه",
                        "value": _money(summary.get("refunds")),
                    },
                    {
                        "label": "کارمزد پلتفرم",
                        "value": _money(summary.get("commission")),
                    },
                    {
                        "label": "خالص سهم مجموعه‌ها",
                        "value": _money(summary.get("net_due")),
                    },
                    {"label": "اختلاف شناسایی‌شده", "value": _money(discrepancy_total)},
                ],
                "top_salons": top_salons,
                "pending_salon_withdrawals": list(
                    pending_salon_withdrawals.order_by("-created_at")[:10]
                ),
                "pending_customer_withdrawals": list(
                    pending_customer_withdrawals.order_by("-created_at")[:10]
                ),
                "reconciliation_rows": reconciliation_rows,
                "finance_alerts": finance_alerts,
            }
        )
        return render(request, self.template_name, context)


class PlatformFinanceAdminReportExportCsvView(_PlatformFinanceAdminMixin, View):
    def get(self, request, *args, **kwargs):
        view = PlatformFinanceAdminReportView()

        try:
            filters = view._get_filters(request)
        except ValidationError as exc:
            return HttpResponse(
                str(exc),
                status=400,
                content_type="text/plain; charset=utf-8",
            )

        settlement_qs = view._build_settlement_queryset(filters)

        wallet_tx_qs = SalonWalletTransaction.objects.select_related(
            "wallet__salon", "settlement"
        )
        if filters["start_date"]:
            wallet_tx_qs = wallet_tx_qs.filter(
                created_at__date__gte=filters["start_date"]
            )
        if filters["end_date"]:
            wallet_tx_qs = wallet_tx_qs.filter(
                created_at__date__lte=filters["end_date"]
            )
        if filters["salon_id"]:
            wallet_tx_qs = wallet_tx_qs.filter(wallet__salon_id=filters["salon_id"])

        settlement_totals = {}
        for tx in wallet_tx_qs.exclude(settlement_id__isnull=True):
            bucket = settlement_totals.setdefault(
                tx.settlement_id, {"pending": 0, "available": 0}
            )
            bucket["pending"] += _to_int(tx.pending_delta)
            bucket["available"] += _to_int(tx.available_delta)

        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = (
            'attachment; filename="loomera-platform-finance-report.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "مجموعه",
                "شماره سفارش",
                "تاریخ ثبت سند",
                "روش پرداخت",
                "وضعیت تسویه",
                "جمع خدمات",
                "تخفیف",
                "پرداخت",
                "بازگشت وجه",
                "کارمزد پلتفرم",
                "خالص سهم مجموعه",
                "اثر واقعی کیف پول",
                "اختلاف",
            ]
        )

        for settlement in settlement_qs.order_by("-created_at", "-id")[
            : _finance_report_export_max_rows()
        ]:
            tx_bucket = settlement_totals.get(
                settlement.id, {"pending": 0, "available": 0}
            )
            actual_wallet_effect = _to_int(tx_bucket["pending"]) + _to_int(
                tx_bucket["available"]
            )

            expected_wallet_effect = _expected_salon_wallet_effect(settlement)

            delta = actual_wallet_effect - expected_wallet_effect

            writer.writerow(
                [
                    _csv_text(settlement.salon.salon_name if settlement.salon else "-"),
                    _csv_text(settlement.order.order_number if settlement.order else "-"),
                    _csv_text(settlement.created_at.strftime("%Y-%m-%d %H:%M")),
                    _csv_text(_payment_method_label(settlement.payment_method)),
                    _csv_text(_payout_state_label(settlement.payout_state)),
                    _to_int(settlement.gross_services_amount),
                    _to_int(settlement.discount_amount),
                    _to_int(settlement.paid_amount),
                    _to_int(settlement.refund_amount),
                    _to_int(settlement.platform_commission_amount),
                    _to_int(settlement.net_amount_due_to_salon),
                    actual_wallet_effect,
                    delta,
                ]
            )

        return response


def _discount_state_counts(queryset, *, now=None):
    """Return mutually-exclusive user-facing state counts for timed discounts."""
    now = now or timezone.now()
    return {
        "total": queryset.count(),
        "running": queryset.filter(
            is_active=True, start_date__lte=now, end_date__gte=now
        ).count(),
        "scheduled": queryset.filter(
            is_active=True, start_date__gt=now
        ).count(),
        "ended": queryset.filter(end_date__lt=now).count(),
        "inactive": queryset.filter(
            is_active=False, end_date__gte=now
        ).count(),
    }


class SalonCouponManagementView(_SalonFinanceMixin, View):
    template_name = "dashboards/finance_coupons.html"

    def _get_editing_coupon(self, request, salon):
        coupon_id = request.GET.get("edit")
        if not coupon_id:
            return None

        parsed_coupon_id = _dashboard_positive_int_or_none(coupon_id)
        if parsed_coupon_id is None:
            raise ValidationError("شناسه کد تخفیف معتبر نیست.")

        return get_object_or_404(Coupon, pk=parsed_coupon_id, salon=salon)

    def _context(self, request, form, salon, editing_coupon=None):
        coupons = salon.coupons.filter(is_archived=False).order_by(
            "-is_active", "-start_date", "-id"
        )
        discount_now = timezone.now()
        context = self._base_context(request, title="کدهای تخفیف")
        context.update(
            {
                "salon": salon,
                "form": form,
                "coupons": coupons,
                "discount_now": discount_now,
                "discount_stats": _discount_state_counts(coupons, now=discount_now),
                "editing_coupon": editing_coupon,
                "form_action_url": (
                    reverse(
                        "dashboards:finance_coupon_update",
                        kwargs={"coupon_id": editing_coupon.id},
                    )
                    if editing_coupon
                    else reverse("dashboards:finance_coupons")
                ),
                "page_meta": {
                    "title": "کدهای تخفیف",
                    "description": "کدی بساز که مشتری هنگام رزرو وارد کند؛ درصد، سقف و بازه اعتبار را یک‌جا مدیریت کن.",
                    "icon": "fa-solid fa-ticket",
                },
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)

        try:
            editing_coupon = self._get_editing_coupon(request, salon)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:finance_coupons")

        form = (
            SalonCouponForm(instance=editing_coupon, salon=salon)
            if editing_coupon
            else SalonCouponForm(salon=salon)
        )
        return render(
            request,
            self.template_name,
            self._context(request, form, salon, editing_coupon=editing_coupon),
        )

    def post(self, request, *args, **kwargs):
        salon = self._get_salon(request)

        try:
            post_data = _sanitize_finance_coupon_post_data(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            form = SalonCouponForm(salon=salon)
            return render(
                request,
                self.template_name,
                self._context(request, form, salon),
                status=400,
            )

        form = SalonCouponForm(post_data, salon=salon)
        if form.is_valid():
            with transaction.atomic():
                coupon = form.save(commit=False)
                coupon.salon = salon
                coupon.save()
            messages.success(request, "کد تخفیف جدید برای مجموعه ذخیره شد.")
            return redirect("dashboards:finance_coupons")

        messages.error(request, "ذخیره کد تخفیف ممکن نشد. خطاهای فرم را بررسی کن.")
        return render(request, self.template_name, self._context(request, form, salon))


class SalonCouponToggleView(_SalonFinanceMixin, View):
    def post(self, request, coupon_id, *args, **kwargs):
        try:
            _validate_finance_coupon_post_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:finance_coupons")

        salon = self._get_salon(request)

        with transaction.atomic():
            coupon = get_object_or_404(
                Coupon.objects.select_for_update(),
                pk=coupon_id,
                salon=salon,
            )
            coupon.is_active = not coupon.is_active
            coupon.save(update_fields=["is_active"])

        messages.success(request, "وضعیت کد تخفیف به‌روزرسانی شد.")
        return redirect("dashboards:finance_coupons")


class SalonCouponUpdateView(_SalonFinanceMixin, View):
    def post(self, request, coupon_id, *args, **kwargs):
        salon = self._get_salon(request)
        management_view = SalonCouponManagementView()

        try:
            post_data = _sanitize_finance_coupon_post_data(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            coupon = get_object_or_404(Coupon, pk=coupon_id, salon=salon)
            form = SalonCouponForm(instance=coupon, salon=salon)
            return render(
                request,
                management_view.template_name,
                management_view._context(request, form, salon, editing_coupon=coupon),
                status=400,
            )

        with transaction.atomic():
            coupon = get_object_or_404(
                Coupon.objects.select_for_update(),
                pk=coupon_id,
                salon=salon,
            )
            form = SalonCouponForm(post_data, instance=coupon, salon=salon)

            if form.is_valid():
                updated_coupon = form.save(commit=False)
                updated_coupon.salon = salon
                updated_coupon.save()
                messages.success(request, "کد تخفیف ویرایش شد.")
                return redirect("dashboards:finance_coupons")

        messages.error(request, "ویرایش کد تخفیف ممکن نشد.")
        return render(
            request,
            management_view.template_name,
            management_view._context(request, form, salon, editing_coupon=coupon),
        )


class SalonCouponDeleteView(_SalonFinanceMixin, View):
    def post(self, request, coupon_id, *args, **kwargs):
        try:
            _validate_finance_coupon_post_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:finance_coupons")

        salon = self._get_salon(request)

        with transaction.atomic():
            coupon = get_object_or_404(
                Coupon.objects.select_for_update(),
                pk=coupon_id,
                salon=salon,
            )
            coupon.is_active = False
            coupon.save(update_fields=["is_active"])

        messages.success(request, "کد تخفیف به‌جای حذف، آرشیو/غیرفعال شد.")
        return redirect("dashboards:finance_coupons")


class SalonDiscountBasketManagementView(_SalonFinanceMixin, View):
    template_name = "dashboards/finance_baskets.html"

    def _get_editing_basket(self, request, salon):
        basket_id = request.GET.get("edit")
        if not basket_id:
            return None
        return get_object_or_404(DiscountBasket, pk=basket_id, salon=salon)

    def _context(self, request, form, salon, editing_basket=None):
        baskets = (
            salon.discount_baskets.filter(is_archived=False)
            .prefetch_related("discount_basket_details1__service")
            .order_by("-is_active", "-start_date", "-id")
        )
        discount_now = timezone.now()
        context = self._base_context(request, title="پیشنهاد خدمات")
        context.update(
            {
                "salon": salon,
                "form": form,
                "baskets": baskets,
                "discount_now": discount_now,
                "discount_stats": _discount_state_counts(baskets, now=discount_now),
                "editing_basket": editing_basket,
                "form_action_url": (
                    reverse(
                        "dashboards:finance_basket_update",
                        kwargs={"basket_id": editing_basket.id},
                    )
                    if editing_basket
                    else reverse("dashboards:finance_baskets")
                ),
                "page_meta": {
                    "title": "پیشنهاد خدمات",
                    "description": "یک تخفیف مشترک را روی چند خدمت قرار بده؛ هر خدمت جداگانه می‌تواند از این پیشنهاد استفاده کند.",
                    "icon": "fa-solid fa-gift",
                },
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        editing_basket = self._get_editing_basket(request, salon)
        form = (
            SalonDiscountBasketForm(instance=editing_basket, salon=salon)
            if editing_basket
            else SalonDiscountBasketForm(salon=salon)
        )
        return render(
            request,
            self.template_name,
            self._context(request, form, salon, editing_basket=editing_basket),
        )

    def post(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        form = SalonDiscountBasketForm(request.POST, salon=salon)

        if form.is_valid():
            requested_active = bool(form.cleaned_data.get("is_active"))
            service_ids = basket_service_ids_from_cleaned_services(
                form.cleaned_data.get("services")
            )

            conflicts = []
            if requested_active:
                conflicts = list(
                    find_basket_activation_conflicts(
                        salon=salon,
                        start_date=form.cleaned_data.get("start_date"),
                        end_date=form.cleaned_data.get("end_date"),
                        service_ids=service_ids,
                    )
                )

            basket = form.save(commit=False)
            basket.salon = salon

            if conflicts:
                basket.is_active = False

            basket.save()
            form.instance = basket
            form.save(commit=True)

            if conflicts:
                basket.is_active = False
                basket.save(update_fields=["is_active"])
                messages.warning(
                    request,
                    "پیشنهاد خدمات ذخیره شد، اما فعال نشد. "
                    + basket_conflict_message(conflicts),
                )
            else:
                messages.success(request, "پیشنهاد خدمات ذخیره شد.")

            return redirect("dashboards:finance_baskets")

        messages.error(request, "ذخیره پیشنهاد خدمات ممکن نشد. خطاهای فرم را بررسی کن.")
        return render(request, self.template_name, self._context(request, form, salon))


class SalonDiscountBasketUpdateView(_SalonFinanceMixin, View):

    def post(self, request, basket_id, *args, **kwargs):
        salon = self._get_salon(request)
        basket = get_object_or_404(DiscountBasket, pk=basket_id, salon=salon)
        form = SalonDiscountBasketForm(request.POST, instance=basket, salon=salon)
        management_view = SalonDiscountBasketManagementView()

        if form.is_valid():
            requested_active = bool(form.cleaned_data.get("is_active"))
            service_ids = basket_service_ids_from_cleaned_services(
                form.cleaned_data.get("services")
            )

            conflicts = []
            if requested_active:
                conflicts = list(
                    find_basket_activation_conflicts(
                        salon=salon,
                        start_date=form.cleaned_data.get("start_date"),
                        end_date=form.cleaned_data.get("end_date"),
                        service_ids=service_ids,
                        exclude_basket_id=basket.pk,
                    )
                )

            updated_basket = form.save(commit=False)
            updated_basket.salon = salon

            if conflicts:
                updated_basket.is_active = False

            updated_basket.save()
            form.instance = updated_basket
            form.save(commit=True)

            if conflicts:
                updated_basket.is_active = False
                updated_basket.save(update_fields=["is_active"])
                messages.warning(
                    request,
                    "پیشنهاد خدمات ویرایش شد، اما فعال نشد. "
                    + basket_conflict_message(conflicts),
                )
            else:
                messages.success(request, "پیشنهاد خدمات ویرایش شد.")

            return redirect("dashboards:finance_baskets")

        messages.error(request, "ویرایش پیشنهاد خدمات ممکن نشد.")
        return render(
            request,
            management_view.template_name,
            management_view._context(request, form, salon, editing_basket=basket),
        )


class SalonDiscountBasketToggleView(_SalonFinanceMixin, View):

    def post(self, request, basket_id, *args, **kwargs):
        salon = self._get_salon(request)
        basket = get_object_or_404(DiscountBasket, pk=basket_id, salon=salon)

        wants_activate = not basket.is_active

        if wants_activate:
            service_ids = basket_service_ids_from_instance(basket)

            conflicts = list(
                find_basket_activation_conflicts(
                    salon=salon,
                    start_date=basket.start_date,
                    end_date=basket.end_date,
                    service_ids=service_ids,
                    exclude_basket_id=basket.pk,
                )
            )

            if conflicts:
                messages.error(request, basket_conflict_message(conflicts))
                return redirect("dashboards:finance_baskets")

        basket.is_active = wants_activate
        basket.save(update_fields=["is_active"])

        if basket.is_active:
            messages.success(request, "سبد تخفیف فعال شد.")
        else:
            messages.success(request, "سبد تخفیف غیرفعال شد.")

        return redirect("dashboards:finance_baskets")


class SalonDiscountBasketDeleteView(_SalonFinanceMixin, View):
    def post(self, request, basket_id, *args, **kwargs):
        salon = self._get_salon(request)
        basket = get_object_or_404(DiscountBasket, pk=basket_id, salon=salon)
        basket.is_active = False
        basket.save(update_fields=["is_active"])
        messages.success(request, "سبد تخفیف به‌جای حذف، آرشیو/غیرفعال شد.")
        return redirect("dashboards:finance_baskets")


class SalonDiscountCampaignManagementView(_SalonFinanceMixin, View):
    template_name = "dashboards/finance_campaigns.html"

    def _get_editing_campaign(self, request, salon):
        campaign_id = request.GET.get("edit")
        if not campaign_id:
            return None
        return get_object_or_404(
            DiscountCampaign, pk=campaign_id, salon=salon, is_archived=False
        )

    def _context(self, request, form, salon, editing_campaign=None):
        campaigns = (
            salon.discount_campaigns.prefetch_related("coupons", "baskets")
            .filter(is_archived=False)
            .order_by("-is_active", "-start_date", "-id")
        )
        discount_now = timezone.now()
        context = self._base_context(request, title="کمپین‌های تخفیف")
        context.update(
            {
                "salon": salon,
                "form": form,
                "campaigns": campaigns,
                "discount_now": discount_now,
                "discount_stats": _discount_state_counts(campaigns, now=discount_now),
                "editing_campaign": editing_campaign,
                "form_action_url": (
                    reverse(
                        "dashboards:finance_campaign_update",
                        kwargs={"campaign_id": editing_campaign.id},
                    )
                    if editing_campaign
                    else reverse("dashboards:finance_campaigns")
                ),
                "page_meta": {
                    "title": "کمپین‌های تخفیف",
                    "description": "کدها و پیشنهادهای موجود را برای یک مناسبت یا بازه تبلیغاتی زیر یک کمپین مدیریت کن.",
                    "icon": "fa-solid fa-bullhorn",
                },
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        editing_campaign = self._get_editing_campaign(request, salon)
        form = (
            SalonDiscountCampaignForm(instance=editing_campaign, salon=salon)
            if editing_campaign
            else SalonDiscountCampaignForm(salon=salon)
        )
        return render(
            request,
            self.template_name,
            self._context(request, form, salon, editing_campaign=editing_campaign),
        )

    def post(self, request, *args, **kwargs):
        salon = self._get_salon(request)
        form = SalonDiscountCampaignForm(request.POST, salon=salon)

        if form.is_valid():
            requested_active = bool(form.cleaned_data.get("is_active"))
            selected_baskets = list(form.cleaned_data.get("baskets") or [])
            selected_coupons = list(form.cleaned_data.get("coupons") or [])

            service_ids = campaign_service_ids_from_selection(
                salon=salon,
                baskets=selected_baskets,
                coupons=selected_coupons,
            )

            conflicts = []
            if requested_active:
                conflicts = list(
                    find_campaign_activation_conflicts(
                        salon=salon,
                        start_date=form.cleaned_data.get("start_date"),
                        end_date=form.cleaned_data.get("end_date"),
                        service_ids=service_ids,
                    )
                )

            campaign = form.save(commit=False)
            campaign.salon = salon

            if conflicts:
                campaign.is_active = False

            campaign.save()
            form.save_m2m()

            if conflicts:
                campaign.is_active = False
                campaign.save(update_fields=["is_active", "updated_at"])
                messages.warning(
                    request,
                    "کمپین تخفیف ذخیره شد، اما فعال نشد. "
                    + campaign_conflict_message(conflicts),
                )
            else:
                messages.success(request, "کمپین تخفیف مجموعه ذخیره شد.")

            return redirect("dashboards:finance_campaigns")

        messages.error(request, "ذخیره کمپین ممکن نشد. خطاهای مشخص‌شده را اصلاح کن.")
        return render(request, self.template_name, self._context(request, form, salon))


class SalonDiscountCampaignUpdateView(_SalonFinanceMixin, View):

    def post(self, request, campaign_id, *args, **kwargs):
        salon = self._get_salon(request)
        campaign = get_object_or_404(
            DiscountCampaign,
            pk=campaign_id,
            salon=salon,
            is_archived=False,
        )
        form = SalonDiscountCampaignForm(request.POST, instance=campaign, salon=salon)
        management_view = SalonDiscountCampaignManagementView()

        if form.is_valid():
            requested_active = bool(form.cleaned_data.get("is_active"))
            selected_baskets = list(form.cleaned_data.get("baskets") or [])
            selected_coupons = list(form.cleaned_data.get("coupons") or [])

            service_ids = campaign_service_ids_from_selection(
                salon=salon,
                baskets=selected_baskets,
                coupons=selected_coupons,
            )

            conflicts = []
            if requested_active:
                conflicts = list(
                    find_campaign_activation_conflicts(
                        salon=salon,
                        start_date=form.cleaned_data.get("start_date"),
                        end_date=form.cleaned_data.get("end_date"),
                        service_ids=service_ids,
                        exclude_campaign_id=campaign.pk,
                    )
                )

            updated = form.save(commit=False)
            updated.salon = salon

            if conflicts:
                updated.is_active = False

            updated.save()
            form.save_m2m()

            if conflicts:
                updated.is_active = False
                updated.save(update_fields=["is_active", "updated_at"])
                messages.warning(
                    request,
                    "کمپین تخفیف ویرایش شد، اما فعال نشد. "
                    + campaign_conflict_message(conflicts),
                )
            else:
                messages.success(request, "کمپین تخفیف ویرایش شد.")

            return redirect("dashboards:finance_campaigns")

        messages.error(request, "ویرایش کمپین ممکن نشد. خطاهای مشخص‌شده را اصلاح کن.")
        return render(
            request,
            management_view.template_name,
            management_view._context(request, form, salon, editing_campaign=campaign),
        )


class SalonDiscountCampaignToggleView(_SalonFinanceMixin, View):

    def post(self, request, campaign_id, *args, **kwargs):
        salon = self._get_salon(request)
        campaign = get_object_or_404(
            DiscountCampaign,
            pk=campaign_id,
            salon=salon,
            is_archived=False,
        )

        wants_activate = not campaign.is_active

        if wants_activate:
            service_ids = campaign_service_ids_from_instance(campaign)

            conflicts = list(
                find_campaign_activation_conflicts(
                    salon=salon,
                    start_date=campaign.start_date,
                    end_date=campaign.end_date,
                    service_ids=service_ids,
                    exclude_campaign_id=campaign.pk,
                )
            )

            if conflicts:
                messages.error(request, campaign_conflict_message(conflicts))
                return redirect("dashboards:finance_campaigns")

        campaign.is_active = wants_activate
        campaign.save(update_fields=["is_active", "updated_at"])

        if campaign.is_active:
            messages.success(request, "کمپین تخفیف فعال شد.")
        else:
            messages.success(request, "کمپین تخفیف غیرفعال شد.")

        return redirect("dashboards:finance_campaigns")


class SalonDiscountCampaignDeleteView(_SalonFinanceMixin, View):
    def post(self, request, campaign_id, *args, **kwargs):
        salon = self._get_salon(request)
        campaign = get_object_or_404(
            DiscountCampaign, pk=campaign_id, salon=salon, is_archived=False
        )
        campaign.is_active = False
        campaign.is_archived = True
        campaign.save(update_fields=["is_active", "is_archived", "updated_at"])
        messages.success(request, "کمپین تخفیف آرشیو شد و از لیست فعال حذف شد.")
        return redirect("dashboards:finance_campaigns")
