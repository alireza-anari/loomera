from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse

from apps.messaging.links import absolute_site_url
from apps.messaging.roles import BotRoleKey, UserBotRoleContext, detect_user_bot_roles

MENU_CALLBACK_PREFIX = "menu:"
MENU_MAIN = "main"
MENU_GUEST = "guest"
MENU_HELP = "help"
MENU_QUICK_LINKS = "quick_links"
MENU_CUSTOMER_SEARCH = "customer_search"
MENU_CUSTOMER_APPOINTMENTS = "customer_appointments"
MENU_CUSTOMER_REVIEWS = "customer_reviews"
MENU_CUSTOMER_SUPPORT = "customer_support"
MENU_STYLIST_TODAY = "stylist_today"
MENU_STYLIST_SLOTS = "stylist_slots"
MENU_STYLIST_BOOKING_LINK = "stylist_booking_link"
MENU_STYLIST_PROMOTION = "stylist_promotion"
MENU_MANAGER_TODAY = "manager_today"
MENU_MANAGER_SUMMARY = "manager_summary"
MENU_MANAGER_SHIFTS = "manager_shifts"
MENU_MANAGER_SLOTS = "manager_slots"
MENU_MANAGER_REQUESTS = "manager_requests"
MENU_MANAGER_PROMOTION = "manager_promotion"


def _url(base_url: str, name: str, *args, **kwargs) -> str:
    return absolute_site_url(base_url, reverse(name, args=args, kwargs=kwargs))


def _safe_url(
    base_url: str, name: str, *args, fallback_name: str = "salons:show_salons", **kwargs
) -> str:
    try:
        return _url(base_url, name, *args, **kwargs)
    except NoReverseMatch:
        return _url(base_url, fallback_name)


def _callback(value: str) -> str:
    return f"{MENU_CALLBACK_PREFIX}{value}"


def _role_callback(role_key: str) -> str:
    return _callback(role_key)


def user_display_name(user) -> str:
    if not user:
        return "کاربر"
    name_getter = getattr(user, "get_fullName", None)
    if callable(name_getter):
        name = (name_getter() or "").strip()
        if name:
            return name
    return (getattr(user, "mobile_number", "") or "کاربر").strip()


def guest_welcome_text(display_name: str = "") -> str:
    greeting = f"سلام {display_name} عزیز 🌿" if display_name else "سلام 🌿"
    return (
        f"{greeting}\n"
        "به Loomera خوش آمدی. اینجا می‌توانی سالن‌ها و خدمات زیبایی/تندرستی را پیدا کنی و رزرو را از سایت ادامه بدهی.\n\n"
        "برای دیدن نوبت‌ها یا انجام کارهای حسابی، ابتدا حساب سایتت را به ربات وصل کن."
    )


def guest_main_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "جستجوی سالن",
                    "callback_data": _callback(MENU_CUSTOMER_SEARCH),
                },
                {"text": "ورود به حساب", "url": _url(base_url, "accounts:login")},
            ],
            [
                {
                    "text": "جستجوی کامل سایت",
                    "url": _url(base_url, "salons:show_salons"),
                },
                {"text": "راهنما", "callback_data": _callback(MENU_HELP)},
            ],
            [
                {
                    "text": "ثبت‌نام مشتری",
                    "url": _url(base_url, "accounts:customer_signup"),
                },
                {
                    "text": "ثبت‌نام متخصص",
                    "url": _url(base_url, "accounts:stylist_signup"),
                },
            ],
            [
                {
                    "text": "ثبت‌نام سالن/مدیر",
                    "url": _url(base_url, "accounts:register"),
                },
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    }


def connected_text(user) -> str:
    name = user_display_name(user)
    return (
        f"حساب {name} با موفقیت به ربات بله وصل شد ✅\n\n"
        "اکنون منوی مناسب نقش‌های حساب شما فعال است. اکشن‌های نوبت متخصص فقط با دکمه امن و بررسی دسترسی اجرا می‌شوند."
    )


def role_summary_text(context: UserBotRoleContext) -> str:
    name = user_display_name(context.user)
    if not context.has_roles:
        return (
            f"سلام {name} عزیز 🌿\n"
            "حساب شما به ربات وصل است، اما هنوز نقش مشتری، متخصص یا مدیر سالن برای این حساب پیدا نشد.\n"
            "از لینک‌های زیر می‌توانی ثبت‌نام نقش موردنظرت را کامل کنی."
        )
    if context.is_multi_role:
        return (
            f"سلام {name} عزیز 🌿\n"
            f"برای این حساب چند نقش فعال پیدا شد: {context.role_labels_text}.\n"
            "یکی از نقش‌ها را انتخاب کن تا منوی همان نقش نمایش داده شود."
        )
    return (
        f"سلام {name} عزیز 🌿\n"
        f"نقش فعال شما: {context.role_labels_text}.\n"
        "از منوی زیر برای دسترسی سریع به بخش‌های اصلی استفاده کن."
    )


def no_role_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "ثبت‌نام مشتری",
                    "url": _url(base_url, "accounts:customer_signup"),
                },
                {
                    "text": "ثبت‌نام متخصص",
                    "url": _url(base_url, "accounts:stylist_signup"),
                },
            ],
            [
                {
                    "text": "ثبت‌نام سالن/مدیر",
                    "url": _url(base_url, "accounts:register"),
                },
                {"text": "وضعیت اتصال ربات", "url": _url(base_url, "messaging:status")},
            ],
            [{"text": "پشتیبانی", "url": _url(base_url, "support")}],
        ]
    }


def role_selector_menu(base_url: str, context: UserBotRoleContext) -> dict:
    if not context.has_roles:
        return no_role_menu(base_url)

    rows: list[list[dict[str, Any]]] = []
    role_buttons = []
    for role in context.roles:
        role_buttons.append(
            {"text": role.label, "callback_data": _role_callback(role.key)}
        )
    for i in range(0, len(role_buttons), 2):
        rows.append(role_buttons[i : i + 2])

    rows.extend(
        [
            [
                {
                    "text": "اعلان‌های من",
                    "url": _safe_url(base_url, "accounts:notifications"),
                },
                {
                    "text": "تنظیمات اعلان",
                    "url": _safe_url(base_url, "messaging:preferences"),
                },
            ],
            [
                {"text": "وضعیت اتصال ربات", "url": _url(base_url, "messaging:status")},
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    )
    return {"inline_keyboard": rows}


def customer_menu_text(user) -> str:
    return (
        f"منوی مشتری {user_display_name(user)} 🌿\n"
        "می‌توانی سالن‌ها را جستجو کنی، کارت سالن ببینی، نوبت‌های خودت را مرور کنی و برای ثبت نظر وارد سایت شوی. "
        "رزرو کامل، پرداخت، لغو مالی و تغییر زمان همچنان داخل سایت انجام می‌شود."
    )


def customer_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "جستجوی سالن",
                    "callback_data": _callback(MENU_CUSTOMER_SEARCH),
                },
                {
                    "text": "جستجوی کامل با فیلتر",
                    "url": _safe_url(base_url, "search:search_page"),
                },
            ],
            [
                {
                    "text": "نوبت‌های من",
                    "callback_data": _callback(MENU_CUSTOMER_APPOINTMENTS),
                },
                {"text": "ثبت نظر", "callback_data": _callback(MENU_CUSTOMER_REVIEWS)},
            ],
            [
                {
                    "text": "اعلان‌های من",
                    "url": _safe_url(base_url, "accounts:notifications"),
                },
                {
                    "text": "تنظیمات اعلان",
                    "url": _safe_url(base_url, "messaging:preferences"),
                },
            ],
            [
                {
                    "text": "پنل مشتری",
                    "url": _safe_url(base_url, "accounts:customer_panel"),
                },
                {"text": "پشتیبانی", "callback_data": _callback(MENU_CUSTOMER_SUPPORT)},
            ],
            [{"text": "منوی نقش‌ها", "callback_data": _callback(MENU_MAIN)}],
        ]
    }


def stylist_menu_text(user, role=None) -> str:
    parts = [
        f"منوی متخصص {user_display_name(user)} ✨",
        "اکشن‌های نوبت با دکمه امن فعال شده‌اند؛ رزرو، پرداخت و تغییرات مالی همچنان داخل سایت انجام می‌شود.",
    ]
    if role:
        active_count = role.metadata.get("active_salon_count")
        pending_count = role.metadata.get("pending_invite_count")
        parts.append(
            f"سالن‌های فعال: {active_count or 0} | دعوت‌های در انتظار: {pending_count or 0}"
        )
    return "\n".join(parts)


def stylist_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "نوبت‌های امروز",
                    "callback_data": _callback(MENU_STYLIST_TODAY),
                },
                {
                    "text": "وقت‌های خالی من",
                    "callback_data": _callback(MENU_STYLIST_SLOTS),
                },
            ],
            [
                {
                    "text": "لینک رزرو متخصص",
                    "callback_data": _callback(MENU_STYLIST_BOOKING_LINK),
                },
                {
                    "text": "تبلیغ و لینک رزرو",
                    "callback_data": _callback(MENU_STYLIST_PROMOTION),
                },
            ],
            [
                {
                    "text": "نوبت‌های من",
                    "url": _safe_url(base_url, "dashboards:stylist_appointments"),
                },
                {
                    "text": "برنامه کاری",
                    "url": _safe_url(base_url, "dashboards:stylist_schedule"),
                },
            ],
            [
                {
                    "text": "پروفایل متخصص",
                    "url": _safe_url(base_url, "dashboards:stylist_profile"),
                },
                {
                    "text": "محتوا و تبلیغ سایت",
                    "url": _safe_url(base_url, "dashboards:stylist_content"),
                },
            ],
            [
                {
                    "text": "داشبورد متخصص",
                    "url": _safe_url(base_url, "dashboards:stylist_dashboard"),
                },
                {"text": "راهنما", "callback_data": _callback(MENU_HELP)},
            ],
            [
                {"text": "منوی نقش‌ها", "callback_data": _callback(MENU_MAIN)},
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    }


def manager_menu_text(user, role=None) -> str:
    parts = [
        f"منوی مدیر سالن {user_display_name(user)} 🧭",
        "اکشن‌های همکاری، مرخصی و شیفت با دکمه امن و بررسی scope سالن فعال شده‌اند؛ رزرو و امور مالی همچنان داخل سایت انجام می‌شود.",
    ]
    if role:
        parts.append(
            f"تعداد سالن‌ها: {role.metadata.get('salon_count') or 0} | سالن‌های فعال: {role.metadata.get('active_salon_count') or 0}"
        )
    return "\n".join(parts)


def manager_menu(base_url: str, role=None) -> dict:
    first_salon_id = None
    if role:
        first_salon_id = role.metadata.get("first_salon_id")

    calendar_button = {
        "text": "تقویم سالن",
        "url": _safe_url(base_url, "dashboards:salon_manager_dashboard"),
    }
    reports_button = {
        "text": "گزارش‌ها",
        "url": _safe_url(base_url, "dashboards:salon_manager_dashboard"),
    }
    if first_salon_id:
        calendar_button = {
            "text": "تقویم امروز",
            "url": _safe_url(
                base_url, "dashboards:appointment_calendar", salon_id=first_salon_id
            ),
        }
        reports_button = {
            "text": "گزارش سالن",
            "url": _safe_url(
                base_url, "dashboards:reports_dashboard", salon_id=first_salon_id
            ),
        }

    return {
        "inline_keyboard": [
            [
                {"text": "تقویم امروز", "callback_data": _callback(MENU_MANAGER_TODAY)},
                {
                    "text": "خلاصه امروز",
                    "callback_data": _callback(MENU_MANAGER_SUMMARY),
                },
            ],
            [
                {
                    "text": "بررسی شیفت‌ها",
                    "callback_data": _callback(MENU_MANAGER_SHIFTS),
                },
                {
                    "text": "وقت خالی متخصصان",
                    "callback_data": _callback(MENU_MANAGER_SLOTS),
                },
            ],
            [
                {
                    "text": "درخواست‌های متخصصان",
                    "callback_data": _callback(MENU_MANAGER_REQUESTS),
                },
                {
                    "text": "داشبورد مدیر",
                    "url": _safe_url(base_url, "dashboards:salon_manager_dashboard"),
                },
            ],
            [
                calendar_button,
                reports_button,
            ],
            [
                {
                    "text": "تبلیغ سالن / استوری",
                    "callback_data": _callback(MENU_MANAGER_PROMOTION),
                },
                {
                    "text": "شیفت و مرخصی",
                    "url": _safe_url(base_url, "dashboards:scheduled_shifts"),
                },
            ],
            [
                {"text": "منوی نقش‌ها", "callback_data": _callback(MENU_MAIN)},
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    }


def quick_links_text() -> str:
    return "لینک‌های سریع Loomera 🌿"


def quick_links_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "جستجوی سالن",
                    "callback_data": _callback(MENU_CUSTOMER_SEARCH),
                },
                {"text": "وضعیت اتصال", "url": _url(base_url, "messaging:status")},
            ],
            [
                {
                    "text": "تنظیمات اعلان",
                    "url": _safe_url(base_url, "messaging:preferences"),
                },
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
            [{"text": "منوی نقش‌ها", "callback_data": _callback(MENU_MAIN)}],
        ]
    }


def help_text() -> str:
    return (
        "راهنمای ربات Loomera 💬\n"
        "می‌توانی حساب سایت را وصل کنی، نقش‌هایت را ببینی، سالن‌ها را با دستور /search جستجو کنی و از منوهای مشتری/متخصص/مدیر استفاده کنی.\n"
        "رزرو کامل، پرداخت، لغو مالی، تغییر زمان و تغییر خدمت همچنان داخل سایت انجام می‌شوند."
    )


def help_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "لینک‌های سریع", "callback_data": _callback(MENU_QUICK_LINKS)},
                {
                    "text": "تنظیمات اعلان",
                    "url": _safe_url(base_url, "messaging:preferences"),
                },
            ],
            [
                {
                    "text": "حریم خصوصی ربات",
                    "url": _safe_url(base_url, "messaging:privacy"),
                },
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
            [{"text": "منوی نقش‌ها", "callback_data": _callback(MENU_MAIN)}],
        ]
    }


def connected_basic_menu(base_url: str, user) -> dict:
    # Backward-compatible alias kept for stage-3 tests/imports.
    return role_selector_menu(base_url, detect_user_bot_roles(user))


def menu_for_user(base_url: str, user) -> tuple[str, dict]:
    context = detect_user_bot_roles(user)
    if not context.has_roles or context.is_multi_role:
        return role_summary_text(context), role_selector_menu(base_url, context)
    role = context.roles[0]
    if role.key == BotRoleKey.CUSTOMER:
        return customer_menu_text(user), customer_menu(base_url)
    if role.key == BotRoleKey.STYLIST:
        return stylist_menu_text(user, role), stylist_menu(base_url)
    if role.key == BotRoleKey.MANAGER:
        return manager_menu_text(user, role), manager_menu(base_url, role)
    return role_summary_text(context), role_selector_menu(base_url, context)


def menu_for_role(base_url: str, user, role_key: str) -> tuple[str, dict]:
    context = detect_user_bot_roles(user)
    role = context.get_role(role_key)
    if role is None:
        return role_summary_text(context), role_selector_menu(base_url, context)
    if role.key == BotRoleKey.CUSTOMER:
        return customer_menu_text(user), customer_menu(base_url)
    if role.key == BotRoleKey.STYLIST:
        return stylist_menu_text(user, role), stylist_menu(base_url)
    if role.key == BotRoleKey.MANAGER:
        return manager_menu_text(user, role), manager_menu(base_url, role)
    return role_summary_text(context), role_selector_menu(base_url, context)


def token_error_text(error_code: str) -> str:
    messages = {
        "token_not_found": "توکن اتصال پیدا نشد یا نامعتبر است.",
        "token_revoked": "توکن اتصال لغو شده است.",
        "token_already_used": "این توکن قبلاً استفاده شده است.",
        "token_expired": "مهلت استفاده از توکن اتصال تمام شده است.",
        "token_missing_user": "توکن اتصال به حساب کاربری مشخصی وصل نیست.",
        "token_provider_mismatch": "این توکن برای پیام‌رسان دیگری ساخته شده است.",
        "identity_already_linked_to_another_user": "این حساب بله قبلاً به کاربر دیگری وصل شده است.",
    }
    return f"اتصال حساب انجام نشد. {messages.get(error_code, 'لطفاً دوباره از سایت توکن اتصال بسازید.')}"


def unknown_start_payload_text() -> str:
    return (
        "لینک یا کد شروع ربات دریافت شد، اما این payload هنوز در فاز فعلی پشتیبانی نمی‌شود.\n"
        "فعلاً می‌توانی از منوی زیر وارد سایت شوی یا حساب خود را از صفحه اتصال ربات وصل کنی."
    )


def unsupported_action_text() -> str:
    return (
        "این دکمه مربوط به اکشن عملیاتی است و در این مرحله هنوز فعال نشده است.\n"
        "برای کارهای مدیریتی فعلاً از لینک‌های سایت استفاده کن."
    )


def disconnected_required_text() -> str:
    return "برای استفاده از منوی نقش‌ها ابتدا حساب سایتت را به ربات وصل کن."


def disconnected_text() -> str:
    return (
        "اتصال حساب بله‌ات از Loomera قطع شد.\n\n"
        "از این به بعد اعلان‌های مربوط به این حساب در بله ارسال نمی‌شود. "
        "برای اتصال دوباره، از پنل Loomera لینک اتصال جدید دریافت کن."
    )


def already_disconnected_text() -> str:
    return (
        "این حساب بله در حال حاضر به Loomera متصل نیست.\n\n"
        "برای اتصال، از پنل Loomera لینک اتصال جدید دریافت کن."
    )
