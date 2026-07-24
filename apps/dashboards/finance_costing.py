from decimal import Decimal, ROUND_HALF_UP

from apps.orders.models import AppointmentMaterialUsage
from apps.services.models import StylistCommissionRule


def to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def money(value):
    amount = to_int(value)
    return f"{amount:,} تومان"


def _round_money(value) -> int:
    amount = Decimal(value or 0)
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _best_commission_rule(*, salon, stylist, service):
    qs = StylistCommissionRule.objects.filter(salon=salon, is_active=True)
    candidates = [
        qs.filter(stylist=stylist, service=service),
        qs.filter(stylist=stylist, service__isnull=True),
        qs.filter(stylist__isnull=True, service=service),
        qs.filter(stylist__isnull=True, service__isnull=True),
    ]
    for candidate in candidates:
        rule = candidate.order_by("-updated_at", "-id").first()
        if rule:
            return rule
    return None


def _rule_label(rule):
    if not rule:
        return "قانون سهم تعریف نشده"

    if rule.commission_type == StylistCommissionRule.CommissionType.FIXED:
        return f"مبلغ ثابت {money(rule.fixed_amount)}"

    percent = Decimal(rule.percent or 0)
    return f"{percent.normalize()}٪ سهم متخصص"


def _share_base_label(rule):
    if not rule:
        return "دریافتی بعد از تخفیف و کارمزد"

    if rule.share_base == StylistCommissionRule.ShareBase.GROSS_AFTER_DISCOUNT:
        return "دریافتی بعد از تخفیف"

    if rule.share_base == StylistCommissionRule.ShareBase.AFTER_PLATFORM_COMMISSION:
        return "بعد از کارمزد پلتفرم"

    return "بعد از کسر هزینه مواد"


def _material_policy_label(rule):
    if not rule:
        return "بر اساس پرداخت‌کننده ثبت‌شده روی مواد"

    if rule.material_cost_policy == StylistCommissionRule.MaterialCostPolicy.SALON_PAYS:
        return "هزینه مواد با مجموعه"

    if rule.material_cost_policy == StylistCommissionRule.MaterialCostPolicy.STYLIST_PAYS:
        return "هزینه مواد با متخصص"

    if rule.material_cost_policy == StylistCommissionRule.MaterialCostPolicy.SPLIT:
        percent = Decimal(rule.stylist_material_cost_percent or 0).normalize()
        return f"تقسیم هزینه مواد؛ سهم متخصص {percent}٪"

    return "بر اساس پرداخت‌کننده ثبت‌شده روی مواد"


def _split_material_costs(usages, rule):
    total = sum(to_int(item.total_cost) for item in usages)
    if total <= 0:
        return 0, 0

    if rule:
        if rule.material_cost_policy == StylistCommissionRule.MaterialCostPolicy.SALON_PAYS:
            return total, 0

        if rule.material_cost_policy == StylistCommissionRule.MaterialCostPolicy.STYLIST_PAYS:
            return 0, total

        if rule.material_cost_policy == StylistCommissionRule.MaterialCostPolicy.SPLIT:
            stylist_percent = Decimal(rule.stylist_material_cost_percent or 0)
            stylist_cost = _round_money(Decimal(total) * stylist_percent / Decimal("100"))
            stylist_cost = min(max(stylist_cost, 0), total)
            return total - stylist_cost, stylist_cost

    salon_cost = 0
    stylist_cost = 0

    for usage in usages:
        item_total = to_int(usage.total_cost)
        if usage.paid_by == AppointmentMaterialUsage.PaidBy.STYLIST:
            stylist_cost += item_total
        elif usage.paid_by == AppointmentMaterialUsage.PaidBy.SHARED:
            stylist_part = _round_money(Decimal(item_total) * Decimal("0.5"))
            stylist_cost += stylist_part
            salon_cost += item_total - stylist_part
        else:
            salon_cost += item_total

    return salon_cost, stylist_cost


def _calculate_stylist_gross_share(*, rule, share_base_amount):
    share_base_amount = max(to_int(share_base_amount), 0)
    if not rule or share_base_amount <= 0:
        return 0

    if rule.commission_type == StylistCommissionRule.CommissionType.FIXED:
        return min(to_int(rule.fixed_amount), share_base_amount)

    percent = Decimal(rule.percent or 0)
    amount = _round_money(Decimal(share_base_amount) * percent / Decimal("100"))
    return min(max(amount, 0), share_base_amount)


def calculate_appointment_finance(appointment):
    service_amount = to_int(getattr(appointment, "price", 0))
    salon = appointment.salon
    stylist = appointment.stylist
    service = appointment.service
    usages = list(
        AppointmentMaterialUsage.objects.filter(order_detail=appointment)
        .select_related("material")
        .order_by("-created_at", "-id")
    )

    materials_total = sum(to_int(item.total_cost) for item in usages)
    rule = _best_commission_rule(salon=salon, stylist=stylist, service=service)
    salon_materials_total, stylist_materials_total = _split_material_costs(usages, rule)

    # در این صفحه preview مالی روی مبلغ خود آیتم محاسبه می‌شود. تخصیص تخفیف/کارمزد نهایی
    # در OrderDetailFinancialSnapshot ذخیره می‌شود و در گزارش سود قابل بررسی است.
    net_after_platform = service_amount

    if rule:
        if rule.share_base == rule.ShareBase.GROSS_AFTER_DISCOUNT:
            share_base_amount = service_amount
        elif rule.share_base == rule.ShareBase.AFTER_PLATFORM_COMMISSION:
            share_base_amount = net_after_platform
        else:
            share_base_amount = max(net_after_platform - materials_total, 0)
    else:
        share_base_amount = net_after_platform

    stylist_gross_share = _calculate_stylist_gross_share(
        rule=rule,
        share_base_amount=share_base_amount,
    )

    stylist_material_deduction = stylist_materials_total
    salon_material_deduction = salon_materials_total

    if rule and rule.share_base == rule.ShareBase.NET_AFTER_MATERIALS:
        stylist_net_share = stylist_gross_share
        salon_gross_share = max(share_base_amount - stylist_gross_share, 0)
        salon_net_share = salon_gross_share
        salon_net_profit = salon_net_share
    else:
        stylist_net_share = max(stylist_gross_share - stylist_material_deduction, 0)
        salon_gross_share = max(net_after_platform - stylist_gross_share, 0)
        salon_net_share = max(salon_gross_share - salon_material_deduction, 0)
        salon_net_profit = salon_net_share

    summary_cards = [
        {"label": "مبلغ خدمت", "value": money(service_amount), "tone": "primary"},
        {"label": "کل مواد مصرفی", "value": money(materials_total), "tone": "warning"},
        {"label": "سهم خالص متخصص", "value": money(stylist_net_share), "tone": "success"},
        {"label": "سود خالص مجموعه", "value": money(salon_net_profit), "tone": "primary"},
    ]
    detail_rows = [
        {"label": "قانون سهم", "value": _rule_label(rule)},
        {"label": "مبنای محاسبه سهم", "value": _share_base_label(rule)},
        {"label": "سیاست هزینه مواد", "value": _material_policy_label(rule)},
        {"label": "سهم ناخالص متخصص", "value": money(stylist_gross_share)},
        {"label": "کسر مواد متخصص", "value": money(stylist_material_deduction)},
        {"label": "سهم خالص متخصص", "value": money(stylist_net_share)},
        {"label": "سهم ناخالص مجموعه", "value": money(salon_gross_share)},
        {"label": "کسر مواد مجموعه", "value": money(salon_material_deduction)},
        {"label": "سهم خالص مجموعه", "value": money(salon_net_share)},
        {"label": "سود خالص مجموعه", "value": money(salon_net_profit)},
    ]
    return {
        "service_amount": service_amount,
        "materials_total": materials_total,
        "salon_materials_total": salon_materials_total,
        "stylist_materials_total": stylist_materials_total,
        "stylist_gross_share": stylist_gross_share,
        "stylist_material_deduction": stylist_material_deduction,
        "stylist_net_share": stylist_net_share,
        "salon_gross_share": salon_gross_share,
        "salon_material_deduction": salon_material_deduction,
        "salon_net_share": salon_net_share,
        "salon_net_profit": salon_net_profit,
        "share_base_amount": share_base_amount,
        "rule": rule,
        "rule_label": _rule_label(rule),
        "share_base_label": _share_base_label(rule),
        "material_policy_label": _material_policy_label(rule),
        "usage_count": len(usages),
        "usages": usages,
        "summary_cards": summary_cards,
        "detail_rows": detail_rows,
    }
