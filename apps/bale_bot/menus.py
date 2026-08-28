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
MENU_MANAGER_SALON = "manager_salon"
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


def _manager_callback(menu_key: str, salon_id: int | None = None) -> str:
    if salon_id:
        return _callback(f"{menu_key}:{int(salon_id)}")
    return _callback(menu_key)


def _manager_role_salons(role) -> list[dict]:
    if not role:
        return []
    salons = role.metadata.get("salons") or []
    return [item for item in salons if isinstance(item, dict) and item.get("id")]


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
    greeting = f"سلام {display_name}" if display_name else "سلام"
    return (
        f"{greeting}، به Loomera خوش آمدی.\n\n"
        "از همین‌جا می‌توانی سالن پیدا کنی. اگر حساب Loomera داری، آن را وصل کن تا نوبت‌ها و کارهای روزانه‌ات هم داخل ربات در دسترس باشد."
    )

def guest_main_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "پیدا کردن سالن", "callback_data": _callback(MENU_CUSTOMER_SEARCH)},
                {"text": "وصل کردن حساب Loomera", "url": _url(base_url, "messaging:bale_quick_connect")},
            ],
            [
                {"text": "جستجوی کامل در سایت", "url": _url(base_url, "salons:show_salons")},
                {"text": "راهنمای ربات", "callback_data": _callback(MENU_HELP)},
            ],
            [
                {"text": "ساخت حساب مشتری", "url": _url(base_url, "accounts:customer_signup")},
                {"text": "ثبت‌نام متخصص", "url": _url(base_url, "accounts:stylist_signup")},
            ],
            [
                {"text": "ثبت سالن", "url": _url(base_url, "accounts:register")},
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    }

def connected_text(user) -> str:
    name = user_display_name(user)
    return (
        f"{name}، حسابت به ربات وصل شد.\n\n"
        "از این به بعد اعلان‌ها و کارهای مربوط به نقش حسابت را می‌توانی همین‌جا ببینی و انجام بدهی."
    )

def role_summary_text(context: UserBotRoleContext) -> str:
    name = user_display_name(context.user)
    if not context.has_roles:
        return (
            f"{name}، حسابت وصل است اما هنوز نقش فعالی برای آن پیدا نکردم.\n"
            "اگر مشتری، متخصص یا مدیر سالن هستی، ثبت‌نام همان بخش را کامل کن."
        )
    if context.is_multi_role:
        return (
            f"{name}، این حساب چند نقش دارد: {context.role_labels_text}.\n"
            "نقشی را که الان با آن کار داری انتخاب کن."
        )
    return f"{name}، چه کاری می‌خواهی انجام بدهی؟"

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
    return f"{user_display_name(user)}، از اینجا می‌توانی سالن پیدا کنی و نوبت‌هایت را ببینی."

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
    parts = [f"{user_display_name(user)}، کارهای امروزت اینجاست."]
    if role:
        today_count = role.metadata.get("today_appointment_count") or 0
        ready_count = role.metadata.get("today_ready_count") or 0
        in_progress_count = role.metadata.get("today_in_progress_count") or 0
        cash_pending_count = role.metadata.get("today_cash_pending_count") or 0
        parts.append(
            f"امروز: {today_count} نوبت | آماده شروع: {ready_count} | در حال انجام: {in_progress_count}"
        )
        if cash_pending_count:
            parts.append(f"منتظر ثبت دریافت وجه: {cash_pending_count}")
        invite_count = role.metadata.get("pending_invite_count") or 0
        if invite_count:
            parts.append(f"دعوت همکاری در انتظار: {invite_count}")
    return "\n".join(parts)

def stylist_menu(base_url: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "نوبت‌های امروز", "callback_data": _callback(MENU_STYLIST_TODAY)},
                {"text": "وقت‌های خالی", "callback_data": _callback(MENU_STYLIST_SLOTS)},
            ],
            [
                {"text": "لینک رزرو من", "callback_data": _callback(MENU_STYLIST_BOOKING_LINK)},
                {"text": "متن و لینک تبلیغ", "callback_data": _callback(MENU_STYLIST_PROMOTION)},
            ],
            [
                {"text": "همه نوبت‌ها", "url": _safe_url(base_url, "dashboards:stylist_appointments")},
                {"text": "برنامه کاری", "url": _safe_url(base_url, "dashboards:stylist_schedule")},
            ],
            [
                {"text": "پروفایل من", "url": _safe_url(base_url, "dashboards:stylist_profile")},
                {"text": "داشبورد متخصص", "url": _safe_url(base_url, "dashboards:stylist_dashboard")},
            ],
            [
                {"text": "تغییر نقش", "callback_data": _callback(MENU_MAIN)},
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    }

def manager_menu_text(user, role=None, *, selected_salon_name: str = "") -> str:
    if selected_salon_name:
        parts = [f"{user_display_name(user)}، {selected_salon_name}"]
    else:
        parts = [f"{user_display_name(user)}، وضعیت سالن و کارهای باز اینجاست."]
    if role:
        today_count = role.metadata.get("today_appointment_count") or 0
        open_count = role.metadata.get("open_staff_request_count") or 0
        if selected_salon_name:
            parts.append("برای جزئیات امروز یا درخواست‌ها یکی از گزینه‌های زیر را بزن.")
        else:
            parts.append(f"امروز: {today_count} نوبت | درخواست باز تیم: {open_count}")
        salon_count = role.metadata.get("salon_count") or 0
        if salon_count > 1 and not selected_salon_name:
            parts.append(f"تعداد سالن‌های تحت مدیریت: {salon_count}")
    return "\n".join(parts)


def manager_salon_selector_text(user, role=None) -> str:
    salons = _manager_role_salons(role)
    if not salons:
        return manager_menu_text(user, role)
    return (
        f"{user_display_name(user)}، کدام سالن را می‌خواهی بررسی کنی؟\n"
        "بعد از انتخاب، خلاصه امروز و درخواست‌های همان سالن را می‌بینی."
    )


def manager_salon_selector_menu(base_url: str, role=None) -> dict:
    rows: list[list[dict[str, Any]]] = []
    for salon in _manager_role_salons(role):
        label = str(salon.get("name") or "سالن")
        if not salon.get("is_active", True):
            label += " (غیرفعال)"
        rows.append(
            [
                {
                    "text": label[:60],
                    "callback_data": _manager_callback(
                        MENU_MANAGER_SALON, int(salon["id"])
                    ),
                }
            ]
        )
    rows.extend(
        [
            [{"text": "تغییر نقش", "callback_data": _callback(MENU_MAIN)}],
            [{"text": "پشتیبانی", "url": _url(base_url, "support")}],
        ]
    )
    return {"inline_keyboard": rows}


def manager_menu(base_url: str, role=None, *, salon_id: int | None = None) -> dict:
    if salon_id is None and role:
        salon_id = role.metadata.get("first_salon_id")
    calendar_url = _safe_url(base_url, "dashboards:salon_manager_dashboard")
    reports_url = _safe_url(base_url, "dashboards:salon_manager_dashboard")
    if salon_id:
        calendar_url = _safe_url(base_url, "dashboards:appointment_calendar", salon_id=salon_id)
        reports_url = _safe_url(base_url, "dashboards:reports_dashboard", salon_id=salon_id)

    scoped = lambda key: _manager_callback(key, salon_id)
    return {
        "inline_keyboard": [
            [
                {"text": "امروز سالن", "callback_data": scoped(MENU_MANAGER_TODAY)},
                {"text": "خلاصه امروز", "callback_data": scoped(MENU_MANAGER_SUMMARY)},
            ],
            [
                {"text": "درخواست‌های همکاری", "callback_data": scoped(MENU_MANAGER_REQUESTS)},
            ],
            [
                {"text": "شیفت و مرخصی", "callback_data": scoped(MENU_MANAGER_SHIFTS)},
                {"text": "وقت خالی متخصصان", "callback_data": scoped(MENU_MANAGER_SLOTS)},
            ],
            [
                {"text": "تقویم کامل", "url": calendar_url},
                {"text": "گزارش سالن", "url": reports_url},
            ],
            [
                {"text": "متن و لینک تبلیغ", "callback_data": scoped(MENU_MANAGER_PROMOTION)},
                {"text": "داشبورد مدیر", "url": _safe_url(base_url, "dashboards:salon_manager_dashboard")},
            ],
            [
                {
                    "text": "انتخاب سالن" if len(_manager_role_salons(role)) > 1 else "تغییر نقش",
                    "callback_data": (
                        _callback(BotRoleKey.MANAGER)
                        if len(_manager_role_salons(role)) > 1
                        else _callback(MENU_MAIN)
                    ),
                },
                {"text": "پشتیبانی", "url": _url(base_url, "support")},
            ],
        ]
    }


def quick_links_text() -> str:
    return "دسترسی‌های سریع"

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
        "این ربات برای کارهای روزمره Loomera است.\n\n"
        "مشتری: پیدا کردن سالن، دیدن نوبت‌ها و پیگیری اعلان‌ها\n"
        "متخصص: نوبت‌های امروز، شروع و پایان خدمت، ثبت عدم حضور، لغو در صورت عدم امکان و ثبت دریافت وجه\n"
        "مدیر: وضعیت امروز سالن، درخواست همکاری، مرخصی و برنامه کاری\n\n"
        "برای تغییرات پیچیده رزرو یا مواردی که نیاز به فرم کامل دارند، ربات لینک همان بخش را در سایت می‌دهد."
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
        salons = _manager_role_salons(role)
        if len(salons) > 1:
            return manager_salon_selector_text(user, role), manager_salon_selector_menu(base_url, role)
        selected_name = str(salons[0].get("name") or "") if salons else ""
        selected_id = int(salons[0]["id"]) if salons else role.metadata.get("first_salon_id")
        return (
            manager_menu_text(user, role, selected_salon_name=selected_name),
            manager_menu(base_url, role, salon_id=selected_id),
        )
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
        salons = _manager_role_salons(role)
        if len(salons) > 1:
            return manager_salon_selector_text(user, role), manager_salon_selector_menu(base_url, role)
        selected_name = str(salons[0].get("name") or "") if salons else ""
        selected_id = int(salons[0]["id"]) if salons else role.metadata.get("first_salon_id")
        return (
            manager_menu_text(user, role, selected_salon_name=selected_name),
            manager_menu(base_url, role, salon_id=selected_id),
        )
    return role_summary_text(context), role_selector_menu(base_url, context)


def token_error_text(error_code: str) -> str:
    messages = {
        "token_not_found": "لینک اتصال معتبر نیست.",
        "token_revoked": "این لینک اتصال لغو شده است.",
        "token_already_used": "این لینک قبلاً استفاده شده است.",
        "token_expired": "مهلت این لینک تمام شده است.",
        "token_missing_user": "حساب مربوط به این لینک پیدا نشد.",
        "token_provider_mismatch": "این لینک برای بله ساخته نشده است.",
        "identity_already_linked_to_another_user": "این حساب بله قبلاً به یک حساب دیگر وصل شده است.",
    }
    return messages.get(error_code, "اتصال انجام نشد. از Loomera یک لینک اتصال تازه بگیر.")

def unknown_start_payload_text() -> str:
    return "این لینک دیگر قابل استفاده نیست. از Loomera یک لینک اتصال تازه باز کن یا از منوی زیر ادامه بده."

def unsupported_action_text() -> str:
    return "این دکمه دیگر قابل استفاده نیست. منوی تازه را باز کن و دوباره اقدام کن."

def disconnected_required_text() -> str:
    return "برای دیدن اطلاعات حسابت، اول حساب Loomera را به این ربات وصل کن."

def disconnected_text() -> str:
    return "اتصال حساب قطع شد. اگر دوباره خواستی اعلان‌ها و کارهای حسابت را اینجا ببینی، یک لینک اتصال تازه از Loomera باز کن."

def already_disconnected_text() -> str:
    return "این حساب بله الان به Loomera وصل نیست. برای اتصال، لینک اتصال را از Loomera باز کن."
