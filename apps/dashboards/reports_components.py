from __future__ import annotations

import csv
from datetime import timedelta
from urllib.parse import urlencode

from django.http import HttpResponse

from django.db.models import Count, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.orders.models import OrderDetail

from .jalali_utils import (
    JALALI_MONTH_NAMES,
    format_jalali_day_month,
    format_jalali_numeric,
    format_jalali_range,
    format_jalali_with_weekday,
    format_time_fa,
    gregorian_to_jalali_parts,
    jalali_to_gregorian_parts,
    parse_jalali_input,
    relative_jalali_label,
    to_persian_digits,
)

TAB_DEFINITIONS = [
    ("overview", "نمای کلی"),
    ("sales", "فروش"),
    ("team", "تیم"),
    ("services", "خدمات"),
]

GROUP_BY_OPTIONS = [
    ("day", "روزانه"),
    ("week", "هفتگی"),
    ("month", "ماهانه"),
]

PRESET_DEFINITIONS = [
    ("today", "امروز"),
    ("7d", "۷ روز اخیر"),
    ("30d", "۳۰ روز اخیر"),
    ("jalali_month", "این ماه"),
]

STATUS_LABELS = {
    "pending": "در انتظار تایید",
    "confirmed": "تایید شده",
    "paid": "پرداخت شده",
    "completed": "انجام شده",
    "cancelled": "لغو شده",
}

STATUS_BADGES = {
    "pending": "bg-amber-100 text-amber-700",
    "confirmed": "bg-loomera-primarySoft text-loomera-primaryText",
    "paid": "bg-emerald-100 text-emerald-700",
    "completed": "bg-sky-100 text-sky-700",
    "cancelled": "bg-rose-100 text-rose-700",
}

MAX_REPORT_RANGE_DAYS = 366


def _safe_reverse(name, fallback="#", kwargs=None):
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return fallback


def _build_query_url(base_url, params, **updates):
    query_params = dict(params)
    for key, value in updates.items():
        if value in (None, "", [], (), {}):
            query_params.pop(key, None)
        else:
            query_params[key] = value
    encoded = urlencode(query_params)
    return f"{base_url}?{encoded}" if encoded else base_url


def _parse_date(value, fallback):
    return parse_jalali_input(value, fallback=fallback)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _currency(value):
    return f"{to_persian_digits(f'{int(value or 0):,}')} تومان"


def _percent(value):
    return f"{to_persian_digits(round(value or 0, 1))}٪"


def _resolve_preset_range(preset, today):
    if preset == "today":
        return today, today
    if preset == "7d":
        return today - timedelta(days=6), today
    if preset == "30d":
        return today - timedelta(days=29), today
    if preset == "jalali_month":
        jy, jm, _ = gregorian_to_jalali_parts(today.year, today.month, today.day)
        gy, gm, gd = jalali_to_gregorian_parts(jy, jm, 1)
        return today.__class__(gy, gm, gd), today
    return today - timedelta(days=29), today


def _apply_filters(
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
            | Q(stylist__user__name__icontains=q)
            | Q(stylist__user__family__icontains=q)
            | Q(service__service_name__icontains=q)
            | Q(order__description__icontains=q)
        )
    if stylist_id:
        qs = qs.filter(stylist_id=stylist_id)
    if service_id:
        qs = qs.filter(service_id=service_id)
    if status:
        qs = qs.filter(order__status=status)
    if start_date and end_date:
        qs = qs.filter(date__range=(start_date, end_date))
    elif start_date:
        qs = qs.filter(date__gte=start_date)
    elif end_date:
        qs = qs.filter(date__lte=end_date)
    return qs


def _serialize_status(status):
    return {
        "key": status,
        "label": STATUS_LABELS.get(status, "نامشخص"),
        "badge_class": STATUS_BADGES.get(status, "bg-slate-100 text-slate-700"),
    }


def _safe_full_name(entity, fallback):
    if not entity:
        return fallback

    get_full_name = getattr(entity, "get_fullName", None)
    if callable(get_full_name):
        full_name = (get_full_name() or "").strip()
        if full_name:
            return full_name

    user = getattr(entity, "user", None)
    name = getattr(user, "name", "") or ""
    family = getattr(user, "family", "") or ""
    full_name = f"{name} {family}".strip()

    return full_name or fallback


def _safe_service_name(service, fallback="خدمت ثبت نشده"):
    return (getattr(service, "service_name", "") or "").strip() or fallback


def _build_stats(filtered_qs):
    totals = filtered_qs.aggregate(
        appointments=Count("id"),
        revenue=Sum(
            "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
        ),
        completed=Count("id", filter=Q(order__status="completed")),
    )
    appointments = totals.get("appointments") or 0
    revenue = totals.get("revenue") or 0
    completed = totals.get("completed") or 0
    unique_customers = filtered_qs.values("order__customer_id").distinct().count()
    average_ticket = int(revenue / appointments) if appointments else 0
    completion_rate = (completed / appointments * 100) if appointments else 0

    return [
        {
            "title": "درآمد بازه",
            "value": _currency(revenue),
            "meta": "فقط رزروهای تایید، پرداخت یا انجام‌شده",
            "icon": "fa-solid fa-wallet",
            "tone": "primary",
        },
        {
            "title": "تعداد رزروها",
            "value": to_persian_digits(appointments),
            "meta": "همه رکوردهای مطابق فیلترها",
            "icon": "fa-regular fa-calendar-check",
            "tone": "neutral",
        },
        {
            "title": "مشتری یکتا",
            "value": to_persian_digits(unique_customers),
            "meta": "بر اساس مشتری‌های یکتای بازه",
            "icon": "fa-regular fa-user",
            "tone": "neutral",
        },
        {
            "title": "میانگین ارزش رزرو",
            "value": _currency(average_ticket),
            "meta": "میانگین مبلغ هر رکورد در بازه",
            "icon": "fa-solid fa-receipt",
            "tone": "success",
        },
        {
            "title": "نرخ تکمیل",
            "value": _percent(completion_rate),
            "meta": "سهم رزروهای انجام‌شده از کل رکوردها",
            "icon": "fa-solid fa-chart-pie",
            "tone": "primary",
        },
    ]


def _daily_rollup(filtered_qs):
    rows = (
        filtered_qs.values("date")
        .annotate(
            appointments=Count("id"),
            revenue=Sum(
                "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
            ),
            completed=Count("id", filter=Q(order__status="completed")),
            customers=Count("order__customer_id", distinct=True),
        )
        .order_by("date")
    )
    return {
        row["date"]: {
            "appointments": row["appointments"] or 0,
            "revenue": row["revenue"] or 0,
            "completed": row["completed"] or 0,
            "customers": row["customers"] or 0,
        }
        for row in rows
        if row["date"]
    }


def _customer_ids_by_date(filtered_qs):
    """Return distinct customer IDs grouped by appointment date.

    This intentionally keeps customer IDs as sets so weekly and monthly
    periods can calculate customers distinct across the entire period.

    Summing daily customer counts would be incorrect when the same customer
    has appointments on multiple days.
    """

    rows = (
        filtered_qs.order_by()
        .values_list(
            "date",
            "order__customer_id",
        )
        .distinct()
    )

    customers_by_date = {}

    for date_value, customer_id in rows:
        if date_value is None:
            continue

        customers_by_date.setdefault(
            date_value,
            set(),
        ).add(customer_id)

    return customers_by_date


def _iter_periods(start_date, end_date, group_by):
    periods = []
    current = start_date
    while current <= end_date:
        if group_by == "month":
            jy, jm, _ = gregorian_to_jalali_parts(
                current.year, current.month, current.day
            )
            cursor = current
            last = current
            while cursor <= end_date:
                cjy, cjm, _ = gregorian_to_jalali_parts(
                    cursor.year, cursor.month, cursor.day
                )
                if (cjy, cjm) != (jy, jm):
                    break
                last = cursor
                cursor += timedelta(days=1)
            periods.append(
                {
                    "start": current,
                    "end": last,
                    "key": f"{jy}-{jm}",
                    "label": f"{JALALI_MONTH_NAMES[jm - 1]} {to_persian_digits(jy)}",
                    "meta": format_jalali_range(current, last),
                }
            )
            current = last + timedelta(days=1)
            continue

        if group_by == "week":
            week_end = min(current + timedelta(days=6), end_date)
            periods.append(
                {
                    "start": current,
                    "end": week_end,
                    "key": f"{current.isoformat()}:{week_end.isoformat()}",
                    "label": f"{format_jalali_day_month(current)} تا {format_jalali_day_month(week_end)}",
                    "meta": format_jalali_range(current, week_end),
                }
            )
            current = week_end + timedelta(days=1)
            continue

        periods.append(
            {
                "start": current,
                "end": current,
                "key": current.isoformat(),
                "label": relative_jalali_label(current, today=timezone.localdate()),
                "meta": format_jalali_with_weekday(current),
            }
        )
        current += timedelta(days=1)
    return periods


def _build_chart(
    filtered_qs,
    start_date,
    end_date,
    group_by,
    *,
    daily=None,
    periods=None,
):
    if daily is None:
        daily = _daily_rollup(filtered_qs)

    if periods is None:
        periods = _iter_periods(
            start_date,
            end_date,
            group_by,
        )

    period_count = len(periods)

    if group_by == "month":
        bar_width = 92
    elif group_by == "week":
        bar_width = 72 if period_count <= 18 else 64
    else:
        bar_width = 64 if period_count <= 20 else 52

    chart_min_width = max(680, period_count * bar_width)

    if period_count <= 14:
        label_step = 1
    else:
        label_step = max(1, (period_count + 11) // 12)

    bars = []
    max_revenue = 0
    total_revenue = 0
    total_appointments = 0
    total_completed = 0

    for index, period in enumerate(periods):
        revenue = 0
        appointments = 0
        completed = 0
        cursor = period["start"]

        while cursor <= period["end"]:
            payload = daily.get(cursor, {})
            revenue += payload.get("revenue", 0)
            appointments += payload.get("appointments", 0)
            completed += payload.get("completed", 0)
            cursor += timedelta(days=1)

        total_revenue += revenue
        total_appointments += appointments
        total_completed += completed
        max_revenue = max(max_revenue, revenue)

        show_label = (
            period_count <= 14
            or index == 0
            or index == period_count - 1
            or index % label_step == 0
        )

        bars.append(
            {
                "label": period["label"],
                "meta": period["meta"],
                "show_label": show_label,
                "revenue": revenue,
                "revenue_label": _currency(revenue),
                "appointments": appointments,
                "appointments_label": to_persian_digits(appointments),
                "completed_label": to_persian_digits(completed),
            }
        )

    for item in bars:
        if max_revenue > 0:
            item["height"] = (
                max(14, int((item["revenue"] / max_revenue) * 100))
                if item["revenue"]
                else 8
            )
        else:
            item["height"] = 8

    average_per_period = int(total_revenue / len(periods)) if periods else 0
    completion_rate = (
        (total_completed / total_appointments * 100) if total_appointments else 0
    )

    return {
        "bars": bars,
        "is_empty": total_appointments == 0,
        "bar_width": bar_width,
        "min_width": chart_min_width,
        "is_dense": period_count > 14,
        "period_count_label": to_persian_digits(period_count),
        "summary": [
            {"label": "جمع درآمد", "value": _currency(total_revenue)},
            {"label": "جمع رزروها", "value": to_persian_digits(total_appointments)},
            {"label": "میانگین هر بازه", "value": _currency(average_per_period)},
            {"label": "نرخ تکمیل", "value": _percent(completion_rate)},
        ],
    }


def _build_status_breakdown(filtered_qs):
    total = filtered_qs.count()
    rows = []
    for status, label in STATUS_LABELS.items():
        qs = filtered_qs.filter(order__status=status)
        count = qs.count()
        revenue = qs.aggregate(total=Sum("price"))["total"] or 0
        share = (count / total * 100) if total else 0
        rows.append(
            {
                "label": label,
                "count": count,
                "count_label": to_persian_digits(count),
                "share": share,
                "share_label": _percent(share),
                "revenue_label": _currency(revenue),
                "badge_class": STATUS_BADGES.get(status, "bg-slate-100 text-slate-700"),
            }
        )
    return {"items": rows, "is_empty": total == 0}


def _build_top_services(filtered_qs):
    rows = list(
        filtered_qs.values("service__service_name")
        .annotate(
            appointments=Count("id"),
            revenue=Sum(
                "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
            ),
        )
        .order_by("-revenue", "-appointments")[:5]
    )
    items = [
        {
            "title": row["service__service_name"] or "خدمت بدون نام",
            "meta": f"{to_persian_digits(row['appointments'])} رزرو",
            "value": _currency(row["revenue"] or 0),
        }
        for row in rows
    ]
    return {"items": items, "is_empty": len(items) == 0}


def _build_top_team(filtered_qs):
    rows = list(
        filtered_qs.values("stylist__user__name", "stylist__user__family")
        .annotate(
            appointments=Count("id"),
            revenue=Sum(
                "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
            ),
            completed=Count("id", filter=Q(order__status="completed")),
        )
        .order_by("-revenue", "-appointments")[:5]
    )
    items = []
    for row in rows:
        full_name = f"{row.get('stylist__user__name') or ''} {row.get('stylist__user__family') or ''}".strip()
        items.append(
            {
                "title": full_name or "عضو تیم",
                "meta": f"{to_persian_digits(row['appointments'])} رزرو • {to_persian_digits(row['completed'])} انجام‌شده",
                "value": _currency(row["revenue"] or 0),
            }
        )
    return {"items": items, "is_empty": len(items) == 0}


def _build_overview_rows(
    filtered_qs,
    start_date,
    end_date,
    group_by,
    *,
    daily=None,
    customers_by_date=None,
    periods=None,
):
    """Build period rows from fixed-query prepared report data."""

    if daily is None:
        daily = _daily_rollup(filtered_qs)

    if customers_by_date is None:
        customers_by_date = _customer_ids_by_date(filtered_qs)

    if periods is None:
        periods = _iter_periods(
            start_date,
            end_date,
            group_by,
        )

    rows = []

    for period in periods:
        appointments = 0
        completed = 0
        revenue = 0
        period_customer_ids = set()

        cursor = period["start"]

        while cursor <= period["end"]:
            daily_payload = daily.get(cursor, {})

            appointments += int(daily_payload.get("appointments", 0) or 0)
            completed += int(daily_payload.get("completed", 0) or 0)
            revenue += daily_payload.get("revenue", 0) or 0

            period_customer_ids.update(customers_by_date.get(cursor, ()))

            cursor += timedelta(days=1)

        customers = len(period_customer_ids)

        rows.append(
            {
                "title": period["label"],
                "subtitle": period["meta"],
                "appointments_label": to_persian_digits(appointments),
                "revenue_label": _currency(revenue),
                "customers_label": to_persian_digits(customers),
                "completion_label": _percent(
                    (completed / appointments * 100) if appointments else 0
                ),
            }
        )

    return rows


def _build_sales_rows(filtered_qs):
    qs = filtered_qs.select_related(
        "order__customer__user", "service", "stylist__user", "order"
    ).order_by("-date", "-time", "-id")[:100]

    rows = []

    for item in qs:
        order = getattr(item, "order", None)
        customer = getattr(order, "customer", None)
        service = getattr(item, "service", None)
        stylist = getattr(item, "stylist", None)

        customer_name = _safe_full_name(customer, "مشتری ثبت نشده")
        service_name = _safe_service_name(service)
        stylist_name = _safe_full_name(stylist, "بدون متخصص")

        order_code = (
            getattr(order, "order_number", None) or f"ORD-{item.order_id or item.id}"
        )
        order_status = getattr(order, "status", None) or "pending"

        rows.append(
            {
                "title": customer_name,
                "subtitle": f"{service_name} • {stylist_name}",
                "date_label": (
                    format_jalali_with_weekday(item.date) if item.date else "بدون تاریخ"
                ),
                "code": order_code,
                "status": _serialize_status(order_status),
                "value_label": _currency(item.price),
            }
        )

    return rows


def _build_team_rows(filtered_qs):
    rows = list(
        filtered_qs.values(
            "stylist_id",
            "stylist__user__name",
            "stylist__user__family",
            "stylist__expert",
        )
        .annotate(
            appointments=Count("id"),
            completed=Count("id", filter=Q(order__status="completed")),
            revenue=Sum(
                "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
            ),
            customers=Count("order__customer_id", distinct=True),
        )
        .order_by("-revenue", "-appointments")[:50]
    )
    items = []
    for row in rows:
        full_name = (
            f"{row.get('stylist__user__name') or ''} {row.get('stylist__user__family') or ''}".strip()
            or "عضو تیم"
        )
        appointments = row["appointments"] or 0
        completed = row["completed"] or 0
        items.append(
            {
                "title": full_name,
                "subtitle": row.get("stylist__expert") or "عضو تیم مجموعه",
                "appointments_label": to_persian_digits(appointments),
                "revenue_label": _currency(row["revenue"] or 0),
                "customers_label": to_persian_digits(row["customers"] or 0),
                "completion_label": _percent(
                    (completed / appointments * 100) if appointments else 0
                ),
            }
        )
    return items


def _build_service_rows(filtered_qs):
    rows = list(
        filtered_qs.values("service_id", "service__service_name")
        .annotate(
            appointments=Count("id"),
            completed=Count("id", filter=Q(order__status="completed")),
            revenue=Sum(
                "price", filter=Q(order__status__in=["confirmed", "paid", "completed"])
            ),
            customers=Count("order__customer_id", distinct=True),
        )
        .order_by("-revenue", "-appointments")[:50]
    )
    items = []
    for row in rows:
        appointments = row["appointments"] or 0
        completed = row["completed"] or 0
        items.append(
            {
                "title": row.get("service__service_name") or "خدمت بدون نام",
                "subtitle": f"{to_persian_digits(row['customers'] or 0)} مشتری یکتا",
                "appointments_label": to_persian_digits(appointments),
                "revenue_label": _currency(row["revenue"] or 0),
                "customers_label": to_persian_digits(row["customers"] or 0),
                "completion_label": _percent(
                    (completed / appointments * 100) if appointments else 0
                ),
            }
        )
    return items


def _build_table(
    filtered_qs,
    *,
    tab,
    start_date,
    end_date,
    group_by,
    daily=None,
    customers_by_date=None,
    periods=None,
):
    if tab == "sales":
        rows = _build_sales_rows(filtered_qs)
        return {
            "kind": "sales",
            "rows": rows,
            "is_empty": len(rows) == 0,
            "title": "جزئیات فروش و رزرو",
            "subtitle": "نمای ردیف‌به‌ردیف رزروها برای کنترل مبلغ، تاریخ جلالی و وضعیت هر مورد.",
        }
    if tab == "team":
        rows = _build_team_rows(filtered_qs)
        return {
            "kind": "aggregate",
            "rows": rows,
            "is_empty": len(rows) == 0,
            "title": "عملکرد اعضای تیم",
            "subtitle": "خلاصه درآمد، رزرو و نرخ تکمیل برای هر عضو تیم در بازه فعال.",
        }
    if tab == "services":
        rows = _build_service_rows(filtered_qs)
        return {
            "kind": "aggregate",
            "rows": rows,
            "is_empty": len(rows) == 0,
            "title": "عملکرد خدمات",
            "subtitle": "بررسی درآمد، تعداد رزرو و مشتری یکتا برای هر خدمت.",
        }
    rows = _build_overview_rows(
        filtered_qs,
        start_date,
        end_date,
        group_by,
        daily=daily,
        customers_by_date=customers_by_date,
        periods=periods,
    )
    return {
        "kind": "aggregate",
        "rows": rows,
        "is_empty": len(rows) == 0,
        "title": "خلاصه بازه‌ها",
        "subtitle": "مرور دوره‌ای داده‌ها براساس گروه‌بندی فعال و تقویم جلالی.",
    }


def _build_filter_options(salon):
    stylist_options = [
        {"id": stylist.pk, "label": stylist.get_fullName()}
        for stylist in salon.stylists.filter(is_active=True)
        .select_related("user")
        .order_by("user__name", "user__family")
    ]
    service_options = [
        {"id": service.pk, "label": service.service_name}
        for service in salon.services.all().order_by("service_name")
    ]
    status_options = [
        {"id": key, "label": label} for key, label in STATUS_LABELS.items()
    ]
    group_options = [{"id": key, "label": label} for key, label in GROUP_BY_OPTIONS]
    return {
        "stylists": stylist_options,
        "services": service_options,
        "statuses": status_options,
        "group_by": group_options,
    }


def _clean_csv_value(value):
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _write_report_csv_rows(writer, reports_dashboard):
    table = reports_dashboard.get("table", {})
    filters = reports_dashboard.get("filters", {})
    tab = filters.get("tab") or "overview"
    rows = table.get("rows", [])

    if tab == "sales":
        writer.writerow(["مشتری", "خدمت و متخصص", "تاریخ", "کد رزرو", "وضعیت", "مبلغ"])
        for row in rows:
            status = row.get("status") or {}
            writer.writerow(
                [
                    _clean_csv_value(row.get("title")),
                    _clean_csv_value(row.get("subtitle")),
                    _clean_csv_value(row.get("date_label")),
                    _clean_csv_value(row.get("code")),
                    _clean_csv_value(status.get("label")),
                    _clean_csv_value(row.get("value_label")),
                ]
            )
        return

    if tab == "team":
        writer.writerow(
            ["متخصص", "توضیح", "تعداد رزرو", "درآمد", "مشتری یکتا", "نرخ تکمیل"]
        )
        for row in rows:
            writer.writerow(
                [
                    _clean_csv_value(row.get("title")),
                    _clean_csv_value(row.get("subtitle")),
                    _clean_csv_value(row.get("appointments_label")),
                    _clean_csv_value(row.get("revenue_label")),
                    _clean_csv_value(row.get("customers_label")),
                    _clean_csv_value(row.get("completion_label")),
                ]
            )
        return

    if tab == "services":
        writer.writerow(
            ["خدمت", "توضیح", "تعداد رزرو", "درآمد", "مشتری یکتا", "نرخ تکمیل"]
        )
        for row in rows:
            writer.writerow(
                [
                    _clean_csv_value(row.get("title")),
                    _clean_csv_value(row.get("subtitle")),
                    _clean_csv_value(row.get("appointments_label")),
                    _clean_csv_value(row.get("revenue_label")),
                    _clean_csv_value(row.get("customers_label")),
                    _clean_csv_value(row.get("completion_label")),
                ]
            )
        return

    writer.writerow(["بازه", "توضیح", "تعداد رزرو", "درآمد", "مشتری یکتا", "نرخ تکمیل"])
    for row in rows:
        writer.writerow(
            [
                _clean_csv_value(row.get("title")),
                _clean_csv_value(row.get("subtitle")),
                _clean_csv_value(row.get("appointments_label")),
                _clean_csv_value(row.get("revenue_label")),
                _clean_csv_value(row.get("customers_label")),
                _clean_csv_value(row.get("completion_label")),
            ]
        )


def build_reports_csv_response(request, salon):
    reports_dashboard = build_reports_context(request, salon)["reports_dashboard"]

    filename = f"loomera-salon-report-{salon.id}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # BOM برای اینکه Excel فارسی را درست‌تر باز کند.
    response.write("\ufeff")

    writer = csv.writer(response)

    writer.writerow(
        [
            "گزارش",
            _clean_csv_value(reports_dashboard.get("workspace", {}).get("page_title")),
        ]
    )
    writer.writerow(
        ["بازه", _clean_csv_value(reports_dashboard.get("active_range_label"))]
    )
    writer.writerow(
        [
            "آخرین به‌روزرسانی",
            _clean_csv_value(
                reports_dashboard.get("filter_summary", {}).get("last_updated")
            ),
        ]
    )
    writer.writerow(
        [
            "تعداد نتایج",
            _clean_csv_value(
                reports_dashboard.get("workspace", {}).get("result_count_label")
            ),
        ]
    )
    writer.writerow([])

    active_chips = reports_dashboard.get("active_filter_chips") or []
    if active_chips:
        writer.writerow(["فیلترهای فعال"])
        writer.writerow(["عنوان", "مقدار"])
        for chip in active_chips:
            writer.writerow(
                [
                    _clean_csv_value(chip.get("label")),
                    _clean_csv_value(chip.get("value")),
                ]
            )
        writer.writerow([])

    writer.writerow([_clean_csv_value(reports_dashboard.get("table", {}).get("title"))])
    _write_report_csv_rows(writer, reports_dashboard)

    return response


def build_reports_context(request, salon):
    today = timezone.localdate()
    default_start, default_end = _resolve_preset_range("30d", today)

    report_notices = []

    preset = (request.GET.get("preset") or "").strip()
    start_input = request.GET.get("start")
    end_input = request.GET.get("end")

    if (
        not start_input
        and not end_input
        and preset in {item[0] for item in PRESET_DEFINITIONS}
    ):
        start_date, end_date = _resolve_preset_range(preset, today)
    else:
        start_date = _parse_date(start_input, default_start)
        end_date = _parse_date(end_input, default_end)

    if start_date > end_date:
        start_date, end_date = end_date, start_date
        report_notices.append(
            {
                "title": "بازه گزارش اصلاح شد",
                "value": "ترتیب تاریخ",
                "description": "تاریخ شروع بعد از تاریخ پایان بود؛ بازه به‌صورت خودکار مرتب شد.",
                "tone": "warning",
            }
        )

    range_was_clamped = False
    max_delta = timedelta(days=MAX_REPORT_RANGE_DAYS - 1)

    if (end_date - start_date) > max_delta:
        start_date = end_date - max_delta
        preset = ""
        range_was_clamped = True
        report_notices.append(
            {
                "title": "بازه گزارش برای عملکرد بهتر محدود شد",
                "value": "حداکثر یک‌سال",
                "description": "بازه واردشده خیلی بزرگ بود؛ گزارش از یک‌سال منتهی به تاریخ پایان محاسبه شد.",
                "tone": "warning",
            }
        )

    filter_options = _build_filter_options(salon)
    valid_stylist_ids = {item["id"] for item in filter_options["stylists"]}
    valid_service_ids = {item["id"] for item in filter_options["services"]}
    valid_tab_keys = {key for key, _ in TAB_DEFINITIONS}
    valid_group_by_keys = {key for key, _ in GROUP_BY_OPTIONS}

    raw_stylist_id = _int_or_none(request.GET.get("stylist"))
    stylist_id = raw_stylist_id
    if stylist_id and stylist_id not in valid_stylist_ids:
        stylist_id = None
        report_notices.append(
            {
                "title": "فیلتر متخصص نامعتبر بود",
                "value": "نادیده گرفته شد",
                "description": "متخصص انتخاب‌شده در این سالن وجود ندارد یا به این مجموعه متصل نیست.",
                "tone": "warning",
            }
        )

    raw_service_id = _int_or_none(request.GET.get("service"))
    service_id = raw_service_id
    if service_id and service_id not in valid_service_ids:
        service_id = None
        report_notices.append(
            {
                "title": "فیلتر خدمت نامعتبر بود",
                "value": "نادیده گرفته شد",
                "description": "خدمت انتخاب‌شده در این سالن وجود ندارد یا از دسترس خارج شده است.",
                "tone": "warning",
            }
        )

    status = (request.GET.get("status") or "").strip()
    if status and status not in STATUS_LABELS:
        status = ""
        report_notices.append(
            {
                "title": "فیلتر وضعیت نامعتبر بود",
                "value": "نادیده گرفته شد",
                "description": "وضعیت واردشده در گزارش‌ها پشتیبانی نمی‌شود.",
                "tone": "warning",
            }
        )

    q = (request.GET.get("q") or "").strip()
    if len(q) > 100:
        q = q[:100]
        report_notices.append(
            {
                "title": "عبارت جستجو کوتاه شد",
                "value": "۱۰۰ کاراکتر",
                "description": "برای جلوگیری از سنگین شدن گزارش، عبارت جستجو به ۱۰۰ کاراکتر محدود شد.",
                "tone": "warning",
            }
        )

    tab = (request.GET.get("tab") or "overview").strip()
    if tab not in valid_tab_keys:
        tab = "overview"
        report_notices.append(
            {
                "title": "تب گزارش نامعتبر بود",
                "value": "نمای کلی",
                "description": "تب واردشده در گزارش‌ها وجود ندارد؛ نمای کلی نمایش داده شد.",
                "tone": "warning",
            }
        )

    range_days = (end_date - start_date).days + 1

    if preset == "jalali_month" or range_days > 120:
        default_group_by = "month"
    elif range_days <= 31:
        default_group_by = "day"
    else:
        default_group_by = "week"

    group_by = (request.GET.get("group_by") or default_group_by).strip()
    if group_by not in valid_group_by_keys:
        group_by = default_group_by
        report_notices.append(
            {
                "title": "گروه‌بندی نامعتبر بود",
                "value": dict(GROUP_BY_OPTIONS).get(default_group_by, "پیش‌فرض"),
                "description": "گروه‌بندی واردشده پشتیبانی نمی‌شود؛ حالت مناسب بازه انتخاب شد.",
                "tone": "warning",
            }
        )

    if group_by == "day" and range_days > 45:
        group_by = "month" if range_days > 120 else "week"
        report_notices.append(
            {
                "title": "گروه‌بندی نمودار اصلاح شد",
                "value": dict(GROUP_BY_OPTIONS).get(group_by, "پیش‌فرض"),
                "description": "برای جلوگیری از شلوغی نمودار، گروه‌بندی روزانه در بازه‌های بلند به حالت مناسب‌تر تبدیل شد.",
                "tone": "warning",
            }
        )

    base_url = _safe_reverse(
        "dashboards:reports_dashboard", kwargs={"salon_id": salon.id}
    )

    current_params = {
        "start": format_jalali_numeric(start_date),
        "end": format_jalali_numeric(end_date),
        "tab": tab,
        "group_by": group_by,
    }

    if stylist_id:
        current_params["stylist"] = str(stylist_id)
    if service_id:
        current_params["service"] = str(service_id)
    if status:
        current_params["status"] = status
    if q:
        current_params["q"] = q

    base_qs = OrderDetail.objects.filter(salon=salon).select_related("order")
    filtered_qs = _apply_filters(
        base_qs,
        q=q,
        stylist_id=stylist_id,
        service_id=service_id,
        status=status or None,
        start_date=start_date,
        end_date=end_date,
    )

    tabs = []
    tab_count_map = {
        "overview": filtered_qs.count(),
        "sales": filtered_qs.count(),
        "team": filtered_qs.values("stylist_id").distinct().count(),
        "services": filtered_qs.values("service_id").distinct().count(),
    }
    for key, label in TAB_DEFINITIONS:
        tabs.append(
            {
                "key": key,
                "label": label,
                "count": to_persian_digits(tab_count_map.get(key, 0)),
                "is_active": key == tab,
                "url": _build_query_url(base_url, current_params, tab=key),
            }
        )

    preset_links = []
    for preset_key, preset_label in PRESET_DEFINITIONS:
        preset_start, preset_end = _resolve_preset_range(preset_key, today)
        is_active = start_date == preset_start and end_date == preset_end

        if preset_key == "jalali_month":
            preset_group_by = "month"
        elif (preset_end - preset_start).days <= 10:
            preset_group_by = "day"
        else:
            preset_group_by = "week"

        preset_links.append(
            {
                "key": preset_key,
                "label": preset_label,
                "is_active": is_active,
                "url": _build_query_url(
                    base_url,
                    current_params,
                    start=format_jalali_numeric(preset_start),
                    end=format_jalali_numeric(preset_end),
                    preset=preset_key,
                    group_by=preset_group_by,
                ),
            }
        )

    active_filter_count = sum(
        1
        for value in [
            q,
            stylist_id,
            service_id,
            status,
            group_by if group_by != default_group_by else "",
            True if start_date != default_start or end_date != default_end else "",
        ]
        if value
    ) + len(report_notices)

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
    group_by_label = dict(GROUP_BY_OPTIONS).get(group_by, "هفتگی")

    active_filter_chips = []
    if q:
        active_filter_chips.append({"label": "جستجو", "value": q})
    if stylist_label:
        active_filter_chips.append({"label": "متخصص", "value": stylist_label})
    if service_label:
        active_filter_chips.append({"label": "خدمت", "value": service_label})
    if status_label:
        active_filter_chips.append({"label": "وضعیت", "value": status_label})
    if start_date != default_start or end_date != default_end:
        range_label = format_jalali_range(start_date, end_date)
        if range_was_clamped:
            range_label = f"{range_label} — محدودشده"
        active_filter_chips.append({"label": "بازه", "value": range_label})
    if group_by != default_group_by:
        active_filter_chips.append({"label": "گروه‌بندی", "value": group_by_label})

    revenue_total = (
        filtered_qs.filter(
            order__status__in=["confirmed", "paid", "completed"]
        ).aggregate(total=Sum("price"))["total"]
        or 0
    )
    total_rows = filtered_qs.count()
    completed_count = filtered_qs.filter(order__status="completed").count()
    cancelled_count = filtered_qs.filter(order__status="cancelled").count()
    unique_customers_count = filtered_qs.values("order__customer_id").distinct().count()
    unique_services_count = filtered_qs.values("service_id").distinct().count()
    unique_team_count = filtered_qs.values("stylist_id").distinct().count()
    completion_rate = (completed_count / total_rows * 100) if total_rows else 0
    cancelled_rate = (cancelled_count / total_rows * 100) if total_rows else 0

    focus_items = list(report_notices)

    if total_rows == 0:
        focus_items.append(
            {
                "title": "در این بازه داده‌ای وجود ندارد",
                "value": "نیازمند داده",
                "description": "بازه یا فیلترها را تغییر بده تا تصویر دقیق‌تری از عملکرد کسب‌وکار ببینی.",
                "tone": "warning",
            }
        )
    if revenue_total == 0 and total_rows > 0:
        focus_items.append(
            {
                "title": "درآمد ثبت‌شده صفر است",
                "value": "نیازمند بررسی",
                "description": "وضعیت سفارش‌ها، پرداخت‌ها یا بازه انتخابی را بررسی کن.",
                "tone": "warning",
            }
        )
    if cancelled_rate >= 20:
        focus_items.append(
            {
                "title": "سهم لغوها بالاست",
                "value": _percent(cancelled_rate),
                "description": "برای کاهش لغوها، ظرفیت تیم، قیمت‌گذاری یا تجربه رزرو را بازبینی کن.",
                "tone": "primary",
            }
        )
    if unique_services_count <= 1 and total_rows > 0:
        focus_items.append(
            {
                "title": "تنوع خدمات در گزارش کم است",
                "value": to_persian_digits(unique_services_count),
                "description": "ممکن است بیشتر رزروها روی یک خدمت متمرکز شده باشند.",
                "tone": "neutral",
            }
        )

    if not focus_items:
        focus_items = [
            {
                "title": "نمای گزارش‌ها در وضعیت خوبی است",
                "value": "آماده",
                "description": "درآمد، نرخ تکمیل و پوشش داده‌ها برای این بازه تصویر مناسبی از عملکرد مجموعه می‌دهند.",
                "tone": "success",
            }
        ]

    quick_actions = [
        {
            "title": "مدیریت نوبت‌ها",
            "description": "بازگشت سریع به تقویم و وضعیت عملیاتی رزروها.",
            "icon": "fa-regular fa-calendar-days",
            "url": _safe_reverse(
                "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
            ),
            "badge": "رزروها",
        },
        {
            "title": "منوی خدمات",
            "description": "بازبینی خدمات برای تحلیل عملکرد و درآمد.",
            "icon": "fa-solid fa-scissors",
            "url": _safe_reverse("dashboards:service_menu"),
            "badge": "خدمات",
        },
        {
            "title": "اعضای تیم",
            "description": "مرور اعضای تیم و ظرفیت برای بهبود عملکرد.",
            "icon": "fa-solid fa-user-group",
            "url": _safe_reverse("dashboards:team_member"),
            "badge": "تیم",
        },
        {
            "title": "رزرو آنلاین",
            "description": "بررسی setup صفحه عمومی و ورودی‌های رزرو.",
            "icon": "fa-solid fa-globe",
            "url": _safe_reverse("dashboards:online_booking"),
            "badge": "Online",
        },
    ]
    report_periods = _iter_periods(
        start_date,
        end_date,
        group_by,
    )

    report_daily_rollup = _daily_rollup(filtered_qs)

    report_customers_by_date = None

    if tab == "overview":
        report_customers_by_date = _customer_ids_by_date(filtered_qs)
    return {
        "reports_dashboard": {
            "has_salon": True,
            "base_url": base_url,
            "title": "گزارش‌ها",
            "subtitle": "صفحه گزارش‌ها با فیلترهای جلالی، نمودارها و جدول‌های فارسی‌سازی‌شده بازنویسی شده است.",
            "stats": _build_stats(filtered_qs),
            "tabs": tabs,
            "preset_links": preset_links,
            "filter_options": filter_options,
            "filters": {
                "q": q,
                "start": format_jalali_numeric(start_date),
                "end": format_jalali_numeric(end_date),
                "stylist": str(stylist_id) if stylist_id else "",
                "service": str(service_id) if service_id else "",
                "status": status,
                "tab": tab,
                "group_by": group_by,
            },
            "has_filters": active_filter_count > 0,
            "active_filter_count": active_filter_count,
            "active_filter_chips": active_filter_chips,
            "clear_filters_url": base_url,
            "active_range_label": format_jalali_range(start_date, end_date),
            "chart": _build_chart(
                filtered_qs,
                start_date,
                end_date,
                group_by,
                daily=report_daily_rollup,
                periods=report_periods,
            ),
            "status_breakdown": _build_status_breakdown(filtered_qs),
            "top_services": _build_top_services(filtered_qs),
            "top_team": _build_top_team(filtered_qs),
            "table": _build_table(
                filtered_qs,
                tab=tab,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                daily=report_daily_rollup,
                customers_by_date=report_customers_by_date,
                periods=report_periods,
            ),
            "filter_summary": {
                "last_updated": format_jalali_with_weekday(today),
                "group_by_label": group_by_label,
                "query_label": q or "بدون جستجو",
            },
            "workspace": {
                "page_title": f"گزارش‌های {salon.salon_name}",
                "result_count_label": f"{to_persian_digits(total_rows)} رکورد",
                "revenue_total_label": _currency(revenue_total),
                "completion_rate_label": _percent(completion_rate),
                "cancelled_rate_label": _percent(cancelled_rate),
                "customers_label": to_persian_digits(unique_customers_count),
                "services_label": to_persian_digits(unique_services_count),
                "team_label": to_persian_digits(unique_team_count),
                "focus_items": focus_items,
                "quick_actions": quick_actions,
            },
            "export_url": _build_query_url(base_url, current_params, export="csv"),
        }
    }
