from __future__ import annotations

from django.core.exceptions import ValidationError
from django.urls import reverse

from .common import normalize_text, read_confirmation, resolve_current_path, user_roles
from .customer_operations import (
    execute_customer_confirmation,
    is_customer_appointment_operation_candidate,
    resolve_customer_choice,
    run_customer_appointment_operation,
)
from .manager_operations import execute_manager_confirmation, run_manager_operation
from .stylist_operations import (
    execute_stylist_confirmation,
    is_stylist_operation_candidate,
    run_stylist_leave,
    run_stylist_payout,
    run_stylist_schedule,
    run_stylist_read_operation,
)
from .work_queries import (
    is_manager_read_query_candidate,
    is_stylist_read_query_candidate,
)


CAPABILITY_TERMS = (
    "چه کارهایی میتونی",
    "چه کارهایی می تونی",
    "چه کارهایی می‌تونی",
    "چه کارایی میتونی",
    "چه کارایی می تونی",
    "چه کارایی می‌تونی",
    "چه قابلیت",
    "توانایی هات",
    "توانایی‌هات",
    "کمکم کنی",
)

NAVIGATION_TERMS = (
    "باز کن",
    "ببر",
    "نشون بده",
    "نشان بده",
    "بریم",
    "میخوام برم",
    "می خوام برم",
    "می‌خوام برم",
)


def _wants_navigation(text: str) -> bool:
    return (
        any(term in text for term in NAVIGATION_TERMS)
        and "چطور" not in text
        and "چگونه" not in text
    )


def _capabilities(request) -> dict:
    roles = user_roles(request.user)
    groups = []
    if "customer" in roles or "guest" in roles:
        groups.append(
            {
                "role": "customer",
                "title": "برای مشتری",
                "items": [
                    "پیدا کردن خدمت با بودجه، محدوده و زمان دلخواه",
                    "پیدا کردن متخصص و زمان آزاد و ادامه تا رزرو",
                    "لغو یا تغییر زمان نوبتی که صفحه‌اش باز است",
                ],
                "prompts": [
                    "کوتاهی مو زیر ۵۰۰ هزار نزدیک من پیدا کن",
                    "نوبت‌های من رو باز کن",
                ],
            }
        )
    if "stylist" in roles:
        groups.append(
            {
                "role": "stylist",
                "title": "برای متخصص",
                "items": [
                    "دیدن نوبت‌های امروز و فردا و نوبت بعدی",
                    "دیدن برنامه کاری و ساعت پایان کار",
                    "ساخت درخواست برنامه کاری برای یک یا چند روز",
                    "ثبت درخواست مرخصی روزانه یا ساعتی",
                    "رفتن مستقیم به درآمد و درخواست برداشت",
                ],
                "prompts": [
                    "شنبه تا چهارشنبه از ۹ صبح تا ۵ عصر برام برنامه کاری ثبت کن",
                    "برای فردا کل روز مرخصی میخوام",
                ],
            }
        )
    if "manager" in roles:
        groups.append(
            {
                "role": "manager",
                "title": "برای مدیر مجموعه",
                "items": [
                    "دیدن نوبت‌های امروز و فردا و نوبت بعدی متخصص",
                    "دیدن برنامه کاری، متخصص‌های فعال و خدمات مجموعه",
                    "دیدن و تأیید یا رد درخواست برنامه کاری و مرخصی تیم",
                    "دعوت متخصص جدید با شماره موبایل",
                    "لغو نوبت یا ثبت پرداخت روی نوبتی که صفحه‌اش باز است",
                    "باز کردن درخواست‌های برداشت متخصص‌ها",
                ],
                "prompts": [
                    "درخواست‌های مرخصی جدید رو نشون بده",
                    "یک متخصص جدید دعوت کن",
                ],
            }
        )
    if not groups:
        groups.append(
            {
                "role": "general",
                "title": "کارهایی که الان می‌تونم انجام بدم",
                "items": ["راهنمایی درباره کار با لومرا و پیدا کردن صفحات مرتبط"],
                "prompts": ["چطور با لومرا کار کنم؟"],
            }
        )
    return {
        "handled": True,
        "kind": "action_capabilities",
        "answer": "می‌تونم هم راهنمایی کنم و هم بخشی از کارها رو داخل همین گفتگو جلو ببرم. عملیات تغییردهنده فقط بعد از تأیید خودت اجرا می‌شن.",
        "action_state": None,
        "capabilities": groups,
    }


def _manager_light_candidate(message: str, state: dict | None, current_path: str) -> bool:
    state = state or {}
    if state.get("mode") == "manager_invite":
        return True
    text = normalize_text(message)
    if any(term in text for term in ("درخواست مرخصی", "درخواست برنامه کاری", "درخواست همکاری", "درخواست های", "درخواست‌های")) and any(
        term in text for term in ("نشون", "نشان", "ببین", "بررسی", "در انتظار", "جدید")
    ):
        return True
    if any(term in text for term in ("دعوت", "متخصص جدید", "عضو جدید")) and "چطور" not in text and "چگونه" not in text:
        return True
    if "برداشت" in text and any(term in text for term in ("متخصص", "متخصص ها", "متخصص‌های", "متخصصها", "تیم")):
        return True
    match = resolve_current_path(current_path)
    if match and match.view_name in {"dashboards:appointment_detail", "dashboards:appointment_detail_legacy"}:
        if "لغو" in text or any(term in text for term in ("ثبت پرداخت", "پرداخت شده", "تسویه", "پرداخت در مجموعه")):
            return True
    return False


def _stylist_navigation(request, message: str) -> dict | None:
    text = normalize_text(message)
    if not _wants_navigation(text):
        return None

    options = (
        (("برنامه کاری", "شیفت", "برنامه من"), "dashboards:stylist_schedule", "برنامه و مرخصی من رو برات آماده کردم.", "باز کردن برنامه کاری", "calendar-days"),
        (("نوبت های من", "نوبت‌های من", "رزروهای من", "قرارهای من"), "dashboards:stylist_appointments", "نوبت‌های متخصص رو برات آماده کردم.", "باز کردن نوبت‌های من", "calendar-check"),
        (("مالی", "درآمد", "کیف پول", "تسویه"), "dashboards:stylist_finance", "بخش مالی متخصص رو برات آماده کردم.", "باز کردن مالی من", "wallet"),
        (("برداشت",), "dashboards:stylist_withdrawals", "درخواست‌های برداشت رو برات آماده کردم.", "باز کردن درخواست‌های برداشت", "money-bill-transfer"),
    )
    for terms, route_name, answer, label, icon in options:
        if any(term in text for term in terms):
            return {
                "handled": True,
                "kind": "action_link",
                "answer": answer,
                "action_state": None,
                "link": {"url": reverse(route_name), "label": label, "icon": icon},
            }
    return None


def _customer_navigation(message: str) -> dict | None:
    text = normalize_text(message)
    if not _wants_navigation(text):
        return None
    if any(term in text for term in ("نوبت های من", "نوبت‌های من", "رزروهای من", "قرارهای من")):
        return {
            "handled": True,
            "kind": "action_link",
            "answer": "نوبت‌هات رو برات آماده کردم.",
            "action_state": None,
            "link": {
                "url": reverse("orders:appointments"),
                "label": "باز کردن نوبت‌های من",
                "icon": "calendar-check",
            },
        }
    return None


def _navigation_candidate(message: str, roles: set[str]) -> bool:
    text = normalize_text(message)
    if not _wants_navigation(text):
        return False
    if "stylist" in roles and any(term in text for term in ("برنامه کاری", "شیفت", "برنامه من", "نوبت های من", "نوبت‌های من", "رزروهای من", "مالی", "درآمد", "کیف پول", "برداشت")):
        return True
    if "manager" in roles and any(term in text for term in ("تیم", "متخصص", "شیفت", "برنامه تیم", "خدمات", "سرویس", "مالی", "تقویم", "نوبت های مجموعه", "نوبت‌های مجموعه", "رزروهای مجموعه")):
        return True
    if "customer" in roles and any(term in text for term in ("نوبت های من", "نوبت‌های من", "رزروهای من", "قرارهای من")):
        return True
    return False


def is_assistant_action_candidate(request, *, message: str = "", action_state: dict | None = None, current_path: str = "", command: str = "") -> bool:
    if command == "execute":
        return True
    text = normalize_text(message)
    if not text:
        return False
    if any(term in text for term in CAPABILITY_TERMS):
        return True
    roles = user_roles(request.user)
    state = action_state or {}
    if state.get("mode") in {"stylist_schedule", "stylist_leave", "stylist_payout", "manager_invite"}:
        return True
    if "manager" in roles and is_manager_read_query_candidate(message):
        return True
    if "stylist" in roles and is_stylist_read_query_candidate(message):
        return True
    if is_stylist_operation_candidate(message, action_state, has_stylist_role="stylist" in roles):
        return True
    if "stylist" in roles and "برداشت" in text:
        return True
    if "manager" in roles and _manager_light_candidate(message, action_state, current_path):
        return True
    if is_customer_appointment_operation_candidate(
        message,
        current_path=current_path,
        has_customer_role="customer" in roles,
    ):
        return True
    if _navigation_candidate(message, roles):
        return True
    return False


def run_assistant_action(request, *, message: str, action_state: dict | None, current_path: str = "") -> dict:
    text = normalize_text(message)
    roles = user_roles(request.user)

    if any(term in text for term in CAPABILITY_TERMS):
        return _capabilities(request)

    state = action_state or {}
    if state.get("mode") == "stylist_schedule" and "stylist" in roles:
        return run_stylist_schedule(request, message, state)
    if state.get("mode") == "stylist_leave" and "stylist" in roles:
        return run_stylist_leave(request, message, state)
    if state.get("mode") == "stylist_payout" and "stylist" in roles:
        return run_stylist_payout(request, message, state)
    if state.get("mode") == "manager_invite" and "manager" in roles:
        result = run_manager_operation(request, message, state, current_path=current_path)
        return result or {"handled": False}

    if "manager" in roles:
        result = run_manager_operation(request, message, state, current_path=current_path)
        if result is not None:
            return result

    if "stylist" in roles:
        if is_stylist_read_query_candidate(message):
            read_result = run_stylist_read_operation(request, message)
            if read_result is not None:
                return read_result
        if is_stylist_operation_candidate(message, state, has_stylist_role=True):
            if any(term in text for term in ("مرخصی", "آف", "عدم حضور")) or state.get("mode") == "stylist_leave":
                return run_stylist_leave(request, message, state)
            if any(term in text for term in ("برداشت", "درخواست پرداخت", "تسویه", "پولم", "درآمدم")) or state.get("mode") == "stylist_payout":
                return run_stylist_payout(request, message, state)
            return run_stylist_schedule(request, message, state)
        nav = _stylist_navigation(request, message)
        if nav:
            return nav

    if "customer" in roles:
        result = run_customer_appointment_operation(request, message, current_path=current_path)
        if result is not None:
            return result
        nav = _customer_navigation(message)
        if nav:
            return nav

    return {"handled": False}


def choose_assistant_option(request, token: str) -> dict:
    payload = read_confirmation(user=request.user, token=token, consume=False)
    action = str(payload.get("action") or "")
    if action == "customer_choose_appointment":
        return resolve_customer_choice(request, payload)
    raise ValidationError("انتخاب تأییدشده معتبر نیست.")


def execute_assistant_confirmation(request, token: str) -> dict:
    payload = read_confirmation(user=request.user, token=token, consume=True)
    action = str(payload.get("action") or "")
    if action.startswith("stylist_"):
        return execute_stylist_confirmation(request, payload)
    if action.startswith("manager_"):
        return execute_manager_confirmation(request, payload)
    if action.startswith("customer_"):
        return execute_customer_confirmation(request, payload)
    raise ValidationError("عملیات تأییدشده معتبر نیست.")
