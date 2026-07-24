from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db.models import Prefetch
from django.utils import timezone

from apps.discounts.models import DiscountBasket
from apps.discounts.services import calculate_discount_amount


@dataclass
class BasketDiscountResult:
    basket: DiscountBasket | None = None
    amount: int = 0
    raw_amount: int = 0
    percent: int = 0
    cap_amount: int = 0
    eligible_subtotal: int = 0
    discounted_service_ids: tuple[int, ...] = ()

    @property
    def title(self) -> str:
        return self.basket.discount_title if self.basket else ""

    @property
    def label(self) -> str:
        if not self.basket:
            return ""
        discount_type = _get_discount_type(self.basket)
        value = _get_discount_value(self.basket)
        if discount_type == "percentage":
            return f"{value}٪ تخفیف خدمات"
        return f"{value:,} تومان تخفیف خدمات"


def _now():
    return timezone.now()


def _get_discount_type(basket: DiscountBasket | None) -> str:
    if not basket:
        return "percentage"
    value = (
        getattr(basket, "effective_discount_type", None)
        or getattr(basket, "discount_type", None)
        or "percentage"
    )
    value = str(value or "percentage")
    if value in ("fixed", "amount", "fixed_amount"):
        return "fixed_amount"
    return "percentage"


def _get_discount_value(basket: DiscountBasket | None) -> int:
    if not basket:
        return 0
    return int(
        getattr(basket, "effective_discount_value", None)
        or getattr(basket, "discount_value", None)
        or getattr(basket, "discount", None)
        or 0
    )


def _get_cap_amount(basket: DiscountBasket | None) -> int:
    if not basket:
        return 0
    return int(
        getattr(basket, "effective_max_discount_amount", None)
        or getattr(basket, "max_discount_amount", None)
        or 0
    )


def _format_discount_cap(cap: int) -> str:
    if int(cap or 0) <= 0:
        return ""
    return f"تا سقف {int(cap):,} تومان"


def active_discount_basket_base_queryset(now=None):
    now = now or _now()
    return (
        DiscountBasket.objects.filter(
            is_active=True,
            is_archived=False,
            start_date__lte=now,
            end_date__gte=now,
        )
        .prefetch_related(
            "discount_basket_details1__service", "discount_basket_details1__stylist"
        )
        .order_by("-discount", "-max_discount_amount", "-start_date", "-id")
    )


def active_discount_basket_queryset(*, salon, now=None):
    return active_discount_basket_base_queryset(now=now).filter(salon=salon)


def active_discount_basket_prefetch(
    *, to_attr: str = "active_discount_baskets"
) -> Prefetch:
    return Prefetch(
        "discount_baskets",
        queryset=active_discount_basket_base_queryset(),
        to_attr=to_attr,
    )


def build_active_service_discount_index(baskets: Iterable[DiscountBasket]):
    """
    خروجی:
    {
        service_id: best_basket
    }

    اگر چند سبد روی یک خدمت فعال باشد، سبدی انتخاب می‌شود که تخفیف بیشتری می‌دهد.
    """
    index: dict[int, DiscountBasket] = {}

    for basket in baskets or []:
        details = list(basket.discount_basket_details1.all())
        if not details:
            continue

        basket_value = _get_discount_value(basket)
        basket_cap = _get_cap_amount(basket)

        for detail in details:
            service_id = int(detail.service_id or 0)
            if not service_id:
                continue

            current = index.get(service_id)
            if current is None:
                index[service_id] = basket
                continue

            current_score = (
                _get_discount_value(current),
                _get_cap_amount(current),
                int(current.pk or 0),
            )
            candidate_score = (
                basket_value,
                basket_cap,
                int(basket.pk or 0),
            )

            if candidate_score > current_score:
                index[service_id] = basket

    return index


def attach_active_service_discount_meta(salons: Iterable):
    salons = list(salons)

    for salon in salons:
        baskets = list(getattr(salon, "active_discount_baskets", []) or [])
        best = baskets[0] if baskets else None

        salon.has_active_service_discount = bool(best)
        salon.active_service_discount_percent = 0
        salon.active_service_discount_max_amount = 0
        salon.active_service_discount_title = ""
        salon.active_service_discount_label = ""
        salon.active_service_discount_caption = ""
        salon.active_discounted_services_count = 0

        if not best:
            continue

        discount_type = _get_discount_type(best)
        discount_value = _get_discount_value(best)
        cap_amount = _get_cap_amount(best)
        details_count = best.discount_basket_details1.count()

        salon.active_service_discount_percent = (
            discount_value if discount_type == "percentage" else 0
        )
        salon.active_service_discount_max_amount = cap_amount
        salon.active_service_discount_title = best.discount_title
        salon.active_discounted_services_count = details_count

        if discount_type == "percentage":
            salon.active_service_discount_label = f"تا {discount_value}٪ تخفیف"
        else:
            salon.active_service_discount_label = f"{discount_value:,} تومان تخفیف"

        cap_label = _format_discount_cap(cap_amount)
        if cap_label and details_count:
            salon.active_service_discount_caption = (
                f"روی {details_count} خدمت • {cap_label}"
            )
        elif cap_label:
            salon.active_service_discount_caption = cap_label
        elif details_count:
            salon.active_service_discount_caption = f"روی {details_count} خدمت"

    return salons


def attach_service_discount_meta(services: Iterable, baskets: Iterable[DiscountBasket]):
    """
    برای صفحه جزئیات سالن:
    روی هر service این attributeها را می‌گذارد:
    service.has_active_discount
    service.active_discount_title
    service.active_discount_label
    service.active_discount_caption
    service.active_discount_amount_on_min_price
    service.active_discounted_min_price
    """
    services = list(services)
    index = build_active_service_discount_index(baskets)

    for service in services:
        basket = index.get(int(service.id or 0))

        service.has_active_discount = bool(basket)
        service.active_discount_title = ""
        service.active_discount_percent = 0
        service.active_discount_max_amount = 0
        service.active_discount_label = ""
        service.active_discount_caption = ""
        service.active_discount_amount_on_min_price = 0
        service.active_discounted_min_price = int(
            getattr(service, "min_price", 0) or getattr(service, "base_price", 0) or 0
        )

        if not basket:
            continue

        discount_type = _get_discount_type(basket)
        discount_value = _get_discount_value(basket)
        cap_amount = _get_cap_amount(basket)
        min_price = int(
            getattr(service, "min_price", 0) or getattr(service, "base_price", 0) or 0
        )

        amount, _raw_amount = calculate_discount_amount(
            discount_type=discount_type,
            value=discount_value,
            base_amount=min_price,
            cap_amount=cap_amount,
        )

        service.active_discount_title = basket.discount_title
        service.active_discount_percent = (
            discount_value if discount_type == "percentage" else 0
        )
        service.active_discount_max_amount = cap_amount
        service.active_discount_amount_on_min_price = int(amount or 0)
        service.active_discounted_min_price = max(min_price - int(amount or 0), 0)

        if discount_type == "percentage":
            service.active_discount_label = f"{discount_value}٪ تخفیف"
        else:
            service.active_discount_label = f"{discount_value:,} تومان تخفیف"

        cap_label = _format_discount_cap(cap_amount)
        if amount:
            service.active_discount_caption = (
                f"{cap_label} • قیمت بعد تخفیف: {service.active_discounted_min_price:,} تومان"
                if cap_label
                else f"قیمت بعد تخفیف: {service.active_discounted_min_price:,} تومان"
            )
        else:
            service.active_discount_caption = cap_label

    return services


def calculate_best_service_discount_for_items(
    *, salon, resolved_items: Iterable
) -> BasketDiscountResult:
    """
    برای checkout:
    تخفیف سبد خدمات را بر اساس service_id حساب می‌کند.
    فعلاً stylist_id را محدودکننده در نظر نمی‌گیریم، چون سبد تخفیف داشبورد سالن service-level است.
    """
    baskets = list(active_discount_basket_queryset(salon=salon))
    if not baskets:
        return BasketDiscountResult()

    service_lines: dict[int, list] = {}

    for item in resolved_items or []:
        service_id = int(getattr(getattr(item, "service", None), "id", 0) or 0)
        if not service_id:
            continue
        service_lines.setdefault(service_id, []).append(item)

    if not service_lines:
        return BasketDiscountResult()

    best: BasketDiscountResult | None = None

    for basket in baskets:
        eligible_service_ids = {
            int(detail.service_id)
            for detail in basket.discount_basket_details1.all()
            if detail.service_id
        }

        matched_service_ids = sorted(
            service_id
            for service_id in service_lines.keys()
            if service_id in eligible_service_ids
        )

        if not matched_service_ids:
            continue

        eligible_subtotal = 0

        for service_id in matched_service_ids:
            for item in service_lines.get(service_id, []):
                eligible_subtotal += int(getattr(item, "price", 0) or 0)

        if eligible_subtotal <= 0:
            continue

        min_order_amount = int(getattr(basket, "min_order_amount", 0) or 0)
        if min_order_amount and eligible_subtotal < min_order_amount:
            continue

        discount_type = _get_discount_type(basket)
        discount_value = _get_discount_value(basket)
        cap_amount = _get_cap_amount(basket)

        amount, raw_amount = calculate_discount_amount(
            discount_type=discount_type,
            value=discount_value,
            base_amount=eligible_subtotal,
            cap_amount=cap_amount,
        )

        candidate = BasketDiscountResult(
            basket=basket,
            amount=max(int(amount or 0), 0),
            raw_amount=max(int(raw_amount or 0), 0),
            percent=discount_value if discount_type == "percentage" else 0,
            cap_amount=cap_amount,
            eligible_subtotal=eligible_subtotal,
            discounted_service_ids=tuple(matched_service_ids),
        )

        if best is None:
            best = candidate
            continue

        current_score = (
            best.amount,
            best.raw_amount,
            best.percent,
            best.cap_amount,
            best.eligible_subtotal,
            int(best.basket.pk or 0) if best.basket else 0,
        )
        candidate_score = (
            candidate.amount,
            candidate.raw_amount,
            candidate.percent,
            candidate.cap_amount,
            candidate.eligible_subtotal,
            int(basket.pk or 0),
        )

        if candidate_score > current_score:
            best = candidate

    return best or BasketDiscountResult()
