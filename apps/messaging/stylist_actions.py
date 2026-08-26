from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse

from apps.orders.models import OrderDetail
from apps.orders.appointment_lifecycle import (
    confirm_order_detail,
    reject_order_detail,
    start_service as start_order_detail_service,
    complete_service as complete_order_detail_service,
)
from apps.orders.lifecycle import (
    mark_review_requested,
    notify_operational_milestone,
)
from apps.payments.finance import sync_settlement_for_order
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.salons.membership import ensure_membership_permissions

from .actions import (
    MessagingActionContext,
    MessagingActionResult,
    build_action_callback_data,
    issue_action_token,
    register_messaging_action,
)
from .constants import MessagingActionStatus
from .links import absolute_site_url


ACTION_CONFIRM_APPOINTMENT = "stylist.appointment.confirm"
ACTION_REJECT_APPOINTMENT = "stylist.appointment.reject"
ACTION_START_SERVICE = "stylist.service.start"
ACTION_COMPLETE_SERVICE = "stylist.service.complete"


ACTION_LABELS = {
    ACTION_CONFIRM_APPOINTMENT: "تأیید نوبت",
    ACTION_REJECT_APPOINTMENT: "رد نوبت",
    ACTION_START_SERVICE: "شروع خدمت",
    ACTION_COMPLETE_SERVICE: "پایان خدمت",
}


def _validation_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        try:
            messages = exc.messages
        except Exception:
            messages = []
        if messages:
            return str(messages[0])
    return str(exc) or "اجرای عملیات ناموفق بود."


def _get_detail(context: MessagingActionContext) -> OrderDetail:
    related = context.related_object
    detail_id = getattr(related, "pk", None)
    if isinstance(related, OrderDetail):
        detail_id = related.pk
    if not detail_id:
        detail_id = context.metadata.get("order_detail_id") or context.metadata.get("detail_id")
    if not detail_id:
        raise ValidationError("نوبت مرتبط با این دکمه پیدا نشد.")
    return (
        OrderDetail.objects.select_related(
            "order",
            "order__customer__user",
            "service",
            "stylist__user",
            "salon",
        )
        .get(pk=detail_id)
    )


def _check_stylist_scope(context: MessagingActionContext, detail: OrderDetail):
    user = context.user
    stylist = getattr(user, "stylist", None)
    if stylist is None:
        raise ValidationError("این عملیات فقط برای حساب متخصص قابل انجام است.")

    if detail.stylist_id != stylist.pk:
        raise ValidationError("این نوبت متعلق به متخصص متصل به این حساب نیست.")

    if context.salon_id and int(context.salon_id) != int(detail.salon_id):
        raise ValidationError("این دکمه برای سالن دیگری ساخته شده است.")

    membership = (
        SalonMembership.objects.filter(
            salon_id=detail.salon_id,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        .select_related("salon", "stylist")
        .first()
    )
    if membership is None:
        raise ValidationError("همکاری فعال شما با سالن این نوبت پیدا نشد.")

    permissions = ensure_membership_permissions(membership)
    if not getattr(permissions, "can_complete_appointments", True):
        raise ValidationError("دسترسی اجرای مراحل نوبت برای شما فعال نیست.")

    return stylist, membership


def _appointment_url(context: MessagingActionContext, detail: OrderDetail) -> str:
    try:
        path = reverse("dashboards:stylist_appointment_detail", kwargs={"appointment_id": detail.pk})
    except NoReverseMatch:
        path = f"/dashboards/stylist/appointments/{detail.pk}/"
    return absolute_site_url(context.base_url, path)


def _result_markup(context: MessagingActionContext, detail: OrderDetail) -> dict:
    rows: list[list[dict]] = []
    if detail.service_started_at and not detail.service_completed_at:
        raw_token, _ = issue_action_token(
            provider=context.provider,
            identity=context.identity,
            user=context.user,
            related_object=detail,
            action_key=ACTION_COMPLETE_SERVICE,
            audience_role="stylist",
            salon_id=detail.salon_id,
            metadata={
                "source": "stylist_action_result",
                "order_detail_id": detail.pk,
            },
        )
        rows.append(
            [
                {
                    "text": "پایان خدمت",
                    "callback_data": build_action_callback_data(raw_token),
                }
            ]
        )
    rows.append(
        [
            {"text": "جزئیات نوبت", "url": _appointment_url(context, detail)},
            {"text": "نوبت‌های امروز", "callback_data": "menu:stylist_today"},
        ]
    )
    return {"inline_keyboard": rows}


def _apply_lightweight_stylist_lifecycle_action(detail: OrderDetail, action: str, *, actor=None) -> str:
    """Run specialist actions without importing the dashboard view module.

    The Bale webhook must stay small and resilient. Importing the full dashboard
    views module inside a provider callback can make the request heavy and, on
    small PaaS instances, may cause workers to become unavailable. This helper
    mirrors the website lifecycle logic using the underlying service functions.
    """

    order = detail.order

    if order.status == "cancelled":
        raise ValidationError("این رزرو لغو شده است.")

    was_fully_confirmed = not order.order_details1.exclude(
        confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
    ).exists()

    if action == "confirm":
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED:
            raise ValidationError("این خدمت قبلاً تایید شده است.")
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
            raise ValidationError("این خدمت قبلاً رد شده است.")

        confirm_order_detail(detail=detail, actor=actor)
        detail.refresh_from_db()
        order = detail.order
        order.refresh_lifecycle_from_details()

        is_fully_confirmed = not order.order_details1.exclude(
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
        ).exists()

        sync_settlement_for_order(
            order, payment=order.payment_order.order_by("-id").first()
        )

        # Customer confirmation notice is emitted exactly once inside
        # confirm_order_detail when the whole multi-service order flips
        # from partial to fully confirmed.

        return "نوبت تأیید شد."

    if action == "reject":
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED:
            raise ValidationError("خدمت تایید شده را از این بخش نمی‌توان رد کرد.")
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
            raise ValidationError("این خدمت قبلاً رد شده است.")

        reject_order_detail(detail=detail, actor=actor, reason="رد شده توسط متخصص")
        return "نوبت رد و لغو شد. به مشتری و مدیر سالن اطلاع داده شد."

    if action == "start_service":
        if not detail.customer_arrived_at:
            raise ValidationError("ابتدا باید رسیدن مشتری ثبت شود.")
        if detail.service_started_at:
            raise ValidationError("شروع این خدمت قبلاً ثبت شده است.")

        start_order_detail_service(detail=detail, actor=actor)
        detail.refresh_from_db()
        order = detail.order
        order.refresh_lifecycle_from_details()

        notify_operational_milestone(
            order,
            event_type="service_started",
            title="انجام کار شروع شد",
            body=f"اجرای خدمت {detail.service.service_name if detail.service_id else ''} شروع شد.",
        )

        return "شروع خدمت ثبت شد."

    if action == "complete_service":
        complete_order_detail_service(detail=detail, actor=actor)
        detail.refresh_from_db()
        order = detail.order
        order.refresh_lifecycle_from_details()

        all_completed = not order.order_details1.filter(
            service_completed_at__isnull=True
        ).exists()

        if all_completed:
            latest_payment = order.payment_order.order_by("-id").first()
            sync_settlement_for_order(order, payment=latest_payment)

            notify_operational_milestone(
                order,
                event_type="service_completed",
                title="خدمت به پایان رسید",
                body="همه خدمات این رزرو انجام شدند. اکنون مواد مصرفی باید ثبت و محاسبات مالی نهایی شود.",
            )

            if order.selected_payment_method == "pay_in_salon" and not order.is_paid:
                notify_operational_milestone(
                    order,
                    event_type="pay_in_salon_pending",
                    title="رزرو آماده تسویه در مجموعه است",
                    body="خدمت کامل شده و مشتری می‌تواند پرداخت نقدی را تایید کند یا آنلاین بپردازد.",
                )
            else:
                mark_review_requested(order)
        else:
            notify_operational_milestone(
                order,
                event_type="service_completed",
                title="یک خدمت به پایان رسید",
                body=f"خدمت {detail.service.service_name if detail.service_id else ''} انجام شد. هنوز همه خدمات این رزرو کامل نشده‌اند.",
            )

        return "پایان خدمت ثبت شد."

    raise ValidationError("این کار از داخل ربات قابل انجام نیست.")


def _run_lifecycle_action(context: MessagingActionContext, *, action: str) -> MessagingActionResult:
    try:
        detail = _get_detail(context)
        _check_stylist_scope(context, detail)

        message = _apply_lightweight_stylist_lifecycle_action(
            detail,
            action,
            actor=context.user,
        )
        detail.refresh_from_db()
        return MessagingActionResult(
            status=MessagingActionStatus.SUCCEEDED,
            user_message=message,
            result={
                "action_key": context.action_key,
                "order_detail_id": detail.pk,
                "salon_id": detail.salon_id,
                "lifecycle_status": detail.lifecycle_status,
                "confirmation_status": detail.confirmation_status,
            },
            reply_markup=_result_markup(context, detail),
        )
    except OrderDetail.DoesNotExist:
        return MessagingActionResult(
            status=MessagingActionStatus.FAILED,
            user_message="نوبت مرتبط با این دکمه دیگر در دسترس نیست.",
            result={"error_code": "order_detail_missing"},
            error_message="order_detail_missing",
        )
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(
            status=MessagingActionStatus.FAILED,
            user_message=text,
            result={"error_code": "stylist_action_failed", "message": text},
            error_message=text,
        )


def confirm_appointment_action(context: MessagingActionContext) -> MessagingActionResult:
    return _run_lifecycle_action(context, action="confirm")


def reject_appointment_action(context: MessagingActionContext) -> MessagingActionResult:
    # The current dashboard flow uses a safe default reason. A free-text reason
    # can be added in a later conversation-state step without changing tokens.
    return _run_lifecycle_action(context, action="reject")


def start_service_action(context: MessagingActionContext) -> MessagingActionResult:
    return _run_lifecycle_action(context, action="start_service")


def complete_service_action(context: MessagingActionContext) -> MessagingActionResult:
    return _run_lifecycle_action(context, action="complete_service")


def register_stylist_messaging_actions() -> None:
    handlers: dict[str, Any] = {
        ACTION_CONFIRM_APPOINTMENT: confirm_appointment_action,
        ACTION_REJECT_APPOINTMENT: reject_appointment_action,
        ACTION_START_SERVICE: start_service_action,
        ACTION_COMPLETE_SERVICE: complete_service_action,
    }
    for key, handler in handlers.items():
        try:
            register_messaging_action(key, handler)
        except ValueError as exc:
            if str(exc) != "action_handler_already_registered":
                raise


register_stylist_messaging_actions()
