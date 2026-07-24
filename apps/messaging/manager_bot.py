from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboards.jalali_utils import format_jalali_numeric, format_jalali_with_weekday, format_time_fa, to_persian_digits
from apps.orders.booking_utils import get_available_slots_for_service
from apps.orders.models import OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.stylists.models import StaffLeaveRequest, StaffScheduleRequest

from .links import absolute_site_url


ACTIVE_ORDER_STATUSES = ["pending", "confirmed", "paid"]


def _url(base_url: str, name: str, *args, **kwargs) -> str:
    try:
        return absolute_site_url(base_url, reverse(name, args=args, kwargs=kwargs))
    except NoReverseMatch:
        return absolute_site_url(base_url, kwargs.pop("fallback", "/dashboards/"))


def _fallback_url(base_url: str, path: str) -> str:
    return absolute_site_url(base_url, path)


def _manager_profile(user):
    return getattr(user, "salon_manager_profile", None) if user else None


def manager_salons(user) -> list[Salon]:
    manager = _manager_profile(user)
    if manager is None:
        return []
    return list(
        Salon.objects.filter(salon_manager=manager)
        .order_by("-is_active", "salon_name", "id")
    )


def _resolve_salon(user, salon_id: int | None = None) -> Salon | None:
    salons = manager_salons(user)
    if not salons:
        return None
    if salon_id:
        for salon in salons:
            if int(salon.pk) == int(salon_id):
                return salon
        return None
    return salons[0]


def _status_label(detail: OrderDetail) -> str:
    try:
        return detail.get_status_display_fa()
    except Exception:
        return str(getattr(detail, "lifecycle_status", "") or getattr(detail, "confirmation_status", "") or "—")


def _customer_name(detail: OrderDetail) -> str:
    customer = getattr(getattr(detail, "order", None), "customer", None)
    getter = getattr(customer, "get_fullName", None)
    if callable(getter):
        return getter() or "مشتری"
    return "مشتری"


def _manager_base_markup(base_url: str, salon: Salon | None = None) -> dict:
    rows: list[list[dict]] = []
    if salon:
        rows.append([
            {"text": "تقویم کامل", "url": _fallback_url(base_url, f"/dashboards/calendar/salon/{salon.pk}/")},
            {"text": "گزارش کامل", "url": _fallback_url(base_url, f"/dashboards/reports/salon/{salon.pk}/")},
        ])
    rows.append([
        {"text": "شیفت و مرخصی", "url": _fallback_url(base_url, "/dashboards/scheduled_shifts/")},
        {"text": "تیم سالن", "url": _fallback_url(base_url, "/dashboards/team_member/")},
    ])
    rows.append([{"text": "منوی مدیر", "callback_data": "menu:manager"}])
    return {"inline_keyboard": rows}


def _not_manager_text() -> str:
    return "برای استفاده از امکانات مدیر سالن، نقش مدیر باید روی حساب شما فعال باشد."


def render_manager_today_calendar(user, base_url: str, *, salon_id: int | None = None, metadata: dict | None = None) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    today = timezone.localdate()
    appointments = list(
        OrderDetail.objects.select_related("order__customer__user", "service", "stylist__user", "salon")
        .filter(salon=salon, date=today, order__status__in=ACTIVE_ORDER_STATUSES)
        .order_by("time", "id")[:10]
    )
    title = f"تقویم امروز {salon.salon_name} - {format_jalali_numeric(today)}"
    if not appointments:
        text = f"{title}\n\nبرای امروز نوبت فعالی ثبت نشده است."
    else:
        lines = [title, ""]
        for index, detail in enumerate(appointments, start=1):
            lines.append(
                f"{to_persian_digits(index)}. {format_time_fa(detail.time)} | "
                f"{getattr(detail.service, 'service_name', 'خدمت')} | "
                f"{getattr(detail.stylist, 'get_fullName', lambda: 'متخصص')()} | "
                f"{_customer_name(detail)} | {_status_label(detail)}"
            )
        text = "\n".join(lines)
    return text, _manager_base_markup(base_url, salon)


def render_manager_today_summary(user, base_url: str, *, salon_id: int | None = None, metadata: dict | None = None) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    today = timezone.localdate()
    qs = OrderDetail.objects.filter(salon=salon, date=today).select_related("order")
    active_qs = qs.filter(order__status__in=ACTIVE_ORDER_STATUSES)
    summary = active_qs.aggregate(count=Count("id"), revenue=Sum("price"))
    confirmed = active_qs.filter(confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED).count()
    pending = active_qs.filter(confirmation_status=OrderDetail.ConfirmationStatus.PENDING).count()
    cancelled = qs.filter(order__status="cancelled").count()
    paid = qs.filter(order__is_paid=True).count()
    leave_pending = StaffLeaveRequest.objects.filter(salon=salon, status=StaffLeaveRequest.Status.PENDING).count()
    schedule_pending = StaffScheduleRequest.objects.filter(salon=salon, status=StaffScheduleRequest.Status.PENDING).count()
    membership_pending = SalonMembership.objects.filter(
        salon=salon,
        status=SalonMembershipStatus.PENDING_ACCEPTANCE,
        stylist__isnull=False,
    ).count()

    text = (
        f"خلاصه امروز {salon.salon_name} - {format_jalali_numeric(today)}\n\n"
        f"نوبت‌های امروز: {to_persian_digits(summary.get('count') or 0)}\n"
        f"تاییدشده: {to_persian_digits(confirmed)}\n"
        f"در انتظار تایید متخصص: {to_persian_digits(pending)}\n"
        f"لغوشده: {to_persian_digits(cancelled)}\n"
        f"پرداخت‌های موفق/ثبت‌شده: {to_persian_digits(paid)}\n"
        f"درآمد ثبت‌شده امروز: {to_persian_digits(summary.get('revenue') or 0)} تومان\n"
        f"درخواست همکاری در انتظار: {to_persian_digits(membership_pending)}\n"
        f"درخواست برنامه کاری در انتظار: {to_persian_digits(schedule_pending)}\n"
        f"درخواست مرخصی در انتظار: {to_persian_digits(leave_pending)}"
    )
    return text, _manager_base_markup(base_url, salon)


def _format_leave(item: StaffLeaveRequest) -> str:
    if item.start_time and item.end_time:
        time_label = f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
    else:
        time_label = "تمام روز"
    return f"{item.stylist.get_fullName()} | {format_jalali_with_weekday(item.date)} | {time_label} | {item.reason or 'بدون توضیح'}"


def _format_schedule(item: StaffScheduleRequest) -> str:
    service_name = getattr(item.service, "service_name", "همه خدمات / بدون خدمت مشخص")
    return (
        f"{item.stylist.get_fullName()} | {service_name} | "
        f"{format_jalali_with_weekday(item.date)} | {format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
    )


def render_manager_shifts_overview(user, base_url: str, *, salon_id: int | None = None, metadata: dict | None = None) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    leaves = list(
        StaffLeaveRequest.objects.select_related("stylist__user")
        .filter(salon=salon, status=StaffLeaveRequest.Status.PENDING)
        .order_by("date", "start_time", "created_at")[:5]
    )
    schedules = list(
        StaffScheduleRequest.objects.select_related("stylist__user", "service")
        .filter(salon=salon, status=StaffScheduleRequest.Status.PENDING)
        .order_by("date", "start_time", "created_at")[:5]
    )

    lines = [f"بررسی شیفت‌ها و مرخصی‌های {salon.salon_name}", ""]
    if schedules:
        lines.append("درخواست‌های برنامه کاری:")
        lines.extend(f"• {_format_schedule(item)}" for item in schedules)
    else:
        lines.append("درخواست برنامه کاری در انتظار ندارید.")
    lines.append("")
    if leaves:
        lines.append("درخواست‌های مرخصی:")
        lines.extend(f"• {_format_leave(item)}" for item in leaves)
    else:
        lines.append("درخواست مرخصی در انتظار ندارید.")

    return "\n".join(lines), _manager_base_markup(base_url, salon)


def render_manager_pending_requests(user, base_url: str, *, salon_id: int | None = None, metadata: dict | None = None) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    memberships = list(
        SalonMembership.objects.select_related("stylist__user")
        .filter(salon=salon, status=SalonMembershipStatus.PENDING_ACCEPTANCE, stylist__isnull=False)
        .order_by("-created_at", "-id")[:8]
    )
    if not memberships:
        text = f"برای {salon.salon_name} درخواست همکاری در انتظار بررسی وجود ندارد."
    else:
        lines = [f"درخواست‌های همکاری {salon.salon_name}", ""]
        for index, membership in enumerate(memberships, start=1):
            metadata = membership.metadata or {}
            lines.append(
                f"{to_persian_digits(index)}. {membership.stylist.get_fullName()} | "
                f"{getattr(membership.stylist, 'expert', '') or 'تخصص ثبت نشده'} | "
                f"پیام: {metadata.get('request_message') or 'بدون پیام'}"
            )
        text = "\n".join(lines)
    return text, _manager_base_markup(base_url, salon)


def render_manager_membership_profile(user, base_url: str, *, salon_id: int | None = None, metadata: dict | None = None) -> tuple[str, dict]:
    metadata = metadata or {}
    membership_id = metadata.get("membership_id")
    if not membership_id:
        return "پروفایل مرتبط با این دکمه پیدا نشد.", _manager_base_markup(base_url)
    membership = (
        SalonMembership.objects.select_related("salon__salon_manager__user", "stylist__user")
        .filter(pk=membership_id)
        .first()
    )
    if not membership or not membership.stylist_id:
        return "پروفایل متخصص دیگر در دسترس نیست.", _manager_base_markup(base_url)
    salon = _resolve_salon(user, membership.salon_id)
    if salon is None or salon.pk != membership.salon_id:
        return "این پروفایل متعلق به سالن‌های تحت مدیریت این حساب نیست.", _manager_base_markup(base_url)

    stylist = membership.stylist
    profile_meta = membership.metadata or {}
    lines = [
        f"پروفایل خلاصه {stylist.get_fullName()} ✨",
        "",
        f"سالن: {membership.salon.salon_name}",
        f"تخصص: {getattr(stylist, 'expert', '') or 'ثبت نشده'}",
        f"رزومه کوتاه: {getattr(stylist, 'resume_headline', '') or getattr(stylist, 'description', '') or 'ثبت نشده'}",
        f"پیام درخواست: {profile_meta.get('request_message') or 'بدون پیام'}",
        f"وضعیت همکاری: {membership.get_status_display() if hasattr(membership, 'get_status_display') else membership.status}",
    ]
    return "\n".join(lines), {
        "inline_keyboard": [
            [
                {"text": "صفحه تیم", "url": _fallback_url(base_url, "/dashboards/team_member/")},
                {"text": "بررسی شیفت‌ها", "callback_data": "menu:manager_shifts"},
            ],
            [{"text": "منوی مدیر", "callback_data": "menu:manager"}],
        ]
    }


def _first_service_for_salon(salon: Salon, stylist=None) -> Services | None:
    qs = Services.objects.filter(is_active=True, services_of_salon=salon)
    if stylist is not None:
        qs = qs.filter(stylists=stylist)
    return qs.order_by("service_name", "id").first()


def render_manager_available_slots(user, base_url: str, *, salon_id: int | None = None, metadata: dict | None = None) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    memberships = list(
        SalonMembership.objects.select_related("stylist__user")
        .filter(salon=salon, status=SalonMembershipStatus.ACTIVE, stylist__isnull=False)
        .order_by("stylist__user__family", "stylist__user__name", "id")[:8]
    )
    today = timezone.localdate()
    found: list[str] = []
    for membership in memberships:
        stylist = membership.stylist
        service = _first_service_for_salon(salon, stylist=stylist)
        if service is None:
            continue
        for offset in range(7):
            date_value = today + timedelta(days=offset)
            slots = get_available_slots_for_service(salon=salon, stylist=stylist, service=service, date_value=date_value)[:1]
            for start, end in slots:
                found.append(
                    f"{stylist.get_fullName()} | {service.service_name} | {format_jalali_numeric(date_value)} | {format_time_fa(start)} تا {format_time_fa(end)}"
                )
                break
            if len(found) >= 5 or slots:
                break
        if len(found) >= 5:
            break

    if found:
        text = f"وقت‌های خالی نزدیک {salon.salon_name}\n\n" + "\n".join(
            f"{to_persian_digits(index)}. {slot}" for index, slot in enumerate(found, start=1)
        )
    else:
        text = "در ۷ روز آینده وقت خالی قابل نمایش برای متخصصان فعال پیدا نشد. برای بررسی دقیق‌تر تقویم سایت را باز کن."
    return text, _manager_base_markup(base_url, salon)
