from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from apps.services.models import Services
from apps.stylists.dashboard_services import (
    build_stylist_finance_payload,
    create_leave_request,
    create_schedule_request,
    create_staff_payout_request,
    resolve_stylist_dashboard_context,
    validate_staff_schedule_request_window,
    validate_salon_opening_window,
)

from .common import (
    date_label,
    issue_confirmation,
    normalize_text,
    parse_dates,
    parse_hhmm,
    parse_iso_date,
    parse_time_range,
    serialize_time,
)
from .work_queries import run_stylist_read_query

SCHEDULE_TERMS = (
    "برنامه کاری",
    "شیفت",
    "برنامه کار",
)
SCHEDULE_ACTION_TERMS = (
    "بساز",
    "بسازم",
    "ثبت کن",
    "ثبت کنم",
    "بذار",
    "بزار",
    "میخوام",
    "می‌خوام",
    "درخواست",
)
LEAVE_TERMS = ("مرخصی", "آف", "عدم حضور")
PAYOUT_TERMS = ("برداشت", "درخواست پرداخت", "تسویه", "پولم", "درآمدم")
PAYOUT_ACTION_TERMS = ("ثبت", "بزن", "بده", "میخوام", "می‌خوام", "برداشت", "درخواست")

LEAVE_ACTION_TERMS = (
    "میخوام",
    "می‌خوام",
    "ثبت کن",
    "ثبت کنم",
    "درخواست",
    "بذار",
    "بزار",
)
CANCEL_TERMS = ("بیخیال", "بی‌خیال", "لغو", "ولش کن")


def _ctx(request):
    ctx = resolve_stylist_dashboard_context(request)
    if ctx.stylist is None:
        raise ValidationError("این عملیات برای حساب متخصص انجام می‌شود.")
    if ctx.salon is None:
        raise ValidationError("برای این کار ابتدا باید یک مجموعه فعال در داشبورد متخصص داشته باشی.")
    return ctx

def run_stylist_read_operation(request, message: str) -> dict | None:
    ctx = _ctx(request)
    return run_stylist_read_query(
        salon=ctx.salon,
        stylist=ctx.stylist,
        message=message,
        can_view_clients=ctx.can("can_view_own_clients", default=False),
    )

def _service_match(*, salon, stylist, text: str, existing_id=None):
    services = list(
        Services.objects.filter(
            services_of_salon=salon,
            stylists=stylist,
            is_active=True,
        )
        .distinct()
        .order_by("service_name")
    )
    if existing_id:
        current = next((item for item in services if str(item.pk) == str(existing_id)), None)
        if current:
            return current
    normalized = normalize_text(text)
    matches = [item for item in services if normalize_text(item.service_name) in normalized]
    if len(matches) == 1:
        return matches[0]
    return None


def is_stylist_operation_candidate(message: str, state: dict | None, *, has_stylist_role: bool) -> bool:
    if not has_stylist_role:
        return False
    state = state or {}
    if state.get("mode") in {"stylist_schedule", "stylist_leave", "stylist_payout"}:
        return True
    text = normalize_text(message)
    if "چطور" in text or "چگونه" in text:
        return False
    if any(term in text for term in SCHEDULE_TERMS) and any(term in text for term in SCHEDULE_ACTION_TERMS):
        return True
    if any(term in text for term in LEAVE_TERMS) and any(term in text for term in LEAVE_ACTION_TERMS):
        return True
    if any(term in text for term in PAYOUT_TERMS) and any(term in text for term in PAYOUT_ACTION_TERMS):
        return True
    return False


def _schedule_state(request, message: str, state: dict | None) -> dict:
    ctx = _ctx(request)
    state = dict(state or {}) if (state or {}).get("mode") == "stylist_schedule" else {"mode": "stylist_schedule"}
    dates = parse_dates(message, allow_weekday_range=True)
    if dates:
        # Existing business logic stores one request per date. Keep batch scope
        # deliberately small so a conversational mistake cannot create dozens.
        state["dates"] = [item.isoformat() for item in dates[:7]]
    start, end = parse_time_range(message)
    if start and end:
        state["start_time"] = serialize_time(start)
        state["end_time"] = serialize_time(end)
    service = _service_match(
        salon=ctx.salon,
        stylist=ctx.stylist,
        text=message,
        existing_id=state.get("service_id"),
    )
    if service:
        state["service_id"] = service.pk
        state["service_name"] = service.service_name
    state["salon_id"] = ctx.salon.pk
    state["salon_name"] = ctx.salon.salon_name
    return state


def _schedule_preview(request, state: dict) -> dict:
    ctx = _ctx(request)
    if str(ctx.salon.pk) != str(state.get("salon_id")):
        raise ValidationError("مجموعه فعال تغییر کرده. اطلاعات برنامه را دوباره بگو.")
    raw_dates = list(state.get("dates") or [])
    if not raw_dates:
        return {
            "handled": True,
            "kind": "action_collect",
            "answer": "چه روزی یا چه روزهایی می‌خوای برنامه کاری ثبت کنی؟ مثلاً «فردا» یا «شنبه تا چهارشنبه».",
            "action_state": state,
            "suggestions": ["فردا", "شنبه تا چهارشنبه"],
        }
    if not state.get("start_time") or not state.get("end_time"):
        return {
            "handled": True,
            "kind": "action_collect",
            "answer": "ساعت شروع و پایان رو هم بگو؛ مثلاً «۹ صبح تا ۵ عصر».",
            "action_state": state,
            "suggestions": ["۹ صبح تا ۵ عصر", "۱۰ تا ۱۸"],
        }

    start_time = parse_hhmm(state["start_time"])
    end_time = parse_hhmm(state["end_time"])
    service = _service_match(
        salon=ctx.salon,
        stylist=ctx.stylist,
        text="",
        existing_id=state.get("service_id"),
    )
    dates = [parse_iso_date(value) for value in raw_dates]
    for value in dates:
        validate_staff_schedule_request_window(
            stylist=ctx.stylist,
            salon=ctx.salon,
            date_value=value,
            start_time=start_time,
            end_time=end_time,
            service=service,
        )

    token = issue_confirmation(
        user=request.user,
        action="stylist_schedule_create",
        data={
            "salon_id": ctx.salon.pk,
            "dates": [value.isoformat() for value in dates],
            "start_time": serialize_time(start_time),
            "end_time": serialize_time(end_time),
            "service_id": service.pk if service else None,
            "note": str(state.get("note") or "")[:500],
        },
    )
    rows = [
        {"label": "مجموعه", "value": ctx.salon.salon_name},
        {"label": "روزها", "value": "، ".join(date_label(value) for value in dates)},
        {"label": "ساعت", "value": f"{serialize_time(start_time)} تا {serialize_time(end_time)}"},
    ]
    if service:
        rows.append({"label": "خدمت مرتبط", "value": service.service_name})
    return {
        "handled": True,
        "kind": "action_preview",
        "answer": "این برنامه به‌صورت درخواست برای بررسی مدیر مجموعه ثبت می‌شه. اگر درسته تأییدش کن.",
        "action_state": state,
        "preview": {
            "title": "درخواست برنامه کاری",
            "icon": "calendar-days",
            "rows": rows,
            "notice": "برای چند روز، لومرا یک درخواست جدا برای هر روز ثبت می‌کند تا قوانین هر تاریخ مستقل بررسی شود.",
        },
        "confirmation_token": token,
        "confirm_label": "تأیید و ثبت درخواست",
        "cancel_label": "انصراف",
    }


def run_stylist_schedule(request, message: str, state: dict | None) -> dict:
    text = normalize_text(message)
    if state and state.get("mode") == "stylist_schedule" and any(term in text for term in CANCEL_TERMS):
        return {
            "handled": True,
            "kind": "action_cancelled",
            "answer": "باشه، ثبت برنامه کاری رو کنار گذاشتم.",
            "action_state": None,
        }
    state = _schedule_state(request, message, state)
    return _schedule_preview(request, state)


def _leave_state(request, message: str, state: dict | None) -> dict:
    ctx = _ctx(request)
    state = dict(state or {}) if (state or {}).get("mode") == "stylist_leave" else {"mode": "stylist_leave"}
    dates = parse_dates(message, allow_weekday_range=False)
    if dates:
        state["date"] = dates[0].isoformat()
    start, end = parse_time_range(message)
    if start and end:
        state["start_time"] = serialize_time(start)
        state["end_time"] = serialize_time(end)
    if any(term in normalize_text(message) for term in ("کل روز", "تمام روز", "تمام روزه", "یک روز کامل")):
        state["start_time"] = ""
        state["end_time"] = ""
        state["full_day"] = True
    state["salon_id"] = ctx.salon.pk
    state["salon_name"] = ctx.salon.salon_name
    return state


def _leave_preview(request, state: dict) -> dict:
    ctx = _ctx(request)
    if not state.get("date"):
        return {
            "handled": True,
            "kind": "action_collect",
            "answer": "مرخصی برای چه روزیه؟ مثلاً «فردا» یا نام روز رو بگو.",
            "action_state": state,
            "suggestions": ["فردا", "شنبه"],
        }
    date_value = parse_iso_date(state["date"])
    start = parse_hhmm(state.get("start_time"), required=False)
    end = parse_hhmm(state.get("end_time"), required=False)
    validate_salon_opening_window(
        salon=ctx.salon,
        date_value=date_value,
        start_time=start,
        end_time=end,
        allow_full_day=True,
    )
    # create_leave_request performs the authoritative appointment/leave
    # conflict check. We intentionally do not duplicate it in preview.
    token = issue_confirmation(
        user=request.user,
        action="stylist_leave_create",
        data={
            "salon_id": ctx.salon.pk,
            "date": date_value.isoformat(),
            "start_time": serialize_time(start),
            "end_time": serialize_time(end),
            "reason": str(state.get("reason") or "")[:500],
        },
    )
    period = "تمام روز" if not start and not end else f"{serialize_time(start)} تا {serialize_time(end)}"
    return {
        "handled": True,
        "kind": "action_preview",
        "answer": "درخواست مرخصی بعد از تأیید برای بررسی مدیر مجموعه ارسال می‌شه.",
        "action_state": state,
        "preview": {
            "title": "درخواست مرخصی",
            "icon": "calendar-xmark",
            "rows": [
                {"label": "مجموعه", "value": ctx.salon.salon_name},
                {"label": "تاریخ", "value": date_label(date_value)},
                {"label": "بازه", "value": period},
            ],
            "notice": "اگر در این بازه نوبت فعال داشته باشی، هنگام ثبت نهایی لومرا اجازه مرخصی نمی‌دهد.",
        },
        "confirmation_token": token,
        "confirm_label": "تأیید و ارسال درخواست",
        "cancel_label": "انصراف",
    }


def run_stylist_leave(request, message: str, state: dict | None) -> dict:
    text = normalize_text(message)
    if state and state.get("mode") == "stylist_leave" and any(term in text for term in CANCEL_TERMS):
        return {
            "handled": True,
            "kind": "action_cancelled",
            "answer": "باشه، درخواست مرخصی رو کنار گذاشتم.",
            "action_state": None,
        }
    state = _leave_state(request, message, state)
    return _leave_preview(request, state)


def _parse_amount_toman(message: str) -> int | None:
    text = normalize_text(message).replace(",", "")
    if any(term in text for term in ("همه", "کل", "تمام", "حداکثر")):
        return None
    import re
    match = re.search(r"(\d+(?:\.\d+)?)\s*(میلیون|هزار|تومن|تومان)?", text)
    if not match:
        return -1
    number = float(match.group(1))
    unit = match.group(2) or ""
    if unit == "میلیون":
        number *= 1_000_000
    elif unit == "هزار":
        number *= 1_000
    return int(number)


def _payout_preview(request, message: str, state: dict | None) -> dict:
    ctx = _ctx(request)
    if not ctx.can("can_request_payout", True):
        raise ValidationError("دسترسی ثبت درخواست برداشت برای این عضویت فعال نیست.")
    state = dict(state or {}) if (state or {}).get("mode") == "stylist_payout" else {"mode": "stylist_payout"}
    state["salon_id"] = ctx.salon.pk
    state["salon_name"] = ctx.salon.salon_name

    finance = build_stylist_finance_payload(ctx.stylist, salon=ctx.salon)
    payable = int(finance.get("staff_payable_amount") or 0)
    if payable <= 0:
        return {
            "handled": True,
            "kind": "action_notice",
            "answer": "الان مبلغ قابل پرداختی برای ثبت درخواست برداشت نداری.",
            "action_state": None,
        }

    parsed = _parse_amount_toman(message)
    if parsed == -1 and state.get("amount") is None:
        state["payable_amount"] = payable
        return {
            "handled": True,
            "kind": "action_collect",
            "answer": f"تا {payable:,} تومان قابل درخواست داری. چه مبلغی می‌خوای برداشت کنی؟",
            "action_state": state,
            "suggestions": ["کل مبلغ قابل دریافت"],
        }
    amount = payable if parsed is None else int(parsed if parsed >= 0 else state.get("amount") or payable)
    if amount <= 0:
        raise ValidationError("مبلغ برداشت باید بیشتر از صفر باشد.")
    if amount > payable:
        raise ValidationError(f"مبلغ درخواستی از موجودی قابل پرداخت بیشتره. حداکثر {payable:,} تومان قابل درخواست داری.")
    state["amount"] = amount
    state["payable_amount"] = payable
    token = issue_confirmation(
        user=request.user,
        action="stylist_payout_create",
        data={"salon_id": ctx.salon.pk, "amount": amount},
    )
    return {
        "handled": True,
        "kind": "action_preview",
        "answer": "مبلغ و مجموعه رو بررسی کن. بعد از تأیید، درخواست برداشت برای بررسی مالی ثبت می‌شه.",
        "action_state": state,
        "preview": {
            "title": "درخواست برداشت",
            "icon": "wallet",
            "rows": [
                {"label": "مجموعه", "value": ctx.salon.salon_name},
                {"label": "مبلغ", "value": f"{amount:,} تومان"},
                {"label": "قابل دریافت", "value": f"{payable:,} تومان"},
            ],
            "notice": "در زمان ثبت، موجودی قابل پرداخت دوباره محاسبه می‌شود.",
        },
        "confirmation_token": token,
        "confirm_label": "تأیید و ثبت درخواست برداشت",
        "cancel_label": "انصراف",
    }


def run_stylist_payout(request, message: str, state: dict | None) -> dict:
    text = normalize_text(message)
    if state and state.get("mode") == "stylist_payout" and any(term in text for term in CANCEL_TERMS):
        return {
            "handled": True,
            "kind": "action_cancelled",
            "answer": "باشه، درخواست برداشت رو کنار گذاشتم.",
            "action_state": None,
        }
    return _payout_preview(request, message, state)


def execute_stylist_confirmation(request, payload: dict) -> dict:
    action = payload.get("action")
    data = payload.get("data") or {}
    ctx = _ctx(request)
    if str(data.get("salon_id")) != str(ctx.salon.pk):
        raise ValidationError("مجموعه فعال تغییر کرده. عملیات را دوباره آماده کن.")

    if action == "stylist_schedule_create":
        dates = [parse_iso_date(value) for value in list(data.get("dates") or [])]
        if not dates or len(dates) > 7:
            raise ValidationError("روزهای برنامه کاری معتبر نیست.")
        start = parse_hhmm(data.get("start_time"))
        end = parse_hhmm(data.get("end_time"))
        service = _service_match(
            salon=ctx.salon,
            stylist=ctx.stylist,
            text="",
            existing_id=data.get("service_id"),
        )
        if data.get("service_id") and service is None:
            raise ValidationError("خدمت انتخاب‌شده دیگر در دسترس نیست.")
        created = []
        with transaction.atomic():
            for value in dates:
                item = create_schedule_request(
                    stylist=ctx.stylist,
                    salon=ctx.salon,
                    service=service,
                    date_value=value,
                    start_time=start,
                    end_time=end,
                    note=str(data.get("note") or "")[:500],
                )
                created.append(item)
        return {
            "handled": True,
            "kind": "action_success",
            "answer": f"{len(created)} درخواست برنامه کاری ثبت شد و برای بررسی مدیر مجموعه فرستاده شد.",
            "action_state": None,
            "success": {
                "title": "درخواست برنامه کاری ثبت شد",
                "detail": "، ".join(date_label(item.date) for item in created),
                "url": reverse("dashboards:stylist_schedule"),
                "url_label": "مشاهده برنامه و درخواست‌ها",
            },
        }

    if action == "stylist_leave_create":
        value = parse_iso_date(data.get("date"))
        start = parse_hhmm(data.get("start_time"), required=False)
        end = parse_hhmm(data.get("end_time"), required=False)
        item = create_leave_request(
            stylist=ctx.stylist,
            salon=ctx.salon,
            date_value=value,
            start_time=start,
            end_time=end,
            reason=str(data.get("reason") or "")[:500],
            actor=request.user,
            auto_approve=False,
        )
        return {
            "handled": True,
            "kind": "action_success",
            "answer": "درخواست مرخصی ثبت شد و برای بررسی مدیر مجموعه فرستاده شد.",
            "action_state": None,
            "success": {
                "title": "درخواست مرخصی ثبت شد",
                "detail": date_label(item.date),
                "url": reverse("dashboards:stylist_schedule"),
                "url_label": "پیگیری وضعیت درخواست",
            },
        }

    if action == "stylist_payout_create":
        if not ctx.can("can_request_payout", True):
            raise ValidationError("دسترسی ثبت درخواست برداشت برای این عضویت فعال نیست.")
        amount = int(data.get("amount") or 0)
        if amount <= 0:
            raise ValidationError("مبلغ برداشت معتبر نیست.")
        item = create_staff_payout_request(
            stylist=ctx.stylist,
            salon=ctx.salon,
            requested_by=request.user,
            amount=amount,
            note="ثبت از طریق لومی",
        )
        return {
            "handled": True,
            "kind": "action_success",
            "answer": f"درخواست برداشت {int(item.requested_amount or 0):,} تومان ثبت شد.",
            "action_state": None,
            "success": {
                "title": "درخواست برداشت ثبت شد",
                "detail": f"{int(item.requested_amount or 0):,} تومان",
                "url": reverse("dashboards:stylist_finance"),
                "url_label": "مشاهده مالی من",
            },
        }

    raise ValidationError("عملیات متخصص معتبر نیست.")
