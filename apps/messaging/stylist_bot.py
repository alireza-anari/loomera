from __future__ import annotations

from datetime import time as dt_time, timedelta

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboards.jalali_utils import format_jalali_numeric, format_time_fa, to_persian_digits
from apps.orders.booking_utils import get_available_slots_for_service
from apps.orders.models import BookingQuickLink, OrderDetail
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.services.models import Services

from .actions import build_action_callback_data, issue_action_token
from .bale_presenters import appointment_block
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


def _stylist_action_button(*, provider, identity, user, detail: OrderDetail, action_key: str, label: str) -> dict | None:
    if provider is None or identity is None:
        return None
    if not bool(getattr(settings, "MESSAGING_ACTIONS_ENABLED", False)):
        return None
    raw_token, _ = issue_action_token(
        provider=provider,
        identity=identity,
        user=user,
        related_object=detail,
        action_key=action_key,
        audience_role="stylist",
        salon_id=detail.salon_id,
        metadata={
            "source": "stylist_today_menu",
            "order_detail_id": detail.pk,
        },
    )
    return {"text": label, "callback_data": build_action_callback_data(raw_token)}


def _stylist_today_rows(*, user, base_url: str, appointments: list[OrderDetail], provider=None, identity=None) -> list[list[dict]]:
    from .stylist_actions import (
        ACTION_CONFIRM_CASH_PAYMENT_PREVIEW,
        ACTION_COMPLETE_SERVICE_PREVIEW,
        ACTION_NO_SHOW_PREVIEW,
        ACTION_REJECT_APPOINTMENT_PREVIEW,
        ACTION_START_SERVICE,
        _no_show_is_available,
    )

    rows: list[list[dict]] = []
    today = timezone.localdate()
    for index, detail in enumerate(appointments, start=1):
        action_row: list[dict] = []

        order = detail.order
        if (
            order.selected_payment_method == "pay_in_salon"
            and (order.service_completed_at or order.status == "completed")
            and not order.is_paid
            and order.status not in {"cancelled", "no_show", "disputed"}
        ):
            cash = _stylist_action_button(
                provider=provider,
                identity=identity,
                user=user,
                detail=detail,
                action_key=ACTION_CONFIRM_CASH_PAYMENT_PREVIEW,
                label=f"دریافت وجه {to_persian_digits(index)}",
            )
            if cash:
                action_row = [cash]
        elif detail.service_started_at and not detail.service_completed_at:
            complete = _stylist_action_button(
                provider=provider,
                identity=identity,
                user=user,
                detail=detail,
                action_key=ACTION_COMPLETE_SERVICE_PREVIEW,
                label=f"پایان خدمت {to_persian_digits(index)}",
            )
            if complete:
                action_row = [complete]
        elif (
            detail.confirmation_status != OrderDetail.ConfirmationStatus.REJECTED
            and not detail.service_completed_at
            and not detail.no_show_confirmed_at
        ):
            start_button = None
            exception_button = None

            if detail.no_show_pending_at:
                exception_button = _stylist_action_button(
                    provider=provider,
                    identity=identity,
                    user=user,
                    detail=detail,
                    action_key=ACTION_NO_SHOW_PREVIEW,
                    label=f"تکمیل عدم حضور {to_persian_digits(index)}",
                )
            else:
                if not detail.date or detail.date <= today:
                    start_button = _stylist_action_button(
                        provider=provider,
                        identity=identity,
                        user=user,
                        detail=detail,
                        action_key=ACTION_START_SERVICE,
                        label=f"شروع خدمت {to_persian_digits(index)}",
                    )

                if _no_show_is_available(detail):
                    exception_button = _stylist_action_button(
                        provider=provider,
                        identity=identity,
                        user=user,
                        detail=detail,
                        action_key=ACTION_NO_SHOW_PREVIEW,
                        label=f"مشتری نیامد {to_persian_digits(index)}",
                    )
                elif not detail.customer_arrived_at and not detail.service_started_at:
                    exception_button = _stylist_action_button(
                        provider=provider,
                        identity=identity,
                        user=user,
                        detail=detail,
                        action_key=ACTION_REJECT_APPOINTMENT_PREVIEW,
                        label=f"امکان انجام ندارم {to_persian_digits(index)}",
                    )

            action_row = [button for button in (start_button, exception_button) if button]

        if action_row:
            rows.append(action_row)
        rows.append(
            [
                {
                    "text": f"جزئیات نوبت {to_persian_digits(index)}",
                    "url": _appointment_detail_url(base_url, detail),
                }
            ]
        )
    return rows


def render_stylist_today(
    user,
    base_url: str,
    *,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
    stylist = _stylist(user)
    if stylist is None:
        return "نقش متخصص برای این حساب فعال نیست.", _connected_links(base_url)

    today = timezone.localdate()
    appointments = list(
        OrderDetail.objects.select_related("order__customer__user", "order", "service", "salon")
        .filter(stylist=stylist, date=today)
        .order_by("time", "id")[:8]
    )

    def _priority(detail: OrderDetail):
        order = detail.order
        if detail.service_started_at and not detail.service_completed_at:
            bucket = 0
        elif detail.no_show_pending_at and not detail.no_show_confirmed_at:
            bucket = 1
        elif (
            order.selected_payment_method == "pay_in_salon"
            and order.status == "completed"
            and not order.is_paid
        ):
            bucket = 2
        else:
            bucket = 3
        return (bucket, detail.time or dt_time.max, detail.pk)

    appointments.sort(key=_priority)

    title = f"نوبت‌های امروز — {format_jalali_numeric(today)}"
    if not appointments:
        text = f"{title}\n\nامروز نوبت فعالی نداری."
    else:
        in_progress = sum(1 for item in appointments if item.service_started_at and not item.service_completed_at)
        completed = sum(1 for item in appointments if item.service_completed_at)
        cash_pending = sum(
            1
            for item in appointments
            if item.order.selected_payment_method == "pay_in_salon"
            and item.order.status == "completed"
            and not item.order.is_paid
        )
        no_show_pending = sum(
            1
            for item in appointments
            if item.no_show_pending_at and not item.no_show_confirmed_at
        )
        blocks = [title]
        summary_parts = []
        if in_progress:
            summary_parts.append(f"در حال انجام: {to_persian_digits(in_progress)}")
        if no_show_pending:
            summary_parts.append(f"عدم حضور نیازمند تصمیم: {to_persian_digits(no_show_pending)}")
        if cash_pending:
            summary_parts.append(f"منتظر ثبت دریافت وجه: {to_persian_digits(cash_pending)}")
        if completed:
            summary_parts.append(f"انجام‌شده: {to_persian_digits(completed)}")
        if summary_parts:
            blocks.append(" | ".join(summary_parts))

        now_time = timezone.localtime().time()
        next_appointment = next(
            (
                item
                for item in sorted(appointments, key=lambda value: (value.time or dt_time.max, value.pk))
                if not item.service_started_at
                and not item.service_completed_at
                and not item.no_show_pending_at
                and not item.no_show_confirmed_at
                and item.time
                and item.time >= now_time
            ),
            None,
        )
        if next_appointment is not None:
            blocks.append(
                "نوبت بعدی: "
                f"{format_time_fa(next_appointment.time)}، "
                f"{getattr(next_appointment.service, 'service_name', 'خدمت')} برای "
                f"{getattr(next_appointment.order.customer, 'get_fullName', lambda: 'مشتری')()}"
            )

        for index, detail in enumerate(appointments, start=1):
            blocks.append(
                appointment_block(
                    detail,
                    heading=f"نوبت {to_persian_digits(index)}",
                    include_salon=True,
                    include_status=True,
                )
            )
        text = "\n\n".join(blocks)

    rows = _stylist_today_rows(
        user=user,
        base_url=base_url,
        appointments=appointments,
        provider=provider,
        identity=identity,
    )
    rows.extend(
        [
            [
                {"text": "همه نوبت‌ها", "url": _safe_dashboard_url(base_url, "dashboards:stylist_appointments")},
                {"text": "وقت‌های خالی", "callback_data": "menu:stylist_slots"},
            ],
            [{"text": "منوی متخصص", "callback_data": "menu:stylist"}],
        ]
    )
    return text, {"inline_keyboard": rows}


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
        text = "نزدیک‌ترین وقت‌های خالی\n\n" + "\n".join(
            f"{to_persian_digits(index)}. {slot}" for index, slot in enumerate(found, start=1)
        )
    else:
        text = "در ۷ روز آینده وقت خالی پیدا نشد. اگر لازم است برنامه کاری را در سایت بررسی کن."

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

    lines = ["لینک رزرو مستقیم", "", "این لینک را برای مشتری بفرست؛ مستقیماً وارد رزرو با شما می‌شود.", ""]
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
