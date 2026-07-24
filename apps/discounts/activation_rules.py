from __future__ import annotations

from typing import Iterable

from apps.discounts.models import DiscountBasket, DiscountCampaign


def _ids_from_services(services: Iterable) -> set[int]:
    return {
        int(service.pk) for service in services or [] if getattr(service, "pk", None)
    }


def salon_service_ids(salon) -> set[int]:
    services = getattr(salon, "services", None)
    if services is None:
        return set()
    return set(services.values_list("id", flat=True))


def basket_service_ids_from_instance(basket: DiscountBasket) -> set[int]:
    return set(basket.discount_basket_details1.values_list("service_id", flat=True))


def basket_service_ids_from_cleaned_services(services: Iterable) -> set[int]:
    return _ids_from_services(services)


def baskets_service_ids(baskets: Iterable[DiscountBasket]) -> set[int]:
    basket_ids = [basket.pk for basket in baskets or [] if getattr(basket, "pk", None)]
    if not basket_ids:
        return set()

    return set(
        DiscountBasket.objects.filter(pk__in=basket_ids)
        .values_list("discount_basket_details1__service_id", flat=True)
        .exclude(discount_basket_details1__service_id__isnull=True)
    )


def campaign_service_ids_from_selection(
    *, salon, baskets: Iterable, coupons: Iterable
) -> set[int]:
    """
    اگر کمپین کد تخفیف داشته باشد، آن را پوشش کل خدمات سالن فرض می‌کنیم؛
    چون کد تخفیف می‌تواند روی کل مبلغ checkout اثر بگذارد.
    اگر فقط سبد داشته باشد، خدمات از سبدها گرفته می‌شود.
    """
    coupons = list(coupons or [])
    baskets = list(baskets or [])

    if coupons:
        return salon_service_ids(salon)

    return baskets_service_ids(baskets)


def campaign_service_ids_from_instance(campaign: DiscountCampaign) -> set[int]:
    if campaign.coupons.exists():
        return salon_service_ids(campaign.salon)

    return baskets_service_ids(campaign.baskets.all())


def find_basket_activation_conflicts(
    *,
    salon,
    start_date,
    end_date,
    service_ids: set[int],
    exclude_basket_id=None,
):
    """
    قانون:
    اول تداخل زمانی، بعد اشتراک خدمات.
    فقط سبدهای فعال و غیرآرشیوشده بررسی می‌شوند.
    """
    qs = DiscountBasket.objects.filter(
        salon=salon,
        is_active=True,
        is_archived=False,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )

    if exclude_basket_id:
        qs = qs.exclude(pk=exclude_basket_id)

    if service_ids:
        qs = qs.filter(discount_basket_details1__service_id__in=service_ids)

    return qs.distinct().prefetch_related("discount_basket_details1__service")


def find_campaign_activation_conflicts(
    *,
    salon,
    start_date,
    end_date,
    service_ids: set[int],
    exclude_campaign_id=None,
):
    """
    قانون:
    اول تداخل زمانی، بعد اشتراک خدمات.
    برای کمپین‌های دارای کد تخفیف، پوشش کل خدمات سالن فرض می‌شود.
    """
    qs = DiscountCampaign.objects.filter(
        salon=salon,
        is_active=True,
        is_archived=False,
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).prefetch_related(
        "coupons",
        "baskets",
        "baskets__discount_basket_details1",
    )

    if exclude_campaign_id:
        qs = qs.exclude(pk=exclude_campaign_id)

    conflicts = []

    for campaign in qs:
        existing_service_ids = campaign_service_ids_from_instance(campaign)

        # اگر یکی از دو طرف پوشش نامشخص/کلی دارد، برای امنیت تداخل حساب می‌کنیم.
        if not service_ids or not existing_service_ids:
            conflicts.append(campaign)
            continue

        if service_ids.intersection(existing_service_ids):
            conflicts.append(campaign)

    return conflicts


def conflict_names(conflicts, *, title_attr: str, limit: int = 3) -> str:
    items = list(conflicts or [])
    names = [getattr(item, title_attr, str(item)) for item in items[:limit]]

    if not names:
        return ""

    text = "، ".join(f"«{name}»" for name in names)

    if len(items) > limit:
        text += f" و {len(items) - limit} مورد دیگر"

    return text


def basket_conflict_message(conflicts) -> str:
    names = conflict_names(conflicts, title_attr="discount_title")
    return (
        f"این سبد تخفیف با سبد فعال {names} از نظر بازه زمانی و خدمات مشترک تداخل دارد. "
        "ابتدا سبد مشابه را غیرفعال کن، سپس این سبد را فعال کن."
    )


def campaign_conflict_message(conflicts) -> str:
    names = conflict_names(conflicts, title_attr="title")
    return (
        f"این کمپین با کمپین فعال {names} از نظر بازه زمانی و خدمات تحت پوشش تداخل دارد. "
        "ابتدا کمپین مشابه را غیرفعال کن، سپس این کمپین را فعال کن."
    )
