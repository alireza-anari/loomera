from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.discounts.models import (
    Coupon,
    DiscountBasket,
    DiscountCampaign,
    DiscountRedemption,
    DiscountSnapshot,
    DiscountStackingPolicy,
    DiscountType,
)
from apps.orders.models import Order


def _safe_model_defaults(model, defaults):
    model_fields = {field.name for field in model._meta.get_fields()}
    return {
        key: value for key, value in (defaults or {}).items() if key in model_fields
    }


@dataclass
class DiscountEligibilityResult:
    is_valid: bool
    coupon: Coupon | None = None
    reason: str = ""
    amount: int = 0
    raw_amount: int = 0
    snapshot: dict[str, Any] | None = None


def calculate_discount_amount(*, discount_type: str, value: int, base_amount: int, cap_amount: int = 0) -> tuple[int, int]:
    base_amount = max(int(base_amount or 0), 0)
    value = max(int(value or 0), 0)
    if base_amount <= 0 or value <= 0:
        return 0, 0
    if discount_type in ("fixed_amount", "fixed", "amount"):
        raw = min(value, base_amount)
    else:
        raw = int((base_amount * min(value, 100)) / 100)
    amount = min(raw, int(cap_amount or 0)) if cap_amount and raw else raw
    return max(amount, 0), max(raw, 0)


class DiscountEligibilityService:
    @staticmethod
    def active_coupon_queryset(code: str, *, salon=None):
        now = timezone.now()
        qs = Coupon.objects.filter(
            coupon_code=(code or "").strip().upper(),
            is_active=True,
            is_archived=False,
            start_date__lte=now,
            end_date__gte=now,
        ).select_related("campaign", "salon")
        if salon is not None:
            qs = qs.filter(Q(salon=salon) | Q(salon__isnull=True))
        return qs.order_by("-salon_id", "-id")

    @staticmethod
    def get_coupon(code: str, *, salon=None) -> Coupon | None:
        if not (code or "").strip():
            return None
        return DiscountEligibilityService.active_coupon_queryset(code, salon=salon).first()

    @staticmethod
    def validate_coupon(*, coupon: Coupon | None, customer, salon, subtotal_after_service_discount: int, subtotal: int, payment_method: str = "") -> DiscountEligibilityResult:
        if not coupon:
            return DiscountEligibilityResult(False, reason="کد تخفیف معتبر یا فعال نیست.")
        if coupon.campaign and not coupon.campaign.is_active_now:
            return DiscountEligibilityResult(False, coupon=coupon, reason="کمپین این کد فعال نیست.")
        if coupon.min_order_amount and subtotal_after_service_discount < coupon.min_order_amount:
            return DiscountEligibilityResult(False, coupon=coupon, reason="مبلغ رزرو کمتر از حداقل مجاز این کد است.")
        if coupon.max_order_amount and subtotal_after_service_discount > coupon.max_order_amount:
            return DiscountEligibilityResult(False, coupon=coupon, reason="مبلغ رزرو بیشتر از سقف مجاز این کد است.")
        if coupon.eligible_payment_methods and payment_method and payment_method not in coupon.eligible_payment_methods:
            return DiscountEligibilityResult(False, coupon=coupon, reason="این کد برای روش پرداخت انتخابی معتبر نیست.")

        if customer and coupon.total_usage_limit:
            used_total = DiscountRedemption.objects.filter(coupon=coupon, status__in=["applied", "reserved"]).count()
            if used_total >= coupon.total_usage_limit:
                return DiscountEligibilityResult(False, coupon=coupon, reason="ظرفیت استفاده از این کد تکمیل شده است.")
        if customer and coupon.per_customer_usage_limit:
            used_customer = DiscountRedemption.objects.filter(
                coupon=coupon,
                customer=customer,
                status__in=["applied", "reserved"],
            ).count()
            if used_customer >= coupon.per_customer_usage_limit:
                return DiscountEligibilityResult(False, coupon=coupon, reason="شما قبلاً از این کد به سقف مجاز استفاده کرده‌اید.")
        if customer and coupon.first_booking_only:
            if Order.objects.filter(customer=customer).exclude(status="cancelled").exists():
                return DiscountEligibilityResult(False, coupon=coupon, reason="این کد فقط برای اولین رزرو کاربر است.")
        if customer and salon and coupon.first_salon_booking_only:
            if Order.objects.filter(customer=customer, salon=salon).exclude(status="cancelled").exists():
                return DiscountEligibilityResult(False, coupon=coupon, reason="این کد فقط برای اولین رزرو شما در این سالن است.")

        amount, raw_amount = calculate_discount_amount(
            discount_type=coupon.effective_discount_type,
            value=coupon.effective_discount_value,
            base_amount=subtotal_after_service_discount,
            cap_amount=coupon.max_discount_amount,
        )
        snapshot = build_coupon_snapshot(coupon, amount=amount, raw_amount=raw_amount, base_amount=subtotal_after_service_discount, subtotal=subtotal)
        return DiscountEligibilityResult(True, coupon=coupon, amount=amount, raw_amount=raw_amount, snapshot=snapshot)


def build_coupon_snapshot(coupon: Coupon | None, *, amount: int = 0, raw_amount: int = 0, base_amount: int = 0, subtotal: int = 0) -> dict[str, Any]:
    if not coupon:
        return {}
    return {
        "type": "coupon",
        "id": coupon.pk,
        "campaign_id": coupon.campaign_id,
        "code": coupon.coupon_code,
        "discount_type": coupon.effective_discount_type,
        "discount_value": coupon.effective_discount_value,
        "percent_legacy": int(coupon.discount or 0),
        "max_discount_amount": int(coupon.max_discount_amount or 0),
        "min_order_amount": int(coupon.min_order_amount or 0),
        "max_order_amount": int(coupon.max_order_amount or 0),
        "funded_by": coupon.funded_by,
        "salon_funding_percent": int(coupon.salon_funding_percent or 0),
        "platform_funding_percent": int(coupon.platform_funding_percent or 0),
        "staff_share_impact": coupon.staff_share_impact,
        "visibility": coupon.visibility,
        "stacking_policy": coupon.stacking_policy,
        "subtotal": int(subtotal or 0),
        "base_amount": int(base_amount or 0),
        "raw_amount": int(raw_amount or 0),
        "amount": int(amount or 0),
        "terms_text": coupon.terms_text,
    }


def build_basket_snapshot(basket: DiscountBasket | None, *, amount: int = 0, raw_amount: int = 0, base_amount: int = 0, service_ids=None) -> dict[str, Any]:
    if not basket:
        return {}
    return {
        "type": "basket",
        "id": basket.pk,
        "campaign_id": basket.campaign_id,
        "title": basket.discount_title,
        "discount_type": basket.effective_discount_type,
        "discount_value": basket.effective_discount_value,
        "percent_legacy": int(basket.discount or 0),
        "max_discount_amount": int(basket.max_discount_amount or 0),
        "min_order_amount": int(basket.min_order_amount or 0),
        "funded_by": basket.funded_by,
        "salon_funding_percent": int(basket.salon_funding_percent or 0),
        "platform_funding_percent": int(basket.platform_funding_percent or 0),
        "staff_share_impact": basket.staff_share_impact,
        "visibility": basket.visibility,
        "stacking_policy": basket.stacking_policy,
        "base_amount": int(base_amount or 0),
        "raw_amount": int(raw_amount or 0),
        "amount": int(amount or 0),
        "service_ids": list(service_ids or []),
        "terms_text": basket.terms_text,
    }


def build_order_discount_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "subtotal": int(payload.get("subtotal") or 0),
        "service_discount_amount": int(payload.get("basket_discount_amount") or 0),
        "coupon_discount_amount": int(payload.get("coupon_discount_amount") or 0),
        "total_discount_amount": int(payload.get("discount_amount") or 0),
        "final_amount": int(payload.get("total_amount") or 0),
        "basket": payload.get("basket_discount_snapshot") or {},
        "coupon": payload.get("coupon_discount_snapshot") or {},
    }


def _safe_model_defaults(model, defaults):
    """
    فقط فیلدهایی را نگه می‌دارد که واقعاً در مدل وجود دارند.
    برای جلوگیری از خطاهایی مثل:
    Invalid field name(s) for model ...
    """
    model_fields = {
        field.name
        for field in model._meta.get_fields()
        if not getattr(field, "auto_created", False)
        or getattr(field, "concrete", False)
    }

    return {
        key: value for key, value in (defaults or {}).items() if key in model_fields
    }


def _safe_model_lookup(model, lookup):
    """
    lookupهای update_or_create هم باید فقط شامل فیلدهای واقعی مدل باشند.
    """
    model_fields = {
        field.name
        for field in model._meta.get_fields()
        if not getattr(field, "auto_created", False)
        or getattr(field, "concrete", False)
    }

    return {key: value for key, value in (lookup or {}).items() if key in model_fields}


@transaction.atomic
def persist_order_discount_records(*, order, payload: dict[str, Any]):
    coupon = payload.get("coupon")
    basket = payload.get("basket_discount_basket")

    campaign = None
    if coupon and getattr(coupon, "campaign_id", None):
        campaign = coupon.campaign
    elif basket and getattr(basket, "campaign_id", None):
        campaign = basket.campaign

    subtotal_amount = int(payload.get("subtotal") or 0)
    service_discount_amount = int(payload.get("basket_discount_amount") or 0)
    coupon_discount_amount = int(payload.get("coupon_discount_amount") or 0)
    total_discount_amount = int(payload.get("discount_amount") or 0)
    final_amount = int(payload.get("total_amount") or 0)

    rules_snapshot = build_order_discount_snapshot(payload)

    snapshot_payload = {
        "subtotal_amount": subtotal_amount,
        "service_discount_amount": service_discount_amount,
        "coupon_discount_amount": coupon_discount_amount,
        "total_discount_amount": total_discount_amount,
        "final_amount": final_amount,
        "rules_snapshot": rules_snapshot,
        "coupon_snapshot": payload.get("coupon_discount_snapshot") or {},
        "basket_snapshot": payload.get("basket_discount_snapshot") or {},
    }

    snapshot_metadata = {
        "subtotal_amount": subtotal_amount,
        "service_discount_amount": service_discount_amount,
        "coupon_discount_amount": coupon_discount_amount,
        "total_discount_amount": total_discount_amount,
        "final_amount": final_amount,
        "rules_snapshot": rules_snapshot,
    }

    snapshot_lookup = _safe_model_lookup(
        DiscountSnapshot,
        {
            "order": order,
        },
    )

    snapshot_defaults = _safe_model_defaults(
        DiscountSnapshot,
        {
            "customer": getattr(order, "customer", None),
            "salon": getattr(order, "salon", None),
            "coupon": coupon,
            "basket": basket,
            "campaign": campaign,
            # فیلدهای مدل جدید/فعلی
            "source_type": "order",
            "title": "خلاصه تخفیف سفارش",
            "code": getattr(coupon, "coupon_code", "") if coupon else "",
            "amount": total_discount_amount,
            "percent": int(payload.get("discount_percent") or 0),
            "discount_amount": total_discount_amount,
            "discount_percent": int(payload.get("discount_percent") or 0),
            "eligible_subtotal": subtotal_amount,
            "max_discount_amount": int(payload.get("discount_cap_amount") or 0),
            "order_total_before_discount": subtotal_amount,
            "order_total_after_discount": final_amount,
            "payload": snapshot_payload,
            "metadata": snapshot_metadata,
            # اگر در بعضی نسخه‌های مدل هنوز این فیلدها وجود داشتند، مقدار می‌گیرند؛
            # اگر وجود نداشتند، _safe_model_defaults حذفشان می‌کند.
            "subtotal_amount": subtotal_amount,
            "service_discount_amount": service_discount_amount,
            "coupon_discount_amount": coupon_discount_amount,
            "total_discount_amount": total_discount_amount,
            "final_amount": final_amount,
            "rules_snapshot": rules_snapshot,
        },
    )

    if snapshot_lookup:
        DiscountSnapshot.objects.update_or_create(
            **snapshot_lookup,
            defaults=snapshot_defaults,
        )

    if coupon and coupon_discount_amount > 0:
        coupon_redemption_lookup = _safe_model_lookup(
            DiscountRedemption,
            {
                "order": order,
                "coupon": coupon,
            },
        )

        coupon_redemption_defaults = _safe_model_defaults(
            DiscountRedemption,
            {
                "customer": getattr(order, "customer", None),
                "salon": getattr(order, "salon", None),
                "campaign": getattr(coupon, "campaign", None),
                "basket": None,
                "code": getattr(coupon, "coupon_code", "") or "",
                "source_type": "coupon",
                "title": getattr(coupon, "title", "")
                or getattr(coupon, "coupon_code", "")
                or "کد تخفیف",
                "amount": coupon_discount_amount,
                "percent": int(
                    getattr(coupon, "effective_discount_value", 0)
                    or getattr(coupon, "discount", 0)
                    or 0
                ),
                "discount_amount": coupon_discount_amount,
                "discount_percent": int(
                    getattr(coupon, "effective_discount_value", 0)
                    or getattr(coupon, "discount", 0)
                    or 0
                ),
                "eligible_subtotal": max(subtotal_amount - service_discount_amount, 0),
                "max_discount_amount": int(
                    getattr(coupon, "max_discount_amount", 0) or 0
                ),
                "funded_by": getattr(coupon, "funded_by", ""),
                "staff_share_impact": getattr(coupon, "staff_share_impact", ""),
                "status": "applied",
                "snapshot": payload.get("coupon_discount_snapshot") or {},
                "payload": {
                    "subtotal_amount": subtotal_amount,
                    "coupon_discount_amount": coupon_discount_amount,
                    "final_amount": final_amount,
                    "coupon_snapshot": payload.get("coupon_discount_snapshot") or {},
                },
                "metadata": {
                    "source": "coupon",
                    "rules_snapshot": rules_snapshot,
                },
                # فیلدهای قدیمی، فقط اگر واقعاً در مدل باشند اعمال می‌شوند.
                "subtotal_amount": subtotal_amount,
                "final_amount": final_amount,
            },
        )

        if coupon_redemption_lookup:
            DiscountRedemption.objects.update_or_create(
                **coupon_redemption_lookup,
                defaults=coupon_redemption_defaults,
            )

    if basket and service_discount_amount > 0:
        basket_redemption_lookup = _safe_model_lookup(
            DiscountRedemption,
            {
                "order": order,
                "basket": basket,
            },
        )

        basket_redemption_defaults = _safe_model_defaults(
            DiscountRedemption,
            {
                "customer": getattr(order, "customer", None),
                "salon": getattr(order, "salon", None),
                "campaign": getattr(basket, "campaign", None),
                "coupon": None,
                "code": "",
                "source_type": "basket",
                "title": getattr(basket, "title", "")
                or getattr(basket, "discount_title", "")
                or "تخفیف خدمات",
                "amount": service_discount_amount,
                "percent": int(
                    payload.get("basket_discount_percent")
                    or getattr(basket, "discount", 0)
                    or 0
                ),
                "discount_amount": service_discount_amount,
                "discount_percent": int(
                    payload.get("basket_discount_percent")
                    or getattr(basket, "discount", 0)
                    or 0
                ),
                "eligible_subtotal": subtotal_amount,
                "max_discount_amount": int(
                    payload.get("basket_discount_cap_amount") or 0
                ),
                "funded_by": getattr(basket, "funded_by", ""),
                "staff_share_impact": getattr(basket, "staff_share_impact", ""),
                "status": "applied",
                "snapshot": payload.get("basket_discount_snapshot") or {},
                "payload": {
                    "subtotal_amount": subtotal_amount,
                    "service_discount_amount": service_discount_amount,
                    "final_amount": final_amount,
                    "basket_snapshot": payload.get("basket_discount_snapshot") or {},
                },
                "metadata": {
                    "source": "basket",
                    "rules_snapshot": rules_snapshot,
                },
                # فیلدهای قدیمی، فقط اگر واقعاً در مدل باشند اعمال می‌شوند.
                "subtotal_amount": subtotal_amount,
                "final_amount": final_amount,
            },
        )

        if basket_redemption_lookup:
            DiscountRedemption.objects.update_or_create(
                **basket_redemption_lookup,
                defaults=basket_redemption_defaults,
            )

    if hasattr(order, "discount_rules_snapshot"):
        order.discount_rules_snapshot = rules_snapshot
        order.save(update_fields=["discount_rules_snapshot"])

    return rules_snapshot


def archive_discount_object(obj):
    if hasattr(obj, "archive"):
        return obj.archive()
    obj.is_active = False
    obj.save(update_fields=["is_active"])
