from __future__ import annotations

from django.db.models import Q

from apps.dashboards.jalali_utils import (
    format_jalali_with_weekday,
    format_time_fa,
    to_persian_digits,
)


ACTIVE_ORDER_STATUSES = ["pending", "confirmed", "paid"]


def _clean(value, fallback: str = "—") -> str:
    text = str(value or "").strip()
    return text or fallback


def format_money(value) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        return "—"
    return f"{to_persian_digits(f'{amount:,}')} تومان"


def customer_name_from_detail(detail) -> str:
    customer = getattr(getattr(detail, "order", None), "customer", None)
    getter = getattr(customer, "get_fullName", None)
    if callable(getter):
        name = _clean(getter(), "")
        if name:
            return name
    user = getattr(customer, "user", None)
    getter = getattr(user, "get_fullName", None)
    if callable(getter):
        name = _clean(getter(), "")
        if name:
            return name
    return "مشتری"


def stylist_name(stylist) -> str:
    getter = getattr(stylist, "get_fullName", None)
    if callable(getter):
        return _clean(getter(), "متخصص")
    return "متخصص"


def appointment_time_label(detail) -> str:
    start = getattr(detail, "time", None)
    end = getattr(detail, "end_time", None)
    duration = int(getattr(detail, "scheduled_duration_minutes", 0) or 0)

    if start and end:
        label = f"{format_time_fa(start)} تا {format_time_fa(end)}"
    elif start:
        label = format_time_fa(start)
    else:
        label = "زمان ثبت نشده"

    if duration > 0:
        label += f" ({to_persian_digits(duration)} دقیقه)"
    return label


def appointment_status_label(detail) -> str:
    try:
        return _clean(detail.get_status_display_fa())
    except Exception:
        pass
    confirmation = _clean(getattr(detail, "confirmation_status", ""), "")
    lifecycle = _clean(getattr(detail, "lifecycle_status", ""), "")
    return lifecycle or confirmation or "—"


def appointment_block(
    detail,
    *,
    heading: str = "",
    include_stylist: bool = False,
    include_salon: bool = True,
    include_status: bool = True,
) -> str:
    lines: list[str] = []
    if heading:
        lines.append(heading)

    lines.extend(
        [
            f"مشتری: {customer_name_from_detail(detail)}",
            f"خدمت: {_clean(getattr(getattr(detail, 'service', None), 'service_name', ''))}",
            f"تاریخ: {format_jalali_with_weekday(detail.date) if getattr(detail, 'date', None) else 'ثبت نشده'}",
            f"ساعت: {appointment_time_label(detail)}",
        ]
    )
    if include_stylist:
        lines.append(f"متخصص: {stylist_name(getattr(detail, 'stylist', None))}")
    if include_salon:
        lines.append(
            f"سالن: {_clean(getattr(getattr(detail, 'salon', None), 'salon_name', ''), 'سالن') }"
        )

    lines.append(f"مبلغ: {format_money(getattr(detail, 'price', 0))}")
    if include_status:
        lines.append(f"وضعیت: {appointment_status_label(detail)}")

    note = _clean(getattr(detail, "operational_note", ""), "")
    if note:
        lines.append(f"یادداشت: {note}")
    return "\n".join(lines)




def order_payment_label(order) -> str:
    if bool(getattr(order, "is_paid", False)):
        return "پرداخت شده"
    method = str(getattr(order, "selected_payment_method", "") or "")
    if method == "pay_in_salon":
        return "پرداخت در مجموعه"
    if method == "wallet":
        return "در انتظار پرداخت کیف پول"
    if method == "online":
        return "در انتظار پرداخت آنلاین"
    return "در انتظار پرداخت"


def customer_appointment_block(detail, *, heading: str = "") -> str:
    lines: list[str] = []
    if heading:
        lines.append(heading)
    lines.extend(
        [
            f"سالن: {_clean(getattr(getattr(detail, 'salon', None), 'salon_name', ''), 'سالن')}",
            f"خدمت: {_clean(getattr(getattr(detail, 'service', None), 'service_name', ''))}",
            f"متخصص: {stylist_name(getattr(detail, 'stylist', None))}",
            f"تاریخ: {format_jalali_with_weekday(detail.date) if getattr(detail, 'date', None) else 'ثبت نشده'}",
            f"ساعت: {appointment_time_label(detail)}",
            f"مبلغ: {format_money(getattr(detail, 'price', 0))}",
            f"وضعیت: {appointment_status_label(detail)}",
            f"پرداخت: {order_payment_label(getattr(detail, 'order', None))}",
        ]
    )
    return "\n".join(lines)


def customer_order_block(order, *, heading: str = "") -> str:
    try:
        details = list(
            order.order_details1.select_related("service", "stylist__user", "salon")
            .order_by("date", "time", "id")[:4]
        )
    except Exception:
        details = []

    if len(details) == 1:
        return customer_appointment_block(details[0], heading=heading)

    lines: list[str] = []
    if heading:
        lines.append(heading)
    lines.append(
        f"سالن: {_clean(getattr(getattr(order, 'salon', None), 'salon_name', ''), 'سالن')}"
    )
    if details:
        services = "، ".join(
            dict.fromkeys(
                _clean(getattr(getattr(item, "service", None), "service_name", ""), "خدمت")
                for item in details
            )
        )
        stylists = "، ".join(
            dict.fromkeys(stylist_name(getattr(item, "stylist", None)) for item in details)
        )
        first = details[0]
        lines.extend(
            [
                f"خدمات: {services}",
                f"متخصص: {stylists}",
                f"تاریخ: {format_jalali_with_weekday(first.date) if first.date else 'ثبت نشده'}",
                f"شروع: {format_time_fa(first.time) if first.time else 'ثبت نشده'}",
            ]
        )
    amount = getattr(order, "total_amount", 0) or 0
    if not amount:
        try:
            amount = order.get_order_total_price()
        except Exception:
            amount = 0
    try:
        status = order.get_status_display()
    except Exception:
        status = _clean(getattr(order, "status", ""))
    lines.extend(
        [
            f"مبلغ: {format_money(amount)}",
            f"وضعیت رزرو: {_clean(status)}",
            f"پرداخت: {order_payment_label(order)}",
        ]
    )
    return "\n".join(lines)


def overlapping_appointment_count(*, salon_id, stylist_id, date_value, start_time=None, end_time=None) -> int:
    if not salon_id or not stylist_id or not date_value:
        return 0
    try:
        from apps.orders.models import OrderDetail

        qs = OrderDetail.objects.filter(
            salon_id=salon_id,
            stylist_id=stylist_id,
            date=date_value,
            order__status__in=ACTIVE_ORDER_STATUSES,
        )
        if start_time and end_time:
            qs = qs.filter(
                Q(time__lt=end_time, end_time__gt=start_time)
                | Q(end_time__isnull=True, time__gte=start_time, time__lt=end_time)
            )
        return qs.count()
    except Exception:
        return 0


def leave_request_block(item, *, heading: str = "درخواست مرخصی") -> str:
    if item.start_time and item.end_time:
        time_label = f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
    else:
        time_label = "تمام روز"
    conflicts = overlapping_appointment_count(
        salon_id=item.salon_id,
        stylist_id=item.stylist_id,
        date_value=item.date,
        start_time=item.start_time,
        end_time=item.end_time,
    )
    lines = [
        heading,
        f"متخصص: {stylist_name(item.stylist)}",
        f"سالن: {_clean(getattr(getattr(item, 'salon', None), 'salon_name', ''), 'سالن')}",
        f"تاریخ: {format_jalali_with_weekday(item.date)}",
        f"ساعت: {time_label}",
        f"دلیل: {_clean(item.reason, 'بدون توضیح')}",
    ]
    if conflicts:
        lines.append(f"نوبت ثبت‌شده در این بازه: {to_persian_digits(conflicts)}")
    else:
        lines.append("نوبت ثبت‌شده در این بازه: ندارد")
    try:
        lines.append(f"وضعیت: {item.get_status_display()}")
    except Exception:
        pass
    review_note = _clean(getattr(item, "review_note", ""), "")
    if review_note:
        lines.append(f"نظر مدیر: {review_note}")
    return "\n".join(lines)


def schedule_request_block(item, *, heading: str = "درخواست برنامه کاری") -> str:
    conflicts = overlapping_appointment_count(
        salon_id=item.salon_id,
        stylist_id=item.stylist_id,
        date_value=item.date,
        start_time=item.start_time,
        end_time=item.end_time,
    )
    service_name = _clean(getattr(getattr(item, "service", None), "service_name", ""), "همه خدمات")
    lines = [
        heading,
        f"متخصص: {stylist_name(item.stylist)}",
        f"سالن: {_clean(getattr(getattr(item, 'salon', None), 'salon_name', ''), 'سالن')}",
        f"خدمت: {service_name}",
        f"تاریخ: {format_jalali_with_weekday(item.date)}",
        f"ساعت: {format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}",
        f"توضیح: {_clean(item.note, 'بدون توضیح')}",
    ]
    if conflicts:
        lines.append(f"نوبت ثبت‌شده در این بازه: {to_persian_digits(conflicts)}")
    else:
        lines.append("نوبت ثبت‌شده در این بازه: ندارد")
    try:
        lines.append(f"وضعیت: {item.get_status_display()}")
    except Exception:
        pass
    review_note = _clean(getattr(item, "review_note", ""), "")
    if review_note:
        lines.append(f"نظر مدیر: {review_note}")
    return "\n".join(lines)


def membership_request_block(item, *, heading: str = "درخواست همکاری") -> str:
    stylist = item.stylist
    metadata = item.metadata or {}
    active_elsewhere = 0
    try:
        from apps.salons.models import SalonMembership, SalonMembershipStatus

        active_elsewhere = (
            SalonMembership.objects.filter(
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            .exclude(pk=item.pk)
            .count()
        )
    except Exception:
        active_elsewhere = 0

    lines = [
        heading,
        f"متخصص: {stylist_name(stylist)}",
        f"تخصص: {_clean(getattr(stylist, 'expert', ''), 'ثبت نشده')}",
    ]
    if _clean(getattr(item, "role_title", ""), ""):
        lines.append(f"عنوان همکاری: {_clean(item.role_title)}")
    lines.append(f"همکاری فعال با سالن‌های دیگر: {to_persian_digits(active_elsewhere)}")
    lines.append(f"پیام: {_clean(metadata.get('request_message'), 'بدون پیام')}")
    return "\n".join(lines)
