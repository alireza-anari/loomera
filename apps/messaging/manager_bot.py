from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.dashboards.jalali_utils import format_jalali_numeric, format_jalali_with_weekday, format_time_fa, to_persian_digits
from apps.orders.booking_utils import get_available_slots_for_service
from apps.orders.models import OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services
from apps.stylists.models import StaffLeaveRequest, StaffScheduleRequest

from .actions import build_action_callback_data, issue_action_token
from .bale_presenters import (
    appointment_block,
    leave_request_block,
    membership_request_block,
    schedule_request_block,
)
from .links import absolute_site_url


ACTIVE_ORDER_STATUSES = ["pending", "confirmed", "paid"]


def _url(base_url: str, name: str, *args, **kwargs) -> str:
    try:
        return absolute_site_url(base_url, reverse(name, args=args, kwargs=kwargs))
    except NoReverseMatch:
        return absolute_site_url(base_url, kwargs.pop("fallback", "/dashboards/"))


def _fallback_url(base_url: str, path: str) -> str:
    return absolute_site_url(base_url, path)


def _menu_callback(key: str, salon_id: int | None = None) -> str:
    if salon_id:
        return f"menu:{key}:{int(salon_id)}"
    return f"menu:{key}"


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
    salon_id = salon.pk if salon else None
    if salon:
        rows.append(
            [
                {"text": "خلاصه امروز", "callback_data": _menu_callback("manager_summary", salon_id)},
                {"text": "امروز سالن", "callback_data": _menu_callback("manager_today", salon_id)},
            ]
        )
        rows.append([
            {"text": "تقویم کامل", "url": _fallback_url(base_url, f"/dashboards/calendar/salon/{salon.pk}/")},
            {"text": "گزارش کامل", "url": _fallback_url(base_url, f"/dashboards/reports/salon/{salon.pk}/")},
        ])
    rows.append([
        {"text": "شیفت و مرخصی", "callback_data": _menu_callback("manager_shifts", salon_id)},
        {"text": "درخواست‌های همکاری", "callback_data": _menu_callback("manager_requests", salon_id)},
    ])
    rows.append([{"text": "منوی مدیر", "callback_data": "menu:manager"}])
    return {"inline_keyboard": rows}


def _not_manager_text() -> str:
    return "برای استفاده از امکانات مدیر سالن، نقش مدیر باید روی حساب شما فعال باشد."


def _manager_action_button(*, provider, identity, user, related_object, action_key: str, label: str, salon_id: int, metadata: dict | None = None) -> dict | None:
    if provider is None or identity is None:
        return None
    if not bool(getattr(settings, "MESSAGING_ACTIONS_ENABLED", False)):
        return None
    raw_token, _ = issue_action_token(
        provider=provider,
        identity=identity,
        user=user,
        related_object=related_object,
        action_key=action_key,
        audience_role="manager",
        salon_id=salon_id,
        metadata={"source": "manager_bot_menu", **(metadata or {})},
    )
    return {"text": label, "callback_data": build_action_callback_data(raw_token)}


def _request_action_rows(*, user, provider, identity, item, kind: str, index: int) -> list[list[dict]]:
    from .manager_actions import (
        ACTION_MANAGER_LEAVE_APPROVE_PREVIEW,
        ACTION_MANAGER_LEAVE_REJECT_PREVIEW,
        ACTION_MANAGER_MEMBERSHIP_ACCEPT_PREVIEW,
        ACTION_MANAGER_MEMBERSHIP_PROFILE,
        ACTION_MANAGER_MEMBERSHIP_REJECT_PREVIEW,
        ACTION_MANAGER_SCHEDULE_APPROVE_PREVIEW,
        ACTION_MANAGER_SCHEDULE_REJECT_PREVIEW,
    )

    number = to_persian_digits(index)
    rows: list[list[dict]] = []
    if kind == "membership":
        metadata = {"membership_id": item.pk}
        accept = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_MEMBERSHIP_ACCEPT_PREVIEW,
            label=f"پذیرش همکاری {number}", salon_id=item.salon_id, metadata=metadata,
        )
        reject = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_MEMBERSHIP_REJECT_PREVIEW,
            label=f"رد درخواست {number}", salon_id=item.salon_id, metadata=metadata,
        )
        profile = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_MEMBERSHIP_PROFILE,
            label=f"پروفایل متخصص {number}", salon_id=item.salon_id, metadata=metadata,
        )
        decision = [button for button in (accept, reject) if button]
        if decision:
            rows.append(decision)
        if profile:
            rows.append([profile])
    elif kind == "leave":
        metadata = {"leave_request_id": item.pk}
        approve = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_LEAVE_APPROVE_PREVIEW,
            label=f"تأیید مرخصی {number}", salon_id=item.salon_id, metadata=metadata,
        )
        reject = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_LEAVE_REJECT_PREVIEW,
            label=f"رد مرخصی {number}", salon_id=item.salon_id, metadata=metadata,
        )
        decision = [button for button in (approve, reject) if button]
        if decision:
            rows.append(decision)
    elif kind == "schedule":
        metadata = {"schedule_request_id": item.pk}
        approve = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_SCHEDULE_APPROVE_PREVIEW,
            label=f"تأیید برنامه {number}", salon_id=item.salon_id, metadata=metadata,
        )
        reject = _manager_action_button(
            provider=provider, identity=identity, user=user, related_object=item,
            action_key=ACTION_MANAGER_SCHEDULE_REJECT_PREVIEW,
            label=f"رد برنامه {number}", salon_id=item.salon_id, metadata=metadata,
        )
        decision = [button for button in (approve, reject) if button]
        if decision:
            rows.append(decision)
    return rows


def render_manager_today_calendar(
    user,
    base_url: str,
    *,
    salon_id: int | None = None,
    metadata: dict | None = None,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    today = timezone.localdate()
    appointments = list(
        OrderDetail.objects.select_related("order__customer__user", "service", "stylist__user", "salon")
        .filter(salon=salon, date=today)
        .order_by("time", "id")[:8]
    )
    title = f"امروز {salon.salon_name} — {format_jalali_numeric(today)}"
    if not appointments:
        text = f"{title}\n\nبرای امروز نوبت فعالی ثبت نشده."
    else:
        blocks = [title]
        for index, detail in enumerate(appointments, start=1):
            blocks.append(
                appointment_block(
                    detail,
                    heading=f"نوبت {to_persian_digits(index)}",
                    include_stylist=True,
                    include_salon=False,
                    include_status=True,
                )
            )
        text = "\n\n".join(blocks)
    return text, _manager_base_markup(base_url, salon)

def render_manager_today_summary(
    user,
    base_url: str,
    *,
    salon_id: int | None = None,
    metadata: dict | None = None,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    today = timezone.localdate()
    qs = OrderDetail.objects.filter(salon=salon, date=today).select_related("order")
    active_qs = qs.filter(order__status__in=ACTIVE_ORDER_STATUSES)
    in_progress = active_qs.filter(
        service_started_at__isnull=False,
        service_completed_at__isnull=True,
    ).count()
    ready = active_qs.filter(
        service_started_at__isnull=True,
        service_completed_at__isnull=True,
        no_show_pending_at__isnull=True,
        no_show_confirmed_at__isnull=True,
    ).count()
    completed = qs.filter(service_completed_at__isnull=False).count()
    cancelled = qs.filter(order__status="cancelled").count()
    no_show = qs.filter(order__status="no_show").count()
    no_show_pending = qs.filter(
        no_show_pending_at__isnull=False,
        no_show_confirmed_at__isnull=True,
    ).count()
    cash_pending = qs.filter(
        order__status="completed",
        order__selected_payment_method="pay_in_salon",
        order__is_paid=False,
    ).count()
    paid = qs.filter(order__is_paid=True).count()
    operational_value = (
        qs.exclude(order__status__in=["cancelled", "no_show", "disputed"])
        .aggregate(revenue=Sum("price"))
        .get("revenue")
        or 0
    )
    leave_pending = StaffLeaveRequest.objects.filter(salon=salon, status=StaffLeaveRequest.Status.PENDING).count()
    schedule_pending = StaffScheduleRequest.objects.filter(salon=salon, status=StaffScheduleRequest.Status.PENDING).count()
    membership_pending = SalonMembership.objects.filter(
        salon=salon,
        status=SalonMembershipStatus.PENDING_ACCEPTANCE,
        stylist__isnull=False,
    ).count()
    staff_waiting = leave_pending + schedule_pending + membership_pending
    operational_attention = no_show_pending + cash_pending

    lines = [
        f"خلاصه امروز {salon.salon_name} — {format_jalali_numeric(today)}",
        "",
        f"نوبت‌های امروز: {to_persian_digits(qs.count())}",
        f"آماده شروع: {to_persian_digits(ready)} | در حال انجام: {to_persian_digits(in_progress)}",
        f"پایان‌یافته: {to_persian_digits(completed)} | لغوشده: {to_persian_digits(cancelled)} | عدم حضور: {to_persian_digits(no_show)}",
        f"پرداخت ثبت‌شده: {to_persian_digits(paid)}",
        f"ارزش نوبت‌های قابل انجام امروز: {to_persian_digits(format(int(operational_value), ','))} تومان",
        "",
        f"نیازمند پیگیری عملیاتی: {to_persian_digits(operational_attention)}",
        f"• عدم حضور در انتظار تصمیم: {to_persian_digits(no_show_pending)}",
        f"• دریافت وجه حضوری ثبت‌نشده: {to_persian_digits(cash_pending)}",
        "",
        f"درخواست‌های تیم: {to_persian_digits(staff_waiting)}",
        f"• همکاری: {to_persian_digits(membership_pending)} | برنامه کاری: {to_persian_digits(schedule_pending)} | مرخصی: {to_persian_digits(leave_pending)}",
    ]
    markup = {
        "inline_keyboard": [
            [{"text": "درخواست‌های همکاری", "callback_data": _menu_callback("manager_requests", salon.pk)}],
            [
                {"text": "شیفت و مرخصی", "callback_data": _menu_callback("manager_shifts", salon.pk)},
                {"text": "امروز سالن", "callback_data": _menu_callback("manager_today", salon.pk)},
            ],
            [{"text": "منوی مدیر", "callback_data": "menu:manager"}],
        ]
    }
    return "\n".join(lines), markup

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


def render_manager_shifts_overview(
    user,
    base_url: str,
    *,
    salon_id: int | None = None,
    metadata: dict | None = None,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    leaves = list(
        StaffLeaveRequest.objects.select_related("stylist__user")
        .filter(salon=salon, status=StaffLeaveRequest.Status.PENDING)
        .order_by("date", "start_time", "created_at")[:4]
    )
    schedules = list(
        StaffScheduleRequest.objects.select_related("stylist__user", "service")
        .filter(salon=salon, status=StaffScheduleRequest.Status.PENDING)
        .order_by("date", "start_time", "created_at")[:4]
    )

    blocks = [f"شیفت و مرخصی — {salon.salon_name}"]
    rows: list[list[dict]] = []
    index = 1
    for item in schedules:
        blocks.append(schedule_request_block(item, heading=f"درخواست {to_persian_digits(index)} — برنامه کاری"))
        rows.extend(_request_action_rows(user=user, provider=provider, identity=identity, item=item, kind="schedule", index=index))
        index += 1
    for item in leaves:
        blocks.append(leave_request_block(item, heading=f"درخواست {to_persian_digits(index)} — مرخصی"))
        rows.extend(_request_action_rows(user=user, provider=provider, identity=identity, item=item, kind="leave", index=index))
        index += 1

    if not schedules and not leaves:
        blocks.append("درخواستی برای بررسی نداری.")

    rows.extend(
        [
            [{"text": "مدیریت کامل شیفت‌ها", "url": _fallback_url(base_url, "/dashboards/scheduled_shifts/")}],
            [{"text": "خلاصه امروز", "callback_data": _menu_callback("manager_summary", salon.pk)}],
            [{"text": "منوی مدیر", "callback_data": "menu:manager"}],
        ]
    )
    return "\n\n".join(blocks), {"inline_keyboard": rows}

def render_manager_pending_requests(
    user,
    base_url: str,
    *,
    salon_id: int | None = None,
    metadata: dict | None = None,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
    salon = _resolve_salon(user, salon_id)
    if salon is None:
        return _not_manager_text(), _manager_base_markup(base_url)

    memberships = list(
        SalonMembership.objects.select_related("stylist__user")
        .filter(salon=salon, status=SalonMembershipStatus.PENDING_ACCEPTANCE, stylist__isnull=False)
        .order_by("-created_at", "-id")[:5]
    )
    blocks = [f"درخواست‌های همکاری — {salon.salon_name}"]
    rows: list[list[dict]] = []
    if not memberships:
        blocks.append("درخواست همکاری در انتظار نداری.")
    else:
        for index, membership in enumerate(memberships, start=1):
            blocks.append(
                membership_request_block(
                    membership,
                    heading=f"درخواست {to_persian_digits(index)}",
                )
            )
            rows.extend(
                _request_action_rows(
                    user=user,
                    provider=provider,
                    identity=identity,
                    item=membership,
                    kind="membership",
                    index=index,
                )
            )

    rows.extend(
        [
            [{"text": "شیفت و مرخصی", "callback_data": _menu_callback("manager_shifts", salon.pk)}],
            [{"text": "خلاصه امروز", "callback_data": _menu_callback("manager_summary", salon.pk)}],
            [{"text": "منوی مدیر", "callback_data": "menu:manager"}],
        ]
    )
    return "\n\n".join(blocks), {"inline_keyboard": rows}

def render_manager_membership_profile(
    user,
    base_url: str,
    *,
    salon_id: int | None = None,
    metadata: dict | None = None,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
    metadata = metadata or {}
    membership_id = metadata.get("membership_id")
    if not membership_id:
        return "این درخواست دیگر در دسترس نیست.", _manager_base_markup(base_url)
    membership = (
        SalonMembership.objects.select_related("salon__salon_manager__user", "stylist__user")
        .filter(pk=membership_id)
        .first()
    )
    if not membership or not membership.stylist_id:
        return "پروفایل متخصص دیگر در دسترس نیست.", _manager_base_markup(base_url)
    salon = _resolve_salon(user, membership.salon_id)
    if salon is None or salon.pk != membership.salon_id:
        return "این درخواست مربوط به سالن دیگری است.", _manager_base_markup(base_url)

    stylist = membership.stylist
    profile_meta = membership.metadata or {}
    lines = [
        f"{stylist.get_fullName()}",
        f"تخصص: {getattr(stylist, 'expert', '') or 'ثبت نشده'}",
        f"رزومه کوتاه: {getattr(stylist, 'resume_headline', '') or getattr(stylist, 'description', '') or 'ثبت نشده'}",
        f"پیام درخواست: {profile_meta.get('request_message') or 'بدون پیام'}",
        f"وضعیت همکاری: {membership.get_status_display() if hasattr(membership, 'get_status_display') else membership.status}",
    ]
    rows: list[list[dict]] = []
    if membership.status == SalonMembershipStatus.PENDING_ACCEPTANCE:
        rows.extend(
            _request_action_rows(
                user=user,
                provider=provider,
                identity=identity,
                item=membership,
                kind="membership",
                index=1,
            )[:1]
        )
    rows.extend(
        [
            [{"text": "تیم سالن در سایت", "url": _fallback_url(base_url, "/dashboards/team_member/")}],
            [{"text": "درخواست‌های همکاری", "callback_data": _menu_callback("manager_requests", salon.pk)}],
        ]
    )
    return "\n".join(lines), {"inline_keyboard": rows}

def _first_service_for_salon(salon: Salon, stylist=None) -> Services | None:
    qs = Services.objects.filter(is_active=True, services_of_salon=salon)
    if stylist is not None:
        qs = qs.filter(stylists=stylist)
    return qs.order_by("service_name", "id").first()


def render_manager_available_slots(
    user,
    base_url: str,
    *,
    salon_id: int | None = None,
    metadata: dict | None = None,
    provider=None,
    identity=None,
) -> tuple[str, dict]:
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
