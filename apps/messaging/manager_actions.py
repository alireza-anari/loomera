from __future__ import annotations
from apps.main.ui_feedback import user_error_message

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone


from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
)
from apps.notifications.services import create_notification
from apps.salons.membership import change_membership_status, ensure_membership_permissions
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.stylists.dashboard_services import review_leave_request, review_schedule_request
from apps.stylists.models import (
    EmergencyInfo,
    JobDetails,
    StaffLeaveRequest,
    StaffScheduleRequest,
)

from .actions import (
    MessagingActionContext,
    MessagingActionResult,
    build_action_callback_data,
    issue_action_token,
    register_messaging_action,
)
from .constants import MessagingActionStatus
from .links import absolute_site_url
from .bale_presenters import (
    leave_request_block,
    membership_request_block,
    schedule_request_block,
)
from .manager_bot import (
    render_manager_membership_profile,
    render_manager_pending_requests,
    render_manager_shifts_overview,
    render_manager_today_calendar,
    render_manager_today_summary,
    render_manager_available_slots,
)


ACTION_MANAGER_MEMBERSHIP_ACCEPT = "manager.membership.accept"
ACTION_MANAGER_MEMBERSHIP_REJECT = "manager.membership.reject"
ACTION_MANAGER_LEAVE_APPROVE = "manager.leave.approve"
ACTION_MANAGER_LEAVE_REJECT = "manager.leave.reject"
ACTION_MANAGER_SCHEDULE_APPROVE = "manager.schedule.approve"
ACTION_MANAGER_SCHEDULE_REJECT = "manager.schedule.reject"
ACTION_MANAGER_MEMBERSHIP_ACCEPT_PREVIEW = "manager.membership.accept.preview"
ACTION_MANAGER_MEMBERSHIP_REJECT_PREVIEW = "manager.membership.reject.preview"
ACTION_MANAGER_LEAVE_APPROVE_PREVIEW = "manager.leave.approve.preview"
ACTION_MANAGER_LEAVE_REJECT_PREVIEW = "manager.leave.reject.preview"
ACTION_MANAGER_SCHEDULE_APPROVE_PREVIEW = "manager.schedule.approve.preview"
ACTION_MANAGER_SCHEDULE_REJECT_PREVIEW = "manager.schedule.reject.preview"
ACTION_MANAGER_SHIFTS_OVERVIEW = "manager.shifts.overview"
ACTION_MANAGER_TODAY_CALENDAR = "manager.today.calendar"
ACTION_MANAGER_TODAY_SUMMARY = "manager.today.summary"
ACTION_MANAGER_AVAILABLE_SLOTS = "manager.available_slots"
ACTION_MANAGER_MEMBERSHIP_PROFILE = "manager.membership.profile"
ACTION_MANAGER_PENDING_REQUESTS = "manager.pending_requests"


ACTION_LABELS = {
    ACTION_MANAGER_MEMBERSHIP_ACCEPT: "پذیرش همکاری",
    ACTION_MANAGER_MEMBERSHIP_REJECT: "رد درخواست",
    ACTION_MANAGER_LEAVE_APPROVE: "تأیید مرخصی",
    ACTION_MANAGER_LEAVE_REJECT: "رد مرخصی",
    ACTION_MANAGER_SCHEDULE_APPROVE: "تأیید برنامه",
    ACTION_MANAGER_SCHEDULE_REJECT: "رد برنامه",
    ACTION_MANAGER_MEMBERSHIP_ACCEPT_PREVIEW: "بررسی پذیرش همکاری",
    ACTION_MANAGER_MEMBERSHIP_REJECT_PREVIEW: "بررسی رد همکاری",
    ACTION_MANAGER_LEAVE_APPROVE_PREVIEW: "بررسی تأیید مرخصی",
    ACTION_MANAGER_LEAVE_REJECT_PREVIEW: "بررسی رد مرخصی",
    ACTION_MANAGER_SCHEDULE_APPROVE_PREVIEW: "بررسی تأیید برنامه",
    ACTION_MANAGER_SCHEDULE_REJECT_PREVIEW: "بررسی رد برنامه",
    ACTION_MANAGER_SHIFTS_OVERVIEW: "بررسی شیفت‌ها",
    ACTION_MANAGER_TODAY_CALENDAR: "تقویم امروز",
    ACTION_MANAGER_TODAY_SUMMARY: "خلاصه امروز",
    ACTION_MANAGER_AVAILABLE_SLOTS: "وقت خالی متخصصان",
    ACTION_MANAGER_MEMBERSHIP_PROFILE: "پروفایل متخصص",
    ACTION_MANAGER_PENDING_REQUESTS: "درخواست‌های همکاری",
}


def _validation_text(exc: Exception) -> str:
    return user_error_message(exc, "اجرای عملیات انجام نشد. لطفاً دوباره تلاش کنید.")


def _manager_user_or_error(context: MessagingActionContext):
    user = context.user
    manager_profile = getattr(user, "salon_manager_profile", None)
    if manager_profile is None:
        raise ValidationError("این عملیات فقط برای حساب مدیر سالن قابل انجام است.")
    return user


def _check_manager_salon_scope(context: MessagingActionContext, salon) -> None:
    user = _manager_user_or_error(context)
    manager_user_id = getattr(getattr(getattr(salon, "salon_manager", None), "user", None), "pk", None)
    if not manager_user_id or int(manager_user_id) != int(user.pk):
        raise ValidationError("این مورد متعلق به سالن‌های تحت مدیریت این حساب نیست.")
    if context.salon_id and int(context.salon_id) != int(salon.pk):
        raise ValidationError("این دکمه برای سالن دیگری ساخته شده است.")


def _detail_url(context: MessagingActionContext, name: str, *, fallback: str, **kwargs) -> str:
    try:
        path = reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        path = fallback
    return absolute_site_url(context.base_url, path)


def _scheduled_shifts_url(context: MessagingActionContext) -> str:
    return _detail_url(context, "dashboards:scheduled_shifts", fallback="/dashboards/scheduled_shifts/")


def _team_member_url(context: MessagingActionContext) -> str:
    return _detail_url(context, "dashboards:team_member", fallback="/dashboards/team_member/")


def _calendar_url(context: MessagingActionContext, salon_id: int) -> str:
    return _detail_url(
        context,
        "dashboards:appointment_calendar",
        fallback=f"/dashboards/calendar/salon/{salon_id}/",
        salon_id=salon_id,
    )


def _manager_result_markup(context: MessagingActionContext, *, salon_id: int | None = None, section: str = "main") -> dict:
    rows = []
    suffix = f":{int(salon_id)}" if salon_id else ""
    if salon_id:
        rows.append([
            {"text": "امروز سالن", "callback_data": f"menu:manager_today{suffix}"},
            {"text": "تقویم کامل", "url": _calendar_url(context, salon_id)},
        ])
    rows.append([
        {"text": "شیفت و مرخصی", "callback_data": f"menu:manager_shifts{suffix}"},
        {"text": "درخواست‌های همکاری", "callback_data": f"menu:manager_requests{suffix}"},
    ])
    rows.append([{"text": "منوی مدیر", "callback_data": "menu:manager"}])
    return {"inline_keyboard": rows}


def _get_membership(context: MessagingActionContext) -> SalonMembership:
    related = context.related_object
    membership_id = getattr(related, "pk", None) if isinstance(related, SalonMembership) else None
    membership_id = membership_id or context.metadata.get("membership_id")
    if not membership_id:
        raise ValidationError("درخواست همکاری مرتبط با این دکمه پیدا نشد.")
    return SalonMembership.objects.select_related("salon__salon_manager__user", "stylist__user").get(pk=membership_id)


def _get_leave_request(context: MessagingActionContext) -> StaffLeaveRequest:
    related = context.related_object
    request_id = getattr(related, "pk", None) if isinstance(related, StaffLeaveRequest) else None
    request_id = request_id or context.metadata.get("leave_request_id")
    if not request_id:
        raise ValidationError("درخواست مرخصی مرتبط با این دکمه پیدا نشد.")
    return StaffLeaveRequest.objects.select_related("salon__salon_manager__user", "stylist__user").get(pk=request_id)


def _get_schedule_request(context: MessagingActionContext) -> StaffScheduleRequest:
    related = context.related_object
    request_id = getattr(related, "pk", None) if isinstance(related, StaffScheduleRequest) else None
    request_id = request_id or context.metadata.get("schedule_request_id")
    if not request_id:
        raise ValidationError("درخواست برنامه کاری مرتبط با این دکمه پیدا نشد.")
    return StaffScheduleRequest.objects.select_related("salon__salon_manager__user", "stylist__user", "service").get(pk=request_id)


def _preview_confirm_button(
    context: MessagingActionContext,
    *,
    related_object,
    action_key: str,
    label: str,
    salon_id: int,
    metadata: dict,
) -> dict:
    raw_token, _ = issue_action_token(
        provider=context.provider,
        identity=context.identity,
        user=context.user,
        notification_delivery=context.token.notification_delivery,
        related_object=related_object,
        action_key=action_key,
        audience_role="manager",
        salon_id=salon_id,
        metadata={"source": "manager_decision_preview", **metadata},
    )
    return {"text": label, "callback_data": build_action_callback_data(raw_token)}


def _manager_decision_preview(
    context: MessagingActionContext,
    *,
    kind: str,
    approved: bool | None = None,
) -> MessagingActionResult:
    if kind == "membership":
        item = _get_membership(context)
        _check_manager_salon_scope(context, item.salon)
        if item.status != SalonMembershipStatus.PENDING_ACCEPTANCE:
            raise ValidationError("این درخواست همکاری قبلاً بررسی شده است.")
        target_action = (
            ACTION_MANAGER_MEMBERSHIP_ACCEPT
            if approved
            else ACTION_MANAGER_MEMBERSHIP_REJECT
        )
        confirm_label = "بله، همکاری را بپذیر" if approved else "بله، درخواست را رد کن"
        heading = "پذیرش این همکاری؟" if approved else "رد این درخواست همکاری؟"
        text = membership_request_block(item, heading=heading)
        note = (
            "با پذیرش، متخصص به تیم فعال سالن اضافه می‌شود و دسترسی‌های همکاری برای او فعال می‌شود."
            if approved
            else "با رد، این درخواست بسته می‌شود و نتیجه برای متخصص ارسال می‌شود."
        )
        metadata = {"membership_id": item.pk}
        back_key = "manager_requests"
    elif kind == "leave":
        item = _get_leave_request(context)
        _check_manager_salon_scope(context, item.salon)
        if item.status != StaffLeaveRequest.Status.PENDING:
            raise ValidationError("این درخواست مرخصی قبلاً بررسی شده است.")
        target_action = ACTION_MANAGER_LEAVE_APPROVE if approved else ACTION_MANAGER_LEAVE_REJECT
        confirm_label = "بله، مرخصی را تأیید کن" if approved else "بله، مرخصی را رد کن"
        heading = "تأیید این مرخصی؟" if approved else "رد این مرخصی؟"
        text = leave_request_block(item, heading=heading)
        note = (
            "اگر در این بازه نوبت ثبت شده، قبل از تأیید مطمئن شو پوشش آن مشخص است."
            if approved
            else "با رد، درخواست بسته می‌شود و نتیجه برای متخصص ثبت خواهد شد."
        )
        metadata = {"leave_request_id": item.pk}
        back_key = "manager_shifts"
    elif kind == "schedule":
        item = _get_schedule_request(context)
        _check_manager_salon_scope(context, item.salon)
        if item.status != StaffScheduleRequest.Status.PENDING:
            raise ValidationError("این درخواست برنامه کاری قبلاً بررسی شده است.")
        target_action = ACTION_MANAGER_SCHEDULE_APPROVE if approved else ACTION_MANAGER_SCHEDULE_REJECT
        confirm_label = "بله، برنامه را تأیید کن" if approved else "بله، برنامه را رد کن"
        heading = "تأیید این برنامه کاری؟" if approved else "رد این برنامه کاری؟"
        text = schedule_request_block(item, heading=heading)
        note = (
            "با تأیید، این برنامه برای متخصص ثبت می‌شود."
            if approved
            else "با رد، این درخواست بسته می‌شود و برنامه تغییری نمی‌کند."
        )
        metadata = {"schedule_request_id": item.pk}
        back_key = "manager_shifts"
    else:
        raise ValidationError("این تصمیم از داخل ربات قابل بررسی نیست.")

    confirm = _preview_confirm_button(
        context,
        related_object=item,
        action_key=target_action,
        label=confirm_label,
        salon_id=item.salon_id,
        metadata=metadata,
    )
    suffix = f":{int(item.salon_id)}"
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=f"{text}\n\n{note}",
        result={
            "preview": True,
            "target_action": target_action,
            "salon_id": item.salon_id,
        },
        reply_markup={
            "inline_keyboard": [
                [confirm],
                [{"text": "انصراف", "callback_data": f"menu:{back_key}{suffix}"}],
            ]
        },
    )


def _notify_stylist_membership_review(*, membership: SalonMembership, actor, accepted: bool) -> None:
    stylist_user = getattr(getattr(membership, "stylist", None), "user", None)
    if not stylist_user:
        return
    salon_name = getattr(membership.salon, "salon_name", "مجموعه")
    if accepted:
        title = "درخواست همکاری تایید شد"
        body = f"درخواست همکاری شما با {salon_name} تایید شد."
        priority = NotificationPriority.HIGH
        event_type = "stylist_membership_request_accepted"
    else:
        title = "درخواست همکاری رد شد"
        body = f"درخواست همکاری شما با {salon_name} رد شد."
        priority = NotificationPriority.NORMAL
        event_type = "stylist_membership_request_rejected"
    create_notification(
        event_type=event_type,
        category=NotificationCategory.STAFF,
        priority=priority,
        title=title,
        body=body,
        action_url=reverse("dashboards:stylist_profile"),
        icon="fa-solid fa-user-check" if accepted else "fa-solid fa-user-xmark",
        recipients=[{"user": stylist_user, "audience_role": NotificationAudienceRole.STYLIST, "channels": [NotificationChannel.DASHBOARD, NotificationChannel.BALE]}],
        actor=actor,
        salon=membership.salon,
        related_object=membership,
        metadata={"membership_id": membership.pk, "salon_id": membership.salon_id, "status": membership.status},
        dedupe_key=f"stylist-membership-review-{membership.pk}-{membership.status}",
    )


def _accept_membership_request(context: MessagingActionContext) -> MessagingActionResult:
    membership = _get_membership(context)
    _check_manager_salon_scope(context, membership.salon)
    if membership.status != SalonMembershipStatus.PENDING_ACCEPTANCE:
        raise ValidationError("این درخواست همکاری قبلاً بررسی شده است.")
    if not membership.stylist_id:
        raise ValidationError("متخصص مرتبط با این درخواست پیدا نشد.")

    with transaction.atomic():
        membership = change_membership_status(
            membership=membership,
            new_status=SalonMembershipStatus.ACTIVE,
            actor=context.user,
            reason="تایید درخواست همکاری متخصص توسط مدیر سالن از ربات",
            request=None,
        )
        ensure_membership_permissions(membership)
        if not membership.salon.stylists.filter(pk=membership.stylist_id).exists():
            membership.salon.stylists.add(membership.stylist)
        accepted_date = timezone.localtime(membership.accepted_at).date() if membership.accepted_at else timezone.localdate()
        JobDetails.objects.get_or_create(
            stylist=membership.stylist,
            salon=membership.salon,
            defaults={"start_date": accepted_date, "employment_type": ""},
        )
        if not EmergencyInfo.objects.filter(stylist=membership.stylist).exists():
            EmergencyInfo.objects.create(stylist=membership.stylist, emergency_contact="", relationship="", full_name="")

    _notify_stylist_membership_review(membership=membership, actor=context.user, accepted=True)
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=f"همکاری {membership.stylist.get_fullName()} پذیرفته شد.",
        result={"membership_id": membership.pk, "salon_id": membership.salon_id, "status": membership.status},
        reply_markup=_manager_result_markup(context, salon_id=membership.salon_id),
    )


def _reject_membership_request(context: MessagingActionContext) -> MessagingActionResult:
    membership = _get_membership(context)
    _check_manager_salon_scope(context, membership.salon)
    if membership.status != SalonMembershipStatus.PENDING_ACCEPTANCE:
        raise ValidationError("این درخواست همکاری قبلاً بررسی شده است.")
    if not membership.stylist_id:
        raise ValidationError("متخصص مرتبط با این درخواست پیدا نشد.")

    membership = change_membership_status(
        membership=membership,
        new_status=SalonMembershipStatus.REJECTED,
        actor=context.user,
        reason="رد درخواست همکاری متخصص توسط مدیر سالن از ربات",
        request=None,
    )
    _notify_stylist_membership_review(membership=membership, actor=context.user, accepted=False)
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=f"درخواست همکاری {membership.stylist.get_fullName()} رد شد.",
        result={"membership_id": membership.pk, "salon_id": membership.salon_id, "status": membership.status},
        reply_markup=_manager_result_markup(context, salon_id=membership.salon_id),
    )


def _review_leave(context: MessagingActionContext, *, approved: bool) -> MessagingActionResult:
    leave_request = _get_leave_request(context)
    _check_manager_salon_scope(context, leave_request.salon)
    reviewed = review_leave_request(
        leave_request=leave_request,
        reviewer=context.user,
        approved=approved,
        review_note="بررسی از ربات بله",
    )
    action_label = "تأیید" if approved else "رد"
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=f"درخواست مرخصی {reviewed.stylist.get_fullName()} {action_label} شد.",
        result={"leave_request_id": reviewed.pk, "salon_id": reviewed.salon_id, "status": reviewed.status},
        reply_markup=_manager_result_markup(context, salon_id=reviewed.salon_id, section="shifts"),
    )


def _review_schedule(context: MessagingActionContext, *, approved: bool) -> MessagingActionResult:
    schedule_request = _get_schedule_request(context)
    _check_manager_salon_scope(context, schedule_request.salon)
    reviewed = review_schedule_request(
        schedule_request=schedule_request,
        reviewer=context.user,
        approved=approved,
        review_note="بررسی از ربات بله",
    )
    action_label = "تأیید" if approved else "رد"
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=f"درخواست برنامه کاری {reviewed.stylist.get_fullName()} {action_label} شد.",
        result={"schedule_request_id": reviewed.pk, "salon_id": reviewed.salon_id, "status": reviewed.status},
        reply_markup=_manager_result_markup(context, salon_id=reviewed.salon_id, section="shifts"),
    )


def _view_result(context: MessagingActionContext, renderer) -> MessagingActionResult:
    _manager_user_or_error(context)
    text, markup = renderer(
        context.user,
        context.base_url,
        salon_id=context.salon_id,
        metadata=context.metadata,
        provider=context.provider,
        identity=context.identity,
    )
    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message=text,
        result={"action_key": context.action_key, "salon_id": context.salon_id},
        reply_markup=markup,
    )


def manager_membership_accept_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _accept_membership_request(context)
    except SalonMembership.DoesNotExist:
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message="درخواست همکاری دیگر در دسترس نیست.", error_message="membership_missing", result={"error_code": "membership_missing"})
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_membership_accept_failed", "message": text})


def manager_membership_reject_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _reject_membership_request(context)
    except SalonMembership.DoesNotExist:
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message="درخواست همکاری دیگر در دسترس نیست.", error_message="membership_missing", result={"error_code": "membership_missing"})
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_membership_reject_failed", "message": text})


def manager_leave_approve_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _review_leave(context, approved=True)
    except StaffLeaveRequest.DoesNotExist:
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message="درخواست مرخصی دیگر در دسترس نیست.", error_message="leave_missing", result={"error_code": "leave_missing"})
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_leave_approve_failed", "message": text})


def manager_leave_reject_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _review_leave(context, approved=False)
    except StaffLeaveRequest.DoesNotExist:
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message="درخواست مرخصی دیگر در دسترس نیست.", error_message="leave_missing", result={"error_code": "leave_missing"})
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_leave_reject_failed", "message": text})


def manager_schedule_approve_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _review_schedule(context, approved=True)
    except StaffScheduleRequest.DoesNotExist:
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message="درخواست برنامه کاری دیگر در دسترس نیست.", error_message="schedule_missing", result={"error_code": "schedule_missing"})
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_schedule_approve_failed", "message": text})


def manager_schedule_reject_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _review_schedule(context, approved=False)
    except StaffScheduleRequest.DoesNotExist:
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message="درخواست برنامه کاری دیگر در دسترس نیست.", error_message="schedule_missing", result={"error_code": "schedule_missing"})
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_schedule_reject_failed", "message": text})


def manager_membership_accept_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _manager_decision_preview(context, kind="membership", approved=True)
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_membership_preview_failed", "message": text})


def manager_membership_reject_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _manager_decision_preview(context, kind="membership", approved=False)
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_membership_preview_failed", "message": text})


def manager_leave_approve_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _manager_decision_preview(context, kind="leave", approved=True)
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_leave_preview_failed", "message": text})


def manager_leave_reject_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _manager_decision_preview(context, kind="leave", approved=False)
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_leave_preview_failed", "message": text})


def manager_schedule_approve_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _manager_decision_preview(context, kind="schedule", approved=True)
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_schedule_preview_failed", "message": text})


def manager_schedule_reject_preview_action(context: MessagingActionContext) -> MessagingActionResult:
    try:
        return _manager_decision_preview(context, kind="schedule", approved=False)
    except Exception as exc:
        text = _validation_text(exc)
        return MessagingActionResult(status=MessagingActionStatus.FAILED, user_message=text, error_message=text, result={"error_code": "manager_schedule_preview_failed", "message": text})


def manager_shifts_overview_action(context: MessagingActionContext) -> MessagingActionResult:
    return _view_result(context, render_manager_shifts_overview)


def manager_today_calendar_action(context: MessagingActionContext) -> MessagingActionResult:
    return _view_result(context, render_manager_today_calendar)


def manager_today_summary_action(context: MessagingActionContext) -> MessagingActionResult:
    return _view_result(context, render_manager_today_summary)


def manager_available_slots_action(context: MessagingActionContext) -> MessagingActionResult:
    return _view_result(context, render_manager_available_slots)


def manager_membership_profile_action(context: MessagingActionContext) -> MessagingActionResult:
    return _view_result(context, render_manager_membership_profile)


def manager_pending_requests_action(context: MessagingActionContext) -> MessagingActionResult:
    return _view_result(context, render_manager_pending_requests)


def register_manager_messaging_actions() -> None:
    handlers: dict[str, Any] = {
        ACTION_MANAGER_MEMBERSHIP_ACCEPT: manager_membership_accept_action,
        ACTION_MANAGER_MEMBERSHIP_REJECT: manager_membership_reject_action,
        ACTION_MANAGER_LEAVE_APPROVE: manager_leave_approve_action,
        ACTION_MANAGER_LEAVE_REJECT: manager_leave_reject_action,
        ACTION_MANAGER_SCHEDULE_APPROVE: manager_schedule_approve_action,
        ACTION_MANAGER_SCHEDULE_REJECT: manager_schedule_reject_action,
        ACTION_MANAGER_MEMBERSHIP_ACCEPT_PREVIEW: manager_membership_accept_preview_action,
        ACTION_MANAGER_MEMBERSHIP_REJECT_PREVIEW: manager_membership_reject_preview_action,
        ACTION_MANAGER_LEAVE_APPROVE_PREVIEW: manager_leave_approve_preview_action,
        ACTION_MANAGER_LEAVE_REJECT_PREVIEW: manager_leave_reject_preview_action,
        ACTION_MANAGER_SCHEDULE_APPROVE_PREVIEW: manager_schedule_approve_preview_action,
        ACTION_MANAGER_SCHEDULE_REJECT_PREVIEW: manager_schedule_reject_preview_action,
        ACTION_MANAGER_SHIFTS_OVERVIEW: manager_shifts_overview_action,
        ACTION_MANAGER_TODAY_CALENDAR: manager_today_calendar_action,
        ACTION_MANAGER_TODAY_SUMMARY: manager_today_summary_action,
        ACTION_MANAGER_AVAILABLE_SLOTS: manager_available_slots_action,
        ACTION_MANAGER_MEMBERSHIP_PROFILE: manager_membership_profile_action,
        ACTION_MANAGER_PENDING_REQUESTS: manager_pending_requests_action,
    }
    for key, handler in handlers.items():
        try:
            register_messaging_action(key, handler)
        except ValueError as exc:
            if str(exc) != "action_handler_already_registered":
                raise


register_manager_messaging_actions()
