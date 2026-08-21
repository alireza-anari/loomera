from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from apps.orders.models import AppointmentNotification, Order, OrderDetail

try:
    from apps.notifications.models import NotificationRecipient
except Exception:
    NotificationRecipient = None
from apps.orders.lifecycle import determine_current_stage
from apps.payments.models import Payment, SalonWalletWithdrawalRequest
from apps.salons.models import (
    CustomerNote,
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services
from apps.accounts.models import Stylist
from apps.stylists.models import JobDetails, StylistSchedule, StylistTimeOff

from .jalali_utils import (
    format_jalali_with_weekday,
    format_time_fa,
    jalali_weekday_name,
    to_persian_digits,
)

ONBOARDING_REDIRECT_URL_NAMES = {
    "dashboards:salon_profile",
    "dashboards:team_managment",
    "dashboards:team_member",
    "dashboards:service_menu",
    "dashboards:online_booking",
    "dashboards:catalog",
    "dashboards:products",
    "dashboards:stocktakes",
    "dashboards:salons_customers_page",
}

WEEKDAY_TO_OPENING_DAY = {
    5: 1,  # Saturday
    6: 2,  # Sunday
    0: 3,  # Monday
    1: 4,  # Tuesday
    2: 5,  # Wednesday
    3: 6,  # Thursday
    4: 7,  # Friday
}


COMING_SOON_SIDEBAR_KEYS = {"membership", "catalog", "products", "stocktakes"}


SECTION_DEFINITIONS = [
    {
        "key": "daily",
        "label": "روزانه",
        "items": ["overview", "appointments", "clients"],
    },
    {
        "key": "management",
        "label": "مدیریت سالن",
        "items": ["services", "team", "schedule", "online_booking"],
    },
    {
        "key": "growth",
        "label": "رشد",
        "items": ["content", "membership", "catalog"],
    },
    {
        "key": "business",
        "label": "کسب‌وکار",
        "items": ["reports", "finance", "products", "stocktakes"],
    },
    {
        "key": "settings",
        "label": "تنظیمات",
        "items": ["profile", "settings"],
    },
]


PATH_KEYWORDS = [
    ("/calendar/", "appointments"),
    ("/appointment/", "appointments"),
    ("/reports/", "reports"),
    ("/salonscustomers/", "clients"),
    ("/team_member/", "team"),
    ("/team_managment/", "team"),
    ("/scheduled_shifts/", "schedule"),
    ("/schedule/", "schedule"),
    ("/add_stylist/", "team"),
    ("/edit_stylist/", "team"),
    ("/stylist_overview/", "team"),
    ("/service_menu/", "services"),
    ("/add_service/", "services"),
    ("/edit_service/", "services"),
    ("/online_booking/", "online_booking"),
    ("/catalog/", "catalog"),
    ("/content/", "content"),
    ("/stylist/content/", "my_content"),
    ("/membership/", "membership"),
    ("/products/", "products"),
    ("/stocktakes/", "stocktakes"),
    ("/salon_profile/", "profile"),
    ("/settings/finance/", "finance"),
    ("/settings/", "settings"),
    ("/manager_profile/", "settings"),
]


PAGE_META = {
    "overview": {
        "title": "خانه داشبورد",
        "description": "خلاصه وضعیت عملیاتی مجموعه، نوبت‌های امروز و میان‌برهای اصلی محیط کاری.",
        "icon": "fa-solid fa-house",
    },
    "appointments": {
        "title": "تقویم و نوبت‌ها",
        "description": "مرکز عملیات روزانه مجموعه برای مدیریت رزروها، برنامه تیم و پیگیری وضعیت هر نوبت.",
        "icon": "fa-regular fa-calendar-check",
    },
    "reports": {
        "title": "گزارش‌ها و خلاصه عملکرد",
        "description": "مرور فروش، عملکرد خدمات و وضعیت ظرفیت مجموعه در بازه‌های زمانی مختلف.",
        "icon": "fa-solid fa-chart-simple",
    },
    "clients": {
        "title": "مشتریان",
        "description": "دفتر مشتریان مجموعه با دسترسی سریع به سابقه رزرو، ارزش مشتری و اطلاعات تماس.",
        "icon": "fa-regular fa-address-book",
    },
    "team": {
        "title": "تیم",
        "description": "اعضای تیم، وضعیت همکاری و دسترسی سریع به مدیریت هر متخصص.",
        "icon": "fa-solid fa-users",
    },
    "schedule": {
        "title": "برنامه کاری",
        "description": "شیفت‌ها، حضور و مرخصی تیم را در یک نمای عملیاتی مدیریت کن.",
        "icon": "fa-regular fa-clock",
    },
    "services": {
        "title": "خدمات و منو",
        "description": "ساختار منوی خدمات، قیمت‌ها، مدت‌زمان و دسترسی سریع به ویرایش هر خدمت.",
        "icon": "fa-solid fa-sparkles",
    },
    "online_booking": {
        "title": "رزرو آنلاین",
        "description": "تنظیمات حضور عمومی مجموعه، رزرو آنلاین و مسیرهای رشد و جذب مشتری.",
        "icon": "fa-solid fa-link",
    },
    "catalog": {
        "title": "کاتالوگ",
        "description": "فضای آماده برای توسعه کاتالوگ خدمات و محصولات در ساختار جدید داشبورد.",
        "icon": "fa-regular fa-rectangle-list",
    },
    "membership": {
        "title": "عضویت و پلن‌ها",
        "description": "مدیریت پلن، دسترسی‌ها و ظرفیت‌های محصولی مجموعه در همین ساختار جدید.",
        "icon": "fa-solid fa-gem",
    },
    "content": {
        "title": "محتوای مجموعه",
        "description": "ساخت مقاله، استوری و بررسی محتوای پیشنهادی اعضای تیم برای مجله و صفحه مجموعه.",
        "icon": "fa-regular fa-newspaper",
    },
    "my_content": {
        "title": "محتوای من",
        "description": "ارسال مقاله، استوری یا نمونه‌کار پیشنهادی برای بررسی مدیر مجموعه.",
        "icon": "fa-regular fa-newspaper",
    },
    "profile": {
        "title": "پروفایل مجموعه",
        "description": "اطلاعاتی که مشتری در صفحه عمومی مجموعه می‌بیند؛ از تماس و موقعیت تا تصاویر و معرفی.",
        "icon": "fa-solid fa-shop",
    },
    "products": {
        "title": "محصولات",
        "description": "",
        "icon": "fa-solid fa-boxes-stacked",
    },
    "stocktakes": {
        "title": "موجودی‌گیری",
        "description": "صفحهٔ عملیاتی موجودی، شمارش و مغایرت انبار ",
        "icon": "fa-solid fa-clipboard-list",
    },
    "settings": {
        "title": "تنظیمات",
        "description": "پروفایل و رزرو آنلاین مجموعه، حساب مدیر، امنیت و اعلان‌ها.",
        "icon": "fa-solid fa-gear",
    },
    "finance": {
        "title": "مالی",
        "description": "موجودی مجموعه، سود و هزینه، پرداخت اعضای تیم و تخفیف‌ها.",
        "icon": "fa-solid fa-coins",
    },
}


NAV_DEFINITIONS = [
    {
        "key": "overview",
        "label": "خانه",
        "icon": "fa-solid fa-house",
        "url_name": "dashboards:salon_manager_dashboard",
    },
    {
        "key": "appointments",
        "label": "تقویم",
        "icon": "fa-regular fa-calendar-check",
        "url_name": "dashboards:appointment_calendar",
        "needs_salon": True,
    },
    {
        "key": "clients",
        "label": "مشتریان",
        "icon": "fa-regular fa-address-book",
        "url_name": "dashboards:salons_customers_page",
    },
    {
        "key": "team",
        "label": "تیم",
        "icon": "fa-solid fa-user-group",
        "url_name": "dashboards:team_member",
    },
    {
        "key": "services",
        "label": "خدمات",
        "icon": "fa-solid fa-sparkles",
        "url_name": "dashboards:service_menu",
    },
    {
        "key": "reports",
        "label": "گزارش‌ها",
        "icon": "fa-solid fa-chart-simple",
        "url_name": "dashboards:reports_dashboard",
        "needs_salon": True,
    },
    {
        "key": "content",
        "label": "محتوا",
        "icon": "fa-regular fa-newspaper",
        "url_name": "dashboards:content_hub",
    },
]


SIDEBAR_DEFINITIONS = {
    "overview": {
        "label": "خانه",
        "caption": "نمای کلی و مرور سریع",
        "icon": "fa-solid fa-house",
        "url_name": "dashboards:salon_manager_dashboard",
    },
    "appointments": {
        "label": "تقویم و نوبت‌ها",
        "caption": "برنامه روزانه، لیست نوبت‌ها و عملیات سریع",
        "icon": "fa-regular fa-calendar-check",
        "url_name": "dashboards:appointment_calendar",
        "needs_salon": True,
    },
    "reports": {
        "label": "گزارش‌ها",
        "caption": "فروش، عملکرد و خلاصه‌های عملیاتی",
        "icon": "fa-solid fa-chart-simple",
        "url_name": "dashboards:reports_dashboard",
        "needs_salon": True,
    },
    "clients": {
        "label": "مشتریان",
        "caption": "دفتر مشتریان و پیگیری ارزش مشتری",
        "icon": "fa-regular fa-address-book",
        "url_name": "dashboards:salons_customers_page",
    },
    "team": {
        "label": "تیم",
        "caption": "اعضای تیم، خدمات و وضعیت همکاری",
        "icon": "fa-solid fa-user-group",
        "url_name": "dashboards:team_member",
    },
    "schedule": {
        "label": "برنامه کاری",
        "caption": "شیفت‌ها، حضور و مرخصی تیم",
        "icon": "fa-regular fa-clock",
        "url_name": "dashboards:scheduled_shifts",
    },
    "services": {
        "label": "خدمات",
        "caption": "منوی خدمات، قیمت و ساختار ارائه",
        "icon": "fa-solid fa-sparkles",
        "url_name": "dashboards:service_menu",
    },
    "online_booking": {
        "label": "صفحه سالن و رزرو آنلاین",
        "caption": "صفحه عمومی و لینک‌های رزرو",
        "icon": "fa-solid fa-link",
        "url_name": "dashboards:online_booking",
    },
    "catalog": {
        "label": "کاتالوگ",
        "caption": "کاتالوگ خدمات و محصولات",
        "icon": "fa-regular fa-rectangle-list",
        "url_name": "dashboards:catalog",
    },
    "content": {
        "label": "محتوای مجموعه",
        "caption": "مقاله‌ها، استوری‌ها و محتوای پیشنهادی تیم",
        "icon": "fa-regular fa-newspaper",
        "url_name": "dashboards:content_hub",
    },
    "membership": {
        "label": "عضویت",
        "caption": "پلن‌ها، سطح دسترسی و ارتقا",
        "icon": "fa-solid fa-gem",
        "url_name": "dashboards:membership",
    },
    "profile": {
        "label": "پروفایل مجموعه",
        "caption": "اطلاعات، موقعیت، ساعات کاری و صفحه عمومی",
        "icon": "fa-solid fa-shop",
        "url_name": "dashboards:salon_profile",
    },
    "products": {
        "label": "محصولات",
        "caption": "فروش کالا و فهرست محصولات",
        "icon": "fa-solid fa-boxes-stacked",
        "url_name": "dashboards:products",
    },
    "stocktakes": {
        "label": "موجودی‌گیری",
        "caption": "شمارش کالا و اختلاف انبار",
        "icon": "fa-solid fa-clipboard-list",
        "url_name": "dashboards:stocktakes",
    },
    "settings": {
        "label": "تنظیمات",
        "caption": "پروفایل، حساب، امنیت و اعلان‌ها",
        "icon": "fa-solid fa-gear",
        "url_name": "dashboards:workspace_settings",
    },
    "finance": {
        "label": "مالی",
        "caption": "موجودی، درآمد، پرداخت تیم و تخفیف‌ها",
        "icon": "fa-solid fa-coins",
        "url_name": "dashboards:finance_hub",
    },
}


STYLIST_CREATE_ACTIONS = [
    {
        "label": "افزودن برنامه کاری",
        "icon": "fa-regular fa-clock",
        "url_name": "dashboards:stylist_add_schedule",
        "style": "primary",
    },
    {
        "label": "افزودن مرخصی",
        "icon": "fa-regular fa-calendar-minus",
        "url_name": "dashboards:stylist_add_time_off",
        "style": "secondary",
    },
    {
        "label": "افزودن مشتری",
        "icon": "fa-solid fa-user-plus",
        "url_name": "dashboards:stylist_add_customer",
        "style": "secondary",
    },
    {
        "label": "افزودن نوبت",
        "icon": "fa-regular fa-calendar-plus",
        "url_name": "dashboards:stylist_add_booking",
        "style": "primary",
    },
    {
        "label": "لینک رزرو من",
        "icon": "fa-solid fa-link",
        "url_name": "dashboards:stylist_quick_links",
        "style": "ghost",
    },
]

CREATE_ACTIONS = [
    {
        "label": "افزودن خدمت",
        "icon": "fa-solid fa-sparkles",
        "url_name": "dashboards:add_service",
        "style": "primary",
    },
    {
        "label": "افزودن رزرو",
        "icon": "fa-regular fa-calendar-plus",
        "url_name": "dashboards:add_booking",
        "needs_salon": True,
        "style": "primary",
    },
    {
        "label": "افزودن مشتری",
        "icon": "fa-solid fa-user-plus",
        "url_name": "accounts:add_customer",
        "needs_salon": True,
        "style": "secondary",
    },
    {
        "label": "افزودن عضو تیم",
        "icon": "fa-solid fa-users",
        "url_name": "dashboards:add_stylist",
        "style": "secondary",
    },
    {
        "label": "تقویم نوبت‌ها",
        "icon": "fa-regular fa-calendar-check",
        "url_name": "dashboards:appointment_calendar",
        "needs_salon": True,
        "style": "ghost",
    },
]

MOBILE_NAV_KEYS = ["overview", "appointments"]
MANAGER_MOBILE_MANAGEMENT_KEYS = [
    "services",
    "team",
    "schedule",
    "online_booking",
    "clients",
]

STYLIST_ALLOWED_NAV_KEYS = {
    "overview",
    "my_appointments",
    "my_finance",
    "my_schedule",
    "my_content",
    "my_profile",
    "my_settings",
    "quick_links",
}
STYLIST_LOCKED_NAV_KEYS = {
    "clients",
    "team",
    "services",
    "reports",
    "online_booking",
    "catalog",
    "membership",
    "products",
    "stocktakes",
    "settings",
}
STYLIST_NAV_ITEMS = [
    {
        "key": "overview",
        "label": "خانه",
        "icon": "fa-solid fa-house",
        "url_name": "dashboards:stylist_dashboard",
    },
    {
        "key": "my_appointments",
        "label": "نوبت‌های من",
        "icon": "fa-regular fa-calendar-check",
        "url_name": "dashboards:stylist_appointments",
    },
    {
        "key": "my_finance",
        "label": "درآمد من",
        "icon": "fa-solid fa-wallet",
        "url_name": "dashboards:stylist_finance",
    },
    {
        "key": "my_schedule",
        "label": "برنامه من",
        "icon": "fa-regular fa-clock",
        "url_name": "dashboards:stylist_schedule",
    },
    {
        "key": "my_content",
        "label": "محتوای من",
        "icon": "fa-regular fa-newspaper",
        "url_name": "dashboards:stylist_content",
    },
    {
        "key": "my_profile",
        "label": "پروفایل من",
        "icon": "fa-regular fa-user",
        "url_name": "dashboards:stylist_profile",
    },
    {
        "key": "my_settings",
        "label": "تنظیمات",
        "icon": "fa-solid fa-gear",
        "url_name": "dashboards:stylist_settings",
    },
]
STYLIST_LOCKED_ITEMS = [
    {
        "key": "clients",
        "label": "مشتریان مجموعه",
        "caption": "نمایش کامل این بخش فقط برای مدیر مجموعه فعال است.",
        "icon": "fa-solid fa-users",
    },
    {
        "key": "team",
        "label": "تیم و شیفت‌ها",
        "caption": "مدیریت اعضای تیم و شیفت‌ها در اختیار مدیر مجموعه است.",
        "icon": "fa-solid fa-users",
    },
    {
        "key": "services",
        "label": "خدمات مجموعه",
        "caption": "مدیریت منوی خدمات و قیمت‌گذاری توسط مدیر انجام می‌شود.",
        "icon": "fa-solid fa-sparkles",
    },
    {
        "key": "reports",
        "label": "گزارش‌ها",
        "caption": "گزارش‌های تحلیلی و عملکرد مجموعه فقط برای مدیر باز است.",
        "icon": "fa-solid fa-chart-simple",
    },
    {
        "key": "settings",
        "label": "تنظیمات و مالی",
        "caption": "تنظیمات مجموعه، مالی و گزارش‌های عملیاتی قفل است.",
        "icon": "fa-solid fa-gear",
    },
]
STYLIST_MOBILE_NAV_KEYS = ["overview", "my_appointments", "my_schedule"]


PAGE_ACTION_MAP = {
    "overview": {
        "label": "تقویم امروز",
        "url_name": "dashboards:appointment_calendar",
        "needs_salon": True,
    },
    "appointments": {
        "label": "بازگشت به خانه",
        "url_name": "dashboards:salon_manager_dashboard",
    },
    "clients": {
        "label": "افزودن مشتری",
        "url_name": "accounts:add_customer",
        "needs_salon": True,
    },
    "team": {"label": "افزودن عضو تیم", "url_name": "dashboards:add_stylist"},
    "schedule": {
        "label": "افزودن برنامه کاری",
        "url_name": "dashboards:scheduled_shifts",
    },
    "services": {"label": "افزودن خدمت", "url_name": "dashboards:add_service"},
    "reports": {
        "label": "تقویم مجموعه",
        "url_name": "dashboards:appointment_calendar",
        "needs_salon": True,
    },
    "profile": {"label": "رزرو آنلاین", "url_name": "dashboards:online_booking"},
    "online_booking": {
        "label": "پروفایل مجموعه",
        "url_name": "dashboards:salon_profile",
    },
    "catalog": {"label": "خدمات", "url_name": "dashboards:service_menu"},
    "content": {"label": "مجله لومرا", "url_name": "articles:magazine_home"},
    "membership": {
        "label": "خانه داشبورد",
        "url_name": "dashboards:salon_manager_dashboard",
    },
    "products": {"label": "موجودی‌گیری", "url_name": "dashboards:stocktakes"},
    "stocktakes": {"label": "محصولات", "url_name": "dashboards:products"},
    "settings": {"label": "پروفایل مجموعه", "url_name": "dashboards:salon_profile"},
    "finance": {
        "label": "سود خالص",
        "url_name": "dashboards:finance_profit_report",
    },
}


def _safe_reverse(*names, fallback="#", kwargs=None):
    for name in names:
        if not name:
            continue
        try:
            return reverse(name, kwargs=kwargs)
        except NoReverseMatch:
            continue
    return fallback


def _get_onboarding_resume_url_for_salon(salon):
    if salon is None:
        return _safe_reverse("dashboards:salon_profile_creator_step1")

    explicit_contacts_ok = bool(
        (getattr(salon, "mobile_phone", "") or "").strip()
        and (getattr(salon, "landline_phone", "") or "").strip()
    )
    if not (
        (salon.salon_name or "").strip()
        and (explicit_contacts_ok or salon.phone_number)
    ):
        return _safe_reverse("dashboards:salon_profile_creator_step1")

    if not (
        salon.zone
        and salon.neighborhood_id
        and (salon.address or "").strip()
        and salon.location
    ):
        return _safe_reverse("dashboards:salon_profile_creator_step2")

    if salon.opening_hours.count() < 7:
        return _safe_reverse("dashboards:salon_profile_creator_step3")

    # Beta UX: فقط اطلاعات پایه، موقعیت و ساعات سالن gate ورود به داشبورد هستند.
    # گالری، امکانات، توضیحات و فعال‌سازی عمومی از readiness داخل داشبورد پیگیری می‌شوند.
    return None


def _notification_meta_from_date(date_value, time_value=None):
    if not date_value:
        return ""
    label = format_jalali_with_weekday(date_value)
    if time_value:
        return f"{label} • {format_time_fa(time_value)}"
    return label


def _notification_meta_from_datetime(value):
    if not value:
        return ""
    try:
        local_value = timezone.localtime(value) if timezone.is_aware(value) else value
    except Exception:
        local_value = value

    date_part = local_value.date() if hasattr(local_value, "date") else None
    time_part = local_value.time() if hasattr(local_value, "time") else None
    return _notification_meta_from_date(date_part, time_part)


def _serialize_lifecycle_notification_item(item, fallback_url="#"):
    return {
        "title": item.title,
        "description": item.body[:120] if item.body else item.get_event_type_display(),
        "meta": _notification_meta_from_datetime(item.created_at),
        "icon": {
            "booking_created": "fa-regular fa-calendar-plus",
            "booking_paid": "fa-solid fa-credit-card",
            "stylist_confirmed": "fa-solid fa-circle-check",
            "customer_arrived": "fa-solid fa-person-walking-arrow-right",
            "service_started": "fa-solid fa-scissors",
            "service_completed": "fa-solid fa-check-double",
            "payment_completed": "fa-solid fa-chart-line",
            "review_requested": "fa-regular fa-star",
        }.get(item.event_type, "fa-regular fa-bell"),
        "url": fallback_url,
        "is_unread": not item.is_read,
        "event_type": item.event_type,
    }


def _notification_category_key(item):
    event_type = item.get("event_type") if isinstance(item, dict) else None
    title = (item.get("title") if isinstance(item, dict) else "") or ""
    if event_type in {"booking_paid", "payment_completed", "pay_in_salon_pending"}:
        return "finance"
    if event_type in {"stylist_confirmed"} or "متخصص" in title:
        return "stylist"
    if (
        event_type in {"review_requested", "review_completed"}
        or "مشتری" in title
        or "یادداشت" in title
    ):
        return "customer"
    return "appointments"


def _notification_category_meta(category):
    labels = {
        "all": ("همه", "fa-regular fa-bell"),
        "finance": ("مالی", "fa-solid fa-chart-line"),
        "appointments": ("نوبت‌ها", "fa-regular fa-calendar-days"),
        "customer": ("مشتری", "fa-solid fa-user-group"),
        "stylist": ("متخصص", "fa-solid fa-user-check"),
    }
    label, icon = labels.get(category, ("اعلان", "fa-regular fa-bell"))
    return {"key": category, "label": label, "icon": icon}


def _attach_notification_categories(items):
    for item in items:
        category = _notification_category_key(item)
        meta = _notification_category_meta(category)
        item["category"] = category
        item["category_label"] = meta["label"]
        item["category_icon"] = meta["icon"]
    return items


def _build_notification_tabs(items):
    tabs = []
    all_meta = _notification_category_meta("all")
    tabs.append(
        {
            **all_meta,
            "count": len(items),
            "unread_count": sum(1 for item in items if item.get("is_unread")),
        }
    )
    for category in ["finance", "appointments", "customer", "stylist"]:
        filtered = [item for item in items if item.get("category") == category]
        meta = _notification_category_meta(category)
        tabs.append(
            {
                **meta,
                "count": len(filtered),
                "unread_count": sum(1 for item in filtered if item.get("is_unread")),
            }
        )
    return tabs


def get_primary_detail_id(order_id):
    try:
        detail = (
            OrderDetail.objects.filter(order_id=order_id)
            .order_by("date", "time", "id")
            .only("id")
            .first()
        )
        return detail.id if detail else 0
    except Exception:
        return 0


def _notification_action_url_for_recipient(recipient):
    note = recipient.notification
    if note.action_url:
        return note.action_url

    related = getattr(note, "related_object", None)
    audience_role = str(getattr(recipient, "audience_role", "") or "")

    if isinstance(related, OrderDetail):
        if audience_role == "stylist":
            return _safe_reverse(
                "dashboards:stylist_appointment_detail",
                kwargs={"appointment_id": related.id},
                fallback=_safe_reverse("notifications:center"),
            )
        if audience_role == "manager":
            return _safe_reverse(
                "dashboards:appointment_detail",
                kwargs={
                    "salon_id": related.salon_id,
                    "appointment_id": related.id,
                },
                fallback=_safe_reverse("notifications:center"),
            )

    if isinstance(related, Order):
        detail_id = get_primary_detail_id(related.id)
        if detail_id:
            if audience_role == "stylist":
                return _safe_reverse(
                    "dashboards:stylist_appointment_detail",
                    kwargs={"appointment_id": detail_id},
                    fallback=_safe_reverse("notifications:center"),
                )
            if audience_role == "manager" and related.salon_id:
                return _safe_reverse(
                    "dashboards:appointment_detail",
                    kwargs={
                        "salon_id": related.salon_id,
                        "appointment_id": detail_id,
                    },
                    fallback=_safe_reverse("notifications:center"),
                )

    return _safe_reverse("notifications:center")


def _serialize_unified_notification_item(recipient):
    note = recipient.notification
    return {
        "title": note.title,
        "description": note.body,
        "meta": _notification_meta_from_datetime(note.created_at),
        "icon": note.icon or "fa-regular fa-bell",
        "url": _notification_action_url_for_recipient(recipient),
        "read_url": _safe_reverse(
            "notifications:read",
            kwargs={"recipient_id": recipient.id},
            fallback="",
        ),
        "recipient_id": recipient.id,
        "is_persistent": True,
        "is_unread": not recipient.is_read,
        "event_type": note.event_type,
    }


def _dedupe_notification_items(items, *, limit=8):
    deduped = []
    seen = set()
    for item in items:
        key = (
            item.get("event_type") or "",
            item.get("url") or "",
            item.get("title") or "",
            item.get("description") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _normalize_dashboard_notification_read_state(items):
    """Only persisted recipient rows can be unread.

    Contextual fallback rows (recent orders/notes/time-off) are useful for the
    notification center, but they have no durable read state and therefore must
    never inflate unread badges/counts.
    """
    for item in items:
        if not item.get("read_url"):
            item["is_unread"] = False
            item["is_persistent"] = False
    return items


def _build_dashboard_notifications(salon, *, role="manager", user=None, stylist=None):
    if salon is None:
        return {
            "items": [],
            "dropdown_items": [],
            "unread_count": 0,
            "tabs": _build_notification_tabs([]),
            "dropdown_tabs": _build_notification_tabs([]),
            "panel_url": "#",
            "title": "اعلان‌های محیط کاری",
            "subtitle": "در این بخش اعلان فعالی ثبت نشده است.",
            "panel_label": "رفتن به صفحه مرتبط",
        }

    if role == "stylist" and stylist is not None:
        items = []
        persistent_unread_count = 0
        if NotificationRecipient is not None and user is not None:
            recipient_qs = (
                NotificationRecipient.objects.filter(
                    user=user,
                    audience_role="stylist",
                    is_archived=False,
                )
                .select_related(
                    "notification",
                    "notification__related_content_type",
                )
                .order_by("-created_at")
            )
            persistent_unread_count = recipient_qs.filter(is_read=False).count()
            for recipient in recipient_qs[:12]:
                items.append(_serialize_unified_notification_item(recipient))
        today = timezone.localdate()
        dynamic_notifications = AppointmentNotification.objects.filter(
            salon=salon,
            audience_role="stylist",
            stylist=stylist,
        ).order_by("-created_at")[:4]
        for note in dynamic_notifications:
            items.append(
                _serialize_lifecycle_notification_item(
                    note,
                    fallback_url=_safe_reverse(
                        "dashboards:stylist_appointment_detail",
                        kwargs={
                            "appointment_id": note.order_detail_id
                            or get_primary_detail_id(note.order_id)
                        },
                    ),
                )
            )
        recent_details = (
            OrderDetail.objects.filter(salon=salon, stylist=stylist)
            .select_related("order__customer__user", "service", "order")
            .order_by("-date", "-time", "-id")[:8]
        )
        for detail in recent_details:
            order = detail.order
            if order.status in ["cancelled", "payment_failed"]:
                title = "نوبت لغوشده"
                icon = "fa-solid fa-ban"
            elif detail.date == today:
                title = "نوبت امروز شما"
                icon = "fa-regular fa-calendar-check"
            else:
                title = "نوبت پیش‌رو"
                icon = "fa-regular fa-clock"
            items.append(
                {
                    "title": title,
                    "description": f"{detail.order.customer.get_fullName()} • {detail.service.service_name if detail.service else 'خدمت'}",
                    "meta": _notification_meta_from_date(detail.date, detail.time),
                    "icon": icon,
                    "url": _safe_reverse(
                        "dashboards:stylist_appointment_detail",
                        kwargs={"appointment_id": detail.id},
                    ),
                    "is_unread": bool(detail.date and detail.date >= today),
                    "event_type": (
                        "service_started"
                        if order.service_started_at
                        else "booking_created"
                    ),
                }
            )
        for time_off in StylistTimeOff.objects.filter(
            stylist=stylist, date__gte=today
        ).order_by("date")[:2]:
            items.append(
                {
                    "title": "مرخصی ثبت‌شده",
                    "description": (time_off.reason or "مرخصی/عدم حضور")[:80],
                    "meta": _notification_meta_from_date(
                        time_off.date, time_off.start_time
                    ),
                    "icon": "fa-regular fa-calendar-xmark",
                    "url": _safe_reverse("dashboards:stylist_schedule"),
                    "is_unread": bool(
                        time_off.date and (time_off.date - today).days <= 7
                    ),
                    "event_type": "stylist_confirmed",
                }
            )
        items = _attach_notification_categories(
            _normalize_dashboard_notification_read_state(
                _dedupe_notification_items(items, limit=12)
            )
        )
        dropdown_items = items[:6]
        return {
            "items": items,
            "dropdown_items": dropdown_items,
            "tabs": _build_notification_tabs(items),
            "dropdown_tabs": _build_notification_tabs(dropdown_items),
            "unread_count": persistent_unread_count,
            "panel_url": _safe_reverse("dashboards:stylist_notifications"),
            "title": "اعلان‌های کاری من",
            "subtitle": "نوبت‌ها، مالی و تغییرات مرتبط با خودت را یک‌جا پیگیری کن.",
            "panel_label": "باز کردن مرکز اعلان‌ها",
        }

    items = []
    persistent_unread_count = 0
    if NotificationRecipient is not None and user is not None:
        recipient_qs = (
            NotificationRecipient.objects.filter(
                user=user,
                audience_role="manager",
                is_archived=False,
            )
            .select_related(
                "notification",
                "notification__related_content_type",
            )
            .order_by("-created_at")
        )
        persistent_unread_count = recipient_qs.filter(is_read=False).count()
        for recipient in recipient_qs[:12]:
            items.append(_serialize_unified_notification_item(recipient))
    seen_orders = set()
    today = timezone.localdate()

    if user is not None:
        dynamic_notifications = AppointmentNotification.objects.filter(
            salon=salon,
            audience_role="manager",
            target_user=user,
        ).order_by("-created_at")[:4]
        for note in dynamic_notifications:
            items.append(
                _serialize_lifecycle_notification_item(
                    note,
                    fallback_url=_safe_reverse(
                        "dashboards:appointment_detail",
                        kwargs={
                            "salon_id": salon.id,
                            "appointment_id": note.order_detail_id
                            or get_primary_detail_id(note.order_id),
                        },
                    ),
                )
            )

    recent_order_details = (
        OrderDetail.objects.filter(salon=salon)
        .select_related("order__customer__user", "service", "stylist__user")
        .order_by("-order__update_date", "-order__register_date", "-id")[:24]
    )

    for detail in recent_order_details:
        order = detail.order
        if order.pk in seen_orders:
            continue
        seen_orders.add(order.pk)

        title = None
        icon = "fa-regular fa-bell"
        unread = False

        if order.status == "pending":
            title = "رزرو جدید در انتظار تایید"
            icon = "fa-regular fa-calendar-plus"
            unread = True
        elif order.status == "cancelled":
            title = "رزرو لغو شد"
            icon = "fa-solid fa-ban"
            unread = bool(order.update_date and (today - order.update_date).days <= 1)
        elif order.is_paid or order.status in ["paid", "completed"]:
            title = "پرداخت رزرو ثبت شد"
            icon = "fa-solid fa-credit-card"
            unread = bool(order.update_date and (today - order.update_date).days <= 1)
        elif order.status == "confirmed":
            title = "رزرو تایید شد"
            icon = "fa-solid fa-circle-check"

        if not title:
            continue

        items.append(
            {
                "title": title,
                "description": f"{order.customer.get_fullName()} • {detail.service.service_name if detail.service else 'خدمت'}",
                "meta": _notification_meta_from_date(
                    order.update_date or order.register_date, detail.time
                ),
                "icon": icon,
                "url": _safe_reverse(
                    "dashboards:appointment_detail",
                    kwargs={"salon_id": salon.id, "appointment_id": detail.id},
                ),
                "is_unread": unread,
                "event_type": (
                    "payment_completed"
                    if (order.is_paid or order.status in ["paid", "completed"])
                    else "booking_created"
                ),
            }
        )

        if len(items) >= 6:
            break

    recent_notes = (
        CustomerNote.objects.filter(salon=salon)
        .select_related("customer__user", "created_by")
        .order_by("-created_at")[:2]
    )

    for note in recent_notes:
        if len(items) >= 8:
            break

        items.append(
            {
                "title": "یادداشت جدید مشتری",
                "description": f"{note.customer.get_fullName()} • {note.note[:60]}",
                "meta": _notification_meta_from_datetime(note.created_at),
                "icon": "fa-regular fa-note-sticky",
                "url": _safe_reverse(
                    "dashboards:customer_detail",
                    kwargs={"customer_id": note.customer_id},
                ),
                "is_unread": bool(
                    note.created_at and (timezone.now() - note.created_at).days < 1
                ),
                "event_type": "review_requested",
            }
        )

    items = _attach_notification_categories(
        _normalize_dashboard_notification_read_state(
            _dedupe_notification_items(items, limit=12)
        )
    )
    dropdown_items = items[:6]

    return {
        "items": items,
        "dropdown_items": dropdown_items,
        "tabs": _build_notification_tabs(items),
        "dropdown_tabs": _build_notification_tabs(dropdown_items),
        "unread_count": persistent_unread_count,
        "panel_url": _safe_reverse("dashboards:notifications_center"),
        "title": "اعلان‌های محیط کاری",
        "subtitle": "مالی، رزروها، مشتری و متخصص را در یک سطح کاری دسته‌بندی‌شده ببین.",
        "panel_label": "باز کردن مرکز اعلان‌ها",
    }


def build_dashboard_create_actions(salon=None, *, role="manager"):
    actions = []
    if role == "stylist":
        for action in STYLIST_CREATE_ACTIONS:
            url = _safe_reverse(action.get("url_name"), fallback="#")
            actions.append(
                {
                    "label": action["label"],
                    "icon": action["icon"],
                    "url": url,
                    "style": action["style"],
                    "is_available": url != "#",
                    "is_locked": url == "#",
                    "lock_reason": "در دسترس نیست" if url == "#" else "",
                }
            )
        return actions

    for action in CREATE_ACTIONS:
        url, is_available = _resolve_url(action, salon)
        actions.append(
            {
                "label": action["label"],
                "icon": action["icon"],
                "url": url,
                "style": action["style"],
                "is_available": is_available,
                "is_locked": not is_available,
                "lock_reason": "در دسترس نیست" if not is_available else "",
            }
        )
    return actions


def _format_time(value):
    if not value:
        return None
    return format_time_fa(value)


def get_dashboard_role(user):
    if not getattr(user, "is_authenticated", False):
        return "guest"
    if hasattr(user, "salon_manager_profile"):
        return "manager"
    if hasattr(user, "stylist"):
        return "stylist"
    if hasattr(user, "customer_profile"):
        return "customer"
    return "guest"


def get_dashboard_stylist(user):
    return (
        getattr(user, "stylist", None)
        if getattr(user, "is_authenticated", False)
        else None
    )


def _get_stylist_dashboard_salon(user):
    stylist = get_dashboard_stylist(user)
    if stylist is None:
        return None

    today = timezone.localdate()

    active_job = (
        JobDetails.objects.filter(stylist=stylist)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .select_related("salon", "salon__salon_manager__user")
        .order_by("-start_date", "-pk")
        .first()
    )

    if active_job is None:
        active_job = (
            JobDetails.objects.filter(stylist=stylist)
            .select_related("salon", "salon__salon_manager__user")
            .order_by("-start_date", "-pk")
            .first()
        )

    if active_job and active_job.salon_id:
        return active_job.salon

    return (
        Salon.objects.select_related("salon_manager__user")
        .prefetch_related("opening_hours", "stylists")
        .filter(stylists=stylist)
        .order_by("id")
        .first()
    )


def get_dashboard_salon(user):
    if not getattr(user, "is_authenticated", False):
        return None

    role = get_dashboard_role(user)
    if role == "manager":
        return (
            Salon.objects.select_related("salon_manager__user")
            .prefetch_related("opening_hours", "stylists")
            .filter(salon_manager__user=user)
            .first()
        )
    if role == "stylist":
        return _get_stylist_dashboard_salon(user)
    return None


def get_today_hours_label(salon):
    if salon is None:
        return "ساعت کاری ثبت نشده"

    opening_hours = list(salon.opening_hours.all())
    if not opening_hours:
        return "ساعت کاری ثبت نشده"

    today_opening_day = WEEKDAY_TO_OPENING_DAY[timezone.localdate().weekday()]
    today_hours = next(
        (item for item in opening_hours if item.day_of_week == today_opening_day),
        None,
    )

    if not today_hours:
        return "ساعت کاری امروز ثبت نشده"

    today_weekday = jalali_weekday_name(timezone.localdate())

    if today_hours.is_closed:
        return f"امروز ({today_weekday}) تعطیل است"

    open_time = _format_time(today_hours.open_time)
    close_time = _format_time(today_hours.close_time)
    if open_time and close_time:
        return f"امروز ({today_weekday}) {open_time} تا {close_time}"

    return "ساعت کاری امروز کامل نشده است"


def _build_manager_shell_snapshot(
    salon,
    *,
    today=None,
):
    """Load shared manager dashboard counters in two fixed queries.

    These counters are reused by the header, page metadata and shell metric
    cards. Keeping them in one plain dictionary prevents repeated queries on
    every dashboard page.
    """

    today = today or timezone.localdate()
    upcoming_end = today + timedelta(days=6)

    appointment_metrics = OrderDetail.objects.filter(
        salon=salon,
    ).aggregate(
        pending_approvals=Count(
            "id",
            filter=Q(
                order__status="pending",
            ),
        ),
        today_count=Count(
            "id",
            filter=(Q(date=today) & ~Q(order__status="cancelled")),
        ),
        upcoming_count=Count(
            "id",
            filter=(
                Q(
                    date__range=(
                        today,
                        upcoming_end,
                    )
                )
                & ~Q(order__status="cancelled")
            ),
        ),
        unpaid_count=Count(
            "id",
            filter=(Q(order__is_paid=False) & ~Q(order__status="cancelled")),
        ),
    )

    salon_metrics = Salon.objects.filter(
        pk=salon.pk,
    ).aggregate(
        active_services_count=Count(
            "services",
            filter=Q(
                services__is_active=True,
            ),
            distinct=True,
        ),
        active_team_count=Count(
            "stylists",
            filter=Q(
                stylists__is_active=True,
            ),
            distinct=True,
        ),
    )

    return {
        "pending_approvals": int(appointment_metrics["pending_approvals"] or 0),
        "today_count": int(appointment_metrics["today_count"] or 0),
        "upcoming_count": int(appointment_metrics["upcoming_count"] or 0),
        "unpaid_count": int(appointment_metrics["unpaid_count"] or 0),
        "active_services_count": int(salon_metrics["active_services_count"] or 0),
        "active_team_count": int(salon_metrics["active_team_count"] or 0),
    }


def _build_shell_metrics(
    salon,
    *,
    user=None,
    role="manager",
    stylist=None,
    manager_snapshot=None,
):
    if salon is None:
        return []

    if stylist is None and user and hasattr(user, "stylist"):
        stylist = user.stylist

    today = timezone.localdate()

    if role == "stylist" and stylist is not None:
        upcoming_end = today + timedelta(days=6)
        base_qs = OrderDetail.objects.filter(
            salon=salon, stylist=stylist
        ).select_related("order", "service")
        today_count = (
            base_qs.filter(date=today).exclude(order__status="cancelled").count()
        )
        upcoming_count = (
            base_qs.filter(date__range=(today, upcoming_end))
            .exclude(order__status="cancelled")
            .count()
        )
        near_time_off_count = StylistTimeOff.objects.filter(
            stylist=stylist, date__gte=today, date__lte=today + timedelta(days=14)
        ).count()
        active_services_count = (
            Services.objects.filter(
                stylists=stylist,
                services_of_salon=salon,
                is_active=True,
            )
            .distinct()
            .count()
        )
        return [
            {
                "label": "نوبت‌های امروز",
                "value": to_persian_digits(today_count),
                "meta": "برنامه امروز شما",
                "icon": "fa-regular fa-calendar-check",
                "tone": "primary",
            },
            {
                "label": "۷ روز آینده",
                "value": to_persian_digits(upcoming_count),
                "meta": "نوبت‌های پیش‌روی شما",
                "icon": "fa-regular fa-clock",
                "tone": "success",
            },
            {
                "label": "خدمات فعال",
                "value": to_persian_digits(active_services_count),
                "meta": "خدمات قابل ارائه شما",
                "icon": "fa-solid fa-sparkles",
                "tone": "neutral",
            },
            {
                "label": "مرخصی‌های نزدیک",
                "value": to_persian_digits(near_time_off_count),
                "meta": "۱۴ روز آینده",
                "icon": "fa-regular fa-calendar-xmark",
                "tone": "warning",
            },
        ]

    if manager_snapshot is None:
        manager_snapshot = _build_manager_shell_snapshot(
            salon,
            today=today,
        )

    today_count = manager_snapshot["today_count"]
    upcoming_count = manager_snapshot["upcoming_count"]
    unpaid_count = manager_snapshot["unpaid_count"]
    active_services_count = manager_snapshot["active_services_count"]
    return [
        {
            "label": "نوبت‌های امروز",
            "value": to_persian_digits(today_count),
            "meta": "رزروهای فعال امروز",
            "icon": "fa-regular fa-calendar-check",
            "tone": "primary",
        },
        {
            "label": "۷ روز آینده",
            "value": to_persian_digits(upcoming_count),
            "meta": "برای برنامه ریزی تیم",
            "icon": "fa-regular fa-clock",
            "tone": "success",
        },
        {
            "label": "پرداخت‌نشده",
            "value": to_persian_digits(unpaid_count),
            "meta": "نیازمند پیگیری مالی",
            "icon": "fa-solid fa-chart-simple",
            "tone": "warning",
        },
        {
            "label": "خدمات فعال",
            "value": to_persian_digits(active_services_count),
            "meta": "در منوی خدمات مجموعه",
            "icon": "fa-solid fa-sparkles",
            "tone": "neutral",
        },
    ]


def _resolve_url(definition, salon):
    onboarding_url = _get_onboarding_resume_url_for_salon(salon)

    if onboarding_url:
        return onboarding_url, True

    kwargs = {"salon_id": salon.id} if definition.get("needs_salon") and salon else None
    if definition.get("needs_salon") and salon is None:
        return "#", False

    url = _safe_reverse(definition.get("url_name"), fallback="#", kwargs=kwargs)
    return url, url != "#"


def _infer_sidebar_active(request_path="", explicit_key=None):
    if explicit_key and explicit_key != "overview":
        return explicit_key

    normalized = (request_path or "").lower()
    if normalized.rstrip("/") in {"/dashboards", "/dashboards/home"}:
        return "overview"

    for keyword, key in PATH_KEYWORDS:
        if keyword in normalized:
            return key
    return explicit_key or "overview"


def _build_primary_action(active_key, salon, *, role="manager"):
    if role == "stylist":
        stylist_actions = {
            "overview": {
                "label": "نوبت‌های من",
                "url": _safe_reverse("dashboards:stylist_appointments"),
            },
            "my_appointments": {
                "label": "برنامه من",
                "url": _safe_reverse("dashboards:stylist_schedule"),
            },
            "my_schedule": {
                "label": "ثبت مرخصی",
                "url": _safe_reverse("dashboards:stylist_add_time_off"),
            },
            "my_profile": {
                "label": "ویرایش پروفایل",
                "url": _safe_reverse("dashboards:stylist_profile"),
            },
        }
        return stylist_actions.get(active_key)

    config = PAGE_ACTION_MAP.get(active_key)
    if not config:
        return None
    url, is_available = _resolve_url(config, salon)
    if not is_available:
        return None
    return {"label": config["label"], "url": url}


def _build_page_meta(
    active_key,
    salon,
    *,
    role="manager",
    stylist=None,
    manager_snapshot=None,
):
    if role == "stylist":
        stylist_meta = {
            "overview": {
                "title": "خانه کاری من",
                "description": "مرور سریع نوبت‌ها، برنامه کاری و دسترسی‌های شخصی متخصص.",
                "icon": "fa-solid fa-house",
            },
            "my_appointments": {
                "title": "نوبت‌های من",
                "description": "فقط رزروهای مربوط به شما در همین بخش نمایش داده می‌شود.",
                "icon": "fa-regular fa-calendar-check",
            },
            "my_schedule": {
                "title": "برنامه و مرخصی من",
                "description": "شیفت‌ها، برنامه حضور و مرخصی‌های شخصی خودت را اینجا دنبال کن.",
                "icon": "fa-regular fa-clock",
            },
            "my_profile": {
                "title": "پروفایل حرفه‌ای من",
                "description": "اطلاعات پایه، تخصص، تصویر و لینک‌های حرفه‌ای خودت را مدیریت کن.",
                "icon": "fa-regular fa-user",
            },
        }
        base = stylist_meta.get(active_key, stylist_meta["overview"]).copy()
        badges = [
            {"label": get_today_hours_label(salon), "icon": "fa-regular fa-clock"}
        ]
        if stylist is not None:
            badges.append(
                {
                    "label": f"{to_persian_digits(Services.objects.filter(stylists=stylist, is_active=True).distinct().count())} خدمت فعال",
                    "icon": "fa-solid fa-sparkles",
                }
            )
        action = _build_primary_action(active_key, salon, role=role)
        base.update({"badges": badges, "primary_action": action})
        return base

    base = PAGE_META.get(active_key, PAGE_META["overview"]).copy()
    badges = [{"label": get_today_hours_label(salon), "icon": "fa-regular fa-clock"}]
    if salon:
        if manager_snapshot is not None:
            active_team_count = manager_snapshot["active_team_count"]
        else:
            # Backward compatibility for direct callers.
            active_team_count = salon.stylists.filter(
                is_active=True,
            ).count()

        badges.append(
            {
                "label": (f"{to_persian_digits(active_team_count)} " "عضو فعال تیم"),
                "icon": "fa-solid fa-users",
            }
        )
    action = _build_primary_action(active_key, salon, role=role)
    base.update({"badges": badges, "primary_action": action})
    return base


def build_dashboard_nav_items(active_key="overview", salon=None, *, role="manager"):
    items = []
    if role == "stylist":
        for definition in STYLIST_NAV_ITEMS:
            url = _safe_reverse(definition.get("url_name"), fallback="#")
            items.append(
                {
                    "key": definition["key"],
                    "label": definition["label"],
                    "url": url,
                    "icon": definition["icon"],
                    "is_available": url != "#",
                    "is_locked": False,
                    "is_active": definition["key"] == active_key,
                }
            )
        return items

    for definition in NAV_DEFINITIONS:
        url, is_available = _resolve_url(definition, salon)
        items.append(
            {
                "key": definition["key"],
                "label": definition["label"],
                "url": url,
                "icon": definition["icon"],
                "is_available": is_available,
                "is_locked": not is_available,
                "is_active": definition["key"] == active_key,
            }
        )
    return items


def build_dashboard_sidebar_sections(
    active_key="overview", salon=None, *, role="manager"
):
    if role == "stylist":
        personal_items = [
            {
                "key": "overview",
                "label": "خانه کاری من",
                "caption": "مرور سریع نوبت‌ها، وضعیت حضور و خلاصه روزانه.",
                "url": _safe_reverse("dashboards:stylist_dashboard"),
                "icon": "fa-solid fa-house",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "overview",
            },
            {
                "key": "my_appointments",
                "label": "نوبت‌های من",
                "caption": "فقط رزروهای مربوط به شما در این بخش دیده می‌شود.",
                "url": _safe_reverse("dashboards:stylist_appointments"),
                "icon": "fa-regular fa-calendar-check",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "my_appointments",
            },
            {
                "key": "my_finance",
                "label": "درآمد من",
                "caption": "مبلغ قابل دریافت، درآمد خدمات و سابقه پرداخت‌ها.",
                "url": _safe_reverse("dashboards:stylist_finance"),
                "icon": "fa-solid fa-chart-simple",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "my_finance",
            },
            {
                "key": "my_schedule",
                "label": "برنامه و مرخصی من",
                "caption": "مشاهده شیفت‌ها و ثبت مرخصی شخصی.",
                "url": _safe_reverse("dashboards:stylist_schedule"),
                "icon": "fa-regular fa-clock",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "my_schedule",
            },
            {
                "key": "my_content",
                "label": "محتوای من",
                "caption": "ارسال مقاله، استوری یا نمونه‌کار پیشنهادی برای بررسی مدیر مجموعه.",
                "url": _safe_reverse("dashboards:stylist_content"),
                "icon": "fa-regular fa-newspaper",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "my_content",
            },
            {
                "key": "my_profile",
                "label": "پروفایل من",
                "caption": "ویرایش اطلاعات پایه و معرفی حرفه‌ای شما.",
                "url": _safe_reverse("dashboards:stylist_profile"),
                "icon": "fa-regular fa-user",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "my_profile",
            },
            {
                "key": "my_settings",
                "label": "تنظیمات",
                "caption": "حساب، رمز عبور و ارتباطات شخصی خودت را مدیریت کن.",
                "url": _safe_reverse("dashboards:stylist_settings"),
                "icon": "fa-solid fa-gear",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key == "my_settings",
            },
        ]
        sections = [
            {"key": "personal", "label": "فضای کاری من", "items": personal_items},
        ]
        return sections, personal_items

    sections = []
    flat_items = []
    for section in SECTION_DEFINITIONS:
        section_items = []
        for item_key in section["items"]:
            definition = SIDEBAR_DEFINITIONS[item_key]
            url, is_available = _resolve_url(definition, salon)
            is_coming_soon = item_key in COMING_SOON_SIDEBAR_KEYS
            item = {
                "key": item_key,
                "label": definition["label"],
                "caption": definition["caption"],
                "url": url,
                "icon": definition["icon"],
                "is_available": is_available and not is_coming_soon,
                "is_locked": (not is_available) and not is_coming_soon,
                "is_coming_soon": is_coming_soon,
                "lock_reason": "به زودی" if is_coming_soon else "در دسترس نیست",
                "is_active": item_key == active_key and not is_coming_soon,
            }
            section_items.append(item)
            flat_items.append(item)
        sections.append(
            {"key": section["key"], "label": section["label"], "items": section_items}
        )
    return sections, flat_items


def build_dashboard_mobile_nav_items(
    active_key="overview", salon=None, *, role="manager"
):
    items = []
    if role == "stylist":
        mapping = {item["key"]: item for item in STYLIST_NAV_ITEMS}
        for key in STYLIST_MOBILE_NAV_KEYS:
            definition = mapping[key]
            url = _safe_reverse(definition.get("url_name"), fallback="#")
            items.append(
                {
                    "key": key,
                    "kind": "link",
                    "label": definition["label"],
                    "short_label": definition["label"].split(" و ")[0],
                    "icon": definition["icon"],
                    "url": url,
                    "is_available": url != "#",
                    "is_locked": False,
                    "is_active": key == active_key,
                }
            )

        more_definitions = [
            ("my_finance", "درآمد من", "درآمد، موجودی و دریافت وجه"),
            ("quick_links", "لینک رزرو", "لینک اختصاصی، QR و قالب چاپ"),
            ("my_content", "محتوای من", "ارسال و پیگیری محتوای پیشنهادی"),
            ("my_profile", "پروفایل من", "رزومه، نمونه‌کار و همکاری‌ها"),
            ("my_settings", "تنظیمات", "حساب، امنیت و ارتباطات"),
        ]
        panel_items = []
        for key, label, caption in more_definitions:
            if key == "quick_links":
                url = _safe_reverse("dashboards:stylist_quick_links", fallback="#")
                icon = "fa-solid fa-link"
            else:
                definition = mapping[key]
                url = _safe_reverse(definition.get("url_name"), fallback="#")
                icon = definition["icon"]
            panel_items.append(
                {
                    "key": key,
                    "label": label,
                    "short_label": label,
                    "caption": caption,
                    "icon": icon,
                    "url": url,
                    "is_available": url != "#",
                    "is_locked": url == "#",
                    "is_active": active_key == key,
                }
            )
        items.append(
            {
                "key": "management",
                "kind": "panel",
                "label": "بیشتر",
                "short_label": "بیشتر",
                "icon": "fa-solid fa-grid-2",
                "url": "#",
                "is_available": True,
                "is_locked": False,
                "is_active": active_key
                in {
                    "my_finance",
                    "my_content",
                    "my_profile",
                    "my_settings",
                    "quick_links",
                },
                "panel_items": panel_items,
            }
        )
        return items

    for key in MOBILE_NAV_KEYS:
        definition = SIDEBAR_DEFINITIONS[key]
        url, is_available = _resolve_url(definition, salon)
        items.append(
            {
                "key": key,
                "kind": "link",
                "label": definition["label"],
                "short_label": definition["label"].split(" و ")[0],
                "icon": definition["icon"],
                "url": url,
                "is_available": is_available,
                "is_locked": not is_available,
                "is_active": key == active_key,
            }
        )

    management_items = []
    for key in MANAGER_MOBILE_MANAGEMENT_KEYS:
        definition = SIDEBAR_DEFINITIONS[key]
        url, is_available = _resolve_url(definition, salon)
        management_items.append(
            {
                "key": key,
                "label": definition["label"],
                "short_label": definition["label"].split(" و ")[0],
                "caption": definition["caption"],
                "icon": definition["icon"],
                "url": url,
                "is_available": is_available,
                "is_locked": not is_available,
                "is_active": key == active_key,
            }
        )

    items.append(
        {
            "key": "management",
            "kind": "panel",
            "label": "مدیریت",
            "short_label": "مدیریت",
            "icon": "fa-solid fa-grid-2",
            "url": "#",
            "is_available": True,
            "is_locked": False,
            "is_active": active_key in MANAGER_MOBILE_MANAGEMENT_KEYS,
            "panel_items": management_items,
        }
    )
    items.append(
        {
            "key": "reports",
            "kind": "link",
            "label": "گزارش‌ها",
            "short_label": "گزارش‌ها",
            "icon": "fa-solid fa-chart-column",
            "url": (f"/dashboards/reports/salon/{salon.id}/" if salon else "#"),
            "is_available": salon is not None,
            "is_locked": salon is None,
            "is_active": active_key == "reports",
        }
    )
    return items


def build_dashboard_quick_actions(salon=None, *, role="manager"):
    if role == "stylist":
        return [
            {
                "label": "افزودن نوبت",
                "icon": "fa-regular fa-calendar-plus",
                "url": _safe_reverse("dashboards:stylist_add_booking"),
                "style": "primary",
                "is_available": True,
                "is_locked": False,
            },
            {
                "label": "افزودن مشتری",
                "icon": "fa-solid fa-user-plus",
                "url": _safe_reverse("dashboards:stylist_add_customer"),
                "style": "secondary",
                "is_available": True,
                "is_locked": False,
            },
            {
                "label": "برنامه کاری",
                "icon": "fa-regular fa-clock",
                "url": _safe_reverse("dashboards:stylist_add_schedule"),
                "style": "secondary",
                "is_available": True,
                "is_locked": False,
            },
            {
                "label": "لینک رزرو من",
                "icon": "fa-solid fa-link",
                "url": _safe_reverse("dashboards:stylist_quick_links"),
                "style": "ghost",
                "is_available": True,
                "is_locked": False,
            },
        ]

    actions = []
    for action in CREATE_ACTIONS:
        url, is_available = _resolve_url(action, salon)
        actions.append(
            {
                "label": action["label"],
                "icon": action["icon"],
                "url": url,
                "style": action["style"],
                "is_available": is_available,
                "is_locked": not is_available,
            }
        )
    return actions


def build_dashboard_context(
    user,
    *,
    nav_active="home",
    sidebar_active="overview",
    page_title="داشبورد",
    request_path="",
    role=None,
    salon_override=None,
    stylist_override=None,
):
    resolved_role = role or get_dashboard_role(user)
    salon = salon_override if salon_override is not None else get_dashboard_salon(user)
    stylist = (
        stylist_override
        if stylist_override is not None
        else (get_dashboard_stylist(user) if resolved_role == "stylist" else None)
    )
    manager_snapshot = None
    if salon is not None and resolved_role != "stylist":
        manager_snapshot = _build_manager_shell_snapshot(salon)

    stylist_active_memberships = []
    if resolved_role == "stylist" and stylist is not None:
        stylist_active_memberships = list(
            SalonMembership.objects.select_related("salon")
            .filter(
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
                salon__is_active=True,
            )
            .order_by("salon__salon_name", "id")
        )

    salon_manager = getattr(salon, "salon_manager", None) if salon else None
    active_key = _infer_sidebar_active(
        request_path=request_path,
        explicit_key=sidebar_active,
    )

    if resolved_role == "stylist" and active_key == "overview":
        active_key = "overview"

    notification_count = 0
    pending_approvals = 0

    if salon is not None:
        if resolved_role == "stylist" and stylist is not None:
            pending_approvals = OrderDetail.objects.filter(
                salon=salon,
                stylist=stylist,
                order__status="pending",
            ).count()
        else:
            pending_approvals = manager_snapshot["pending_approvals"]

        notification_count = pending_approvals

    sidebar_sections, sidebar_items = build_dashboard_sidebar_sections(
        active_key,
        salon=salon,
        role=resolved_role,
    )
    page_meta = _build_page_meta(
        active_key,
        salon,
        role=resolved_role,
        stylist=stylist,
        manager_snapshot=manager_snapshot,
    )
    notifications = _build_dashboard_notifications(
        salon,
        role=resolved_role,
        user=user,
        stylist=stylist,
    )
    create_actions = build_dashboard_create_actions(
        salon=salon,
        role=resolved_role,
    )

    if resolved_role == "stylist":
        profile_url = _safe_reverse("dashboards:stylist_profile")
        manager_profile_url = profile_url

        display_name = (
            user.get_fullName()
            if hasattr(user, "get_fullName")
            else f"{getattr(user, 'name', '')} {getattr(user, 'family', '')}".strip()
        ) or "متخصص"

        workspace_name = salon.salon_name if salon else "داشبورد متخصص"

        avatar_url = None
        if stylist and getattr(stylist, "profile_image", None):
            try:
                avatar_url = stylist.profile_image.url
            except Exception:
                avatar_url = None

        active_service_count = (
            Services.objects.filter(
                stylists=stylist,
                services_of_salon=salon,
                is_active=True,
            )
            .distinct()
            .count()
            if stylist and salon
            else 0
        )

        header = {
            "salon_name": workspace_name,
            "manager_name": display_name,
            "manager_initial": display_name[:1] if display_name else "م",
            "salon_initial": workspace_name[:1] if workspace_name else "س",
            "manager_avatar_url": avatar_url,
            "working_hours": get_today_hours_label(salon),
            "notifications_count": notifications["unread_count"],
            "pending_approvals": pending_approvals,
            "team_count": active_service_count,
            "is_active": bool(stylist and stylist.is_active),
            "shell_metrics": _build_shell_metrics(
                salon,
                user=user,
                role=resolved_role,
                stylist=stylist,
            ),
            "role_label": "متخصص",
            "status_panel_title": "وضعیت کاری شما",
            "active_salon_id": salon.id if salon else None,
            "active_salon_name": salon.salon_name if salon else "بدون مجموعه فعال",
            "active_memberships_count": len(stylist_active_memberships),
        }
        dashboard_profile_label = "پروفایل من"

    else:
        profile_url = _safe_reverse("dashboards:salon_profile") if salon else "#"
        manager_profile_url = (
            _safe_reverse("dashboards:manager_profile")
            if getattr(user, "is_authenticated", False)
            and hasattr(user, "salon_manager_profile")
            else profile_url
        )

        manager_name = (
            salon_manager.user.get_fullName() if salon_manager else "مدیر مجموعه"
        )
        salon_name = salon.salon_name if salon else "مجموعه شما"

        avatar_url = None
        if salon_manager and getattr(salon_manager, "profile_image", None):
            try:
                avatar_url = salon_manager.profile_image.url
            except Exception:
                avatar_url = None

        header = {
            "salon_name": salon_name,
            "manager_name": manager_name,
            "manager_initial": manager_name[:1] if manager_name else "م",
            "salon_initial": salon_name[:1] if salon_name else "س",
            "manager_avatar_url": avatar_url,
            "working_hours": get_today_hours_label(salon),
            "notifications_count": notifications["unread_count"],
            "pending_approvals": pending_approvals,
            "team_count": (
                manager_snapshot["active_team_count"]
                if manager_snapshot is not None
                else 0
            ),
            "is_active": bool(salon and salon.is_active),
            "shell_metrics": _build_shell_metrics(
                salon,
                user=user,
                role=resolved_role,
                manager_snapshot=manager_snapshot,
            ),
            "role_label": "مدیر مجموعه",
            "status_panel_title": "وضعیت محیط کاری",
            "pending_approvals_label": "مورد در انتظار",
            "team_count_label": "عضو فعال",
        }
        dashboard_profile_label = "پروفایل مجموعه"

    has_manager_workspace = bool(
        getattr(user, "is_authenticated", False)
        and hasattr(user, "salon_manager_profile")
    )
    has_stylist_workspace = bool(
        getattr(user, "is_authenticated", False) and hasattr(user, "stylist")
    )
    workspace_modes = []
    if has_manager_workspace and has_stylist_workspace:
        workspace_modes = [
            {
                "key": "manager",
                "label": "مدیریت سالن",
                "description": "نوبت‌ها، تیم، خدمات و تنظیمات کل سالن",
                "icon": "fa-solid fa-store",
                "url": _safe_reverse("dashboards:salon_manager_dashboard"),
                "is_active": resolved_role == "manager",
            },
            {
                "key": "stylist",
                "label": "کارهای من",
                "description": "نوبت‌ها و برنامه شخصی من به‌عنوان متخصص",
                "icon": "fa-regular fa-user",
                "url": _safe_reverse("dashboards:stylist_dashboard"),
                "is_active": resolved_role == "stylist",
            },
        ]

    return {
        "page_title": page_title or page_meta["title"],
        "page_meta": page_meta,
        "salon": salon,
        "salon_manager": salon_manager,
        "stylist": stylist,
        "dashboard_role": resolved_role,
        "dashboard_nav_items": build_dashboard_nav_items(
            active_key,
            salon=salon,
            role=resolved_role,
        ),
        "dashboard_sidebar_sections": sidebar_sections,
        "dashboard_sidebar_items": sidebar_items,
        "dashboard_mobile_nav_items": build_dashboard_mobile_nav_items(
            active_key,
            salon=salon,
            role=resolved_role,
        ),
        "dashboard_create_actions": create_actions,
        "dashboard_notifications": notifications,
        "dashboard_profile_url": profile_url,
        "dashboard_manager_profile_url": manager_profile_url,
        "dashboard_active_key": active_key,
        "dashboard_quick_actions": build_dashboard_quick_actions(
            salon=salon,
            role=resolved_role,
        ),
        "dashboard_header": header,
        "dashboard_profile_label": dashboard_profile_label,
        "stylist_active_memberships": (
            stylist_active_memberships if resolved_role == "stylist" else []
        ),
        "stylist_salon": salon if resolved_role == "stylist" else None,
        "dashboard_workspace_modes": workspace_modes,
        "dashboard_has_workspace_switch": len(workspace_modes) > 1,
    }
