from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from django.conf import settings

from loomera.logging_utils import mask_email, mask_mobile
from django.db import transaction
from django.utils import timezone

from apps.comments_scores_favories.models import Comments
from apps.dashboards.jalali_utils import (
    format_jalali_with_weekday,
    format_time_fa,
    to_persian_digits,
)
from .models import AppointmentNotification, Order, OrderDetail
from .notification_delivery import maybe_deliver_immediately

logger = logging.getLogger(__name__)


LIFECYCLE_LABELS = {
    "booked": "رزرو ثبت شد",
    "awaiting_stylist_confirmation": "در انتظار تایید متخصص",
    "stylist_confirmed": "متخصص تایید کرد",
    "arrived": "مشتری به سالن رسید",
    "in_service": "انجام کار شروع شد",
    "completed": "پایان کار",
    "no_show": "عدم حضور تأیید شد",
    "pay_in_salon_pending": "پرداخت در سالن مانده است",
    "paid": "پرداخت انجام شد",
    "review_pending": "آماده ثبت نظرسنجی",
    "reviewed": "نظرسنجی ثبت شد",
    "cancelled": "رزرو لغو شد",
}


def _safe_localtime(value):
    if not value:
        return None
    try:
        return timezone.localtime(value) if timezone.is_aware(value) else value
    except Exception:
        return value


def _format_progress_datetime(value):
    local_value = _safe_localtime(value)
    if not local_value:
        return ""

    try:
        if hasattr(local_value, "date") and hasattr(local_value, "time"):
            return f"{format_jalali_with_weekday(local_value.date())} • ساعت {format_time_fa(local_value.time())}"

        return format_jalali_with_weekday(local_value)
    except Exception:
        return ""


def get_order_items(order: Order):
    return list(
        order.order_details1.select_related(
            "service", "stylist__user", "salon"
        ).order_by("date", "time", "id")
    )


def get_primary_appointment(order: Order):
    items = get_order_items(order)
    return items[0] if items else None


def get_order_visit_window(order: Order):
    items = get_order_items(order)
    if not items:
        return None, None
    first_item = items[0]
    last_item = items[-1]
    if not first_item.date or not first_item.time:
        return None, None
    start_naive = datetime.combine(first_item.date, first_item.time)
    end_naive = datetime.combine(last_item.date, last_item.end_time or last_item.time)
    tz = timezone.get_current_timezone()
    start_dt = (
        timezone.make_aware(start_naive, tz)
        if timezone.is_naive(start_naive)
        else start_naive
    )
    end_dt = (
        timezone.make_aware(end_naive, tz)
        if timezone.is_naive(end_naive)
        else end_naive
    )
    return timezone.localtime(start_dt), timezone.localtime(end_dt)


def build_notification_meta(order: Order):
    start_dt, _ = get_order_visit_window(order)
    if start_dt:
        return f"{format_jalali_with_weekday(start_dt.date())} • {format_time_fa(start_dt.time())}"
    primary = get_primary_appointment(order)
    if primary and primary.date:
        return format_jalali_with_weekday(primary.date)
    return ""


def determine_current_stage(order: Order) -> str:
    if order.status == "cancelled":
        return "cancelled"
    if order.status == "no_show":
        return "no_show"
    if order.review_completed_at:
        return "reviewed"
    if (
        order.service_completed_at
        and order.selected_payment_method == "pay_in_salon"
        and not order.is_paid
    ):
        return "pay_in_salon_pending"
    if order.review_requested_at:
        return "review_pending"
    if order.is_paid and order.service_completed_at:
        return "paid"
    if order.service_completed_at:
        return "completed"
    if order.service_started_at:
        return "in_service"
    if order.customer_arrived_at:
        return "arrived"
    if order.stylist_confirmed_at or order.stylist_approved:
        return "stylist_confirmed"
    if order.is_paid or order.status in {"paid", "confirmed", "pending"}:
        return "awaiting_stylist_confirmation"
    return "booked"


def build_progress_steps(order: Order):
    steps = [
        {
            "key": "booked",
            "label": LIFECYCLE_LABELS["booked"],
            "is_done": True,
            "is_current": False,
            "meta": _format_progress_datetime(order.register_date),
            "description": "رزرو شما ثبت شد و برای تایید متخصص ارسال شد.",
        },
        {
            "key": "awaiting_stylist_confirmation",
            "label": LIFECYCLE_LABELS["awaiting_stylist_confirmation"],
            "is_done": bool(order.stylist_confirmed_at or order.stylist_approved),
            "is_current": False,
            "meta": (
                "منتظر تایید متخصص"
                if not (order.stylist_confirmed_at or order.stylist_approved)
                else "تایید شد"
            ),
            "description": "متخصص در حال بررسی نوبت شماست. بعد از تایید، وضعیت نوبت به‌روزرسانی می‌شود.",
        },
        {
            "key": "stylist_confirmed",
            "label": LIFECYCLE_LABELS["stylist_confirmed"],
            "is_done": bool(order.stylist_confirmed_at or order.stylist_approved),
            "is_current": False,
            "meta": (
                _format_progress_datetime(order.stylist_confirmed_at)
                if order.stylist_confirmed_at
                else ""
            ),
            "description": "نوبت شما توسط متخصص تایید شده است.",
        },
        {
            "key": "arrived",
            "label": LIFECYCLE_LABELS["arrived"],
            "is_done": bool(order.customer_arrived_at),
            "is_current": False,
            "meta": _format_progress_datetime(order.customer_arrived_at),
            "description": "حضور شما در سالن ثبت شده است.",
        },
        {
            "key": "in_service",
            "label": LIFECYCLE_LABELS["in_service"],
            "is_done": bool(order.service_started_at),
            "is_current": False,
            "meta": _format_progress_datetime(order.service_started_at),
            "description": "خدمت شما در حال انجام است.",
        },
        {
            "key": "completed",
            "label": LIFECYCLE_LABELS["completed"],
            "is_done": bool(order.service_completed_at),
            "is_current": False,
            "meta": _format_progress_datetime(order.service_completed_at),
            "description": "خدمت شما به پایان رسیده است.",
        },
    ]

    if order.selected_payment_method == "pay_in_salon":
        steps.append(
            {
                "key": "pay_in_salon_pending",
                "label": LIFECYCLE_LABELS["pay_in_salon_pending"],
                "is_done": bool(order.is_paid),
                "is_current": False,
                "meta": "پرداخت در سالن" if not order.is_paid else "پرداخت نهایی شد",
                "description": "پرداخت این نوبت در سالن تکمیل می‌شود.",
            }
        )
    else:
        steps.append(
            {
                "key": "paid",
                "label": LIFECYCLE_LABELS["paid"],
                "is_done": bool(order.is_paid),
                "is_current": False,
                "meta": "پرداخت انجام شده" if order.is_paid else "در انتظار پرداخت",
                "description": "پرداخت این نوبت ثبت شده است.",
            }
        )

    steps.append(
        {
            "key": "review_pending",
            "label": LIFECYCLE_LABELS["review_pending"],
            "is_done": bool(order.review_requested_at),
            "is_current": False,
            "meta": _format_progress_datetime(order.review_requested_at),
            "description": "می‌توانید تجربه خود از این نوبت را ثبت کنید.",
        }
    )

    steps.append(
        {
            "key": "reviewed",
            "label": LIFECYCLE_LABELS["reviewed"],
            "is_done": bool(order.review_completed_at),
            "is_current": False,
            "meta": _format_progress_datetime(order.review_completed_at),
            "description": "دیدگاه شما ثبت شده است.",
        }
    )

    current_stage = determine_current_stage(order)

    # اگر رزرو تازه ثبت شده و هنوز متخصص تایید نکرده، مرحله فعال باید انتظار تایید باشد.
    if current_stage == "booked" and not (
        order.stylist_confirmed_at or order.stylist_approved
    ):
        current_stage = "awaiting_stylist_confirmation"

    reached_current = False

    for step in steps:
        if step["key"] == current_stage:
            step["is_current"] = True
            reached_current = True
        elif not reached_current:
            step["is_done"] = (
                True if step["key"] == "booked" or step["is_done"] else step["is_done"]
            )

    return steps, current_stage


def build_customer_progress_context(order: Order):
    steps, current_stage = build_progress_steps(order)
    current_step = next(
        (step for step in steps if step.get("key") == current_stage),
        None,
    )

    if current_step is None:
        current_step = {
            "key": current_stage,
            "label": LIFECYCLE_LABELS.get(current_stage, "وضعیت رزرو"),
            "is_done": False,
            "is_current": True,
            "meta": "",
            "description": "",
        }
    reminder_text = ""
    if order.reminder_due_at:
        local_due = _safe_localtime(order.reminder_due_at)
        reminder_text = f"یادآوری این نوبت برای {format_jalali_with_weekday(local_due.date())} ساعت {format_time_fa(local_due.time())} برنامه‌ریزی شده است."
    elif order.reminder_status == "skipped":
        reminder_text = "به‌دلیل نزدیک بودن زمان رزرو یا نبود زمان معتبر، یادآوری خودکار زمان‌بندی نشد."

    cash_payment = None
    cash_meta = {}
    try:
        cash_payment = (
            order.payment_order.filter(
                purpose="appointment",
                provider="manual",
                meta__source="pay_in_salon_cash",
            )
            .order_by("-id")
            .first()
        )
        cash_meta = (
            cash_payment.meta
            if cash_payment and isinstance(cash_payment.meta, dict)
            else {}
        )
    except Exception:
        cash_payment = None
        cash_meta = {}

    cash_customer_confirmed = bool(cash_meta.get("customer_confirmed_at"))
    cash_stylist_confirmed = bool(cash_meta.get("stylist_confirmed_at"))
    is_verified_salon = (
        getattr(getattr(order, "salon", None), "verification_status", "") == "verified"
    )
    needs_pay_in_salon = bool(
        order.selected_payment_method == "pay_in_salon"
        and order.service_completed_at
        and not order.is_paid
    )

    current_step = next(
        (step for step in steps if step.get("key") == current_stage),
        None,
    )

    if current_step is None:
        current_step = {
            "key": current_stage,
            "label": LIFECYCLE_LABELS.get(current_stage, "وضعیت رزرو"),
            "is_done": False,
            "is_current": True,
            "meta": "",
            "description": "",
        }

    return {
        "current_stage": current_stage,
        "current_stage_label": LIFECYCLE_LABELS.get(current_stage, "وضعیت رزرو"),
        "current_step": current_step,
        "current_step_label": current_step.get(
            "label", LIFECYCLE_LABELS.get(current_stage, "وضعیت رزرو")
        ),
        "steps": steps,
        "reminder_text": reminder_text,
        "needs_stylist_confirmation": not bool(
            order.stylist_confirmed_at or order.stylist_approved
        ),
        "needs_pay_in_salon": needs_pay_in_salon,
        "pay_in_salon_online_enabled": bool(needs_pay_in_salon and is_verified_salon),
        "pay_in_salon_cash_customer_confirmed": cash_customer_confirmed,
        "pay_in_salon_cash_stylist_confirmed": cash_stylist_confirmed,
        "pay_in_salon_cash_waiting_for_stylist": bool(
            cash_customer_confirmed and not cash_stylist_confirmed and not order.is_paid
        ),
        "pay_in_salon_cash_waiting_for_customer": bool(
            cash_stylist_confirmed and not cash_customer_confirmed and not order.is_paid
        ),
        "can_review": bool(order.review_requested_at and not order.review_completed_at),
    }


@transaction.atomic
def schedule_order_reminder(order: Order):
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    start_dt, _ = get_order_visit_window(locked_order)
    if not start_dt:
        locked_order.reminder_due_at = None
        locked_order.reminder_sent_at = None
        locked_order.reminder_status = "skipped"
        locked_order.save(
            update_fields=[
                "reminder_due_at",
                "reminder_sent_at",
                "reminder_status",
                "update_date",
            ]
        )
        return locked_order

    due_at = start_dt - timedelta(hours=2)
    now = timezone.now()
    if due_at <= now:
        locked_order.reminder_due_at = due_at
        locked_order.reminder_sent_at = None
        locked_order.reminder_status = "skipped"
        locked_order.save(
            update_fields=[
                "reminder_due_at",
                "reminder_sent_at",
                "reminder_status",
                "update_date",
            ]
        )
        return locked_order

    locked_order.reminder_due_at = due_at
    locked_order.reminder_sent_at = None
    locked_order.reminder_status = "scheduled"
    locked_order.save(
        update_fields=[
            "reminder_due_at",
            "reminder_sent_at",
            "reminder_status",
            "update_date",
        ]
    )
    create_notification(
        order=locked_order,
        audience_role="system",
        channel="system",
        event_type="reminder_scheduled",
        title="یادآوری نوبت زمان‌بندی شد",
        body=f"برای این رزرو، یادآوری ۲ ساعت قبل از مراجعه در {build_notification_meta(locked_order)} برنامه‌ریزی شد.",
        delivery_status="queued",
        meta={"reminder_due_at": due_at.isoformat()},
    )
    return locked_order


@transaction.atomic
def cancel_order_reminder(order: Order):
    """Mark a scheduled appointment reminder as cancelled when the booking is cancelled.

    This keeps the booking lifecycle data clean and prevents stale scheduled
    reminders from appearing in customer progress state.
    """
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    if locked_order.reminder_status in {"sent", "cancelled", "skipped"}:
        return locked_order

    locked_order.reminder_status = "cancelled"
    locked_order.save(update_fields=["reminder_status", "update_date"])
    return locked_order


def _create_email_notification(
    *,
    order: Order,
    audience_role: str,
    target_user,
    title: str,
    body: str,
    event_type: str,
):
    notification = create_notification(
        order=order,
        audience_role=audience_role,
        target_user=target_user,
        channel="email",
        event_type=event_type,
        title=title,
        body=body,
        delivery_status="queued",
        meta={"queued_at": timezone.now().isoformat()},
    )
    return maybe_deliver_immediately(notification)


def _create_sms_notification(
    *,
    order: Order,
    title: str,
    body: str,
    event_type: str,
    audience_role: str = "customer",
    customer=None,
    stylist=None,
    target_user=None,
    order_detail=None,
):
    if target_user is None:
        if customer is not None:
            target_user = getattr(customer, "user", None)
        elif stylist is not None:
            target_user = getattr(stylist, "user", None)

    notification = create_notification(
        order=order,
        order_detail=order_detail,
        audience_role=audience_role,
        customer=customer,
        stylist=stylist,
        target_user=target_user,
        channel="sms",
        event_type=event_type,
        title=title,
        body=body,
        delivery_status="queued",
        meta={"queued_at": timezone.now().isoformat()},
    )
    return maybe_deliver_immediately(notification)


def create_notification(
    *,
    order: Order,
    audience_role: str,
    channel: str,
    event_type: str,
    title: str,
    body: str,
    delivery_status: str = "sent",
    order_detail: OrderDetail | None = None,
    customer=None,
    stylist=None,
    target_user=None,
    meta: dict | None = None,
):
    notification = AppointmentNotification.objects.create(
        order=order,
        order_detail=order_detail,
        salon=order.salon,
        customer=customer or getattr(order, "customer", None),
        stylist=stylist,
        target_user=target_user,
        audience_role=audience_role,
        channel=channel,
        event_type=event_type,
        title=title,
        body=body,
        delivery_status=delivery_status,
        meta=meta or {},
    )
    try:
        from apps.notifications.services import sync_legacy_appointment_notification

        sync_legacy_appointment_notification(notification)
    except Exception:
        pass
    return notification


def notify_manager_and_stylists_for_booking(order: Order, *, event_type: str):
    order = Order.objects.select_related(
        "customer__user", "salon__salon_manager__user"
    ).get(pk=order.pk)
    items = get_order_items(order)
    meta_label = build_notification_meta(order)
    customer_name = order.customer.get_fullName()
    service_names = (
        "، ".join(
            sorted({item.service.service_name for item in items if item.service_id})
        )
        or "خدمت رزرو شده"
    )
    manager_user = (
        getattr(getattr(order.salon, "salon_manager", None), "user", None)
        if order.salon_id
        else None
    )

    title = (
        "رزرو جدید ثبت شد" if event_type == "booking_created" else "پرداخت رزرو ثبت شد"
    )
    body = f"{customer_name} برای {service_names} در {meta_label or 'برنامه رزرو'} ثبت شده است."

    if event_type == "booking_created":
        customer_user = getattr(order.customer, "user", None)
        if customer_user:
            create_notification(
                order=order,
                audience_role="customer",
                channel="dashboard",
                event_type="booking_created",
                title="رزرو شما ثبت شد",
                body=f"رزرو شما برای {service_names} در {meta_label or 'زمان انتخاب‌شده'} ثبت شد و در انتظار تایید مجموعه/متخصص است.",
                target_user=customer_user,
                delivery_status="sent",
                meta={"panel": "customer", "date_label": meta_label},
            )

    if manager_user:
        create_notification(
            order=order,
            audience_role="manager",
            channel="dashboard",
            event_type=event_type,
            title=title,
            body=body,
            target_user=manager_user,
            delivery_status="sent",
            meta={"panel": "dashboard", "date_label": meta_label},
        )

    notified_stylist_ids = set()
    for item in items:
        stylist = item.stylist
        if not stylist or stylist.pk in notified_stylist_ids:
            continue
        notified_stylist_ids.add(stylist.pk)
        stylist_title = (
            "رزرو جدید نیازمند تایید شماست"
            if not order.stylist_approved
            else "رزرو جدید برای شما ثبت شد"
        )
        stylist_body = f"{customer_name} برای {item.service.service_name if item.service_id else 'خدمت'} در {meta_label or 'برنامه رزرو'} به شما تخصیص داده شد."
        create_notification(
            order=order,
            order_detail=item,
            audience_role="stylist",
            channel="dashboard",
            event_type=event_type,
            title=stylist_title,
            body=stylist_body,
            stylist=stylist,
            target_user=getattr(stylist, "user", None),
            delivery_status="sent",
            meta={"detail_id": item.id, "date_label": meta_label},
        )
        _create_email_notification(
            order=order,
            audience_role="stylist",
            target_user=getattr(stylist, "user", None),
            title=stylist_title,
            body=stylist_body,
            event_type=event_type,
        )
        _create_sms_notification(
            order=order,
            order_detail=item,
            audience_role="stylist",
            stylist=stylist,
            target_user=getattr(stylist, "user", None),
            title=stylist_title,
            body=stylist_body,
            event_type=event_type,
        )


def notify_customer_after_stylist_confirmation(order: Order):
    order = Order.objects.select_related("customer__user", "salon").get(pk=order.pk)
    title = "نوبت شما توسط متخصص تایید شد"
    body = f"رزرو شما برای {build_notification_meta(order) or 'نوبت ثبت‌شده'} تایید شد و در برنامه سالن قرار گرفت."
    create_notification(
        order=order,
        audience_role="customer",
        channel="dashboard",
        event_type="stylist_confirmed",
        title=title,
        body=body,
        target_user=getattr(order.customer, "user", None),
        delivery_status="sent",
        meta={"stage": "stylist_confirmed"},
    )
    _create_email_notification(
        order=order,
        audience_role="customer",
        target_user=getattr(order.customer, "user", None),
        title=title,
        body=body,
        event_type="stylist_confirmed",
    )
    _create_sms_notification(
        order=order,
        audience_role="customer",
        customer=order.customer,
        target_user=getattr(order.customer, "user", None),
        title=title,
        body=body,
        event_type="stylist_confirmed",
    )


def notify_operational_milestone(
    order: Order, *, event_type: str, title: str, body: str
):
    order = Order.objects.select_related(
        "customer__user", "salon__salon_manager__user"
    ).get(pk=order.pk)
    manager_user = (
        getattr(getattr(order.salon, "salon_manager", None), "user", None)
        if order.salon_id
        else None
    )
    customer_user = getattr(order.customer, "user", None)

    create_notification(
        order=order,
        audience_role="customer",
        channel="dashboard",
        event_type=event_type,
        title=title,
        body=body,
        target_user=customer_user,
        delivery_status="sent",
    )
    if manager_user:
        create_notification(
            order=order,
            audience_role="manager",
            channel="dashboard",
            event_type=event_type,
            title=title,
            body=body,
            target_user=manager_user,
            delivery_status="sent",
        )


def mark_review_requested(order: Order):
    updated = False
    if not order.review_requested_at:
        order.review_requested_at = timezone.now()
        order.save(update_fields=["review_requested_at", "update_date"])
        updated = True
    if updated:
        title = "زمان ثبت دیدگاه شما رسید"
        body = "خدمت شما کامل و وضعیت مالی رزرو نهایی شده است. حالا می‌توانید دیدگاه و امتیاز خود را ثبت کنید."
        create_notification(
            order=order,
            audience_role="customer",
            channel="dashboard",
            event_type="review_requested",
            title=title,
            body=body,
            target_user=getattr(order.customer, "user", None),
            delivery_status="sent",
        )
    return updated


def mark_review_completed(order: Order):
    if order.review_completed_at:
        return False
    order.review_completed_at = timezone.now()
    order.save(update_fields=["review_completed_at", "update_date"])
    create_notification(
        order=order,
        audience_role="customer",
        channel="dashboard",
        event_type="review_completed",
        title="دیدگاه شما ثبت شد",
        body="بازخورد شما برای این رزرو ثبت شد و پس از بررسی در صفحه سالن نمایش داده می‌شود.",
        target_user=getattr(order.customer, "user", None),
        delivery_status="sent",
    )
    return True


def find_reviewable_order_for_customer(
    *, customer, salon, stylist=None, service=None, appointment_id=None
):
    qs = Order.objects.filter(customer=customer, salon=salon).exclude(
        status="cancelled"
    )
    if appointment_id:
        try:
            return qs.get(order_details1__id=appointment_id)
        except Order.DoesNotExist:
            return None
    if stylist:
        qs = qs.filter(order_details1__stylist=stylist)
    if service:
        qs = qs.filter(order_details1__service=service)
    qs = qs.filter(service_completed_at__isnull=False).order_by(
        "-service_completed_at", "-id"
    )
    return qs.first()


@transaction.atomic
def dispatch_due_order_reminders(*, limit: int = 100):
    """
    یادآوری‌های موعدرسیده را ارسال می‌کند.
    این تابع برای اجرا با cron یا management command طراحی شده است.

    نکته:
    برای جلوگیری از خطای PostgreSQL روی nullable outer join،
    ابتدا فقط خود Order را lock می‌کنیم و سپس رکوردها را با select_related می‌خوانیم.
    """
    now = timezone.now()

    order_ids = list(
        Order.objects.select_for_update(skip_locked=True, of=("self",))
        .filter(
            reminder_status="scheduled",
            reminder_due_at__isnull=False,
            reminder_due_at__lte=now,
        )
        .exclude(status="cancelled")
        .order_by("reminder_due_at", "id")
        .values_list("id", flat=True)[:limit]
    )

    if not order_ids:
        return {
            "processed": 0,
            "sent": 0,
        }

    orders = list(
        Order.objects.select_for_update(of=("self",))
        .select_related("customer__user", "salon")
        .filter(
            pk__in=order_ids,
            reminder_status="scheduled",
            reminder_due_at__isnull=False,
            reminder_due_at__lte=now,
        )
    )

    sent_count = 0

    for order in orders:
        title = "یادآوری نوبت شما"
        body = f"یادآوری: نوبت شما برای {build_notification_meta(order) or 'زمان رزرو شده'} ثبت شده است."

        create_notification(
            order=order,
            audience_role="customer",
            channel="dashboard",
            event_type="reminder_due",
            title=title,
            body=body,
            customer=order.customer,
            target_user=getattr(order.customer, "user", None),
            delivery_status="sent",
            meta={"reminder_due_at": order.reminder_due_at.isoformat()},
        )

        try:
            from apps.accounts.notifications import notify_appointment_reminder

            notify_appointment_reminder(
                customer=order.customer,
                order=order,
            )
        except Exception:
            logger.exception(
                "Failed to create customer in-app appointment reminder | order=%s",
                order.pk,
            )

        _create_email_notification(
            order=order,
            audience_role="customer",
            target_user=getattr(order.customer, "user", None),
            title=title,
            body=body,
            event_type="reminder_due",
        )

        _create_sms_notification(
            order=order,
            audience_role="customer",
            customer=order.customer,
            target_user=getattr(order.customer, "user", None),
            title=title,
            body=body,
            event_type="reminder_due",
        )

        order.reminder_status = "sent"
        order.reminder_sent_at = timezone.now()
        order.save(update_fields=["reminder_status", "reminder_sent_at", "update_date"])

        sent_count += 1

    return {
        "processed": len(orders),
        "sent": sent_count,
    }


def get_customer_notifications(order: Order, limit: int = 6):
    return list(
        AppointmentNotification.objects.filter(
            order=order, audience_role="customer"
        ).order_by("-created_at")[:limit]
    )
