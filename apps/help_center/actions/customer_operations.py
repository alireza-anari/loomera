from __future__ import annotations

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import OrderDetail

from .common import (
    date_label,
    issue_confirmation,
    normalize_text,
    parse_relative_date,
    resolve_current_path,
    serialize_time,
)


def _current_customer_appointment(request, current_path: str) -> OrderDetail | None:
    if not getattr(request.user, "is_authenticated", False) or not hasattr(request.user, "customer_profile"):
        return None
    match = resolve_current_path(current_path)
    if not match or match.view_name not in {
        "orders:appointment_detail",
        "orders:appointment_detail_legacy",
        "orders:appointment_sms",
    }:
        return None
    pk = match.kwargs.get("pk")
    if not pk:
        return None
    return (
        OrderDetail.objects.select_related(
            "order",
            "order__customer__user",
            "salon",
            "service",
            "stylist__user",
        )
        .filter(pk=pk, order__customer__user=request.user)
        .first()
    )


def _rows(item: OrderDetail) -> list[dict]:
    stylist_name = "—"
    if getattr(item, "stylist", None):
        try:
            stylist_name = item.stylist.get_fullName()
        except Exception:
            stylist_name = str(item.stylist)
    return [
        {"label": "خدمت", "value": getattr(getattr(item, "service", None), "service_name", "—")},
        {"label": "مجموعه", "value": getattr(getattr(item, "salon", None), "salon_name", "—")},
        {"label": "متخصص", "value": stylist_name},
        {"label": "تاریخ", "value": date_label(item.date) if item.date else "—"},
        {"label": "ساعت", "value": serialize_time(item.time) if item.time else "—"},
    ]


RESCHEDULE_TERMS = ("تغییر زمان", "عوض کنم", "عوضش کن", "جابه جا", "جابجا", "زمانش رو", "زمان نوبت")


def _wants_cancel(text: str) -> bool:
    return "لغو" in text and any(term in text for term in ("نوبت", "رزرو", "وقت", "این"))


def _wants_reschedule(text: str) -> bool:
    return any(term in text for term in RESCHEDULE_TERMS)


def _cancel_preview(request, item: OrderDetail) -> dict:
    if not item.can_cancel():
        return {
            "handled": True,
            "kind": "action_notice",
            "answer": "امکان لغو این نوبت در وضعیت فعلی وجود نداره. اگر لازم باشه می‌تونی از پشتیبانی یا خود مجموعه پیگیری کنی.",
            "action_state": None,
        }
    token = issue_confirmation(
        user=request.user,
        action="customer_cancel_current_appointment",
        data={"appointment_id": item.pk},
    )
    return {
        "handled": True,
        "kind": "action_preview",
        "answer": "جزئیات نوبت رو بررسی کن و فقط اگر مطمئنی لغوش کن.",
        "action_state": None,
        "preview": {
            "title": "لغو نوبت",
            "icon": "calendar-xmark",
            "rows": _rows(item),
            "notice": "در مرحله اجرا، امکان لغو و مالکیت نوبت دوباره توسط سیستم اصلی لومرا بررسی می‌شود.",
            "danger": True,
        },
        "confirmation_token": token,
        "confirm_label": "تأیید لغو نوبت",
        "cancel_label": "بی‌خیال",
    }


def _reschedule_link(item: OrderDetail) -> dict:
    return {
        "handled": True,
        "kind": "action_link",
        "answer": "صفحه انتخاب زمان جدید همین نوبت رو آماده کردم؛ زمان‌های آزاد واقعی اونجا دوباره بررسی می‌شن.",
        "action_state": None,
        "link": {
            "url": reverse("orders:reschedule", kwargs={"pk": item.pk}),
            "label": "تغییر زمان این نوبت",
            "icon": "calendar-days",
        },
    }


def _owned_upcoming_appointments(request, message: str, *, intent: str) -> list[OrderDetail]:
    qs = (
        OrderDetail.objects.select_related(
            "order",
            "order__customer__user",
            "salon",
            "service",
            "stylist__user",
        )
        .filter(
            order__customer__user=request.user,
            date__gte=timezone.localdate(),
        )
        .order_by("date", "time", "pk")
    )
    requested_date = parse_relative_date(message)
    if requested_date is not None:
        qs = qs.filter(date=requested_date)
    rows = list(qs[:20])
    if intent == "cancel":
        rows = [item for item in rows if item.can_cancel()]
    return rows[:8]


def _choice_item(request, item: OrderDetail, *, intent: str) -> dict:
    token = issue_confirmation(
        user=request.user,
        action="customer_choose_appointment",
        data={"appointment_id": item.pk, "intent": intent},
    )
    stylist_name = ""
    if getattr(item, "stylist", None):
        try:
            stylist_name = item.stylist.get_fullName()
        except Exception:
            stylist_name = str(item.stylist)
    return {
        "title": getattr(getattr(item, "service", None), "service_name", "نوبت"),
        "subtitle": f"{getattr(getattr(item, 'salon', None), 'salon_name', 'مجموعه')} · {date_label(item.date)} · {serialize_time(item.time)}",
        "detail": stylist_name,
        "choice_token": token,
        "choice_label": "انتخاب این نوبت",
    }


def is_customer_appointment_operation_candidate(
    message: str,
    *,
    current_path: str,
    has_customer_role: bool,
) -> bool:
    if not has_customer_role:
        return False
    text = normalize_text(message)
    if "چطور" in text or "چگونه" in text:
        return False
    if is_customer_current_appointment_candidate(
        message, current_path=current_path, has_customer_role=has_customer_role
    ):
        return True
    return _wants_cancel(text) or _wants_reschedule(text)


def run_customer_appointment_operation(request, message: str, *, current_path: str) -> dict | None:
    current = run_customer_current_appointment(request, message, current_path=current_path)
    if current is not None:
        return current

    text = normalize_text(message)
    intent = "cancel" if _wants_cancel(text) else ("reschedule" if _wants_reschedule(text) else "")
    if not intent:
        return None

    rows = _owned_upcoming_appointments(request, message, intent=intent)
    if not rows:
        label = "قابل لغو" if intent == "cancel" else "آینده"
        return {
            "handled": True,
            "kind": "action_link",
            "answer": f"نوبت {label}ی که با این درخواست تطبیق داشته باشه پیدا نکردم. فهرست نوبت‌هات رو باز کن و مورد درست رو بررسی کن.",
            "action_state": None,
            "link": {
                "url": reverse("orders:appointments"),
                "label": "مشاهده نوبت‌های من",
                "icon": "calendar-check",
            },
        }
    if len(rows) == 1:
        return _cancel_preview(request, rows[0]) if intent == "cancel" else _reschedule_link(rows[0])

    return {
        "handled": True,
        "kind": "action_choice_list",
        "answer": "چند نوبت با درخواستت جور درمیاد. مورد درست رو انتخاب کن تا قبل از هر تغییری جزئیاتش رو نشون بدم.",
        "action_state": None,
        "choice_list": {
            "title": "کدوم نوبت؟",
            "items": [_choice_item(request, item, intent=intent) for item in rows],
        },
    }


def resolve_customer_choice(request, payload: dict) -> dict:
    if payload.get("action") != "customer_choose_appointment":
        raise ValidationError("انتخاب نوبت معتبر نیست.")
    data = payload.get("data") or {}
    item = (
        OrderDetail.objects.select_related(
            "order", "order__customer__user", "salon", "service", "stylist__user"
        )
        .filter(pk=data.get("appointment_id"), order__customer__user=request.user)
        .first()
    )
    if item is None:
        raise ValidationError("این نوبت برای حساب فعلی پیدا نشد.")
    intent = str(data.get("intent") or "")
    if intent == "cancel":
        return _cancel_preview(request, item)
    if intent == "reschedule":
        return _reschedule_link(item)
    raise ValidationError("نوع عملیات نوبت معتبر نیست.")


def is_customer_current_appointment_candidate(message: str, *, current_path: str, has_customer_role: bool) -> bool:
    if not has_customer_role:
        return False
    text = normalize_text(message)
    if "چطور" in text or "چگونه" in text:
        return False
    match = resolve_current_path(current_path)
    if not match or match.view_name not in {
        "orders:appointment_detail",
        "orders:appointment_detail_legacy",
        "orders:appointment_sms",
    }:
        return False
    return (
        ("لغو" in text and ("نوبت" in text or "این" in text))
        or any(term in text for term in ("تغییر زمان", "عوض کنم", "عوضش کن", "جابه جا", "جابجا", "زمانش رو"))
    )


def run_customer_current_appointment(request, message: str, *, current_path: str) -> dict | None:
    text = normalize_text(message)
    item = _current_customer_appointment(request, current_path)
    if item is None:
        return None

    wants_cancel = _wants_cancel(text)
    wants_reschedule = _wants_reschedule(text)

    if wants_reschedule:
        return _reschedule_link(item)

    if wants_cancel:
        return _cancel_preview(request, item)
    return None


def execute_customer_confirmation(request, payload: dict) -> dict:
    if payload.get("action") != "customer_cancel_current_appointment":
        raise ValidationError("عملیات مشتری معتبر نیست.")
    data = payload.get("data") or {}
    item = (
        OrderDetail.objects.select_related("order", "order__customer")
        .filter(pk=data.get("appointment_id"), order__customer__user=request.user)
        .first()
    )
    if item is None:
        raise ValidationError("این نوبت برای حساب فعلی پیدا نشد.")
    if not item.can_cancel():
        raise ValidationError("امکان لغو این نوبت در وضعیت فعلی وجود ندارد.")
    # Reuse the existing customer cancellation endpoint. It owns refund/payment
    # rules and performs another authoritative ownership/cancelability check.
    return {
        "handled": True,
        "kind": "action_remote_post",
        "answer": "تأیید شد؛ لغو از مسیر اصلی نوبت انجام می‌شود.",
        "action_state": None,
        "remote_post": {
            "url": reverse("orders:cancel_appointment", kwargs={"pk": item.pk}),
            "success_url": reverse("orders:appointments"),
            "success_label": "مشاهده نوبت‌های من",
        },
    }
