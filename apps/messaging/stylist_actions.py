from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.orders.models import OrderDetail
from apps.orders.appointment_lifecycle import (
    confirm_order_detail,
    reject_order_detail,
    mark_customer_arrived as mark_order_detail_customer_arrived,
    start_service as start_order_detail_service,
    complete_service as complete_order_detail_service,
    mark_no_show_pending,
    confirm_no_show,
    mark_disputed as mark_order_detail_disputed,
    get_delay_policy,
)
from apps.orders.lifecycle import (
    mark_review_requested,
    notify_operational_milestone,
)
from apps.payments.finance import (
    confirm_pay_in_salon_cash_payment,
    finalize_order_financials,
    sync_settlement_for_order,
)
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
from .bale_presenters import appointment_block


ACTION_CONFIRM_APPOINTMENT = "stylist.appointment.confirm"
ACTION_REJECT_APPOINTMENT = "stylist.appointment.reject"
ACTION_START_SERVICE = "stylist.service.start"
ACTION_COMPLETE_SERVICE = "stylist.service.complete"
ACTION_REJECT_APPOINTMENT_PREVIEW = "stylist.appointment.reject.preview"
ACTION_COMPLETE_SERVICE_PREVIEW = "stylist.service.complete.preview"
ACTION_NO_SHOW_PREVIEW = "stylist.appointment.no_show.preview"
ACTION_NO_SHOW_CONFIRM = "stylist.appointment.no_show.confirm"
ACTION_NO_SHOW_REVIEW = "stylist.appointment.no_show.review"
ACTION_CONFIRM_CASH_PAYMENT_PREVIEW = "stylist.payment.cash.preview"
ACTION_CONFIRM_CASH_PAYMENT = "stylist.payment.cash.confirm"


ACTION_LABELS = {
    ACTION_CONFIRM_APPOINTMENT: "تأیید نوبت",
    ACTION_REJECT_APPOINTMENT: "رد نوبت",
    ACTION_START_SERVICE: "شروع خدمت",
    ACTION_COMPLETE_SERVICE: "پایان خدمت",
    ACTION_REJECT_APPOINTMENT_PREVIEW: "بررسی لغو نوبت",
    ACTION_COMPLETE_SERVICE_PREVIEW: "بررسی پایان خدمت",
    ACTION_NO_SHOW_PREVIEW: "بررسی عدم حضور",
    ACTION_NO_SHOW_CONFIRM: "تأیید عدم حضور",
    ACTION_NO_SHOW_REVIEW: "ارجاع عدم حضور برای بررسی",
    ACTION_CONFIRM_CASH_PAYMENT_PREVIEW: "بررسی دریافت وجه",
    ACTION_CONFIRM_CASH_PAYMENT: "دریافت وجه شد",
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


def _no_show_is_available(detail: OrderDetail) -> bool:
    if detail.customer_arrived_at or detail.service_started_at or detail.service_completed_at:
        return False
    if detail.no_show_confirmed_at:
        return False
    start_dt = detail.appointment_start_datetime()
    if not start_dt:
        return False
    policy = get_delay_policy(detail.salon)
    threshold_minutes = int(policy.no_show_after_minutes if policy else 20)
    return timezone.now() >= start_dt + timedelta(minutes=threshold_minutes)


def _issue_stylist_button(
    context: MessagingActionContext,
    *,
    detail: OrderDetail,
    action_key: str,
    label: str,
    source: str,
) -> dict:
    raw_token, _ = issue_action_token(
        provider=context.provider,
        identity=context.identity,
        user=context.user,
        related_object=detail,
        action_key=action_key,
        audience_role="stylist",
        salon_id=detail.salon_id,
        metadata={"source": source, "order_detail_id": detail.pk},
    )
    return {"text": label, "callback_data": build_action_callback_data(raw_token)}


def _result_markup(context: MessagingActionContext, detail: OrderDetail) -> dict:
    rows: list[list[dict]] = []
    order = detail.order
    if (
        order.selected_payment_method == "pay_in_salon"
        and (order.service_completed_at or order.status == "completed")
        and not order.is_paid
        and order.status not in {"cancelled", "no_show", "disputed"}
    ):
        rows.append(
            [
                _issue_stylist_button(
                    context,
                    detail=detail,
                    action_key=ACTION_CONFIRM_CASH_PAYMENT_PREVIEW,
                    label="دریافت وجه شد",
                    source="stylist_action_result",
                )
            ]
        )
    elif detail.service_started_at and not detail.service_completed_at:
        rows.append(
            [
                _issue_stylist_button(
                    context,
                    detail=detail,
                    action_key=ACTION_COMPLETE_SERVICE_PREVIEW,
                    label="پایان خدمت",
                    source="stylist_action_result",
                )
            ]
        )
    elif (
        order.status not in {"cancelled", "completed", "no_show", "disputed"}
        and detail.confirmation_status != OrderDetail.ConfirmationStatus.REJECTED
        and not detail.service_completed_at
    ):
        action_row: list[dict] = []
        if detail.no_show_pending_at and not detail.no_show_confirmed_at:
            action_row.append(
                _issue_stylist_button(
                    context,
                    detail=detail,
                    action_key=ACTION_NO_SHOW_PREVIEW,
                    label="تکمیل وضعیت عدم حضور",
                    source="stylist_action_result",
                )
            )
        else:
            if not detail.date or detail.date <= timezone.localdate():
                action_row.append(
                    _issue_stylist_button(
                        context,
                        detail=detail,
                        action_key=ACTION_START_SERVICE,
                        label="شروع خدمت",
                        source="stylist_action_result",
                    )
                )
            if _no_show_is_available(detail):
                action_row.append(
                    _issue_stylist_button(
                        context,
                        detail=detail,
                        action_key=ACTION_NO_SHOW_PREVIEW,
                        label="مشتری نیامد",
                        source="stylist_action_result",
                    )
                )
            elif not detail.customer_arrived_at:
                action_row.append(
                    _issue_stylist_button(
                        context,
                        detail=detail,
                        action_key=ACTION_REJECT_APPOINTMENT_PREVIEW,
                        label="امکان انجام ندارم",
                        source="stylist_action_result",
                    )
                )
        if action_row:
            rows.append(action_row[:2])
    rows.append(
        [
            {"text": "جزئیات نوبت", "url": _appointment_url(context, detail)},
            {"text": "نوبت‌های امروز", "callback_data": "menu:stylist_today"},
        ]
    )
    return {"inline_keyboard": rows}


def _stylist_decision_preview(
    context: MessagingActionContext, *, decision: str
) -> MessagingActionResult:
    detail = _get_detail(context)
    _check_stylist_scope(context, detail)

    if getattr(detail.order, "status", "") == "cancelled":
        raise ValidationError("این رزرو لغو شده است.")

    if decision == "reject":
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
            raise ValidationError("این نوبت قبلاً لغو شده است.")
        if detail.customer_arrived_at or detail.service_started_at or detail.service_completed_at:
            raise ValidationError("بعد از شروع فرایند خدمت، این نوبت از این مسیر قابل لغو نیست.")
        if detail.no_show_pending_at or detail.no_show_confirmed_at:
            raise ValidationError("برای این نوبت وضعیت عدم حضور ثبت شده است.")
        target_action = ACTION_REJECT_APPOINTMENT
        heading = "این نوبت لغو شود؟"
        note = "اگر امکان انجام این نوبت را نداری، با تأیید این گزینه رزرو لغو می‌شود و به مشتری و مدیر مجموعه اطلاع داده خواهد شد."
        confirm_label = "بله، نوبت را لغو کن"
    elif decision == "complete":
        if not detail.service_started_at:
            raise ValidationError("شروع این خدمت هنوز ثبت نشده است.")
        if detail.service_completed_at:
            raise ValidationError("پایان این خدمت قبلاً ثبت شده است.")
        target_action = ACTION_COMPLETE_SERVICE
        heading = "پایان خدمت ثبت شود؟"
        note = "بعد از ثبت پایان، خدمت انجام‌شده محسوب می‌شود و ادامه مراحل تسویه یا ثبت نظر بر اساس وضعیت رزرو انجام می‌شود."
        confirm_label = "بله، پایان خدمت را ثبت کن"
    elif decision == "cash":
        order = detail.order
        if order.selected_payment_method != "pay_in_salon":
            raise ValidationError("این رزرو برای پرداخت در مجموعه ثبت نشده است.")
        if not (order.service_completed_at or order.status == "completed"):
            raise ValidationError("ثبت دریافت وجه فقط بعد از پایان خدمت امکان‌پذیر است.")
        if order.is_paid:
            raise ValidationError("پرداخت این رزرو قبلاً نهایی شده است.")
        target_action = ACTION_CONFIRM_CASH_PAYMENT
        heading = "دریافت وجه ثبت شود؟"
        note = "فقط وقتی مبلغ این رزرو را از مشتری دریافت کرده‌ای این گزینه را تأیید کن. با ثبت آن، پرداخت رزرو نهایی می‌شود."
        confirm_label = "بله، وجه را دریافت کردم"
    elif decision == "no_show":
        if not _no_show_is_available(detail) and not detail.no_show_pending_at:
            raise ValidationError("هنوز زمان ثبت عدم حضور این مشتری نرسیده است.")

        text = appointment_block(
            detail,
            heading="مشتری برای این نوبت نیامده؟",
            include_salon=True,
            include_status=True,
        )
        confirm_button = _issue_stylist_button(
            context,
            detail=detail,
            action_key=ACTION_NO_SHOW_CONFIRM,
            label="تأیید عدم حضور",
            source="stylist_no_show_preview",
        )
        review_button = _issue_stylist_button(
            context,
            detail=detail,
            action_key=ACTION_NO_SHOW_REVIEW,
            label="نیاز به بررسی دارد",
            source="stylist_no_show_preview",
        )
        return MessagingActionResult(
            status=MessagingActionStatus.SUCCEEDED,
            user_message=(
                f"{text}\n\n"
                "اگر مطمئنی مشتری مراجعه نکرده، «تأیید عدم حضور» را بزن. "
                "اگر درباره حضور یا شرایط نوبت ابهامی وجود دارد، مورد را برای بررسی ثبت کن."
            ),
            result={
                "preview": True,
                "target_action": "no_show_decision",
                "order_detail_id": detail.pk,
                "salon_id": detail.salon_id,
            },
            reply_markup={
                "inline_keyboard": [
                    [confirm_button],
                    [review_button],
                    [{"text": "انصراف", "callback_data": "menu:stylist_today"}],
                ]
            },
        )
    else:
        raise ValidationError("این تصمیم از داخل ربات قابل بررسی نیست.")

    raw_token, _ = issue_action_token(
        provider=context.provider,
        identity=context.identity,
        user=context.user,
        notification_delivery=context.token.notification_delivery,
        related_object=detail,
        action_key=target_action,
        audience_role="stylist",
        salon_id=detail.salon_id,
        metadata={
            "source": "stylist_decision_preview",
            "order_detail_id": detail.pk,
        },
    )
    text = appointment_block(
        detail,
        heading=heading,
        include_salon=True,
        include_status=True,
    )
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=f"{text}\n\n{note}",
        result={
            "preview": True,
            "target_action": target_action,
            "order_detail_id": detail.pk,
            "salon_id": detail.salon_id,
        },
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": confirm_label,
                        "callback_data": build_action_callback_data(raw_token),
                    }
                ],
                [{"text": "انصراف", "callback_data": "menu:stylist_today"}],
            ]
        },
    )


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
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
            raise ValidationError("این نوبت قبلاً لغو شده است.")
        if detail.customer_arrived_at or detail.service_started_at or detail.service_completed_at:
            raise ValidationError("بعد از شروع فرایند خدمت، این نوبت از این مسیر قابل لغو نیست.")
        if detail.no_show_pending_at or detail.no_show_confirmed_at:
            raise ValidationError("برای این نوبت وضعیت عدم حضور ثبت شده است.")

        reject_order_detail(
            detail=detail,
            actor=actor,
            reason="متخصص اعلام کرد امکان انجام این نوبت را ندارد",
        )
        return "نوبت لغو شد و به مشتری و مدیر مجموعه اطلاع داده شد."

    if action == "start_service":
        if detail.service_started_at:
            raise ValidationError("شروع این خدمت قبلاً ثبت شده است.")
        if detail.service_completed_at:
            raise ValidationError("این خدمت قبلاً پایان یافته است.")
        if detail.no_show_pending_at or detail.no_show_confirmed_at:
            raise ValidationError("برای این نوبت وضعیت عدم حضور ثبت شده است.")

        # Booking finalization auto-confirms normal rows. Legacy pending rows are
        # normalized on the first operational action, exactly like the website.
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.PENDING:
            confirm_order_detail(detail=detail, actor=actor, auto=True)
            detail.refresh_from_db()

        if detail.confirmation_status != OrderDetail.ConfirmationStatus.CONFIRMED:
            raise ValidationError("این نوبت در وضعیت قابل شروع نیست.")

        # Starting service is also the check-in action in the current fast flow.
        if not detail.customer_arrived_at:
            mark_order_detail_customer_arrived(detail=detail, actor=actor)
            detail.refresh_from_db()

        start_order_detail_service(detail=detail, actor=actor)
        detail.refresh_from_db()
        order = detail.order
        order.refresh_lifecycle_from_details()

        notify_operational_milestone(
            order,
            event_type="service_started",
            title="انجام خدمت شروع شد",
            body=f"اجرای خدمت {detail.service.service_name if detail.service_id else ''} شروع شد.",
        )

        return "خدمت شروع شد."

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

            finance_finalized = True
            try:
                finalize_order_financials(
                    order,
                    payment=latest_payment,
                    recorded_by=actor,
                    require_all_completed=True,
                )
            except Exception:
                finance_finalized = False

            notify_operational_milestone(
                order,
                event_type="service_completed",
                title="خدمت به پایان رسید",
                body=(
                    "همه خدمات این رزرو انجام شدند و محاسبات مالی به‌صورت خودکار نهایی شد."
                    if finance_finalized
                    else "همه خدمات این رزرو انجام شدند. محاسبات مالی برای بررسی بیشتر در جزئیات باقی مانده است."
                ),
            )

            if order.selected_payment_method == "pay_in_salon" and not order.is_paid:
                notify_operational_milestone(
                    order,
                    event_type="pay_in_salon_pending",
                    title="رزرو آماده تسویه در مجموعه است",
                    body="خدمت کامل شده است. پس از دریافت وجه، متخصص می‌تواند پرداخت حضوری را با «دریافت وجه شد» نهایی کند.",
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

    if action == "confirm_cash_payment":
        result = confirm_pay_in_salon_cash_payment(order, actor=actor, role="stylist")
        if result.get("already_paid"):
            return "پرداخت این رزرو قبلاً نهایی شده است."
        return "دریافت وجه ثبت شد و پرداخت رزرو نهایی شد."

    if action == "no_show_confirm":
        if detail.customer_arrived_at or detail.service_started_at:
            raise ValidationError("برای نوبتی که حضور یا شروع خدمت ثبت شده، عدم حضور قابل ثبت نیست.")
        if not detail.no_show_pending_at:
            if not _no_show_is_available(detail):
                raise ValidationError("هنوز زمان ثبت عدم حضور این مشتری نرسیده است.")
            mark_no_show_pending(
                detail=detail,
                actor=actor,
                note="ثبت اولیه عدم حضور از ربات بله",
                notify=False,
            )
            detail.refresh_from_db()
        confirm_no_show(
            detail=detail,
            actor=actor,
            note="عدم حضور توسط متخصص از ربات بله تأیید شد.",
        )
        return "عدم حضور مشتری ثبت شد."

    if action == "no_show_review":
        if detail.customer_arrived_at or detail.service_started_at:
            raise ValidationError("برای نوبتی که حضور یا شروع خدمت ثبت شده، این مسیر قابل استفاده نیست.")
        if not detail.no_show_pending_at:
            if not _no_show_is_available(detail):
                raise ValidationError("هنوز زمان ثبت عدم حضور این مشتری نرسیده است.")
            mark_no_show_pending(
                detail=detail,
                actor=actor,
                note="عدم حضور برای بررسی بیشتر از ربات بله ثبت شد.",
                notify=False,
            )
            detail.refresh_from_db()
        mark_order_detail_disputed(
            detail=detail,
            actor=actor,
            note="عدم حضور نیازمند بررسی بیشتر؛ ثبت‌شده از ربات بله",
        )
        return "این مورد برای بررسی بیشتر ثبت شد."

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


def reject_appointment_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _stylist_decision_preview(context, decision="reject")
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
            result={"error_code": "stylist_preview_failed", "message": text},
            error_message=text,
        )


def complete_service_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _stylist_decision_preview(context, decision="complete")
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
            result={"error_code": "stylist_preview_failed", "message": text},
            error_message=text,
        )


def no_show_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _stylist_decision_preview(context, decision="no_show")
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
            result={"error_code": "stylist_no_show_preview_failed", "message": text},
            error_message=text,
        )


def confirm_cash_payment_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _stylist_decision_preview(context, decision="cash")
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
            result={"error_code": "stylist_cash_preview_failed", "message": text},
            error_message=text,
        )


def no_show_confirm_action(context: MessagingActionContext) -> MessagingActionResult:
    return _run_lifecycle_action(context, action="no_show_confirm")


def no_show_review_action(context: MessagingActionContext) -> MessagingActionResult:
    return _run_lifecycle_action(context, action="no_show_review")


def confirm_cash_payment_action(context: MessagingActionContext) -> MessagingActionResult:
    return _run_lifecycle_action(context, action="confirm_cash_payment")


def register_stylist_messaging_actions() -> None:
    handlers: dict[str, Any] = {
        ACTION_CONFIRM_APPOINTMENT: confirm_appointment_action,
        ACTION_REJECT_APPOINTMENT: reject_appointment_action,
        ACTION_START_SERVICE: start_service_action,
        ACTION_COMPLETE_SERVICE: complete_service_action,
        ACTION_REJECT_APPOINTMENT_PREVIEW: reject_appointment_preview_action,
        ACTION_COMPLETE_SERVICE_PREVIEW: complete_service_preview_action,
        ACTION_NO_SHOW_PREVIEW: no_show_preview_action,
        ACTION_NO_SHOW_CONFIRM: no_show_confirm_action,
        ACTION_NO_SHOW_REVIEW: no_show_review_action,
        ACTION_CONFIRM_CASH_PAYMENT_PREVIEW: confirm_cash_payment_preview_action,
        ACTION_CONFIRM_CASH_PAYMENT: confirm_cash_payment_action,
    }
    for key, handler in handlers.items():
        try:
            register_messaging_action(key, handler)
        except ValueError as exc:
            if str(exc) != "action_handler_already_registered":
                raise


register_stylist_messaging_actions()
