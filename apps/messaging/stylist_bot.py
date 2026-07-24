from __future__ import annotations

from datetime import timedelta

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboards.jalali_utils import format_jalali_numeric, format_time_fa, to_persian_digits
from apps.orders.booking_utils import get_available_slots_for_service
from apps.orders.models import BookingQuickLink, OrderDetail
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.services.models import Services

from .links import absolute_site_url


ACTIVE_ORDER_STATUSES = ["pending", "confirmed", "paid"]


def _url(base_url: str, name: str, *args, **kwargs) -> str:
    return absolute_site_url(base_url, reverse(name, args=args, kwargs=kwargs))


def _fallback_url(base_url: str, path: str) -> str:
    return absolute_site_url(base_url, path)


def _stylist(user):
    return getattr(user, "stylist", None) if user else None


def _active_memberships(stylist):
    if stylist is None:
        return []
    return list(
        SalonMembership.objects.filter(
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        .select_related("salon")
        .order_by("salon__salon_name", "id")
    )


def _safe_dashboard_url(base_url: str, name: str, **kwargs) -> str:
    try:
        return _url(base_url, name, **kwargs)
    except NoReverseMatch:
        return _fallback_url(base_url, "/dashboards/stylist/")


def _appointment_detail_url(base_url: str, detail: OrderDetail) -> str:
    try:
        return _url(base_url, "dashboards:stylist_appointment_detail", appointment_id=detail.pk)
    except NoReverseMatch:
        return _fallback_url(base_url, f"/dashboards/stylist/appointments/{detail.pk}/")


def _status_label(detail: OrderDetail) -> str:
    try:
        return detail.get_status_display_fa()
    except Exception:
        return str(getattr(detail, "lifecycle_status", "") or "—")


def render_stylist_today(user, base_url: str) -> tuple[str, dict]:
    stylist = _stylist(user)
    if stylist is None:
        return "برای دیدن نوبت‌های متخصص، ابتدا باید نقش متخصص روی حساب شما فعال باشد.", _connected_links(base_url)

    today = timezone.localdate()
    appointments = list(
        OrderDetail.objects.select_related("order__customer__user", "service", "salon")
        .filter(stylist=stylist, date=today, order__status__in=ACTIVE_ORDER_STATUSES)
        .order_by("time", "id")[:8]
    )

    title = f"نوبت‌های امروز شما - {format_jalali_numeric(today)}"
    if not appointments:
        text = f"{title}\n\nبرای امروز نوبت فعالی ثبت نشده است."
    else:
        lines = [title, ""]
        for index, detail in enumerate(appointments, start=1):
            customer = getattr(getattr(detail.order, "customer", None), "get_fullName", lambda: "مشتری")()
            lines.append(
                f"{to_persian_digits(index)}. {format_time_fa(detail.time)} | "
                f"{getattr(detail.service, 'service_name', 'خدمت')} | "
                f"{customer or 'مشتری'} | "
                f"{getattr(detail.salon, 'salon_name', 'سالن')} | "
                f"{_status_label(detail)}"
            )
        text = "\n".join(lines)

    return text, {
        "inline_keyboard": [
            [
                {"text": "مشاهده همه نوبت‌ها", "url": _safe_dashboard_url(base_url, "dashboards:stylist_appointments")},
                {"text": "وقت‌های خالی من", "callback_data": "menu:stylist_slots"},
            ],
            [{"text": "منوی متخصص", "callback_data": "menu:stylist"}],
        ]
    }


def _first_active_service(stylist, salon) -> Services | None:
    return (
        Services.objects.filter(is_active=True, services_of_salon=salon, stylists=stylist)
        .order_by("service_name", "id")
        .first()
    )


def _format_slot(date_value, start, end, salon, service) -> str:
    return (
        f"{format_jalali_numeric(date_value)}، {format_time_fa(start)} تا {format_time_fa(end)} "
        f"| {getattr(salon, 'salon_name', 'سالن')} | {getattr(service, 'service_name', 'خدمت')}"
    )


def render_stylist_available_slots(user, base_url: str) -> tuple[str, dict]:
    stylist = _stylist(user)
    memberships = _active_memberships(stylist)
    if stylist is None or not memberships:
        return "برای نمایش وقت‌های خالی، همکاری فعال شما با یک سالن باید وجود داشته باشد.", _connected_links(base_url)

    found: list[str] = []
    today = timezone.localdate()
    for membership in memberships[:4]:
        salon = membership.salon
        service = _first_active_service(stylist, salon)
        if service is None:
            continue
        for offset in range(7):
            date_value = today + timedelta(days=offset)
            slots = get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=date_value,
            )[:2]
            for start, end in slots:
                found.append(_format_slot(date_value, start, end, salon, service))
                if len(found) >= 5:
                    break
            if len(found) >= 5:
                break
        if len(found) >= 5:
            break

    if found:
        text = "اولین وقت‌های خالی شما 🌿\n\n" + "\n".join(
            f"{to_persian_digits(index)}. {slot}" for index, slot in enumerate(found, start=1)
        )
    else:
        text = "در ۷ روز آینده وقت خالی قابل نمایش برای خدمات فعال شما پیدا نشد. برای بررسی دقیق‌تر برنامه کاری را در سایت ببینید."

    return text, {
        "inline_keyboard": [
            [
                {"text": "تقویم در سایت", "url": _safe_dashboard_url(base_url, "dashboards:stylist_schedule")},
                {"text": "ایجاد نوبت در سایت", "url": _safe_dashboard_url(base_url, "dashboards:stylist_add_booking")},
            ],
            [
                {"text": "لینک رزرو متخصص", "callback_data": "menu:stylist_booking_link"},
                {"text": "نوبت‌های امروز", "callback_data": "menu:stylist_today"},
            ],
        ]
    }


def _quick_link_payload(salon, stylist):
    return {
        "mode": BookingQuickLink.Mode.STYLIST,
        "salon_id": salon.pk,
        "service_ids": [],
        "stylist_user_id": stylist.pk,
        "date": "",
        "time": "",
        "summary": {
            "salon": getattr(salon, "salon_name", ""),
            "stylist": stylist.get_fullName(),
        },
    }


def _get_or_create_stylist_link(*, user, stylist, salon) -> BookingQuickLink:
    existing = (
        BookingQuickLink.objects.filter(
            creator=user,
            salon=salon,
            stylist=stylist,
            mode=BookingQuickLink.Mode.STYLIST,
            is_permanent=True,
            is_active=True,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if existing:
        return existing
    return BookingQuickLink.objects.create(
        creator=user,
        salon=salon,
        stylist=stylist,
        mode=BookingQuickLink.Mode.STYLIST,
        payload=_quick_link_payload(salon, stylist),
        title=f"لینک رزرو {stylist.get_fullName()} در {salon.salon_name}",
        is_permanent=True,
        expires_at=None,
    )


def _booking_quick_link_url(base_url: str, quick_link: BookingQuickLink) -> str:
    try:
        path = reverse("orders:quick_booking_entry", kwargs={"token": str(quick_link.token)})
    except NoReverseMatch:
        path = f"/orders/quick-booking/{quick_link.token}/"
    return absolute_site_url(base_url, path)


def render_stylist_booking_link(user, base_url: str) -> tuple[str, dict]:
    stylist = _stylist(user)
    memberships = _active_memberships(stylist)
    if stylist is None or not memberships:
        return "برای ساخت لینک رزرو متخصص، همکاری فعال شما با یک سالن باید وجود داشته باشد.", _connected_links(base_url)

    lines = ["لینک رزرو متخصص شما ✨", ""]
    rows = []
    for index, membership in enumerate(memberships[:3], start=1):
        link = _get_or_create_stylist_link(user=user, stylist=stylist, salon=membership.salon)
        url = _booking_quick_link_url(base_url, link)
        lines.append(f"{to_persian_digits(index)}. {membership.salon.salon_name}\n{url}")
        rows.append([{"text": f"رزرو در {membership.salon.salon_name}", "url": url}])

    rows.append([
        {"text": "مدیریت لینک‌ها", "url": _safe_dashboard_url(base_url, "dashboards:stylist_quick_links")},
        {"text": "وقت‌های خالی من", "callback_data": "menu:stylist_slots"},
    ])
    return "\n\n".join(lines), {"inline_keyboard": rows}


def _connected_links(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "داشبورد متخصص", "url": _safe_dashboard_url(base_url, "dashboards:stylist_dashboard")}],
            [{"text": "منوی نقش‌ها", "callback_data": "menu:main"}],
        ]
    }
