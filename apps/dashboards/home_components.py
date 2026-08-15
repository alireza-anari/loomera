from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.orders.models import OrderDetail
from apps.services.models import Services
from apps.stylists.models import (
    StaffLeaveRequest,
    StaffScheduleRequest,
    StylistSchedule,
    StylistTimeOff,
)

from .jalali_utils import (
    format_jalali_day_month,
    format_jalali_numeric,
    format_jalali_with_weekday,
    format_time_fa,
    relative_jalali_label,
    to_persian_digits,
)
from .layout import (
    get_dashboard_role,
    get_dashboard_salon,
    get_dashboard_stylist,
    get_today_hours_label,
)
from apps.dashboards.readiness import build_salon_readiness_checklist


def _safe_reverse(name, fallback="#", kwargs=None):
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return fallback


SALON_SETUP_PRIORITY_ORDER = {
    "profile": 10,
    "location": 20,
    "services": 30,
    "team": 40,
    "stylist_services": 50,
    "schedule": 60,
    "bookable_path": 70,
    "opening_hours": 80,
    "gallery": 90,
    "payout": 100,
    "verification": 110,
    "public_active": 120,
}


def _build_dashboard_setup_priority(readiness):
    """Return one safe, actionable setup step for the manager dashboard.

    The readiness checklist remains the source of truth. This helper only
    selects one missing item for prominent display and does not mutate models
    or readiness state.
    """
    if not readiness or not readiness.get("enabled"):
        return None

    if readiness.get("is_ready"):
        return None

    actionable_items = [
        item
        for item in readiness.get("missing_items", [])
        if item.get("action_url") and item.get("action_url") != "#"
    ]
    if not actionable_items:
        return None

    selected = min(
        actionable_items,
        key=lambda item: (
            SALON_SETUP_PRIORITY_ORDER.get(item.get("key"), 999),
            -int(item.get("weight") or 0),
            str(item.get("key") or ""),
        ),
    )

    missing_count = len(actionable_items)
    remaining_after = max(missing_count - 1, 0)

    return {
        "key": selected.get("key"),
        "title": selected.get("title"),
        "description": selected.get("description"),
        "action_label": selected.get("action_label"),
        "action_url": selected.get("action_url"),
        "percent": int(readiness.get("percent") or 0),
        "percent_label": readiness.get("percent_label") or "۰٪",
        "missing_count": missing_count,
        "missing_count_label": to_persian_digits(missing_count),
        "remaining_after": remaining_after,
        "remaining_after_label": to_persian_digits(remaining_after),
    }


def _currency(value):
    return f"{to_persian_digits(f'{int(value or 0):,}')} تومان"


def _label_for_date(target_date, today):
    return relative_jalali_label(target_date, today=today)


def _status_meta(order_detail):
    status = getattr(order_detail.order, "status", None) or "pending"
    mapping = {
        "pending": {
            "label": "در انتظار تایید",
            "badge_class": "bg-amber-100 text-amber-700",
        },
        "confirmed": {
            "label": "تایید شده",
            "badge_class": "bg-loomera-primarySoft text-loomera-primaryText",
        },
        "paid": {
            "label": "پرداخت شده",
            "badge_class": "bg-emerald-100 text-emerald-700",
        },
        "completed": {"label": "انجام شده", "badge_class": "bg-sky-100 text-sky-700"},
        "cancelled": {"label": "لغو شده", "badge_class": "bg-rose-100 text-rose-700"},
    }
    return mapping.get(status, mapping["pending"])


def _serialize_appointment(item, today):
    customer_name = "مشتری ثبت نشده"
    customer = getattr(item.order, "customer", None)
    if customer and getattr(customer, "user", None):
        customer_name = customer.get_fullName()

    stylist_name = item.stylist.get_fullName() if item.stylist_id else "بدون متخصص"
    status_meta = _status_meta(item)

    detail_url = "#"
    if getattr(item, "salon_id", None):
        detail_url = _safe_reverse(
            "dashboards:appointment_detail",
            kwargs={"salon_id": item.salon_id, "appointment_id": item.id},
        )

    return {
        "id": item.id,
        "detail_url": detail_url,
        "customer_name": customer_name,
        "service_name": (
            item.service.service_name if item.service_id else "خدمت ثبت نشده"
        ),
        "stylist_name": stylist_name,
        "time": format_time_fa(item.time) if item.time else "بدون ساعت",
        "date": item.date,
        "date_label": _label_for_date(item.date, today) if item.date else "بدون تاریخ",
        "full_date_label": (
            format_jalali_with_weekday(item.date) if item.date else "بدون تاریخ"
        ),
        "price_label": _currency(item.price),
        "status_label": status_meta["label"],
        "status_badge_class": status_meta["badge_class"],
    }


def _build_manager_metrics(salon, base_qs, today):
    """Return manager-dashboard metrics with a fixed query budget.

    All OrderDetail-backed counters are calculated in one aggregate query.
    Active team/service counts are calculated together in a second query.

    The returned dictionary is plain in-memory data and can safely be reused by
    multiple dashboard components without executing additional queries.
    """

    seven_days_ago = today - timedelta(days=6)
    next_seven_days = today + timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)

    order_metrics = base_qs.aggregate(
        sales_7d=Sum(
            "price",
            filter=Q(
                order__is_finally=True,
                date__range=(seven_days_ago, today),
            ),
        ),
        appointments_today=Count(
            "id",
            filter=Q(date=today),
        ),
        upcoming_7d=Count(
            "id",
            filter=Q(date__range=(today, next_seven_days)),
        ),
        unique_customers_30d=Count(
            "order__customer_id",
            filter=Q(date__range=(thirty_days_ago, today)),
            distinct=True,
        ),
        unpaid_count=Count(
            "id",
            filter=Q(order__is_paid=False) & ~Q(order__status="cancelled"),
        ),
    )

    salon_metrics = salon.__class__.objects.filter(pk=salon.pk).aggregate(
        active_team_members=Count(
            "stylists",
            filter=Q(stylists__is_active=True),
            distinct=True,
        ),
        active_services_count=Count(
            "services",
            filter=Q(services__is_active=True),
            distinct=True,
        ),
    )

    return {
        "sales_7d": int(order_metrics["sales_7d"] or 0),
        "appointments_today": int(order_metrics["appointments_today"] or 0),
        "upcoming_7d": int(order_metrics["upcoming_7d"] or 0),
        "unique_customers_30d": int(order_metrics["unique_customers_30d"] or 0),
        "unpaid_count": int(order_metrics["unpaid_count"] or 0),
        "active_team_members": int(salon_metrics["active_team_members"] or 0),
        "active_services_count": int(salon_metrics["active_services_count"] or 0),
    }


def _build_stats(metrics):
    """Build manager stat cards from already-calculated metrics."""

    return [
        {
            "title": "فروش ۷ روز اخیر",
            "value": _currency(metrics["sales_7d"]),
            "meta": "فقط سفارش‌های نهایی‌شده",
            "icon": "fa-solid fa-wallet",
            "tone": "primary",
        },
        {
            "title": "نوبت‌های امروز",
            "value": to_persian_digits(metrics["appointments_today"]),
            "meta": "همه نوبت‌های ثبت‌شده برای امروز",
            "icon": "fa-regular fa-calendar-check",
            "tone": "neutral",
        },
        {
            "title": "نوبت‌های ۷ روز آینده",
            "value": to_persian_digits(metrics["upcoming_7d"]),
            "meta": "برای برنامه‌ریزی تیم",
            "icon": "fa-regular fa-clock",
            "tone": "success",
        },
        {
            "title": "مشتری یکتا در ۳۰ روز",
            "value": to_persian_digits(metrics["unique_customers_30d"]),
            "meta": "بر اساس سفارش‌های ثبت‌شده",
            "icon": "fa-regular fa-user",
            "tone": "neutral",
        },
        {
            "title": "اعضای فعال تیم",
            "value": to_persian_digits(metrics["active_team_members"]),
            "meta": "متخصصهای فعال مجموعه",
            "icon": "fa-solid fa-user-group",
            "tone": "neutral",
        },
    ]


def _build_actions(salon):
    calendar_url = "#"
    calendar_available = False
    reports_url = "#"
    reports_available = False
    if salon:
        calendar_url = _safe_reverse(
            "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
        )
        calendar_available = calendar_url != "#"
        reports_url = _safe_reverse(
            "dashboards:reports_dashboard", kwargs={"salon_id": salon.id}
        )
        reports_available = reports_url != "#"

    return [
        {
            "title": "تقویم نوبت‌ها",
            "description": "بررسی رزروهای آینده و مدیریت روزانه مجموعه.",
            "icon": "fa-regular fa-calendar-days",
            "url": calendar_url,
            "is_available": calendar_available,
            "badge": "اصلی",
        },
        {
            "title": "گزارش‌ها",
            "description": "گزارش‌های فروش، عملکرد تیم و تحلیل خدمات را مرور کن.",
            "icon": "fa-solid fa-chart-line",
            "url": reports_url,
            "is_available": reports_available,
            "badge": " تحلیلی",
        },
        {
            "title": "منوی خدمات",
            "description": "خدمات، قیمت‌ها و ساختار منوی مجموعه را مدیریت کن.",
            "icon": "fa-solid fa-scissors",
            "url": _safe_reverse("dashboards:service_menu"),
            "is_available": True,
            "badge": "خدمات",
        },
        {
            "title": "تیم و شیفت‌ها",
            "description": "اعضای تیم، شیفت‌ها و ظرفیت کاری را مرور کن.",
            "icon": "fa-solid fa-user-group",
            "url": _safe_reverse("dashboards:team_managment"),
            "is_available": True,
            "badge": "تیم",
        },
        {
            "title": "پروفایل مجموعه",
            "description": "اطلاعات برند، تصاویر و جزئیات پروفایل مجموعه را به‌روزرسانی کن.",
            "icon": "fa-regular fa-id-card",
            "url": _safe_reverse("dashboards:salon_profile"),
            "is_available": True,
            "badge": "پروفایل",
        },
    ]


def _build_sales_activity(base_qs, today):
    start_date = today - timedelta(days=6)
    final_qs = base_qs.filter(order__is_finally=True, date__range=(start_date, today))
    grouped = {
        item["date"]: {"count": item["count"], "sales": item["sales"] or 0}
        for item in final_qs.values("date").annotate(
            count=Count("id"), sales=Sum("price")
        )
    }

    days = []
    total_sales = 0
    total_count = 0
    max_sales = max((item["sales"] for item in grouped.values()), default=0)

    for offset in range(7):
        current_date = start_date + timedelta(days=offset)
        payload = grouped.get(current_date, {"count": 0, "sales": 0})
        total_sales += payload["sales"]
        total_count += payload["count"]
        percentage = 0
        if max_sales > 0:
            percentage = (
                max(12, int((payload["sales"] / max_sales) * 100))
                if payload["sales"]
                else 0
            )

        days.append(
            {
                "label": _label_for_date(current_date, today),
                "full_date": format_jalali_with_weekday(current_date),
                "sales_label": _currency(payload["sales"]),
                "appointments": payload["count"],
                "appointments_label": to_persian_digits(payload["count"]),
                "bar_width": percentage,
            }
        )

    return {
        "days": days,
        "summary": [
            {"label": "فروش کل", "value": _currency(total_sales)},
            {"label": "رزرو نهایی", "value": to_persian_digits(total_count)},
        ],
        "is_empty": total_count == 0,
    }


def _build_upcoming(base_qs, today):
    upcoming = list(
        base_qs.filter(date__gte=today)
        .select_related("order__customer__user", "stylist__user", "service")
        .order_by("date", "time")[:6]
    )
    items = [_serialize_appointment(item, today) for item in upcoming]
    return {"items": items, "is_empty": len(items) == 0}


def _build_today(base_qs, today):
    today_items = list(
        base_qs.filter(date=today)
        .select_related("order__customer__user", "stylist__user", "service")
        .order_by("time", "id")[:6]
    )
    items = [_serialize_appointment(item, today) for item in today_items]
    return {"items": items, "is_empty": len(items) == 0}


def _build_popular_services(base_qs):
    rows = list(
        base_qs.values("service__service_name")
        .annotate(count=Count("id"), revenue=Sum("price"))
        .order_by("-count", "-revenue")[:5]
    )
    items = [
        {
            "title": row["service__service_name"] or "خدمت بدون نام",
            "meta": f"{to_persian_digits(row['count'])} رزرو",
            "value": _currency(row["revenue"] or 0),
        }
        for row in rows
    ]
    return {"items": items, "is_empty": len(items) == 0}


def _build_top_stylists(base_qs):
    rows = list(
        base_qs.values("stylist__user__name", "stylist__user__family")
        .annotate(count=Count("id"), revenue=Sum("price"))
        .order_by("-count", "-revenue")[:5]
    )
    items = []
    for row in rows:
        full_name = f"{row.get('stylist__user__name') or ''} {row.get('stylist__user__family') or ''}".strip()
        items.append(
            {
                "title": full_name or "عضو تیم",
                "meta": f"{to_persian_digits(row['count'])} رزرو",
                "value": _currency(row["revenue"] or 0),
            }
        )
    return {"items": items, "is_empty": len(items) == 0}


def _build_snapshot(salon, base_qs, today):
    appointments_today = base_qs.filter(date=today).count()
    pending_approvals = base_qs.filter(order__status="pending").count()
    upcoming_7d = base_qs.filter(date__range=(today, today + timedelta(days=6))).count()

    services_count = salon.services.count()
    active_team_count = salon.stylists.filter(is_active=True).count()
    gallery_count = salon.gallery_images.count()
    features_count = salon.supplementary_info.filter(is_active=True).count()
    open_days_count = salon.opening_hours.filter(is_closed=False).count()
    description_length = len((salon.description or "").strip())

    completion_items = [
        {
            "title": "منوی خدمات",
            "description": "حداقل یک خدمت فعال ثبت کن تا مسیر رزرو واقعی‌تر شود.",
            "count_label": f"{to_persian_digits(services_count)} خدمت",
            "is_done": services_count > 0,
            "url": _safe_reverse("dashboards:service_menu"),
            "icon": "fa-solid fa-scissors",
        },
        {
            "title": "اعضای تیم",
            "description": "حداقل یک عضو فعال تیم اضافه کن تا مدیریت ظرفیت دقیق‌تر شود.",
            "count_label": f"{to_persian_digits(active_team_count)} عضو فعال",
            "is_done": active_team_count > 0,
            "url": _safe_reverse("dashboards:team_managment"),
            "icon": "fa-solid fa-user-group",
        },
        {
            "title": "گالری مجموعه",
            "description": "حداقل یک تصویر واقعی از مجموعه یا برند اضافه کن.",
            "count_label": f"{to_persian_digits(gallery_count)} تصویر",
            "is_done": gallery_count > 0,
            "url": _safe_reverse("dashboards:salon_profile_creator_step6"),
            "icon": "fa-regular fa-images",
        },
        {
            "title": "توضیحات مجموعه",
            "description": "معرفی مجموعه را کامل کن تا صفحه عمومی حرفه‌ای‌تر شود.",
            "count_label": f"{to_persian_digits(description_length)} کاراکتر",
            "is_done": description_length > 0,
            "url": _safe_reverse("dashboards:salon_profile_creator_step8"),
            "icon": "fa-regular fa-pen-to-square",
        },
        {
            "title": "ساعت‌های کاری",
            "description": "برای روزهای کاری اصلی، زمان شروع و پایان را ثبت کن.",
            "count_label": f"{to_persian_digits(open_days_count)} روز فعال",
            "is_done": open_days_count > 0,
            "url": _safe_reverse("dashboards:salon_profile_creator_step3"),
            "icon": "fa-regular fa-clock",
        },
    ]

    if bool(getattr(settings, "ONLINE_PAYMENT_ENABLED", False)):
        completion_items.append(
            {
                "title": "مالی و قوانین لغو",
                "description": "برای دریافت و تسویه پرداخت آنلاین، اطلاعات مالی و قوانین لغو را کامل کن.",
                "count_label": (
                    "آماده" if salon.payout_profile_complete else "نیازمند تکمیل"
                ),
                "is_done": salon.payout_profile_complete,
                "url": _safe_reverse("dashboards:payout_settings"),
                "icon": "fa-solid fa-wallet",
            }
        )

    completed_count = sum(1 for item in completion_items if item["is_done"])
    completion_percentage = (
        int((completed_count / len(completion_items)) * 100) if completion_items else 0
    )

    return {
        "eyebrow": get_today_hours_label(salon),
        "title": "مرکز کنترل امروز",
        "description": "در یک نگاه وضعیت رزروها، آمادگی محیط کاری و مسیرهای مهم بعدی را ببین و از همین‌جا به بخش‌های کلیدی برو.",
        "highlights": [
            {
                "title": "رزرو امروز",
                "value": to_persian_digits(appointments_today),
                "icon": "fa-regular fa-calendar-check",
            },
            {
                "title": "در انتظار تایید",
                "value": to_persian_digits(pending_approvals),
                "icon": "fa-regular fa-bell",
            },
            {
                "title": "۷ روز آینده",
                "value": to_persian_digits(upcoming_7d),
                "icon": "fa-regular fa-clock",
            },
            {
                "title": "امکانات فعال",
                "value": to_persian_digits(features_count),
                "icon": "fa-solid fa-stars",
            },
        ],
        "primary_buttons": [
            {
                "label": "تقویم امروز",
                "url": _safe_reverse(
                    "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
                ),
                "icon": "fa-regular fa-calendar-days",
                "style": "primary",
            },
            {
                "label": "افزودن خدمت",
                "url": _safe_reverse("dashboards:add_service"),
                "icon": "fa-solid fa-plus",
                "style": "secondary",
            },
            {
                "label": "افزودن عضو تیم",
                "url": _safe_reverse("dashboards:add_stylist"),
                "icon": "fa-solid fa-user-plus",
                "style": "secondary",
            },
        ],
        "completion_items": completion_items,
        "completion_count_label": f"{to_persian_digits(completed_count)} از {to_persian_digits(len(completion_items))} بخش",
        "completion_percentage": completion_percentage,
    }


def _build_priority_actions(salon, snapshot):
    suggestions = [
        {
            "title": item["title"],
            "description": item["description"],
            "icon": item["icon"],
            "url": item["url"],
            "is_available": item["url"] != "#",
            "badge": "نیاز به تکمیل",
        }
        for item in snapshot["completion_items"]
        if not item["is_done"]
    ]

    if suggestions:
        return suggestions[:3]

    return [
        {
            "title": "گزارش‌ها",
            "description": "مرور سریع فروش، خدمات محبوب و عملکرد تیم.",
            "icon": "fa-solid fa-chart-line",
            "url": _safe_reverse(
                "dashboards:reports_dashboard", kwargs={"salon_id": salon.id}
            ),
            "is_available": True,
            "badge": "رشد",
        },
        {
            "title": "مشتریان",
            "description": "دفتر مشتریان و سابقه رزروها را مدیریت کن.",
            "icon": "fa-solid fa-users",
            "url": _safe_reverse("dashboards:salons_customers_page"),
            "is_available": True,
            "badge": "CRM",
        },
        {
            "title": "پروفایل مجموعه",
            "description": "ظاهر عمومی مجموعه و جزئیات برند را بازبینی کن.",
            "icon": "fa-regular fa-id-card",
            "url": _safe_reverse("dashboards:salon_profile"),
            "is_available": True,
            "badge": "پروفایل",
        },
    ]


def _build_workspace(salon, metrics):
    sales_7d = metrics["sales_7d"]
    appointments_today = metrics["appointments_today"]
    upcoming_7d = metrics["upcoming_7d"]
    unpaid_count = metrics["unpaid_count"]
    active_team_members = metrics["active_team_members"]
    active_services_count = metrics["active_services_count"]

    focus_items = []
    if active_team_members == 0:
        focus_items.append(
            {
                "title": "عضو فعال برای اجرای رزروها وجود ندارد",
                "value": "نیازمند اقدام",
                "description": "برای اینکه تقویم،  برنامه ریزی و رزروها واقعاً قابل استفاده باشند، باید حداقل یک عضو فعال در تیم داشته باشی.",
                "tone": "warning",
            }
        )
    if appointments_today == 0 and upcoming_7d == 0:
        focus_items.append(
            {
                "title": "در حال حاضر رزرو فعالی در جریان نیست",
                "value": "آرام",
                "description": "یا بازه‌ی آینده هنوز خالی است یا رزروها نیاز به جذب و پیگیری بیشتری دارند.",
                "tone": "neutral",
            }
        )
    if unpaid_count > 0:
        focus_items.append(
            {
                "title": "رزروهای پرداخت‌نشده نیاز به پیگیری دارند",
                "value": to_persian_digits(unpaid_count),
                "description": "برای نظم بهتر عملیات روزانه، وضعیت مالی رزروهای معلق را سریع‌تر روشن کن.",
                "tone": "primary",
            }
        )
    if active_services_count == 0:
        focus_items.append(
            {
                "title": "هنوز خدمت فعالی برای مجموعه ثبت نشده",
                "value": "ضروری",
                "description": "بدون خدمت فعال، هم منوی خدمات ناقص می‌ماند و هم بخش رزرو آنلاین تجربه ضعیفی خواهد داشت.",
                "tone": "warning",
            }
        )

    if not focus_items:
        focus_items = [
            {
                "title": "خانه داشبورد در وضعیت خوبی است",
                "value": "آماده",
                "description": "فروش، تیم، رزروها و منوی خدمات تصویر مناسبی از وضعیت جاری مجموعه ارائه می‌کنند.",
                "tone": "success",
            }
        ]

    return {
        "page_title": f"خانه مدیریتی {salon.salon_name}",
        "badges": [
            {
                "icon": "fa-regular fa-calendar-check",
                "label": f"{to_persian_digits(appointments_today)} نوبت برای امروز",
            },
            {
                "icon": "fa-regular fa-clock",
                "label": f"{to_persian_digits(upcoming_7d)} نوبت در ۷ روز آینده",
            },
            {
                "icon": "fa-solid fa-user-group",
                "label": f"{to_persian_digits(active_team_members)} عضو فعال تیم",
            },
            {
                "icon": "fa-solid fa-scissors",
                "label": f"{to_persian_digits(active_services_count)} خدمت فعال",
            },
            {
                "icon": "fa-solid fa-wallet",
                "label": f"فروش ۷ روز اخیر: {_currency(sales_7d)}",
            },
        ],
        "focus_items": focus_items,
        "appointments_today_label": to_persian_digits(appointments_today),
        "upcoming_7d_label": to_persian_digits(upcoming_7d),
        "active_team_label": to_persian_digits(active_team_members),
        "active_services_label": to_persian_digits(active_services_count),
        "unpaid_count_label": to_persian_digits(unpaid_count),
        "sales_7d_label": _currency(sales_7d),
    }


def _build_manager_daily_snapshot(salon, base_qs, today):
    """Return only the operational facts a manager needs on Dashboard Home."""
    active_qs = base_qs.exclude(order__status="cancelled")
    calendar_url = _safe_reverse(
        "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
    )
    schedule_url = _safe_reverse("dashboards:scheduled_shifts")

    today_qs = active_qs.filter(date=today)
    appointments_today = today_qs.count()
    upcoming_7d = active_qs.filter(
        date__range=(today, today + timedelta(days=6))
    ).count()

    pending_appointments = active_qs.filter(
        date__gte=today,
        order__status="pending",
    ).count()
    pending_schedule_requests = StaffScheduleRequest.objects.filter(
        salon=salon,
        status=StaffScheduleRequest.Status.PENDING,
    ).count()
    pending_leave_requests = StaffLeaveRequest.objects.filter(
        salon=salon,
        status=StaffLeaveRequest.Status.PENDING,
    ).count()

    attention_items = []
    if pending_appointments:
        attention_items.append(
            {
                "title": "نوبت‌های در انتظار تأیید",
                "count": pending_appointments,
                "count_label": to_persian_digits(pending_appointments),
                "description": "وضعیت این نوبت‌ها را بررسی و مشخص کنید.",
                "url": calendar_url,
                "icon": "fa-regular fa-calendar-check",
            }
        )
    if pending_schedule_requests:
        attention_items.append(
            {
                "title": "درخواست برنامه کاری",
                "count": pending_schedule_requests,
                "count_label": to_persian_digits(pending_schedule_requests),
                "description": "درخواست‌های جدید تیم برای برنامه کاری نیاز به بررسی دارند.",
                "url": schedule_url,
                "icon": "fa-regular fa-clock",
            }
        )
    if pending_leave_requests:
        attention_items.append(
            {
                "title": "درخواست مرخصی",
                "count": pending_leave_requests,
                "count_label": to_persian_digits(pending_leave_requests),
                "description": "درخواست‌های مرخصی تیم را بررسی کنید.",
                "url": schedule_url,
                "icon": "fa-regular fa-calendar-xmark",
            }
        )

    attention_count = sum(item["count"] for item in attention_items)

    local_now = timezone.localtime()
    next_item = (
        active_qs.filter(
            Q(date__gt=today) | Q(date=today, time__gte=local_now.time()),
        )
        .exclude(order__status="completed")
        .select_related(
            "order__customer__user",
            "stylist__user",
            "service",
            "salon",
        )
        .order_by("date", "time", "id")
        .first()
    )

    today_items = list(
        today_qs.select_related(
            "order__customer__user",
            "stylist__user",
            "service",
            "salon",
        )
        .order_by("time", "id")[:6]
    )

    return {
        "date_label": format_jalali_with_weekday(today),
        "appointments_today": appointments_today,
        "appointments_today_label": to_persian_digits(appointments_today),
        "upcoming_7d": upcoming_7d,
        "upcoming_7d_label": to_persian_digits(upcoming_7d),
        "attention_count": attention_count,
        "attention_count_label": to_persian_digits(attention_count),
        "attention_items": attention_items,
        "next_appointment": (
            _serialize_appointment(next_item, today) if next_item else None
        ),
        "today": {
            "items": [_serialize_appointment(item, today) for item in today_items],
            "is_empty": not bool(today_items),
        },
        "calendar_url": calendar_url,
        "add_booking_url": _safe_reverse(
            "dashboards:add_booking", kwargs={"salon_id": salon.id}
        ),
    }

def _build_manager_home_payload(salon, base_qs, today, readiness):
    daily = _build_manager_daily_snapshot(salon, base_qs, today)
    mode = "operational" if readiness["is_ready"] else "setup"
    public_page_url = salon.get_absolute_url() if salon.is_active else "#"
    setup_priority = _build_dashboard_setup_priority(readiness)
    next_action = setup_priority or readiness.get("next_action")

    return {
        "mode": mode,
        "salon_name": salon.salon_name,
        "daily": daily,
        "public_page_url": public_page_url,
        "setup_priority": setup_priority,
        "setup": {
            "percent": readiness["percent"],
            "percent_label": readiness.get(
                "percent_label",
                f"{to_persian_digits(readiness.get('percent', 0))}٪",
            ),
            "completed_count_label": readiness.get(
                "completed_count_label",
                to_persian_digits(readiness.get("completed_count", 0)),
            ),
            "total_count_label": readiness.get(
                "total_count_label",
                to_persian_digits(readiness.get("total_count", 0)),
            ),
            "missing_count_label": readiness.get(
                "missing_count_label",
                to_persian_digits(
                    readiness.get(
                        "missing_count",
                        len(readiness.get("missing_items", [])),
                    )
                ),
            ),
            "next_action": next_action,
            "items": readiness.get("items", readiness.get("missing_items", [])),
        },
        "quick_actions": [
            {
                "label": "ثبت نوبت",
                "url": daily["add_booking_url"],
                "icon": "fa-solid fa-plus",
                "style": "primary",
            },
            {
                "label": "همه نوبت‌ها",
                "url": daily["calendar_url"],
                "icon": "fa-regular fa-calendar-days",
                "style": "secondary",
            },
            {
                "label": "صفحه سالن",
                "url": public_page_url,
                "icon": "fa-solid fa-arrow-up-right-from-square",
                "style": "secondary",
                "is_available": public_page_url != "#",
            },
        ],
    }

def build_dashboard_home_context(
    user,
    role=None,
    *,
    salon_override=None,
    stylist_override=None,
):
    resolved_role = role or get_dashboard_role(user)
    salon = salon_override if salon_override is not None else get_dashboard_salon(user)
    stylist = (
        stylist_override
        if stylist_override is not None
        else get_dashboard_stylist(user) if resolved_role == "stylist" else None
    )

    if salon is None:
        empty_title = (
            "خانه مدیریتی مجموعه" if resolved_role != "stylist" else "خانه کاری من"
        )
        return {
            "dashboard_home": {
                "has_salon": False,
                "setup_priority": None,
                "stats": [],
                "actions": [],
                "primary_calendar_url": "#",
                "salon_profile_url": (
                    _safe_reverse("dashboards:stylist_profile")
                    if resolved_role == "stylist"
                    else _safe_reverse("dashboards:salon_profile")
                ),
                "reports_url": "#",
                "sales_activity": {"items": [], "is_empty": True},
                "upcoming": {"items": [], "is_empty": True},
                "today": {"items": [], "is_empty": True},
                "popular_services": {"items": [], "is_empty": True},
                "top_stylists": {"items": [], "is_empty": True},
                "readiness": build_salon_readiness_checklist(salon),
                "setup_priority": None,
                "workspace": {
                    "page_title": empty_title,
                    "hero_description": "بعد از اتصال به مجموعه، کارت‌های داشبورد و بخش‌های شخصی شما با داده‌های واقعی همین‌جا نمایش داده می‌شود.",
                    "primary_cta_label": (
                        "پروفایل من"
                        if resolved_role == "stylist"
                        else "ساخت پروفایل مجموعه"
                    ),
                    "secondary_cta_label": None,
                    "tertiary_cta_label": None,
                    "secondary_cta_url": "#",
                    "tertiary_cta_url": "#",
                    "badges": [],
                    "focus_title": "وضعیت فعلی",
                    "focus_items": [
                        {
                            "title": "هنوز محیط کاری فعالی برای این حساب پیدا نشد",
                            "value": "نیازمند اقدام",
                            "description": "بعد از تکمیل اتصال متخصص به مجموعه، نوبت‌ها، برنامه کاری و اعلان‌های شخصی شما اینجا نمایش داده می‌شود.",
                            "tone": "warning",
                        }
                    ],
                    "appointments_today_label": "۰",
                    "upcoming_7d_label": "۰",
                    "active_team_label": "۰",
                    "active_services_label": "۰",
                    "unpaid_count_label": "۰",
                    "sales_7d_label": _currency(0),
                },
                "sections": {
                    "sales_activity_title": "خلاصه فعالیت",
                    "sales_activity_subtitle": "داده‌ای برای نمایش وجود ندارد.",
                    "sales_activity_action_label": None,
                    "sales_activity_action_url": "#",
                    "upcoming_title": "نوبت‌های پیش‌رو",
                    "upcoming_subtitle": "رزروی برای نمایش وجود ندارد.",
                    "upcoming_action_label": None,
                    "upcoming_action_url": "#",
                    "today_title": "نوبت‌های امروز",
                    "today_subtitle": "نمای سریع برای شروع روز کاری",
                    "today_action_label": None,
                    "today_action_url": "#",
                    "popular_title": "خدمات فعال",
                    "popular_subtitle": "خدماتی که شما ارائه می‌دهید",
                    "top_title": "بخش‌های مدیریتی قفل‌شده",
                    "top_subtitle": "این بخش‌ها فقط برای مدیر مجموعه فعال هستند.",
                },
            }
        }

    today = timezone.localdate()

    if resolved_role == "stylist" and stylist is not None:
        readiness = build_salon_readiness_checklist(salon)
        setup_priority = _build_dashboard_setup_priority(readiness)
        base_qs = OrderDetail.objects.filter(
            salon=salon, stylist=stylist
        ).select_related("order", "service", "stylist", "order__customer__user")
        stats = [
            {
                "title": "نوبت‌های امروز من",
                "value": to_persian_digits(
                    base_qs.filter(date=today)
                    .exclude(order__status="cancelled")
                    .count()
                ),
                "meta": "برنامه کاری امروز شما",
                "icon": "fa-regular fa-calendar-check",
                "tone": "primary",
            },
            {
                "title": "نوبت‌های ۷ روز آینده",
                "value": to_persian_digits(
                    base_qs.filter(date__range=(today, today + timedelta(days=6)))
                    .exclude(order__status="cancelled")
                    .count()
                ),
                "meta": "برای برنامه‌ریزی شخصی",
                "icon": "fa-regular fa-clock",
                "tone": "success",
            },
            {
                "title": "خدمات فعال من",
                "value": to_persian_digits(
                    Services.objects.filter(
                        stylists=stylist, services_of_salon=salon, is_active=True
                    )
                    .distinct()
                    .count()
                ),
                "meta": "خدماتی که در رزرو آنلاین به شما متصل‌اند",
                "icon": "fa-solid fa-scissors",
                "tone": "neutral",
            },
            {
                "title": "مرخصی‌های نزدیک",
                "value": to_persian_digits(
                    StylistTimeOff.objects.filter(
                        stylist=stylist,
                        date__gte=today,
                        date__lte=today + timedelta(days=14),
                    ).count()
                ),
                "meta": "برای ۱۴ روز آینده",
                "icon": "fa-regular fa-calendar-xmark",
                "tone": "warning",
            },
            {
                "title": "مشتری یکتا در ۳۰ روز",
                "value": to_persian_digits(
                    base_qs.filter(date__range=(today - timedelta(days=29), today))
                    .values("order__customer_id")
                    .distinct()
                    .count()
                ),
                "meta": "فقط مشتری‌های شما",
                "icon": "fa-regular fa-user",
                "tone": "neutral",
            },
        ]
        actions = [
            {
                "title": "نوبت‌های من",
                "description": "فهرست کامل رزروهای مربوط به شما با تب‌های امروز، آینده و گذشته.",
                "icon": "fa-regular fa-calendar-days",
                "url": _safe_reverse("dashboards:stylist_appointments"),
                "is_available": True,
                "badge": "شخصی",
            },
            {
                "title": "برنامه و مرخصی من",
                "description": "شیفت‌ها، حضور و مرخصی‌های خودتان را یکجا ببینید.",
                "icon": "fa-regular fa-clock",
                "url": _safe_reverse("dashboards:stylist_schedule"),
                "is_available": True,
                "badge": "برنامه",
            },
            {
                "title": "ثبت مرخصی",
                "description": "اگر نیاز به عدم حضور دارید، از همین‌جا مرخصی شخصی ثبت کنید.",
                "icon": "fa-regular fa-calendar-xmark",
                "url": _safe_reverse("dashboards:stylist_add_time_off"),
                "is_available": True,
                "badge": "مرخصی",
            },
            {
                "title": "پروفایل من",
                "description": "اطلاعات حرفه‌ای، تخصص، تصویر و معرفی خود را به‌روزرسانی کنید.",
                "icon": "fa-regular fa-id-card",
                "url": _safe_reverse("dashboards:stylist_profile"),
                "is_available": True,
                "badge": "پروفایل",
            },
        ]
        upcoming_items = [
            _serialize_appointment(item, today)
            for item in base_qs.filter(date__gte=today)
            .exclude(order__status="cancelled")
            .order_by("date", "time")[:6]
        ]
        today_items = [
            _serialize_appointment(item, today)
            for item in base_qs.filter(date=today)
            .exclude(order__status="cancelled")
            .order_by("time")[:6]
        ]
        services_widget = {
            "items": [
                {
                    "title": service.service_name,
                    "value": "فعال",
                    "meta": "متصل به پروفایل شما",
                }
                for service in Services.objects.filter(
                    stylists=stylist, is_active=True
                ).distinct()[:5]
            ],
            "is_empty": False,
        }
        if not services_widget["items"]:
            services_widget["is_empty"] = True
        personal_summary_widget = {
            "items": [],
            "is_empty": False,
        }
        next_shift = (
            StylistSchedule.objects.filter(
                stylist=stylist,
                salon=salon,
                date__gte=today,
            )
            .order_by("date", "start_time")
            .first()
        )
        next_time_off = (
            StylistTimeOff.objects.filter(stylist=stylist, date__gte=today)
            .order_by("date", "start_time")
            .first()
        )
        if next_shift:
            personal_summary_widget["items"].append(
                {
                    "title": "شیفت بعدی",
                    "value": (
                        format_time_fa(next_shift.start_time)
                        if next_shift.start_time
                        else "—"
                    ),
                    "meta": format_jalali_with_weekday(next_shift.date),
                }
            )
        if next_time_off:
            personal_summary_widget["items"].append(
                {
                    "title": "مرخصی نزدیک",
                    "value": format_jalali_numeric(next_time_off.date),
                    "meta": (next_time_off.reason or "مرخصی ثبت‌شده")[:40],
                }
            )
        personal_summary_widget["items"].append(
            {
                "title": "رزرو پرداخت‌نشده",
                "value": to_persian_digits(
                    base_qs.filter(order__is_paid=False)
                    .exclude(order__status="cancelled")
                    .count()
                ),
                "meta": "فقط رزروهای مربوط به شما",
            }
        )
        personal_summary_widget["is_empty"] = not bool(personal_summary_widget["items"])

        focus_items = [
            {
                "title": "اولین نوبت بعدی",
                "value": (
                    upcoming_items[0]["full_date_label"]
                    if upcoming_items
                    else "بدون نوبت"
                ),
                "description": (
                    upcoming_items[0]["customer_name"]
                    + " • "
                    + upcoming_items[0]["service_name"]
                    if upcoming_items
                    else "در حال حاضر نوبت پیش‌روی ثبت‌شده‌ای برای شما وجود ندارد."
                ),
                "tone": "primary" if upcoming_items else "neutral",
            },
            {
                "title": "شیفت بعدی",
                "value": (
                    format_jalali_with_weekday(next_shift.date)
                    if next_shift
                    else "ثبت نشده"
                ),
                "description": (
                    f"{format_time_fa(next_shift.start_time)} تا {format_time_fa(next_shift.end_time)}"
                    if next_shift
                    else "اگر برنامه کاری هنوز تنظیم نشده، با مدیر مجموعه هماهنگ کنید."
                ),
                "tone": "success" if next_shift else "warning",
            },
            {
                "title": "مرخصی نزدیک",
                "value": (
                    format_jalali_with_weekday(next_time_off.date)
                    if next_time_off
                    else "بدون مرخصی"
                ),
                "description": (
                    (next_time_off.reason or "مرخصی ثبت‌شده")
                    if next_time_off
                    else "در ۱۴ روز آینده مرخصی ثبت نشده است."
                ),
                "tone": "warning" if next_time_off else "neutral",
            },
        ]
        return {
            "dashboard_home": {
                "has_salon": True,
                "readiness": None,
                "setup_priority": None,
                "stats": stats,
                "actions": actions,
                "primary_calendar_url": _safe_reverse(
                    "dashboards:stylist_appointments"
                ),
                "reports_url": "#",
                "salon_profile_url": _safe_reverse("dashboards:stylist_profile"),
                "sales_activity": _build_sales_activity(base_qs, today),
                "upcoming": {"items": upcoming_items, "is_empty": not upcoming_items},
                "today": {"items": today_items, "is_empty": not today_items},
                "popular_services": services_widget,
                "top_stylists": personal_summary_widget,
                "workspace": {
                    "page_title": "خانه کاری من",
                    "hero_description": "داشبورد شخصی شما روی همان ساختار اصلی پنل مجموعه ساخته شده، اما فقط داده‌ها و اکشن‌های مربوط به خودتان را فعال می‌کند.",
                    "primary_cta_label": "نوبت‌های من",
                    "secondary_cta_label": "برنامه من",
                    "tertiary_cta_label": "پروفایل من",
                    "secondary_cta_url": _safe_reverse("dashboards:stylist_schedule"),
                    "tertiary_cta_url": _safe_reverse("dashboards:stylist_profile"),
                    "badges": [
                        {"icon": "fa-solid fa-store", "label": salon.salon_name},
                        {
                            "icon": "fa-solid fa-scissors",
                            "label": f"{to_persian_digits(Services.objects.filter(
                                stylists=stylist,
                                services_of_salon=salon,
                                is_active=True,
                            ).distinct().count())} خدمت فعال",
                        },
                        {
                            "icon": "fa-regular fa-calendar-check",
                            "label": f"{to_persian_digits(base_qs.filter(date=today).exclude(order__status='cancelled').count())} نوبت امروز",
                        },
                    ],
                    "focus_title": "فوکوس امروز شما",
                    "focus_items": focus_items,
                    "appointments_today_label": to_persian_digits(
                        base_qs.filter(date=today)
                        .exclude(order__status="cancelled")
                        .count()
                    ),
                    "upcoming_7d_label": to_persian_digits(
                        base_qs.filter(date__range=(today, today + timedelta(days=6)))
                        .exclude(order__status="cancelled")
                        .count()
                    ),
                    "active_team_label": to_persian_digits(1),
                    "active_services_label": to_persian_digits(
                        Services.objects.filter(
                            stylists=stylist, services_of_salon=salon, is_active=True
                        )
                        .distinct()
                        .count()
                    ),
                    "unpaid_count_label": to_persian_digits(
                        base_qs.filter(order__is_paid=False)
                        .exclude(order__status="cancelled")
                        .count()
                    ),
                    "sales_7d_label": _currency(
                        base_qs.filter(
                            date__range=(today - timedelta(days=6), today),
                            order__is_finally=True,
                        ).aggregate(total=Sum("price"))["total"]
                        or 0
                    ),
                },
                "sections": {
                    "sales_activity_title": "مرور سریع وضعیت کاری",
                    "sales_activity_subtitle": "خلاصه آماده‌به‌کار بودن، شیفت و وضعیت‌های نزدیک شما",
                    "sales_activity_action_label": "برنامه من",
                    "sales_activity_action_url": _safe_reverse(
                        "dashboards:stylist_schedule"
                    ),
                    "upcoming_title": "نوبت‌های پیش‌روی من",
                    "upcoming_subtitle": "فقط رزروهای مربوط به شما در همین بخش دیده می‌شود",
                    "upcoming_action_label": "نوبت‌های من",
                    "upcoming_action_url": _safe_reverse(
                        "dashboards:stylist_appointments"
                    ),
                    "today_title": "نوبت‌های امروز من",
                    "today_subtitle": "نمای سریع برای شروع شیفت امروز",
                    "today_action_label": "نوبت‌های من",
                    "today_action_url": _safe_reverse(
                        "dashboards:stylist_appointments"
                    ),
                    "popular_title": "خدمات فعال من",
                    "popular_subtitle": "خدماتی که در مجموعه روی پروفایل شما فعال هستند",
                    "top_title": "خلاصه فعالیت شخصی",
                    "top_subtitle": "مرور سریع وضعیت نزدیک‌ترین شیفت، مرخصی و پیگیری‌های شخصی شما",
                },
            }
        }

    readiness = build_salon_readiness_checklist(salon)
    setup_priority = _build_dashboard_setup_priority(readiness)

    base_qs = OrderDetail.objects.filter(salon=salon).select_related("order")
    readiness = build_salon_readiness_checklist(salon)
    manager_home = _build_manager_home_payload(salon, base_qs, today, readiness)
    return {
        "dashboard_home": {
            "has_salon": True,
            "mode": manager_home["mode"],
            "manager": manager_home,
            "readiness": readiness,
            "setup_priority": manager_home.get("setup_priority"),
            "today": manager_home["daily"]["today"],
            "primary_calendar_url": manager_home["daily"]["calendar_url"],
            "salon_profile_url": _safe_reverse("dashboards:salon_profile"),
        }
    }
