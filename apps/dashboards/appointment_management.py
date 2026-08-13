from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum, Q, Value, Max
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.orders.models import Order, OrderDetail
from apps.orders.lifecycle import determine_current_stage, mark_review_requested
from apps.salons.models import SalonOpeningHours
from apps.payments.finance import wallet_refund_amount_for_order
from .jalali_utils import (
    format_jalali_numeric,
    format_jalali_range,
    format_jalali_with_weekday,
    format_time_fa,
    parse_jalali_input,
    relative_jalali_label,
    to_persian_digits,
)
from .layout import WEEKDAY_TO_OPENING_DAY
from apps.main.models import DisputeCase

TAB_DEFINITIONS = [
    ("all", "همه نوبت‌ها"),
    ("today", "امروز"),
    ("upcoming", "آینده"),
    ("in_progress", "در حال اجرا"),
    ("attention", "نیازمند پیگیری"),
    ("past", "گذشته"),
    ("unpaid", "پرداخت‌نشده"),
    ("paid", "پرداخت‌شده"),
    ("no_show", "عدم حضور"),
    ("cancelled", "لغوشده"),
    ("completed", "انجام‌شده"),
]

STATUS_LABELS = {
    "pending": "در انتظار تایید",
    "confirmed": "تایید شده",
    "paid": "پرداخت شده",
    "completed": "انجام شده",
    "cancelled": "لغو شده",
    "unpaid": "پرداخت‌نشده",
    "awaiting_stylist_confirmation": "در انتظار تایید متخصص",
    "stylist_confirmed": "متخصص تایید کرد",
    "arrived": "مشتری رسید",
    "in_service": "در حال انجام خدمت",
    "pay_in_salon_pending": "تسویه در مجموعه مانده",
    "review_pending": "آماده نظرسنجی",
    "reviewed": "نظرسنجی ثبت شد",
    "no_show": "عدم حضور",
}

STATUS_BADGES = {
    "pending": "bg-amber-100 text-amber-700",
    "confirmed": "bg-loomera-primarySoft text-loomera-primaryText",
    "paid": "bg-emerald-100 text-emerald-700",
    "completed": "bg-sky-100 text-sky-700",
    "cancelled": "bg-rose-100 text-rose-700",
    "unpaid": "bg-orange-100 text-orange-700",
    "awaiting_stylist_confirmation": "bg-amber-100 text-amber-700",
    "stylist_confirmed": "bg-indigo-100 text-indigo-700",
    "arrived": "bg-cyan-100 text-cyan-700",
    "in_service": "bg-violet-100 text-violet-700",
    "pay_in_salon_pending": "bg-orange-100 text-orange-700",
    "review_pending": "bg-fuchsia-100 text-fuchsia-700",
    "reviewed": "bg-emerald-100 text-emerald-700",
    "no_show": "bg-orange-100 text-orange-800",
}

CARD_TONES = {
    "pending": "border-r-4 border-amber-400 bg-amber-50/70",
    "confirmed": "border-r-4 border-loomera-primary bg-loomera-primarySoft/70",
    "paid": "border-r-4 border-emerald-400 bg-emerald-50",
    "completed": "border-r-4 border-sky-400 bg-sky-50",
    "cancelled": "border-r-4 border-rose-400 bg-rose-50",
    "unpaid": "border-r-4 border-orange-400 bg-orange-50",
    "awaiting_stylist_confirmation": "border-r-4 border-amber-400 bg-amber-50/70",
    "stylist_confirmed": "border-r-4 border-indigo-400 bg-indigo-50",
    "arrived": "border-r-4 border-cyan-400 bg-cyan-50",
    "in_service": "border-r-4 border-violet-400 bg-violet-50",
    "pay_in_salon_pending": "border-r-4 border-orange-500 bg-orange-50",
    "review_pending": "border-r-4 border-fuchsia-400 bg-fuchsia-50",
    "reviewed": "border-r-4 border-emerald-400 bg-emerald-50",
    "no_show": "border-r-4 border-orange-500 bg-orange-50",
}

BULK_ACTIONS = {
    "mark_paid": {
        "label": "ثبت تسویه‌های در مجموعه",
        "message": "تسویه رزروهای مجاز ثبت شد.",
    },
    "cancel": {
        "label": "لغو رزروهای آینده",
        "message": "رزروهای مجاز انتخاب‌شده لغو شدند.",
    },
}

DETAIL_ACTIONS = {
    "mark_paid": {
        "label": "ثبت تسویه در مجموعه",
        "button_class": "bg-emerald-600 text-white hover:bg-emerald-700",
    },
    "cancel": {
        "label": "لغو نوبت",
        "button_class": "bg-rose-600 text-white hover:bg-rose-700",
    },
}


NON_ACTIVE_OPERATIONAL_STATUSES = (
    "cancelled",
    "no_show",
)


CALENDAR_FALLBACK_COLORS = [
    "#735CBE",  # Loomera purple
    "#2F8DE4",  # blue
    "#4AA84A",  # green
    "#F28A2E",  # orange
    "#D85A9D",  # pink
    "#1D9A8A",  # teal
    "#A56B35",  # warm brown
    "#5F6FC4",  # indigo
]

PERSIAN_WEEKDAY_LABELS = {
    5: "شنبه",
    6: "یکشنبه",
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنج‌شنبه",
    4: "جمعه",
}

CALENDAR_HALF_HOUR_PX = 32

def _calendar_week_start(value):
    """Return Saturday for the week containing ``value``."""
    return value - timedelta(days=(value.weekday() + 2) % 7)

def _normalize_hex_color(value):
    raw = str(value or "").strip()
    if len(raw) == 7 and raw.startswith("#"):
        try:
            int(raw[1:], 16)
            return raw.upper()
        except ValueError:
            return ""
    return ""

def _build_calendar_stylists(salon):
    stylists = list(
        salon.stylists.filter(is_active=True)
        .select_related("user")
        .order_by("user__name", "user__family", "pk")
    )
    used_colors = set()
    items = []

    for index, stylist in enumerate(stylists):
        configured = _normalize_hex_color(getattr(stylist, "calendar_color", ""))
        color = configured
        if not color or color in used_colors:
            for offset in range(len(CALENDAR_FALLBACK_COLORS)):
                candidate = CALENDAR_FALLBACK_COLORS[(index + offset) % len(CALENDAR_FALLBACK_COLORS)]
                if candidate.upper() not in used_colors:
                    color = candidate
                    break
        if not color:
            color = CALENDAR_FALLBACK_COLORS[index % len(CALENDAR_FALLBACK_COLORS)]
        color = color.upper()
        used_colors.add(color)

        avatar_url = ""
        try:
            if stylist.profile_image:
                avatar_url = stylist.profile_image.url
        except Exception:
            avatar_url = ""

        initials = (stylist.user.name[:1] if stylist.user.name else "?") + (
            stylist.user.family[:1] if stylist.user.family else ""
        )
        items.append(
            {
                "object": stylist,
                "id": stylist.pk,
                "name": stylist.get_fullName(),
                "expertise": stylist.expert or "عضو تیم",
                "color": color,
                "avatar_url": avatar_url,
                "initials": initials,
            }
        )

    return items

def _appointment_minutes(item):
    if not item.time:
        return None, None
    start = item.time.hour * 60 + item.time.minute
    duration = int(
        getattr(item, "scheduled_duration_minutes", 0)
        or getattr(getattr(item, "service", None), "duration_minutes", 0)
        or 30
    )
    if getattr(item, "end_time", None):
        end = item.end_time.hour * 60 + item.end_time.minute
        if end > start:
            duration = end - start
    return start, max(15, duration)

def _assign_calendar_lanes(events):
    """Assign simple overlap lanes so simultaneous bookings stay readable."""
    if not events:
        return events

    lane_ends = []
    for event in events:
        lane = None
        for lane_index, lane_end in enumerate(lane_ends):
            if lane_end <= event["start_minutes"]:
                lane = lane_index
                lane_ends[lane_index] = event["end_minutes"]
                break
        if lane is None:
            lane = len(lane_ends)
            lane_ends.append(event["end_minutes"])
        event["lane"] = lane

    for event in events:
        overlapping = [
            other
            for other in events
            if other["start_minutes"] < event["end_minutes"]
            and other["end_minutes"] > event["start_minutes"]
        ]
        lane_count = max([other.get("lane", 0) for other in overlapping] or [0]) + 1
        event["lane_count"] = lane_count
        event["lane_width"] = 100 / lane_count
        event["lane_offset"] = event["lane"] * event["lane_width"]
    return events

def _build_week_calendar(
    salon,
    queryset,
    focus_date,
    calendar_stylists,
    *,
    base_url,
    current_params,
    selected_stylist_id=None,
    count_queryset=None,
    calendar_view="",
):
    week_start = _calendar_week_start(focus_date)
    week_end = week_start + timedelta(days=6)
    color_map = {item["id"]: item["color"] for item in calendar_stylists}

    week_items = list(
        queryset.filter(date__range=(week_start, week_end))
        .select_related("order__customer__user", "stylist__user", "service", "order")
        .order_by("date", "time", "id")
    )

    start_candidates = []
    end_candidates = []
    serialized_by_day = {week_start + timedelta(days=offset): [] for offset in range(7)}

    for item in week_items:
        start_minutes, duration = _appointment_minutes(item)
        if start_minutes is None:
            continue
        end_minutes = start_minutes + duration
        start_candidates.append(start_minutes)
        end_candidates.append(end_minutes)
        serialized = _serialize_appointment(item, stylist_color=color_map.get(item.stylist_id))
        serialized.update(
            {
                "start_minutes": start_minutes,
                "end_minutes": end_minutes,
                "duration_minutes": duration,
            }
        )
        serialized_by_day.setdefault(item.date, []).append(serialized)

    calendar_start = min([8 * 60] + start_candidates)
    calendar_start = max(0, (calendar_start // 60) * 60)
    calendar_end = max([21 * 60] + end_candidates)
    calendar_end = min(24 * 60, ((calendar_end + 59) // 60) * 60)
    if calendar_end <= calendar_start:
        calendar_end = calendar_start + 8 * 60

    total_minutes = calendar_end - calendar_start
    total_half_hours = max(1, total_minutes // 30)
    height_px = total_half_hours * CALENDAR_HALF_HOUR_PX

    time_labels = []
    for minute in range(calendar_start, calendar_end + 1, 60):
        hour = minute // 60
        minute_part = minute % 60
        time_labels.append(
            {
                "label": to_persian_digits(f"{hour:02d}:{minute_part:02d}"),
                "top_px": int(((minute - calendar_start) / 30) * CALENDAR_HALF_HOUR_PX),
            }
        )

    days = []
    focus_day = None
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        events = _assign_calendar_lanes(serialized_by_day.get(day, []))
        for event in events:
            event["top_px"] = int(((event["start_minutes"] - calendar_start) / 30) * CALENDAR_HALF_HOUR_PX)
            event["height_px"] = max(
                46,
                int((event["duration_minutes"] / 30) * CALENDAR_HALF_HOUR_PX) - 4,
            )

        day_item = {
            "date": day,
            "weekday_label": PERSIAN_WEEKDAY_LABELS.get(day.weekday(), ""),
            "date_label": format_jalali_numeric(day),
            "full_label": format_jalali_with_weekday(day),
            "is_focus": day == focus_date,
            "is_today": day == timezone.localdate(),
            "appointments": events,
            "count": len(events),
            "count_label": to_persian_digits(len(events)),
            "url": _build_query_url(
                base_url,
                current_params,
                start=format_jalali_numeric(day),
                end=format_jalali_numeric(day),
            ),
        }
        days.append(day_item)
        if day == focus_date:
            focus_day = day_item

    if focus_day is None:
        focus_day = days[0]

    count_items = list(
        (count_queryset if count_queryset is not None else queryset)
        .select_related("stylist")
        .order_by("date", "time", "id")
    )
    stylist_week_counts = {}
    for item in count_items:
        stylist_week_counts[item.stylist_id] = stylist_week_counts.get(item.stylist_id, 0) + 1

    stylist_chips = [
        {
            "id": None,
            "name": "همه متخصصان",
            "color": "#735CBE",
            "is_active": not selected_stylist_id,
            "count": len(count_items),
            "count_label": to_persian_digits(len(count_items)),
            "url": _build_query_url(base_url, current_params, stylist=None),
        }
    ]
    for stylist in calendar_stylists:
        count = stylist_week_counts.get(stylist["id"], 0)
        stylist_chips.append(
            {
                **{key: stylist[key] for key in ("id", "name", "color", "avatar_url", "initials")},
                "is_active": stylist["id"] == selected_stylist_id,
                "count": count,
                "count_label": to_persian_digits(count),
                "url": _build_query_url(base_url, current_params, stylist=stylist["id"]),
            }
        )

    previous_week_focus = focus_date - timedelta(days=7)
    next_week_focus = focus_date + timedelta(days=7)

    return {
        "week_start": week_start,
        "week_end": week_end,
        "range_label": format_jalali_range(week_start, week_end),
        "days": days,
        "focus_day": focus_day,
        "stylists": stylist_chips,
        "time_labels": time_labels,
        "calendar_height_px": height_px,
        "calendar_start_minutes": calendar_start,
        "calendar_end_minutes": calendar_end,
        "appointment_count": len(week_items),
        "appointment_count_label": to_persian_digits(len(week_items)),
        "previous_week_url": _build_query_url(
            base_url,
            current_params,
            start=format_jalali_numeric(previous_week_focus),
            end=format_jalali_numeric(previous_week_focus),
        ),
        "next_week_url": _build_query_url(
            base_url,
            current_params,
            start=format_jalali_numeric(next_week_focus),
            end=format_jalali_numeric(next_week_focus),
        ),
        "today_url": _build_query_url(
            base_url,
            current_params,
            start=format_jalali_numeric(timezone.localdate()),
            end=format_jalali_numeric(timezone.localdate()),
        ),
        "view_mode": calendar_view if calendar_view in {"day", "week"} else "",
        "day_view_url": _build_query_url(base_url, current_params, calendar_view="day"),
        "week_view_url": _build_query_url(base_url, current_params, calendar_view="week"),
    }

def _safe_reverse(name, fallback="#", kwargs=None):
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return fallback


def _parse_date(value, fallback):
    return parse_jalali_input(value, fallback=fallback)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _currency(value):
    return f"{to_persian_digits(f'{int(value or 0):,}')} تومان"


def _cancel_order_by_manager_with_notifications(order, appointment=None, *, actor=None):
    from apps.orders.lifecycle import cancel_order_reminder
    from apps.orders.appointment_lifecycle import _notify_appointment_lifecycle
    from apps.payments.finance import cancel_order_with_financials

    cancellation = cancel_order_with_financials(
        order=order,
        reason="لغو توسط مدیر مجموعه",
        refund_reason="لغو توسط مدیر مجموعه",
        payment=order.payment_order.order_by("-id").first(),
    )

    cancelled_order = cancellation.order
    refund_amount = int(getattr(cancellation, "refund_amount", 0) or 0)

    try:
        cancel_order_reminder(cancelled_order)
    except Exception:
        pass

    detail = appointment
    if detail is None:
        detail = (
            cancelled_order.order_details1.select_related(
                "order",
                "order__customer__user",
                "service",
                "stylist__user",
                "salon",
                "salon__salon_manager__user",
            )
            .order_by("date", "time", "id")
            .first()
        )

    if detail:
        refund_text = ""
        if refund_amount:
            refund_text = f" مبلغ {refund_amount:,} تومان به کیف پول شما برگشت داده شد."

        _notify_appointment_lifecycle(
            detail=detail,
            event_type="manager_cancelled_booking",
            title="نوبت شما توسط مجموعه لغو شد",
            body=f"نوبت شما از سمت مجموعه لغو شد.{refund_text}",
            actor=actor,
            include_customer=True,
            include_stylist=True,
            include_manager=True,
            priority="high",
            meta={
                "cancelled_by": "manager",
                "refund_amount": refund_amount,
                "order_id": cancelled_order.pk,
            },
        )

    return cancellation


def _appointment_item_pricing_meta(item, *, subtotal=None, total_discount=None):
    order = item.order
    base_price = int(item.price or 0)

    subtotal_amount = int(
        subtotal if subtotal is not None else (order.subtotal_amount or base_price or 0)
    )
    discount_amount = int(
        total_discount if total_discount is not None else (order.discount_amount or 0)
    )

    discount_amount = max(min(discount_amount, subtotal_amount), 0)

    item_discount = 0
    if base_price > 0 and subtotal_amount > 0 and discount_amount > 0:
        item_discount = round((discount_amount * base_price) / subtotal_amount)

    item_discount = max(min(int(item_discount or 0), base_price), 0)
    final_price = max(base_price - item_discount, 0)

    discount_parts = []
    if int(order.basket_discount_amount or 0):
        discount_parts.append(f"تخفیف خدمات: {_currency(order.basket_discount_amount)}")
    if int(order.coupon_discount_amount or 0):
        discount_parts.append(f"کد تخفیف: {_currency(order.coupon_discount_amount)}")

    return {
        "base_price": base_price,
        "discount_amount": item_discount,
        "final_price": final_price,
        "has_discount": item_discount > 0,
        "base_price_label": _currency(base_price),
        "discount_label": _currency(item_discount),
        "final_price_label": _currency(final_price),
        "discount_summary": (
            " / ".join(discount_parts) if discount_parts else "بدون تخفیف"
        ),
    }


def _safe_jalali_label(value, formatter=format_jalali_numeric, fallback="—"):
    if not value:
        return fallback
    try:
        return formatter(value)
    except Exception:
        return str(value)


def _serialize_dispute_case(case):
    return {
        "id": case.id,
        "type_label": case.get_dispute_type_display(),
        "status": case.status,
        "status_label": case.get_status_display(),
        "priority_label": case.get_priority_display(),
        "subject": case.subject or "پرونده اختلاف",
        "description": case.description or "",
        "resolution": case.resolution or "",
        "resolution_note": case.resolution_note or "",
        "created_label": _safe_jalali_label(case.created_at),
        "updated_label": _safe_jalali_label(case.updated_at),
    }


def _build_query_url(base_url, params, **updates):
    query_params = dict(params)
    for key, value in updates.items():
        if value in (None, "", [], ()):
            query_params.pop(key, None)
        else:
            query_params[key] = value
    encoded = urlencode(query_params)
    return f"{base_url}?{encoded}" if encoded else base_url


def _visual_status_key(status, is_paid=False):
    key = status or "pending"
    if key == "cancelled":
        return "cancelled"
    if key == "no_show":
        return "no_show"
    if key == "completed":
        return "completed"
    if key == "paid" or is_paid:
        return "paid"
    if key in ["pending", "confirmed"] and not is_paid:
        return "unpaid"
    if key == "confirmed":
        return "confirmed"
    return key


def get_order_status_meta(order):
    stage = determine_current_stage(order)
    return {
        "key": stage,
        "label": STATUS_LABELS.get(
            stage, STATUS_LABELS.get(getattr(order, "status", "pending"), "نامشخص")
        ),
        "badge_class": STATUS_BADGES.get(stage, "bg-slate-100 text-slate-700"),
        "stage": stage,
    }


def _stage_description(stage):
    descriptions = {
        "awaiting_stylist_confirmation": "رزرو ثبت یا پرداخت شده و اکنون منتظر تایید متخصص است.",
        "stylist_confirmed": "متخصص رزرو را تایید کرده و مجموعه آماده پذیرش مشتری است.",
        "arrived": "ورود مشتری ثبت شده و رزرو در آستانه شروع خدمت قرار دارد.",
        "in_service": "خدمت در حال اجرا است و مدیر فقط visibility عملیاتی دارد.",
        "completed": "خدمت تمام شده و رزرو از نظر اجرایی بسته شده است.",
        "pay_in_salon_pending": "خدمت تمام شده اما تسویه نهایی در مجموعه هنوز ثبت نشده است.",
        "review_pending": "از نظر مالی بسته شده و آماده دریافت بازخورد مشتری است.",
        "reviewed": "نظرسنجی مشتری برای این رزرو ثبت شده است.",
        "cancelled": "این رزرو لغو شده و فقط برای پیگیری و گزارش باقی مانده است.",
        "no_show": "عدم حضور مشتری برای این نوبت تأیید شده و رزرو دیگر در چرخه عملیاتی فعال قرار ندارد.",
    }
    return descriptions.get(
        stage, "وضعیت رزرو در همین صفحه از روی lifecycle فعلی قابل پیگیری است."
    )


def _build_summary_cards(metrics):
    """Build appointment cards from prepared aggregate metrics."""

    return [
        {
            "title": "نوبت‌های این نما",
            "value": to_persian_digits(metrics["rows_count"]),
            "meta": "بر اساس فیلترهای فعال",
            "icon": "fa-regular fa-calendar-check",
            "tone": "primary",
        },
        {
            "title": "آینده",
            "value": to_persian_digits(metrics["upcoming_count"]),
            "meta": "رزروهای در انتظار خدمت",
            "icon": "fa-regular fa-hourglass-half",
            "tone": "neutral",
        },
        {
            "title": "پرداخت‌نشده",
            "value": to_persian_digits(metrics["unpaid_count"]),
            "meta": "نیازمند پیگیری مالی یا پرداخت",
            "icon": "fa-solid fa-triangle-exclamation",
            "tone": "warning",
        },
        {
            "title": "پرداخت‌شده",
            "value": to_persian_digits(metrics["paid_count"]),
            "meta": "آماده ارائه خدمت یا تکمیل",
            "icon": "fa-solid fa-circle-check",
            "tone": "success",
        },
        {
            "title": "لغوشده",
            "value": to_persian_digits(metrics["cancelled_count"]),
            "meta": "برای پیگیری ظرفیت یا مشتری",
            "icon": "fa-solid fa-ban",
            "tone": "danger",
        },
        {
            "title": "ارزش رزروها",
            "value": _currency(metrics["total_value"]),
            "meta": "جمع مبلغ نوبت‌های نمایش‌داده‌شده",
            "icon": "fa-solid fa-wallet",
            "tone": "primary",
        },
    ]


def _build_chart(filtered_qs, start_date, end_date):
    range_days = (end_date - start_date).days + 1
    if range_days <= 0:
        range_days = 1

    if range_days > 10:
        start_date = end_date - timedelta(days=9)
        range_days = 10

    grouped = {
        row["date"]: {"count": row["count"], "sales": row["sales"] or 0}
        for row in filtered_qs.filter(date__range=(start_date, end_date))
        .values("date")
        .annotate(count=Count("id"), sales=Sum("price"))
    }

    peak = max((payload["count"] for payload in grouped.values()), default=0)
    bars = []
    total_sales = 0
    total_count = 0

    for offset in range(range_days):
        current_date = start_date + timedelta(days=offset)
        payload = grouped.get(current_date, {"count": 0, "sales": 0})
        total_sales += payload["sales"]
        total_count += payload["count"]
        height = 12
        if peak > 0:
            height = (
                max(14, int((payload["count"] / peak) * 100))
                if payload["count"]
                else 12
            )

        bars.append(
            {
                "label": relative_jalali_label(
                    current_date, today=timezone.localdate()
                ),
                "full_date": format_jalali_with_weekday(current_date),
                "count": payload["count"],
                "count_label": to_persian_digits(payload["count"]),
                "sales_label": _currency(payload["sales"]),
                "height": min(height, 100),
            }
        )

    return {
        "bars": bars,
        "is_empty": total_count == 0,
        "summary": [
            {"label": "تعداد کل", "value": to_persian_digits(total_count)},
            {"label": "فروش کل", "value": _currency(total_sales)},
        ],
    }


def _serialize_appointment(item, stylist_color=None):
    customer_name = "مشتری ثبت نشده"
    customer_mobile = ""
    customer_avatar_url = ""

    customer = getattr(item.order, "customer", None)

    if customer:
        customer_name = customer.get_fullName()
        customer_mobile = getattr(customer.user, "mobile_number", "") or ""

        try:
            if customer.profile_image:
                customer_avatar_url = customer.profile_image.url
        except Exception:
            customer_avatar_url = ""

    status_meta = get_order_status_meta(item.order)
    stylist_name = item.stylist.get_fullName() if item.stylist_id else "بدون متخصص"
    service_name = item.service.service_name if item.service_id else "خدمت ثبت نشده"
    stylist_color = stylist_color or getattr(item.stylist, "calendar_color", "") or "#6d5ef7"
    lifecycle_stage = status_meta["key"]

    pricing = _appointment_item_pricing_meta(item)

    return {
        "id": item.id,
        "order_id": item.order_id,
        "order_code": getattr(item.order, "order_number", f"ORD-{item.order_id}"),
        "customer_name": customer_name,
        "customer_mobile": customer_mobile,
        "customer_avatar_url": customer_avatar_url,
        "service_name": service_name,
        "stylist_name": stylist_name,
        "date_label": (
            format_jalali_with_weekday(item.date) if item.date else "بدون تاریخ"
        ),
        "date_short_label": (
            format_jalali_numeric(item.date) if item.date else "بدون تاریخ"
        ),
        "time_label": format_time_fa(item.time) if item.time else "--:--",
        "end_time_label": (
            format_time_fa(item.end_time) if getattr(item, "end_time", None) else ""
        ),
        "price_label": pricing["final_price_label"],
        "base_price_label": pricing["base_price_label"],
        "discount_label": pricing["discount_label"],
        "has_discount": pricing["has_discount"],
        "status": status_meta,
        "lifecycle_description": _stage_description(lifecycle_stage),
        "description": item.order.description or "",
        "card_class": CARD_TONES.get(
            lifecycle_stage, "border-r-4 border-slate-200 bg-slate-50"
        ),
        "stylist_color": stylist_color,
        "detail_url": _safe_reverse(
            "dashboards:appointment_detail",
            kwargs={"salon_id": item.salon_id, "appointment_id": item.id},
        ),
    }


def _build_schedule_board(salon, filtered_qs, focus_date, calendar_stylists=None):
    calendar_stylists = calendar_stylists or _build_calendar_stylists(salon)
    stylists = [item["object"] for item in calendar_stylists]
    color_map = {item["id"]: item["color"] for item in calendar_stylists}
    day_items = list(
        filtered_qs.filter(date=focus_date)
        .select_related("order__customer__user", "stylist__user", "service", "order")
        .order_by("time", "id")
    )

    appointments_by_stylist = {}
    time_slots = []
    for item in day_items:
        serialized = _serialize_appointment(item, stylist_color=color_map.get(item.stylist_id))
        appointments_by_stylist.setdefault(item.stylist_id, []).append(serialized)
        if item.time:
            slot_label = format_time_fa(item.time)
            if slot_label not in time_slots:
                time_slots.append(slot_label)

    columns = []
    busiest_column = None
    busy_members_count = 0
    in_service_count = 0
    arrived_count = 0
    pending_settlement_count = 0

    for stylist in stylists:
        appointments = appointments_by_stylist.get(stylist.pk, [])
        initials = (stylist.user.name[:1] if stylist.user.name else "?") + (
            stylist.user.family[:1] if stylist.user.family else ""
        )
        stylist_avatar_url = ""
        try:
            if stylist.profile_image:
                stylist_avatar_url = stylist.profile_image.url
        except Exception:
            stylist_avatar_url = ""
        count = len(appointments)
        if count > 0:
            busy_members_count += 1
        stage_counts = {"arrived": 0, "in_service": 0, "pay_in_salon_pending": 0}
        for appointment in appointments:
            stage_counts[appointment["status"]["key"]] = (
                stage_counts.get(appointment["status"]["key"], 0) + 1
            )
        in_service_count += stage_counts.get("in_service", 0)
        arrived_count += stage_counts.get("arrived", 0)
        pending_settlement_count += stage_counts.get("pay_in_salon_pending", 0)
        column = {
            "id": stylist.pk,
            "name": stylist.get_fullName(),
            "expertise": stylist.expert or "عضو تیم",
            "appointments": appointments,
            "count": count,
            "count_label": to_persian_digits(count),
            "initials": initials,
            "avatar_url": stylist_avatar_url,
            "profile_url": _safe_reverse(
                "dashboards:stylist_overview",
                kwargs={"stylist_id": stylist.user.id},
            ),
            "color": color_map.get(stylist.pk) or stylist.calendar_color or "#6d5ef7",
            "stage_counts": {
                "arrived": to_persian_digits(stage_counts.get("arrived", 0)),
                "in_service": to_persian_digits(stage_counts.get("in_service", 0)),
                "pay_in_salon_pending": to_persian_digits(
                    stage_counts.get("pay_in_salon_pending", 0)
                ),
            },
        }
        columns.append(column)
        if busiest_column is None or column["count"] > busiest_column["count"]:
            busiest_column = column

    day_of_week = WEEKDAY_TO_OPENING_DAY[focus_date.weekday()]
    opening_hours = SalonOpeningHours.objects.filter(
        salon=salon, day_of_week=day_of_week
    ).first()

    opening_label = "ساعت کاری ثبت نشده"
    planner_window = ""
    if opening_hours:
        if opening_hours.is_closed:
            opening_label = "مجموعه در این روز تعطیل است"
        elif opening_hours.open_time and opening_hours.close_time:
            planner_window = f"{format_time_fa(opening_hours.open_time)} تا {format_time_fa(opening_hours.close_time)}"
            opening_label = planner_window

    total_revenue = sum(item.price or 0 for item in day_items)
    unpaid_count = sum(
        1
        for item in day_items
        if not item.order.is_paid and item.order.status != "cancelled"
    )

    summary = [
        {"label": "نوبت‌های روز", "value": to_persian_digits(len(day_items))},
        {"label": "ارزش روز", "value": _currency(total_revenue)},
        {"label": "در حال انجام", "value": to_persian_digits(in_service_count)},
        {"label": "رسیده‌اند", "value": to_persian_digits(arrived_count)},
        {"label": "تسویه مانده", "value": to_persian_digits(pending_settlement_count)},
        {"label": "اعضای درگیر", "value": to_persian_digits(busy_members_count)},
    ]

    if busiest_column and busiest_column["count"]:
        summary.append({"label": "شلوغ‌ترین عضو", "value": busiest_column["name"]})

    return {
        "date_label": format_jalali_with_weekday(focus_date),
        "opening_label": opening_label,
        "planner_window": planner_window,
        "columns": columns,
        "time_slots": time_slots[:12],
        "is_empty": len(day_items) == 0,
        "summary": summary,
        "focus_actions": [
            {
                "label": "بازگشت به امروز",
                "url": _safe_reverse(
                    "dashboards:appointment_calendar",
                    kwargs={"salon_id": salon.id},
                )
                + f"?start={format_jalali_numeric(timezone.localdate())}&end={format_jalali_numeric(timezone.localdate())}",
            },
            {
                "label": "شیفت‌ها و مرخصی",
                "url": _safe_reverse("dashboards:scheduled_shifts"),
            },
            {
                "label": "فهرست اعضای تیم",
                "url": _safe_reverse("dashboards:team_member"),
            },
        ],
    }


def _build_table(filtered_qs):
    rows_qs = filtered_qs.select_related(
        "order__customer__user", "stylist__user", "service", "order"
    ).order_by("date", "time", "id")[:100]
    rows = [_serialize_appointment(item) for item in rows_qs]
    return {"rows": rows, "is_empty": len(rows) == 0}


def _build_filter_options(salon):
    stylist_options = [
        {"id": stylist.pk, "label": stylist.get_fullName()}
        for stylist in salon.stylists.filter(is_active=True)
        .select_related("user")
        .order_by("user__name", "user__family")
    ]
    service_options = [
        {"id": service.pk, "label": service.service_name}
        for service in salon.services.filter(is_active=True).order_by("service_name")
    ]
    status_keys = [
        "awaiting_stylist_confirmation",
        "stylist_confirmed",
        "arrived",
        "in_service",
        "pay_in_salon_pending",
        "unpaid",
        "paid",
        "completed",
        "no_show",
        "cancelled",
    ]
    status_options = [{"id": key, "label": STATUS_LABELS[key]} for key in status_keys]
    return {
        "stylists": stylist_options,
        "services": service_options,
        "statuses": status_options,
    }


def _apply_basic_filters(
    qs,
    *,
    q=None,
    stylist_id=None,
    service_id=None,
    status=None,
    start_date=None,
    end_date=None,
):
    if q:
        qs = qs.filter(
            Q(order__customer__user__name__icontains=q)
            | Q(order__customer__user__family__icontains=q)
            | Q(order__customer__user__mobile_number__icontains=q)
            | Q(service__service_name__icontains=q)
            | Q(stylist__user__name__icontains=q)
            | Q(stylist__user__family__icontains=q)
            | Q(order__description__icontains=q)
        )
    if stylist_id:
        qs = qs.filter(stylist_id=stylist_id)
    if service_id:
        qs = qs.filter(service_id=service_id)
    if status:
        if status == "unpaid":
            qs = qs.filter(order__is_paid=False).exclude(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
        elif status == "paid":
            qs = qs.filter(order__is_paid=True)
        elif status == "awaiting_stylist_confirmation":
            qs = (
                qs.filter(order__status__in=["pending", "confirmed", "paid"])
                .filter(
                    order__stylist_confirmed_at__isnull=True,
                    order__service_started_at__isnull=True,
                    order__service_completed_at__isnull=True,
                )
                .exclude(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
            )
        elif status == "stylist_confirmed":
            qs = qs.filter(
                order__stylist_confirmed_at__isnull=False,
                order__customer_arrived_at__isnull=True,
                order__service_started_at__isnull=True,
                order__service_completed_at__isnull=True,
            ).exclude(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
        elif status == "arrived":
            qs = qs.filter(
                order__customer_arrived_at__isnull=False,
                order__service_started_at__isnull=True,
                order__service_completed_at__isnull=True,
            ).exclude(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
        elif status == "in_service":
            qs = qs.filter(
                order__service_started_at__isnull=False,
                order__service_completed_at__isnull=True,
            ).exclude(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
        elif status == "pay_in_salon_pending":
            qs = qs.filter(
                order__service_completed_at__isnull=False,
                order__selected_payment_method="pay_in_salon",
                order__is_paid=False,
            ).exclude(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
        elif status == "review_pending":
            qs = qs.filter(
                order__review_requested_at__isnull=False,
                order__review_completed_at__isnull=True,
            )
        elif status == "reviewed":
            qs = qs.filter(order__review_completed_at__isnull=False)
        else:
            qs = qs.filter(order__status=status)
    if start_date and end_date:
        qs = qs.filter(date__range=(start_date, end_date))
    elif start_date:
        qs = qs.filter(date__gte=start_date)
    elif end_date:
        qs = qs.filter(date__lte=end_date)
    return qs



def _apply_tab_filter(qs, tab, today):
    if tab == "today":
        return qs.filter(date=today)

    if tab == "upcoming":
        return qs.filter(date__gte=today).exclude(
            order__status__in=[
                "cancelled",
                "completed",
                "no_show",
            ]
        )

    if tab == "in_progress":
        return (
            qs.filter(
                order__stylist_confirmed_at__isnull=False
            )
            .filter(
                order__service_completed_at__isnull=True
            )
            .exclude(
                order__status__in=(
                    NON_ACTIVE_OPERATIONAL_STATUSES
                )
            )
        )

    if tab == "attention":
        return qs.filter(
            Q(
                order__stylist_confirmed_at__isnull=True,
                order__status__in=[
                    "pending",
                    "confirmed",
                    "paid",
                ],
            )
            | Q(
                order__service_completed_at__isnull=False,
                order__selected_payment_method=(
                    "pay_in_salon"
                ),
                order__is_paid=False,
            )
        ).exclude(
            order__status__in=(
                NON_ACTIVE_OPERATIONAL_STATUSES
            )
        )

    if tab == "past":
        return qs.filter(
            Q(date__lt=today)
            | Q(
                order__status__in=[
                    "completed",
                    "no_show",
                ]
            )
        )

    if tab == "unpaid":
        return qs.filter(
            order__is_paid=False
        ).exclude(
            order__status__in=(
                NON_ACTIVE_OPERATIONAL_STATUSES
            )
        )

    if tab == "paid":
        return qs.filter(order__is_paid=True)

    if tab == "no_show":
        return qs.filter(order__status="no_show")

    if tab == "cancelled":
        return qs.filter(order__status="cancelled")

    if tab == "completed":
        return qs.filter(order__status="completed")

    return qs


def _build_appointment_tab_counts(
    filtered_base,
    today,
):
    """Calculate all appointment-tab counters in one query."""

    attention_filter = (
        Q(
            order__stylist_confirmed_at__isnull=True,
            order__status__in=[
                "pending",
                "confirmed",
                "paid",
            ],
        )
        | Q(
            order__service_completed_at__isnull=False,
            order__selected_payment_method="pay_in_salon",
            order__is_paid=False,
        )
    ) & ~Q(
        order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES
    )

    raw = filtered_base.aggregate(
        all_count=Count("id"),
        today_count=Count(
            "id",
            filter=Q(date=today),
        ),
        upcoming_count=Count(
            "id",
            filter=(
                Q(date__gte=today)
                & ~Q(
                    order__status__in=[
                        "cancelled",
                        "completed",
                        "no_show",
                    ]
                )
            ),
        ),
        in_progress_count=Count(
            "id",
            filter=(
                Q(
                    order__stylist_confirmed_at__isnull=False,
                    order__service_completed_at__isnull=True,
                )
                & ~Q(
                    order__status__in=(
                        NON_ACTIVE_OPERATIONAL_STATUSES
                    )
                )
            ),
        ),
        attention_count=Count(
            "id",
            filter=attention_filter,
        ),
        past_count=Count(
            "id",
            filter=(
                Q(date__lt=today)
                | Q(
                    order__status__in=[
                        "completed",
                        "no_show",
                    ]
                )
            ),
        ),
        unpaid_count=Count(
            "id",
            filter=(
                Q(order__is_paid=False)
                & ~Q(
                    order__status__in=(
                        NON_ACTIVE_OPERATIONAL_STATUSES
                    )
                )
            ),
        ),
        paid_count=Count(
            "id",
            filter=Q(order__is_paid=True),
        ),
        no_show_count=Count(
            "id",
            filter=Q(order__status="no_show"),
        ),
        cancelled_count=Count(
            "id",
            filter=Q(order__status="cancelled"),
        ),
        completed_count=Count(
            "id",
            filter=Q(order__status="completed"),
        ),
    )

    return {
        tab_key: int(
            raw.get(f"{tab_key}_count") or 0
        )
        for tab_key, _tab_label in TAB_DEFINITIONS
    }

def _build_appointment_summary_metrics(
    filtered_qs,
    today,
):
    """Calculate appointment cards and workspace metrics in one query."""

    raw = filtered_qs.aggregate(
        rows_count=Count("id"),
        total_value=Coalesce(
            Sum("price"),
            Value(0),
        ),
        last_date=Max("date"),
        unpaid_count=Count(
            "id",
            filter=(Q(order__is_paid=False) & ~Q(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)),
        ),
        paid_count=Count(
            "id",
            filter=Q(order__is_paid=True),
        ),
        cancelled_count=Count(
            "id",
            filter=Q(order__status="cancelled"),
        ),
        completed_count=Count(
            "id",
            filter=Q(order__status="completed"),
        ),
        awaiting_confirm_count=Count(
            "id",
            filter=(
                Q(
                    order__status__in=[
                        "pending",
                        "confirmed",
                        "paid",
                    ],
                    order__stylist_confirmed_at__isnull=True,
                    order__service_completed_at__isnull=True,
                )
                & ~Q(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
            ),
        ),
        arrived_count=Count(
            "id",
            filter=(
                Q(
                    order__customer_arrived_at__isnull=False,
                    order__service_started_at__isnull=True,
                    order__service_completed_at__isnull=True,
                )
                & ~Q(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
            ),
        ),
        in_service_count=Count(
            "id",
            filter=(
                Q(
                    order__service_started_at__isnull=False,
                    order__service_completed_at__isnull=True,
                )
                & ~Q(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
            ),
        ),
        pay_in_salon_pending_count=Count(
            "id",
            filter=(
                Q(
                    order__service_completed_at__isnull=False,
                    order__selected_payment_method="pay_in_salon",
                    order__is_paid=False,
                )
                & ~Q(order__status__in=NON_ACTIVE_OPERATIONAL_STATUSES)
            ),
        ),
        upcoming_count=Count(
            "id",
            filter=(
                Q(date__gte=today)
                & ~Q(
                    order__status__in=[
                        "cancelled",
                        "completed",
                        "no_show",
                    ]
                )
            ),
        ),
        unique_customers_count=Count(
            "order__customer_id",
            distinct=True,
        ),
        unique_team_count=Count(
            "stylist_id",
            filter=Q(stylist_id__isnull=False),
            distinct=True,
        ),
    )

    count_keys = (
        "rows_count",
        "unpaid_count",
        "paid_count",
        "cancelled_count",
        "completed_count",
        "awaiting_confirm_count",
        "arrived_count",
        "in_service_count",
        "pay_in_salon_pending_count",
        "upcoming_count",
        "unique_customers_count",
        "unique_team_count",
    )

    metrics = {key: int(raw.get(key) or 0) for key in count_keys}

    metrics["total_value"] = raw.get("total_value") or 0
    metrics["last_date"] = raw.get("last_date")

    return metrics


def apply_bulk_appointment_action(request, salon, redirect_url):
    selected_ids = request.POST.getlist("selected_appointments")
    action = request.POST.get("bulk_action")
    today = timezone.localdate()

    if not selected_ids:
        messages.warning(request, "حداقل یک نوبت را برای عملیات دسته‌ای انتخاب کنید.")
        return redirect(redirect_url)

    if action not in BULK_ACTIONS:
        messages.error(request, "عملیات انتخاب‌شده معتبر نیست.")
        return redirect(redirect_url)

    details = list(
        OrderDetail.objects.filter(salon=salon, pk__in=selected_ids)
        .select_related("order")
        .order_by("date", "time", "id")
    )
    if not details:
        messages.error(request, "هیچ نوبت معتبری برای این مجموعه پیدا نشد.")
        return redirect(redirect_url)

    first_detail_by_order = {}
    for detail in details:
        first_detail_by_order.setdefault(detail.order_id, detail)

    updated = 0
    skipped = 0

    for order in Order.objects.filter(pk__in=first_detail_by_order.keys()):
        detail = first_detail_by_order[order.pk]
        stage = determine_current_stage(order)

        if action == "mark_paid":
            if stage != "pay_in_salon_pending":
                skipped += 1
                continue
            order.is_paid = True
            order.is_finally = True
            order.status = "completed"
            order.save(update_fields=["is_paid", "is_finally", "status", "update_date"])
            from apps.payments.finance import sync_settlement_for_order

            sync_settlement_for_order(
                order, payment=order.payment_order.order_by("-id").first()
            )
            mark_review_requested(order)
            updated += 1
            continue

        if action == "cancel":
            if stage in [
                "arrived",
                "in_service",
                "completed",
                "pay_in_salon_pending",
                "paid",
                "review_pending",
                "reviewed",
                "no_show",
                "cancelled",
            ]:
                skipped += 1
                continue
            if detail.date and detail.date < today:
                skipped += 1
                continue
            _cancel_order_by_manager_with_notifications(
                order,
                appointment=detail,
                actor=request.user,
            )
            updated += 1
            continue

    if updated:
        messages.success(request, f"{updated} مورد با موفقیت به‌روزرسانی شد.")
    if skipped:
        messages.warning(
            request,
            f"{skipped} مورد به‌دلیل وضعیت lifecycle یا محدودیت نقش نادیده گرفته شد.",
        )
    if not updated and not skipped:
        messages.info(request, "تغییری اعمال نشد.")

    return redirect(redirect_url)


def get_allowed_partner_actions(order, appointment):
    today = timezone.localdate()
    actions = []
    stage = determine_current_stage(order)

    if stage == "pay_in_salon_pending":
        actions.append("mark_paid")

    if stage not in [
        "cancelled",
        "arrived",
        "in_service",
        "completed",
        "pay_in_salon_pending",
        "paid",
        "review_pending",
        "reviewed",
        "no_show",
    ]:
        if appointment.date and appointment.date >= today:
            actions.append("cancel")

    return actions


def apply_partner_appointment_action(order, appointment, action, *, actor=None):
    allowed_actions = set(get_allowed_partner_actions(order, appointment))
    if action not in allowed_actions:
        raise ValidationError("این عملیات برای وضعیت فعلی این نوبت مجاز نیست.")

    if action == "mark_paid":
        order.is_paid = True
        order.is_finally = True
        order.status = "completed"
        order.save(update_fields=["is_paid", "is_finally", "status", "update_date"])
        from apps.payments.finance import sync_settlement_for_order

        sync_settlement_for_order(
            order, payment=order.payment_order.order_by("-id").first()
        )
        mark_review_requested(order)
        return "تسویه در مجموعه با موفقیت ثبت شد و مسیر نظرسنجی برای مشتری آماده شد."

    if action == "cancel":
        _cancel_order_by_manager_with_notifications(
            order,
            appointment=appointment,
            actor=actor,
        )
        return "نوبت لغو شد و به مشتری اطلاع داده شد."

    raise ValidationError("عملیات ناشناخته است.")


def build_manager_appointment_detail_context(salon, appointment):
    order = appointment.order
    customer = order.customer
    order_items = list(
        order.order_details1.filter(salon=salon)
        .select_related("service", "stylist__user", "salon")
        .order_by("date", "time", "id")
    )
    dispute_cases = list(
        DisputeCase.objects.filter(order=order, salon=salon)
        .filter(Q(order_detail__in=order_items) | Q(order_detail__isnull=True))
        .select_related("order_detail", "stylist__user", "customer__user")
        .order_by("-updated_at", "-created_at")
    )

    order_subtotal_for_split = int(
        order.subtotal_amount or sum(int(item.price or 0) for item in order_items) or 0
    )
    order_discount_for_split = int(order.discount_amount or 0)

    detail_items = []
    for index, item in enumerate(order_items, start=1):
        pricing = _appointment_item_pricing_meta(
            item,
            subtotal=order_subtotal_for_split,
            total_discount=order_discount_for_split,
        )
        detail_items.append(
            {
                "id": item.id,
                "material_cost_label": _currency(item.get_material_cost_total()),
                "financial_finalized": bool(
                    getattr(item, "financial_finalized_at", None)
                ),
                "material_url": _safe_reverse(
                    "dashboards:appointment_material_usage",
                    kwargs={"salon_id": salon.id, "appointment_id": item.id},
                ),
                "finance_finalize_url": _safe_reverse(
                    "dashboards:appointment_finance_finalize",
                    kwargs={"salon_id": salon.id, "appointment_id": item.id},
                ),
                "can_finalize_finance": bool(
                    getattr(item, "service_completed_at", None)
                )
                and not bool(getattr(item, "financial_finalized_at", None)),
                "sequence_label": f"مرحله {to_persian_digits(index)}",
                "service_name": (
                    item.service.service_name if item.service_id else "خدمت ثبت نشده"
                ),
                "stylist_name": (
                    item.stylist.get_fullName() if item.stylist_id else "بدون متخصص"
                ),
                "date_label": (
                    format_jalali_with_weekday(item.date) if item.date else "بدون تاریخ"
                ),
                "time_label": format_time_fa(item.time) if item.time else "--:--",
                "price_label": pricing["final_price_label"],
                "base_price_label": pricing["base_price_label"],
                "discount_label": pricing["discount_label"],
                "discount_summary": pricing["discount_summary"],
                "has_discount": pricing["has_discount"],
                "finance_rows": [
                    {"label": "قیمت خام خدمت", "value": pricing["base_price_label"]},
                    {
                        "label": "سهم تخفیف این خدمت",
                        "value": (
                            pricing["discount_label"]
                            if pricing["has_discount"]
                            else "بدون تخفیف"
                        ),
                    },
                    {
                        "label": "مبلغ نهایی این خدمت",
                        "value": pricing["final_price_label"],
                    },
                    {"label": "نوع تخفیف", "value": pricing["discount_summary"]},
                ],
                "duration_label": f"{to_persian_digits(getattr(item.service, 'duration_minutes', 0) or 0)} دقیقه",
                "id": item.id,
                "material_cost_label": _currency(item.get_material_cost_total()),
                "financial_finalized": bool(
                    getattr(item, "financial_finalized_at", None)
                ),
                "material_url": _safe_reverse(
                    "dashboards:appointment_material_usage",
                    kwargs={"salon_id": salon.id, "appointment_id": item.id},
                ),
            }
        )

    status_meta = get_order_status_meta(order)
    actions = [
        {
            "key": action_key,
            "label": DETAIL_ACTIONS[action_key]["label"],
            "button_class": DETAIL_ACTIONS[action_key]["button_class"],
        }
        for action_key in get_allowed_partner_actions(order, appointment)
    ]

    if order.status == "cancelled":
        timeline_hint = "این رزرو لغو شده و دیگر در برنامه عملیاتی فعال قرار ندارد."
    elif order.status == "no_show":
        timeline_hint = "عدم حضور مشتری برای این نوبت تأیید شده و رزرو دیگر در چرخه عملیاتی فعال قرار ندارد."
    elif not (order.stylist_confirmed_at or order.stylist_approved):
        timeline_hint = "رزرو ثبت شده و اکنون در انتظار تایید متخصص است."
    elif status_meta["key"] == "unpaid":
        timeline_hint = "رزرو ثبت شده اما هنوز از نظر مالی نهایی نشده است."
    elif (
        order.status == "completed"
        and order.selected_payment_method == "pay_in_salon"
        and not order.is_paid
    ):
        timeline_hint = (
            "خدمت به پایان رسیده اما تسویه نهایی در مجموعه هنوز کامل نشده است."
        )
    elif order.status == "completed":
        timeline_hint = "این نوبت به‌عنوان انجام‌شده ثبت شده است."
    else:
        timeline_hint = "این نوبت در چرخه فعال مجموعه قرار دارد و قابل مدیریت است."

    total_price = int(
        order.total_amount or sum(item.price or 0 for item in order_items) or 0
    )
    first_item = order_items[0] if order_items else appointment
    last_item = order_items[-1] if order_items else appointment
    order_date = first_item.date if getattr(first_item, "date", None) else None
    time_window = f"{format_time_fa(first_item.time) if first_item.time else '--:--'} تا {format_time_fa(last_item.end_time or last_item.time) if (last_item.end_time or last_item.time) else '--:--'}"

    customer_history = OrderDetail.objects.filter(
        salon=salon, order__customer=customer
    ).aggregate(
        visits=Count("id"),
        total_spent=Coalesce(
            Sum(
                "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
            ),
            Value(0),
        ),
        last_visit=Max("date"),
    )

    timeline = [
        {
            "title": "ثبت سفارش",
            "meta": _safe_jalali_label(order.register_date),
            "description": "رزرو توسط مشتری در سیستم ایجاد شده است.",
        },
        {
            "title": "وضعیت فعلی",
            "meta": status_meta["label"],
            "description": timeline_hint,
        },
    ]
    if order.stylist_confirmed_at or order.stylist_approved:
        timeline.append(
            {
                "title": "تایید متخصص",
                "meta": _safe_jalali_label(order.stylist_confirmed_at),
                "description": "متخصص این رزرو را برای اجرا تایید کرده است.",
            }
        )
    if order.customer_arrived_at:
        timeline.append(
            {
                "title": "رسیدن مشتری",
                "meta": _safe_jalali_label(order.customer_arrived_at),
                "description": "رسیدن مشتری در فضای کاری متخصص ثبت شده است.",
            }
        )
    if order.service_started_at:
        timeline.append(
            {
                "title": "شروع خدمت",
                "meta": _safe_jalali_label(order.service_started_at),
                "description": "اجرای خدمت برای این رزرو آغاز شده است.",
            }
        )
    if order.is_paid:
        timeline.append(
            {
                "title": "پرداخت",
                "meta": "تکمیل شده",
                "description": "وضعیت مالی سفارش در حالت پرداخت‌شده قرار دارد.",
            }
        )
    if order.status == "no_show":
        timeline.append(
            {
                "title": "عدم حضور",
                "meta": _safe_jalali_label(
                    getattr(
                        appointment,
                        "no_show_confirmed_at",
                        None,
                    )
                    or order.update_date
                ),
                "description": "عدم حضور تأیید شد",
            }
        )

    if order.status == "completed":
        timeline.append(
            {
                "title": "ارائه خدمت",
                "meta": _safe_jalali_label(
                    order.service_completed_at or order.update_date
                ),
                "description": "سفارش به‌عنوان انجام‌شده بسته شده است.",
            }
        )
    if order.review_requested_at:
        timeline.append(
            {
                "title": "درخواست نظرسنجی",
                "meta": _safe_jalali_label(order.review_requested_at),
                "description": "بعد از نهایی‌شدن مالی، CTA ثبت دیدگاه برای مشتری فعال شده است.",
            }
        )

    customer_url = None
    try:
        customer_url = reverse(
            "dashboards:customer_detail", kwargs={"customer_id": customer.pk}
        )
    except Exception:
        customer_url = None

    customer_avatar_url = ""
    try:
        if customer and customer.profile_image:
            customer_avatar_url = customer.profile_image.url
    except Exception:
        customer_avatar_url = ""

    refund_amount_for_summary = max(
        int(order.refunded_to_wallet_amount or 0),
        wallet_refund_amount_for_order(order),
    )

    return {
        "manager_appointment_detail": {
            "appointment_id": appointment.id,
            "order_code": getattr(order, "order_number", f"ORD-{order.id}"),
            "status": status_meta,
            "payment_label": order.get_selected_payment_method_display(),
            "payment_badge_class": (
                "bg-emerald-100 text-emerald-700"
                if order.is_paid
                else "bg-orange-100 text-orange-700"
            ),
            "customer_name": customer.get_fullName(),
            "customer_mobile": getattr(customer.user, "mobile_number", ""),
            "customer_url": customer_url,
            "customer_avatar_url": customer_avatar_url,
            "salon_name": salon.salon_name,
            "description": order.description or "",
            "items": detail_items,
            "actions": actions,
            "back_url": _safe_reverse(
                "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
            ),
            "timeline_hint": timeline_hint,
            "total_price_label": _currency(total_price),
            "finance_summary": [
                {
                    "label": "بازگشت وجه",
                    "value": _currency(refund_amount_for_summary),
                },
                {
                    "label": "تخفیف خدمات",
                    "value": _currency(order.basket_discount_amount or 0),
                },
                {
                    "label": "عنوان سبد تخفیف",
                    "value": order.basket_discount_title or "بدون سبد تخفیف",
                },
                {"label": "کد تخفیف", "value": order.coupon_code or "بدون کد"},
                {
                    "label": "تخفیف کد",
                    "value": _currency(order.coupon_discount_amount or 0),
                },
                {
                    "label": "جمع کل تخفیف",
                    "value": _currency(order.discount_amount or 0),
                },
                {
                    "label": "روش پرداخت",
                    "value": order.get_selected_payment_method_display(),
                },
                {"label": "مبلغ نهایی", "value": _currency(order.total_amount or 0)},
                {
                    "label": "بازگشت وجه",
                    "value": _currency(order.refunded_to_wallet_amount or 0),
                },
                {
                    "label": "زمان بازگشت وجه",
                    "value": (
                        _safe_jalali_label(order.refunded_to_wallet_at)
                        if order.refunded_to_wallet_at
                        else (
                            "ثبت شده در کیف پول"
                            if refund_amount_for_summary
                            else "بدون بازگشت وجه"
                        )
                    ),
                },
            ],
            "time_window": time_window,
            "service_count_label": to_persian_digits(len(detail_items)),
            "date_label": _safe_jalali_label(
                order_date, formatter=format_jalali_with_weekday
            ),
            "customer_summary": {
                "visits": to_persian_digits(customer_history.get("visits") or 0),
                "total_spent": _currency(customer_history.get("total_spent") or 0),
                "last_visit": _safe_jalali_label(customer_history.get("last_visit")),
            },
            "timeline": timeline,
            "dispute_cases": [_serialize_dispute_case(case) for case in dispute_cases],
            "has_dispute_cases": bool(dispute_cases),
            "dispute_count_label": to_persian_digits(len(dispute_cases)),
            "metadata": [
                {
                    "label": "ثبت سفارش",
                    "value": _safe_jalali_label(order.register_date),
                },
                {
                    "label": "آخرین بروزرسانی",
                    "value": _safe_jalali_label(order.update_date),
                },
                {
                    "label": "کد داخلی سفارش",
                    "value": getattr(order, "order_code", order.id),
                },
            ],
        }
    }


def build_appointment_management_context(request, salon):
    today = timezone.localdate()
    default_start = today
    # Beta UX: a normal navigation opens on today. Contextual links (for example
    # customer search) keep the previous short multi-day window unless they pass
    # an explicit date range.
    has_context_filter = any(
        request.GET.get(key)
        for key in ("q", "stylist", "service", "status", "tab")
    )
    default_end = today + timedelta(days=6) if has_context_filter else today

    start_input = request.GET.get("start")
    end_input = request.GET.get("end")
    start_date = _parse_date(start_input, default_start)
    end_date = _parse_date(end_input, default_end)
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    stylist_id = _int_or_none(request.GET.get("stylist"))
    service_id = _int_or_none(request.GET.get("service"))
    status = request.GET.get("status") or ""
    tab = request.GET.get("tab") or "all"
    if tab not in {item[0] for item in TAB_DEFINITIONS}:
        tab = "all"
    calendar_view = request.GET.get("calendar_view") or ""
    if calendar_view not in {"day", "week"}:
        calendar_view = ""
    q = (request.GET.get("q") or "").strip()

    base_url = _safe_reverse(
        "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
    )
    current_params = {
        "start": format_jalali_numeric(start_date),
        "end": format_jalali_numeric(end_date),
        "tab": tab,
    }
    if stylist_id:
        current_params["stylist"] = str(stylist_id)
    if service_id:
        current_params["service"] = str(service_id)
    if status:
        current_params["status"] = status
    if q:
        current_params["q"] = q
    if calendar_view:
        current_params["calendar_view"] = calendar_view

    base_qs = OrderDetail.objects.filter(salon=salon)
    filtered_base = _apply_basic_filters(
        base_qs,
        q=q,
        stylist_id=stylist_id,
        service_id=service_id,
        status=status or None,
        start_date=start_date,
        end_date=end_date,
    )
    filtered_qs = _apply_tab_filter(filtered_base, tab, today)

    focus_date = (
        start_date
        if start_date == end_date
        else today if start_date <= today <= end_date else start_date
    )
    calendar_week_start = _calendar_week_start(focus_date)
    calendar_week_end = calendar_week_start + timedelta(days=6)

    # Calendar quick-filter counts must describe the same visible week as the
    # scheduler, not the narrower list range (which is often only today).
    calendar_tab_base = _apply_basic_filters(
        base_qs,
        q=q,
        stylist_id=stylist_id,
        service_id=service_id,
        status=status or None,
        start_date=calendar_week_start,
        end_date=calendar_week_end,
    )
    tab_counts = _build_appointment_tab_counts(calendar_tab_base, today)
    tabs = []
    for tab_key, tab_label in TAB_DEFINITIONS:
        count = tab_counts[tab_key]
        tabs.append(
            {
                "key": tab_key,
                "label": tab_label,
                "count": count,
                "count_label": to_persian_digits(count),
                "is_active": tab_key == tab,
                "url": _build_query_url(base_url, current_params, tab=tab_key),
            }
        )

    filter_options = _build_filter_options(salon)

    active_filter_count = sum(
        1
        for value in [
            q,
            stylist_id,
            service_id,
            status,
            tab if tab != "all" else "",
            True if start_date != default_start or end_date != default_end else "",
        ]
        if value
    )

    stylist_label = next(
        (
            item["label"]
            for item in filter_options["stylists"]
            if item["id"] == stylist_id
        ),
        "",
    )
    service_label = next(
        (
            item["label"]
            for item in filter_options["services"]
            if item["id"] == service_id
        ),
        "",
    )
    status_label = dict(STATUS_LABELS).get(status, "")
    tab_label = dict(TAB_DEFINITIONS).get(tab, "همه نوبت‌ها")

    active_filter_chips = []
    if q:
        active_filter_chips.append({"label": "جستجو", "value": q})
    if stylist_label:
        active_filter_chips.append({"label": "متخصص", "value": stylist_label})
    if service_label:
        active_filter_chips.append({"label": "خدمت", "value": service_label})
    if status_label:
        active_filter_chips.append({"label": "وضعیت", "value": status_label})
    if tab != "all":
        active_filter_chips.append({"label": "تب فعال", "value": tab_label})
    if start_date != default_start or end_date != default_end:
        active_filter_chips.append(
            {"label": "بازه", "value": format_jalali_range(start_date, end_date)}
        )

    previous_focus_date = focus_date - timedelta(days=1)
    next_focus_date = focus_date + timedelta(days=1)

    focus_navigation = {
        "today_url": _build_query_url(
            base_url,
            current_params,
            start=format_jalali_numeric(today),
            end=format_jalali_numeric(today),
        ),
        "previous_url": _build_query_url(
            base_url,
            current_params,
            start=format_jalali_numeric(previous_focus_date),
            end=format_jalali_numeric(previous_focus_date),
        ),
        "next_url": _build_query_url(
            base_url,
            current_params,
            start=format_jalali_numeric(next_focus_date),
            end=format_jalali_numeric(next_focus_date),
        ),
    }

    summary_metrics = _build_appointment_summary_metrics(filtered_qs, today)
    rows_count = summary_metrics["rows_count"]
    unpaid_count = summary_metrics["unpaid_count"]
    paid_count = summary_metrics["paid_count"]
    cancelled_count = summary_metrics["cancelled_count"]
    completed_count = summary_metrics["completed_count"]
    awaiting_confirm_count = summary_metrics["awaiting_confirm_count"]
    arrived_count = summary_metrics["arrived_count"]
    in_service_count = summary_metrics["in_service_count"]
    pay_in_salon_pending_count = summary_metrics["pay_in_salon_pending_count"]
    upcoming_count = summary_metrics["upcoming_count"]
    unique_customers_count = summary_metrics["unique_customers_count"]
    unique_team_count = summary_metrics["unique_team_count"]
    total_value = summary_metrics["total_value"]
    last_date = summary_metrics["last_date"]

    focus_items = []
    if rows_count == 0:
        focus_items.append(
            {
                "title": "در این بازه نوبتی پیدا نشد",
                "value": "نیازمند داده",
                "description": "بازه زمانی یا فیلترها را تغییر بده تا تصویر دقیق‌تری از رزروهای مجموعه ببینی.",
                "tone": "warning",
            }
        )
    if unpaid_count > 0:
        focus_items.append(
            {
                "title": "نوبت‌های پرداخت‌نشده نیاز به پیگیری دارند",
                "value": to_persian_digits(unpaid_count),
                "description": "برای روان‌تر شدن عملیات روزانه، وضعیت مالی رزروهای معلق را سریع‌تر روشن کن.",
                "tone": "primary",
            }
        )
    if cancelled_count > 0:
        focus_items.append(
            {
                "title": "لغوها روی ظرفیت تیم اثر گذاشته‌اند",
                "value": to_persian_digits(cancelled_count),
                "description": "لغوها را مرور کن تا فرصت‌های خالی‌شده را دوباره پر یا بازتنظیم کنی.",
                "tone": "neutral",
            }
        )
    if unique_team_count == 0 and rows_count > 0:
        focus_items.append(
            {
                "title": "بعضی رزروها هنوز بدون متخصص مشخص هستند",
                "value": " برنامه ریزی",
                "description": "برای اجرا و هماهنگی بهتر، رزروها باید به اعضای تیم متصل باشند.",
                "tone": "warning",
            }
        )

    if not focus_items:
        focus_items = [
            {
                "title": "نمای نوبت‌ها در وضعیت خوبی است",
                "value": "آماده",
                "description": "فیلترها، وضعیت مالی و نمای روزانه، تصویر مناسبی از عملیات رزرو این بازه ارائه می‌کنند.",
                "tone": "success",
            }
        ]

    quick_actions = [
        {
            "title": "گزارش‌های مجموعه",
            "description": "مرور روند درآمد، رزروها و کیفیت عملکرد در همین بازه‌ها.",
            "icon": "fa-solid fa-chart-line",
            "url": _safe_reverse(
                "dashboards:reports_dashboard", kwargs={"salon_id": salon.id}
            ),
            "badge": "تحلیل",
        },
        {
            "title": "شیفت‌ها و مرخصی",
            "description": "هماهنگی ظرفیت تیم با رزروهای آینده و مرخصی‌ها.",
            "icon": "fa-regular fa-calendar-days",
            "url": _safe_reverse("dashboards:scheduled_shifts"),
            "badge": " برنامه ریزی",
        },
        {
            "title": "اعضای تیم",
            "description": "مرور سریع اعضا، وضعیت آن‌ها و دسترسی به پروفایل هر عضو.",
            "icon": "fa-solid fa-user-group",
            "url": _safe_reverse("dashboards:team_member"),
            "badge": "تیم",
        },
        {
            "title": "مشتریان مجموعه",
            "description": "مدیریت سوابق مشتریان و پیگیری برای رزروهای بعدی",
            "icon": "fa-solid fa-users",
            "url": _safe_reverse("dashboards:salons_customers_page"),
            "badge": "CRM",
        },
    ]

    calendar_stylists = _build_calendar_stylists(salon)
    week_filtered_base = _apply_basic_filters(
        base_qs,
        q=q,
        stylist_id=stylist_id,
        service_id=service_id,
        status=status or None,
        start_date=calendar_week_start,
        end_date=calendar_week_end,
    )
    week_filtered_qs = _apply_tab_filter(week_filtered_base, tab, today)

    # Specialist chip counts intentionally ignore only the stylist filter, so
    # selecting one specialist does not zero every other chip. All other active
    # filters (service/status/tab/search/week) still apply.
    week_count_base = _apply_basic_filters(
        base_qs,
        q=q,
        stylist_id=None,
        service_id=service_id,
        status=status or None,
        start_date=calendar_week_start,
        end_date=calendar_week_end,
    )
    week_count_qs = _apply_tab_filter(week_count_base, tab, today)
    week_calendar = _build_week_calendar(
        salon,
        week_filtered_qs,
        focus_date,
        calendar_stylists,
        base_url=base_url,
        current_params=current_params,
        selected_stylist_id=stylist_id,
        count_queryset=week_count_qs,
        calendar_view=calendar_view,
    )
    schedule_board = _build_schedule_board(
        salon, filtered_qs, focus_date, calendar_stylists=calendar_stylists
    )

    return {
        "appointment_management": {
            "has_salon": True,
            "base_url": base_url,
            "title": "مدیریت نوبت‌ها",
            "subtitle": "نمای عملیاتی رزروها با تمرکز روی تقویم، وضعیت مالی و اقدام سریع تیم.",
            "stats": _build_summary_cards(summary_metrics),
            "tabs": tabs,
            "filter_options": filter_options,
            "filters": {
                "q": q,
                "start": format_jalali_numeric(start_date),
                "end": format_jalali_numeric(end_date),
                "stylist": str(stylist_id) if stylist_id else "",
                "service": str(service_id) if service_id else "",
                "status": status,
                "tab": tab,
                "calendar_view": calendar_view,
            },
            "has_filters": active_filter_count > 0,
            "clear_filters_url": base_url,
            "active_filter_count": active_filter_count,
            "active_filter_chips": active_filter_chips,
            "active_range_label": format_jalali_range(start_date, end_date),
            "chart": _build_chart(filtered_qs, start_date, end_date),
            "schedule_board": schedule_board,
            "week_calendar": week_calendar,
            "focus_navigation": focus_navigation,
            "table": _build_table(filtered_qs),
            "bulk_actions": [
                {"key": key, "label": meta["label"]}
                for key, meta in BULK_ACTIONS.items()
            ],
            "hidden_fields": [
                {"name": key, "value": value}
                for key, value in current_params.items()
                if key != "tab" or value != "all"
            ],
            "filter_summary": {
                "last_updated": format_jalali_with_weekday(today),
                "tab_label": tab_label,
                "query_label": q or "بدون جستجو",
            },
            "workspace": {
                "page_title": f"تقویم ونمای نوبت‌های {salon.salon_name}",
                "dashboard_url": _safe_reverse("dashboards:salon_manager_dashboard"),
                "rows_count_label": to_persian_digits(rows_count),
                "calendar_rows_count_label": week_calendar["appointment_count_label"],
                "unpaid_count_label": to_persian_digits(unpaid_count),
                "paid_count_label": to_persian_digits(paid_count),
                "cancelled_count_label": to_persian_digits(cancelled_count),
                "completed_count_label": to_persian_digits(completed_count),
                "awaiting_confirm_count_label": to_persian_digits(
                    awaiting_confirm_count
                ),
                "arrived_count_label": to_persian_digits(arrived_count),
                "in_service_count_label": to_persian_digits(in_service_count),
                "pay_in_salon_pending_count_label": to_persian_digits(
                    pay_in_salon_pending_count
                ),
                "upcoming_count_label": to_persian_digits(upcoming_count),
                "customers_count_label": to_persian_digits(unique_customers_count),
                "team_count_label": to_persian_digits(unique_team_count),
                "total_value_label": _currency(total_value),
                "last_date_label": _safe_jalali_label(last_date),
                "focus_items": focus_items,
                "quick_actions": quick_actions,
            },
            "add_booking_url": _safe_reverse(
                "dashboards:add_booking", kwargs={"salon_id": salon.id}
            ),
            "export_url": _build_query_url(base_url, current_params),
        }
    }
