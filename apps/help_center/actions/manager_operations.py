from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from apps.dashboards.appointment_management import (
    apply_partner_appointment_action,
    get_allowed_partner_actions,
)
from apps.orders.models import OrderDetail
from apps.salons.membership import normalize_mobile
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.stylists.dashboard_services import review_leave_request, review_schedule_request
from apps.stylists.models import StaffLeaveRequest, StaffScheduleRequest

from .common import date_label, issue_confirmation, normalize_text, resolve_current_path, serialize_time

CANCEL_TERMS = ("بیخیال", "بی خیال", "بی‌خیال", "ولش کن", "انصراف")
INVITE_TERMS = ("دعوت", "اضافه", "متخصص جدید", "عضو جدید")
INVITE_ACTION_TERMS = ("کن", "بفرست", "اضافه", "دعوت", "میخوام", "می خوام", "می‌خوام")


def _manager_salon(request) -> Salon:
    if not getattr(request.user, "is_authenticated", False) or not hasattr(request.user, "salon_manager_profile"):
        raise ValidationError("این عملیات از حساب مدیر مجموعه انجام می‌شود.")
    salon = (
        Salon.objects.select_related("salon_manager__user")
        .filter(salon_manager__user=request.user)
        .first()
    )
    if salon is None:
        raise ValidationError("برای این حساب، مجموعه‌ای پیدا نشد.")
    return salon


def _mobile_from_message(message: str) -> str:
    raw = str(message or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    match = re.search(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)", raw)
    if not match:
        return ""
    return normalize_mobile(match.group(0))


def _role_title_from_message(message: str) -> str:
    value = str(message or "").strip()
    match = re.search(r"(?:عنوان|سمت|تخصص)\s*[:：]?\s*([^،,.\n]{2,60})", value)
    return (match.group(1).strip() if match else "")[:60]


def _current_manager_appointment(request, current_path: str) -> tuple[Salon, OrderDetail] | None:
    match = resolve_current_path(current_path)
    if not match or match.view_name not in {
        "dashboards:appointment_detail",
        "dashboards:appointment_detail_legacy",
    }:
        return None
    appointment_id = match.kwargs.get("appointment_id")
    if not appointment_id:
        return None
    salon = _manager_salon(request)
    item = (
        OrderDetail.objects.select_related(
            "order",
            "order__customer__user",
            "service",
            "stylist__user",
            "salon",
        )
        .filter(pk=appointment_id, salon=salon)
        .first()
    )
    if item is None:
        return None
    return salon, item


def _appointment_rows(item: OrderDetail) -> list[dict]:
    customer = getattr(getattr(item.order, "customer", None), "user", None)
    customer_name = "مشتری"
    if customer is not None:
        try:
            customer_name = customer.get_fullName() or customer_name
        except Exception:
            customer_name = (
                f"{getattr(customer, 'name', '')} {getattr(customer, 'family', '')}".strip()
                or customer_name
            )
    stylist_name = "—"
    if getattr(item, "stylist", None):
        try:
            stylist_name = item.stylist.get_fullName()
        except Exception:
            stylist_name = str(item.stylist)
    return [
        {"label": "مشتری", "value": customer_name},
        {"label": "خدمت", "value": getattr(getattr(item, "service", None), "service_name", "—")},
        {"label": "متخصص", "value": stylist_name},
        {"label": "تاریخ", "value": date_label(item.date) if item.date else "—"},
        {"label": "ساعت", "value": serialize_time(item.time) if item.time else "—"},
    ]


def _run_current_appointment(request, message: str, current_path: str) -> dict | None:
    text = normalize_text(message)
    current = _current_manager_appointment(request, current_path)
    if current is None:
        return None
    salon, appointment = current
    allowed = set(get_allowed_partner_actions(appointment.order, appointment))

    wants_cancel = "لغو" in text and ("نوبت" in text or "این" in text)
    wants_paid = any(term in text for term in ("ثبت پرداخت", "ثبت کن پرداخت", "پرداخت شده", "تسویه", "پرداخت در مجموعه"))
    action = "cancel" if wants_cancel else ("mark_paid" if wants_paid else "")
    if not action:
        return None
    if action not in allowed:
        label = "لغو" if action == "cancel" else "ثبت پرداخت"
        return {
            "handled": True,
            "kind": "action_notice",
            "answer": f"{label} برای وضعیت فعلی این نوبت مجاز نیست.",
            "action_state": None,
        }

    token = issue_confirmation(
        user=request.user,
        action="manager_appointment_action",
        data={
            "salon_id": salon.pk,
            "appointment_id": appointment.pk,
            "partner_action": action,
        },
    )
    destructive = action == "cancel"
    title = "لغو این نوبت" if destructive else "ثبت پرداخت در مجموعه"
    return {
        "handled": True,
        "kind": "action_preview",
        "answer": (
            "جزئیات همین نوبت رو بررسی کن. با تأیید، نوبت لغو می‌شه و به مشتری اطلاع داده می‌شه."
            if destructive
            else "جزئیات همین نوبت رو بررسی کن. با تأیید، پرداخت در مجموعه روی همین نوبت ثبت می‌شه."
        ),
        "action_state": None,
        "preview": {
            "title": title,
            "icon": "calendar-xmark" if destructive else "money-check-dollar",
            "rows": _appointment_rows(appointment),
            "notice": "قبل از اجرا، وضعیت نوبت و مالکیت مجموعه دوباره بررسی می‌شود.",
            "danger": destructive,
        },
        "confirmation_token": token,
        "confirm_label": "تأیید لغو نوبت" if destructive else "تأیید ثبت پرداخت",
        "cancel_label": "بی‌خیال",
    }


def _serialize_schedule_request(request, item: StaffScheduleRequest) -> dict:
    stylist_name = item.stylist.get_fullName() if item.stylist else "متخصص"
    service_name = getattr(getattr(item, "service", None), "service_name", "همه خدمات")
    base = {
        "id": item.pk,
        "type": "schedule",
        "title": stylist_name,
        "subtitle": f"{service_name} · {date_label(item.date)} · {serialize_time(item.start_time)} تا {serialize_time(item.end_time)}",
        "detail": item.note or "بدون توضیح",
    }
    base["approve_token"] = issue_confirmation(
        user=request.user,
        action="manager_schedule_review",
        data={"request_id": item.pk, "approved": True, "salon_id": item.salon_id},
    )
    base["reject_token"] = issue_confirmation(
        user=request.user,
        action="manager_schedule_review",
        data={"request_id": item.pk, "approved": False, "salon_id": item.salon_id},
    )
    return base


def _serialize_leave_request(request, item: StaffLeaveRequest) -> dict:
    stylist_name = item.stylist.get_fullName() if item.stylist else "متخصص"
    if item.start_time and item.end_time:
        period = f"{serialize_time(item.start_time)} تا {serialize_time(item.end_time)}"
    else:
        period = "تمام روز"
    base = {
        "id": item.pk,
        "type": "leave",
        "title": stylist_name,
        "subtitle": f"{date_label(item.date)} · {period}",
        "detail": item.reason or "بدون توضیح",
    }
    base["approve_token"] = issue_confirmation(
        user=request.user,
        action="manager_leave_review",
        data={"request_id": item.pk, "approved": True, "salon_id": item.salon_id},
    )
    base["reject_token"] = issue_confirmation(
        user=request.user,
        action="manager_leave_review",
        data={"request_id": item.pk, "approved": False, "salon_id": item.salon_id},
    )
    return base


def _serialize_membership_request(request, item: SalonMembership) -> dict:
    stylist_name = item.stylist.get_fullName() if item.stylist else (item.invited_phone or "متخصص")
    base = {
        "id": item.pk,
        "type": "membership",
        "title": stylist_name,
        "subtitle": item.role_title or "درخواست همکاری",
        "detail": "درخواست عضویت در تیم این مجموعه",
    }
    base["approve_token"] = issue_confirmation(
        user=request.user,
        action="manager_membership_review",
        data={"membership_id": item.pk, "decision": "accept", "salon_id": item.salon_id},
    )
    base["reject_token"] = issue_confirmation(
        user=request.user,
        action="manager_membership_review",
        data={"membership_id": item.pk, "decision": "reject", "salon_id": item.salon_id},
    )
    return base


def _pending_requests(request, message: str) -> dict | None:
    text = normalize_text(message)
    asks_requests = any(term in text for term in ("درخواست", "درخواست ها", "درخواست‌های", "درخواستهای"))
    asks_pending = any(term in text for term in ("نشون", "نشان", "ببین", "بررسی", "در انتظار", "جدید"))
    if not asks_requests or not asks_pending:
        return None
    salon = _manager_salon(request)

    rows: list[dict] = []
    if "مرخصی" in text:
        rows = [
            _serialize_leave_request(request, item)
            for item in StaffLeaveRequest.objects.select_related("stylist__user", "salon")
            .filter(salon=salon, status=StaffLeaveRequest.Status.PENDING)
            .order_by("date", "start_time", "created_at")[:10]
        ]
        title = "درخواست‌های مرخصی در انتظار بررسی"
    elif "همکاری" in text or "عضویت" in text or "تیم" in text:
        rows = [
            _serialize_membership_request(request, item)
            for item in SalonMembership.objects.select_related("stylist__user", "salon")
            .filter(
                salon=salon,
                status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                stylist__isnull=False,
            )
            .order_by("created_at", "id")[:10]
        ]
        title = "درخواست‌های همکاری در انتظار بررسی"
    else:
        rows = [
            _serialize_schedule_request(request, item)
            for item in StaffScheduleRequest.objects.select_related("stylist__user", "salon", "service")
            .filter(salon=salon, status=StaffScheduleRequest.Status.PENDING)
            .order_by("date", "start_time", "created_at")[:10]
        ]
        title = "درخواست‌های برنامه کاری در انتظار بررسی"

    return {
        "handled": True,
        "kind": "action_review_list",
        "answer": f"{len(rows)} مورد پیدا کردم." if rows else "درخواستی برای بررسی پیدا نکردم.",
        "action_state": None,
        "review_list": {
            "title": title,
            "items": rows,
            "empty": not bool(rows),
            "manage_url": reverse("dashboards:scheduled_shifts") if "همکاری" not in text and "عضویت" not in text and "تیم" not in text else reverse("dashboards:team_member"),
        },
    }


def _invite_state(request, message: str, state: dict | None) -> dict:
    salon = _manager_salon(request)
    state = dict(state or {}) if (state or {}).get("mode") == "manager_invite" else {"mode": "manager_invite"}
    mobile = _mobile_from_message(message)
    if mobile:
        state["mobile_number"] = mobile
    role_title = _role_title_from_message(message)
    if role_title:
        state["role_title"] = role_title
    state["salon_id"] = salon.pk
    state["salon_name"] = salon.salon_name
    return state


def _invite_preview(request, state: dict) -> dict:
    salon = _manager_salon(request)
    if str(state.get("salon_id")) != str(salon.pk):
        raise ValidationError("مجموعه تغییر کرده. دعوت متخصص را دوباره آماده کن.")
    mobile = normalize_mobile(state.get("mobile_number") or "")
    if not mobile or len(mobile) < 10:
        return {
            "handled": True,
            "kind": "action_collect",
            "answer": "شماره موبایل متخصص رو بفرست تا دعوت رو آماده کنم.",
            "action_state": state,
            "suggestions": [],
        }
    token = issue_confirmation(
        user=request.user,
        action="manager_invite_prepare_submit",
        data={
            "salon_id": salon.pk,
            "mobile_number": mobile,
            "invitee_name": str(state.get("invitee_name") or "")[:80],
            "role_title": str(state.get("role_title") or "")[:80],
            "invite_message": str(state.get("invite_message") or "")[:500],
        },
    )
    rows = [
        {"label": "مجموعه", "value": salon.salon_name},
        {"label": "شماره موبایل", "value": mobile},
    ]
    if state.get("role_title"):
        rows.append({"label": "عنوان", "value": state["role_title"]})
    return {
        "handled": True,
        "kind": "action_preview",
        "answer": "دعوت رو آماده کردم. اگر شماره و مجموعه درسته، تأیید کن.",
        "action_state": state,
        "preview": {
            "title": "دعوت متخصص به مجموعه",
            "icon": "user-plus",
            "rows": rows,
            "notice": "بعد از تأیید، همان فرایند رسمی مدیریت تیم لومرا اجرا می‌شود.",
        },
        "confirmation_token": token,
        "confirm_label": "تأیید و ارسال دعوت",
        "cancel_label": "انصراف",
    }


def run_manager_operation(request, message: str, state: dict | None, *, current_path: str = "") -> dict | None:
    text = normalize_text(message)
    state = state or {}

    if state.get("mode") == "manager_invite":
        if any(term in text for term in CANCEL_TERMS):
            return {
                "handled": True,
                "kind": "action_cancelled",
                "answer": "باشه، دعوت متخصص رو کنار گذاشتم.",
                "action_state": None,
            }
        return _invite_preview(request, _invite_state(request, message, state))

    current_result = _run_current_appointment(request, message, current_path)
    if current_result is not None:
        return current_result

    pending = _pending_requests(request, message)
    if pending is not None:
        return pending

    if any(term in text for term in INVITE_TERMS) and any(term in text for term in INVITE_ACTION_TERMS) and "چطور" not in text and "چگونه" not in text:
        return _invite_preview(request, _invite_state(request, message, state))

    if "برداشت" in text and any(term in text for term in ("متخصص", "متخصص ها", "متخصص‌های", "متخصصها", "تیم")):
        return {
            "handled": True,
            "kind": "action_link",
            "answer": "درخواست‌های برداشت متخصص‌ها از بخش مالی مجموعه قابل بررسیه.",
            "action_state": None,
            "link": {
                "url": reverse("dashboards:finance_stylist_withdrawals"),
                "label": "باز کردن درخواست‌های برداشت",
                "icon": "wallet",
            },
        }

    navigation_verbs = ("باز کن", "ببر", "نشون بده", "نشان بده", "بریم", "میخوام برم", "می خوام برم", "می‌خوام برم")
    wants_navigation = any(term in text for term in navigation_verbs) and "چطور" not in text and "چگونه" not in text
    if wants_navigation:
        if any(term in text for term in ("تیم", "متخصص ها", "متخصص‌های", "اعضا", "اعضای تیم")):
            return {
                "handled": True,
                "kind": "action_link",
                "answer": "مدیریت تیم رو برات آماده کردم.",
                "action_state": None,
                "link": {
                    "url": reverse("dashboards:team_member"),
                    "label": "باز کردن مدیریت تیم",
                    "icon": "user-group",
                },
            }
        if any(term in text for term in ("شیفت", "برنامه تیم", "برنامه کاری تیم", "مرخصی ها", "مرخصی‌های")):
            return {
                "handled": True,
                "kind": "action_link",
                "answer": "برنامه و درخواست‌های تیم رو برات آماده کردم.",
                "action_state": None,
                "link": {
                    "url": reverse("dashboards:scheduled_shifts"),
                    "label": "باز کردن برنامه تیم",
                    "icon": "calendar-days",
                },
            }
        if any(term in text for term in ("خدمات", "سرویس", "منوی خدمات")):
            return {
                "handled": True,
                "kind": "action_link",
                "answer": "منوی خدمات مجموعه رو برات آماده کردم.",
                "action_state": None,
                "link": {
                    "url": reverse("dashboards:service_menu"),
                    "label": "باز کردن خدمات",
                    "icon": "scissors",
                },
            }
        if any(term in text for term in ("مالی", "گزارش مالی", "درآمد مجموعه", "تسویه مجموعه")):
            return {
                "handled": True,
                "kind": "action_link",
                "answer": "بخش مالی مجموعه رو برات آماده کردم.",
                "action_state": None,
                "link": {
                    "url": reverse("dashboards:finance_hub"),
                    "label": "باز کردن بخش مالی",
                    "icon": "chart-line",
                },
            }
        if "تقویم" in text or any(term in text for term in ("نوبت های مجموعه", "نوبت‌های مجموعه", "رزروهای مجموعه")):
            salon = _manager_salon(request)
            return {
                "handled": True,
                "kind": "action_link",
                "answer": "تقویم نوبت‌های مجموعه رو برات آماده کردم.",
                "action_state": None,
                "link": {
                    "url": reverse("dashboards:appointment_calendar", kwargs={"salon_id": salon.pk}),
                    "label": "باز کردن تقویم نوبت‌ها",
                    "icon": "calendar",
                },
            }

    return None


def execute_manager_confirmation(request, payload: dict) -> dict:
    action = str(payload.get("action") or "")
    data = payload.get("data") or {}
    salon = _manager_salon(request)
    if str(data.get("salon_id")) != str(salon.pk):
        raise ValidationError("این عملیات برای مجموعه فعلی معتبر نیست.")

    if action == "manager_schedule_review":
        with transaction.atomic():
            item = (
                StaffScheduleRequest.objects.select_for_update()
                .select_related("stylist__user", "salon", "service")
                .filter(
                    pk=data.get("request_id"),
                    salon=salon,
                    status=StaffScheduleRequest.Status.PENDING,
                )
                .first()
            )
            if item is None:
                raise ValidationError("این درخواست دیگر در انتظار بررسی نیست.")
            reviewed = review_schedule_request(
                schedule_request=item,
                reviewer=request.user,
                approved=bool(data.get("approved")),
                review_note="بررسی از طریق لومی",
            )
        approved = reviewed.status == StaffScheduleRequest.Status.APPROVED
        return {
            "handled": True,
            "kind": "action_success",
            "answer": f"درخواست برنامه کاری {reviewed.stylist.get_fullName()} {'تأیید' if approved else 'رد'} شد.",
            "action_state": None,
            "success": {
                "title": "درخواست بررسی شد",
                "detail": date_label(reviewed.date),
                "url": reverse("dashboards:scheduled_shifts"),
                "url_label": "مشاهده برنامه تیم",
            },
        }

    if action == "manager_leave_review":
        with transaction.atomic():
            item = (
                StaffLeaveRequest.objects.select_for_update()
                .select_related("stylist__user", "salon")
                .filter(
                    pk=data.get("request_id"),
                    salon=salon,
                    status=StaffLeaveRequest.Status.PENDING,
                )
                .first()
            )
            if item is None:
                raise ValidationError("این درخواست دیگر در انتظار بررسی نیست.")
            reviewed = review_leave_request(
                leave_request=item,
                reviewer=request.user,
                approved=bool(data.get("approved")),
                review_note="بررسی از طریق لومی",
            )
        approved = reviewed.status == StaffLeaveRequest.Status.APPROVED
        return {
            "handled": True,
            "kind": "action_success",
            "answer": f"درخواست مرخصی {reviewed.stylist.get_fullName()} {'تأیید' if approved else 'رد'} شد.",
            "action_state": None,
            "success": {
                "title": "درخواست مرخصی بررسی شد",
                "detail": date_label(reviewed.date),
                "url": reverse("dashboards:scheduled_shifts"),
                "url_label": "مشاهده برنامه تیم",
            },
        }

    if action == "manager_membership_review":
        item = (
            SalonMembership.objects.select_related("stylist__user", "salon")
            .filter(
                pk=data.get("membership_id"),
                salon=salon,
                status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                stylist__isnull=False,
            )
            .first()
        )
        if item is None:
            raise ValidationError("این درخواست همکاری دیگر در انتظار بررسی نیست.")
        decision = str(data.get("decision") or "")
        if decision not in {"accept", "reject"}:
            raise ValidationError("تصمیم بررسی معتبر نیست.")
        return {
            "handled": True,
            "kind": "action_form_submit",
            "answer": "تأیید شد؛ فرایند رسمی مدیریت تیم اجرا می‌شود.",
            "action_state": None,
            "form_submit": {
                "url": reverse("dashboards:membership_request_action", kwargs={"membership_id": item.pk}),
                "fields": {"action": decision},
            },
        }

    if action == "manager_invite_prepare_submit":
        mobile = normalize_mobile(data.get("mobile_number") or "")
        if not mobile or len(mobile) < 10:
            raise ValidationError("شماره موبایل متخصص معتبر نیست.")
        return {
            "handled": True,
            "kind": "action_form_submit",
            "answer": "تأیید شد؛ دعوت از مسیر رسمی مدیریت تیم ارسال می‌شود.",
            "action_state": None,
            "form_submit": {
                "url": reverse("dashboards:create_stylist_invite"),
                "fields": {
                    "mobile_number": mobile,
                    "invitee_name": str(data.get("invitee_name") or "")[:80],
                    "role_title": str(data.get("role_title") or "")[:80],
                    "invite_message": str(data.get("invite_message") or "")[:500],
                },
            },
        }

    if action == "manager_appointment_action":
        appointment = (
            OrderDetail.objects.select_related("order", "service", "stylist__user", "salon")
            .filter(pk=data.get("appointment_id"), salon=salon)
            .first()
        )
        if appointment is None:
            raise ValidationError("این نوبت در مجموعه فعلی پیدا نشد.")
        partner_action = str(data.get("partner_action") or "")
        with transaction.atomic():
            message = apply_partner_appointment_action(
                appointment.order,
                appointment,
                partner_action,
                actor=request.user,
            )
        return {
            "handled": True,
            "kind": "action_success",
            "answer": message,
            "action_state": None,
            "success": {
                "title": "نوبت به‌روزرسانی شد",
                "detail": getattr(getattr(appointment, "service", None), "service_name", "نوبت"),
                "url": reverse(
                    "dashboards:appointment_detail",
                    kwargs={"salon_id": salon.pk, "appointment_id": appointment.pk},
                ),
                "url_label": "مشاهده نوبت",
            },
        }

    raise ValidationError("عملیات مدیر معتبر نیست.")
