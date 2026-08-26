from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Avg, Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboards.jalali_utils import format_jalali_numeric, format_time_fa, to_persian_digits
from apps.orders.booking_utils import resolve_best_available_stylist_for_service
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon

from .links import absolute_site_url


ACTIVE_ORDER_STATUSES = ["pending", "confirmed", "paid"]
PAST_ORDER_STATUSES = ["completed", "cancelled", "no_show", "disputed"]


def _url(base_url: str, name: str, *args, **kwargs) -> str:
    return absolute_site_url(base_url, reverse(name, args=args, kwargs=kwargs))


def _fallback_url(base_url: str, path: str) -> str:
    return absolute_site_url(base_url, path)


def _safe_url(base_url: str, name: str, *args, fallback_path: str = "/", **kwargs) -> str:
    try:
        return _url(base_url, name, *args, **kwargs)
    except NoReverseMatch:
        return _fallback_url(base_url, fallback_path)


def _customer(user):
    return getattr(user, "customer_profile", None) if user else None


def _salon_url(base_url: str, salon: Salon) -> str:
    try:
        if getattr(salon, "slug", ""):
            return _url(base_url, "salons:detail_salon_slug", salon_slug=salon.slug)
        return _url(base_url, "salons:detail_salon", salon_id=salon.pk)
    except NoReverseMatch:
        return _fallback_url(base_url, f"/detail_salon/{salon.pk}/")


def _appointments_url(base_url: str) -> str:
    return _safe_url(base_url, "orders:appointments", fallback_path="/orders/appointments/")


def _appointment_detail_url(base_url: str, detail: OrderDetail) -> str:
    try:
        return _url(base_url, "orders:appointment_detail", pk=detail.pk)
    except NoReverseMatch:
        return _fallback_url(base_url, f"/orders/appointment_detail/{detail.pk}/")


def _rebook_url(base_url: str, order: Order) -> str:
    try:
        return _url(base_url, "orders:rebook", order_id=order.pk)
    except NoReverseMatch:
        return _fallback_url(base_url, f"/orders/rebook/{order.pk}/")


def _search_url(base_url: str, query: str = "") -> str:
    base = _safe_url(base_url, "search:search_page", fallback_path="/search/")
    query = (query or "").strip()
    if not query:
        return base
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}q={query}"


def _support_url(base_url: str) -> str:
    return _safe_url(base_url, "support", fallback_path="/support/")


def _score_label(salon: Salon) -> str:
    try:
        from apps.comments_scores_favories.models import Scoring

        score = Scoring.objects.filter(salon=salon).aggregate(avg=Avg("score"))["avg"]
        if score is None:
            return "بدون امتیاز"
        return to_persian_digits(f"{float(score):.1f}")
    except Exception:
        return "بدون امتیاز"


def _service_names(salon: Salon, limit: int = 3) -> list[str]:
    try:
        return list(salon.services.filter(is_active=True).order_by("service_name").values_list("service_name", flat=True)[:limit])
    except Exception:
        return []


def _first_available_label(salon: Salon) -> str:
    today = timezone.localdate()
    try:
        services = list(salon.services.filter(is_active=True).order_by("service_name", "id")[:4])
        for service in services:
            best = resolve_best_available_stylist_for_service(
                salon=salon,
                service=service,
                start_date=today,
                horizon_days=7,
            )
            if not best:
                continue
            slot = best["first_slot"]
            stylist = best.get("stylist")
            stylist_name = stylist.get_fullName() if stylist else "متخصص"
            return (
                f"{format_jalali_numeric(slot['date'])}، {format_time_fa(slot['time'])} "
                f"| {service.service_name} | {stylist_name}"
            )
    except Exception:
        pass
    return "برای دیدن زمان‌های آزاد، صفحه سالن را باز کن."


def _active_salons_queryset(query: str = ""):
    qs = (
        Salon.objects.filter(is_active=True)
        .select_related("neighborhood")
        .prefetch_related("services", "stylists")
        .order_by("salon_name", "id")
    )
    query = (query or "").strip()
    if query:
        qs = qs.filter(
            Q(salon_name__icontains=query)
            | Q(description__icontains=query)
            | Q(address__icontains=query)
            | Q(services__service_name__icontains=query)
            | Q(neighborhood__name__icontains=query)
        ).distinct()
    return qs


def _salon_card_lines(salon: Salon, index: int) -> list[str]:
    services = _service_names(salon)
    service_text = "، ".join(services) if services else "خدمات فعال در صفحه سالن"
    location = getattr(getattr(salon, "neighborhood", None), "name", "") or (f"منطقه {salon.zone}" if getattr(salon, "zone", None) else "")
    lines = [
        f"{to_persian_digits(index)}. {salon.salon_name}",
        f"امتیاز: {_score_label(salon)}",
        f"خدمات شاخص: {service_text}",
        f"اولین زمان آزاد: {_first_available_label(salon)}",
    ]
    if location:
        lines.insert(2, f"محدوده: {location}")
    return lines


def render_customer_salon_search(user, base_url: str, query: str = "") -> tuple[str, dict]:
    query = (query or "").strip()
    salons = list(_active_salons_queryset(query)[:5])
    title = "نتیجه جستجوی سالن" if query else "چند سالن فعال در Loomera"

    if not salons:
        text = (
            f"برای «{query}» سالن فعالی پیدا نشد.\n"
            "برای فیلترهای دقیق‌تر مثل شهر، محدوده، خدمت، تاریخ و بازه زمانی، جستجوی سایت را باز کن."
        )
        return text, {
            "inline_keyboard": [
                [{"text": "جستجوی کامل در سایت", "url": _search_url(base_url, query)}],
                [{"text": "منوی اصلی", "callback_data": "menu:guest"}, {"text": "پشتیبانی", "url": _support_url(base_url)}],
            ]
        }

    parts = [title, ""]
    back_callback = "menu:customer" if user else "menu:guest"
    back_label = "منوی مشتری" if user else "منوی اصلی"
    rows: list[list[dict[str, Any]]] = []
    for index, salon in enumerate(salons, start=1):
        parts.extend(_salon_card_lines(salon, index))
        parts.append(_salon_url(base_url, salon))
        parts.append("")
        rows.append([
            {"text": f"مشاهده {salon.salon_name}"[:60], "url": _salon_url(base_url, salon)},
            {"text": "رزرو", "url": _salon_url(base_url, salon)},
        ])

    parts.append("برای رزرو کامل، پرداخت، تغییر زمان یا لغو مالی وارد سایت شو.")
    rows.append([
        {"text": "جستجوی کامل با فیلتر", "url": _search_url(base_url, query)},
        {"text": back_label, "callback_data": back_callback},
    ])
    return "\n".join(parts).strip(), {"inline_keyboard": rows[:7]}


def _payment_label(order: Order) -> str:
    if getattr(order, "is_paid", False):
        return "پرداخت شده"
    method = getattr(order, "selected_payment_method", "")
    if method == "pay_in_salon":
        return "پرداخت در سالن"
    if method == "wallet":
        return "در انتظار پرداخت کیف پول"
    if method == "online":
        return "در انتظار پرداخت آنلاین"
    return "در انتظار پرداخت"


def _detail_status_label(detail: OrderDetail) -> str:
    try:
        return detail.get_status_display_fa()
    except Exception:
        return str(getattr(detail, "lifecycle_status", "") or "—")


def _appointment_line(detail: OrderDetail, index: int) -> str:
    order = detail.order
    return (
        f"{to_persian_digits(index)}. {format_jalali_numeric(detail.date)}، {format_time_fa(detail.time)}\n"
        f"سالن: {getattr(detail.salon, 'salon_name', 'سالن')} | خدمت: {getattr(detail.service, 'service_name', 'خدمت')}\n"
        f"متخصص: {detail.stylist.get_fullName() if detail.stylist_id else '—'}\n"
        f"وضعیت نوبت: {_detail_status_label(detail)} | پرداخت: {_payment_label(order)}"
    )


def render_customer_appointments(user, base_url: str) -> tuple[str, dict]:
    customer = _customer(user)
    if customer is None:
        return "برای دیدن نوبت‌ها ابتدا باید نقش مشتری روی حساب شما فعال باشد.", _customer_base_markup(base_url)

    today = timezone.localdate()
    upcoming = list(
        OrderDetail.objects.select_related("order", "service", "stylist__user", "salon")
        .filter(order__customer=customer, date__gte=today, order__status__in=ACTIVE_ORDER_STATUSES)
        .order_by("date", "time", "id")[:5]
    )
    past = list(
        OrderDetail.objects.select_related("order", "service", "stylist__user", "salon")
        .filter(Q(order__customer=customer), Q(date__lt=today) | Q(order__status__in=PAST_ORDER_STATUSES))
        .order_by("-date", "-time", "-id")[:3]
    )

    lines = ["نوبت‌های من 🌿", ""]
    rows: list[list[dict[str, Any]]] = []

    if upcoming:
        lines.append("نوبت‌های آینده:")
        for index, detail in enumerate(upcoming, start=1):
            lines.append(_appointment_line(detail, index))
            rows.append([{"text": f"جزئیات نوبت {to_persian_digits(index)}", "url": _appointment_detail_url(base_url, detail)}])
    else:
        lines.append("نوبت آینده‌ای برای شما پیدا نشد.")

    if past:
        lines.extend(["", "آخرین نوبت‌های گذشته:"])
        for index, detail in enumerate(past, start=1):
            lines.append(_appointment_line(detail, index))
        first_past_order = past[0].order
        rows.append([{"text": "رزرو مجدد آخرین نوبت", "url": _rebook_url(base_url, first_past_order)}])

    rows.extend(
        [
            [{"text": "همه نوبت‌ها در سایت", "url": _appointments_url(base_url)}],
            [
                {"text": "ثبت نظر", "callback_data": "menu:customer_reviews"},
                {"text": "جستجوی سالن", "callback_data": "menu:customer_search"},
            ],
        ]
    )
    return "\n\n".join(lines).strip(), {"inline_keyboard": rows[:8]}


def render_customer_review_links(user, base_url: str) -> tuple[str, dict]:
    customer = _customer(user)
    if customer is None:
        return "برای ثبت نظر ابتدا باید نقش مشتری روی حساب شما فعال باشد.", _customer_base_markup(base_url)

    completed = list(
        OrderDetail.objects.select_related("order", "service", "stylist__user", "salon")
        .filter(
            order__customer=customer,
            lifecycle_status=OrderDetail.ServiceLifecycleStatus.COMPLETED,
        )
        .order_by("-date", "-time", "-id")[:5]
    )
    if not completed:
        return (
            "فعلاً نوبت تکمیل‌شده‌ای برای ثبت نظر پیدا نشد. بعد از اتمام خدمت، لینک ثبت نظر از صفحه جزئیات نوبت در سایت در دسترس است.",
            _customer_base_markup(base_url),
        )

    lines = ["ثبت نظر و امتیاز ✨", "برای حفظ دقت، ثبت متن نظر و امتیاز کامل داخل سایت انجام می‌شود.", ""]
    rows: list[list[dict[str, Any]]] = []
    for index, detail in enumerate(completed, start=1):
        lines.append(
            f"{to_persian_digits(index)}. {getattr(detail.salon, 'salon_name', 'سالن')} | "
            f"{getattr(detail.service, 'service_name', 'خدمت')} | {format_jalali_numeric(detail.date)}"
        )
        rows.append([{"text": f"ثبت نظر برای مورد {to_persian_digits(index)}", "url": _appointment_detail_url(base_url, detail)}])

    rows.append([{"text": "نوبت‌های من", "callback_data": "menu:customer_appointments"}])
    return "\n".join(lines), {"inline_keyboard": rows[:6]}


def render_customer_support(user, base_url: str) -> tuple[str, dict]:
    text = (
        "اگر موضوعت مربوط به پرداخت، لغو یا حساب کاربری است، از صفحه پشتیبانی درخواست ثبت کن تا قابل پیگیری باشد.\n"
        "برای سؤال‌های عمومی هم همان‌جا می‌توانی با پشتیبانی در تماس باشی."
    )
    return text, {
        "inline_keyboard": [
            [{"text": "پشتیبانی در سایت", "url": _support_url(base_url)}],
            [{"text": "نوبت‌های من", "callback_data": "menu:customer_appointments"}],
            [{"text": "منوی مشتری", "callback_data": "menu:customer"}],
        ]
    }


def _customer_base_markup(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "جستجوی سالن", "callback_data": "menu:customer_search"},
                {"text": "نوبت‌های من", "callback_data": "menu:customer_appointments"},
            ],
            [{"text": "منوی نقش‌ها", "callback_data": "menu:main"}],
        ]
    }
