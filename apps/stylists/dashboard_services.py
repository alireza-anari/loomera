from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone
from django.urls import reverse

from apps.orders.models import OrderDetail
from apps.payments.models import (
    StaffEarning,
    StaffPayoutRequest,
    StylistWallet,
    OrderDetailFinancialSnapshot,
)
from apps.salons.models import (
    SalonMembership,
    SalonMembershipStatus,
    StaffDashboardPermission,
    SalonOpeningHours,
)
from apps.salons.membership import ensure_membership_permissions, sync_legacy_membership
from apps.stylists.models import (
    StylistSchedule,
    StylistTimeOff,
    StaffLeaveRequest,
    StaffScheduleRequest,
    JobDetails,
)
from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
)
from apps.notifications.services import create_notification

ACTIVE_APPOINTMENT_ORDER_STATUSES = [
    "pending",
    "confirmed",
    "paid",
]
ACTIVE_DETAIL_LIFECYCLE_STATUSES = [
    "scheduled",
    "awaiting_confirmation",
    "confirmed",
    "client_late",
    "arrived",
    "in_service",
    "service_overrun",
    "no_show_pending_review",
    "disputed",
]


def _salon_day_number(date_value):
    # Python weekday: Monday=0
    # Loomera model: Saturday=1 ... Friday=7
    return ((date_value.weekday() + 2) % 7) + 1


def _format_time_for_message(value):
    if not value:
        return "—"
    return value.strftime("%H:%M")


def _get_salon_opening_hours_for_date(*, salon, date_value):
    if not salon or not date_value:
        return None

    return SalonOpeningHours.objects.filter(
        salon=salon,
        day_of_week=_salon_day_number(date_value),
        is_closed=False,
    ).first()


def validate_salon_opening_window(
    *, salon, date_value, start_time=None, end_time=None, allow_full_day=False
):
    """
    تمام درخواست‌های برنامه کاری و مرخصی ساعتی باید داخل ساعت کاری همان روز سالن باشند.
    مرخصی تمام‌روز می‌تواند بدون start/end ثبت شود، اما اگر روز سالن تعطیل باشد درخواست برنامه کاری مجاز نیست.
    """
    if not salon or not date_value:
        return

    opening = _get_salon_opening_hours_for_date(salon=salon, date_value=date_value)

    if not opening or not opening.open_time or not opening.close_time:
        raise ValidationError("برای این تاریخ، مجموعه ساعت کاری فعال ندارد.")

    if allow_full_day and not start_time and not end_time:
        return

    if not start_time or not end_time:
        raise ValidationError("برای این بازه باید ساعت شروع و پایان مشخص باشد.")

    if start_time < opening.open_time or end_time > opening.close_time:
        raise ValidationError(
            "بازه انتخاب‌شده خارج از ساعت کاری مجموعه است. "
            f"ساعت کاری این روز: {_format_time_for_message(opening.open_time)} تا {_format_time_for_message(opening.close_time)}."
        )


def _active_appointment_conflicts_for_leave(
    *, stylist, salon, date_value, start_time=None, end_time=None
):
    qs = OrderDetail.objects.filter(
        stylist=stylist,
        salon=salon,
        date=date_value,
        order__status__in=ACTIVE_APPOINTMENT_ORDER_STATUSES,
    ).select_related("order", "service", "salon")

    conflicts = []
    for detail in qs:
        existing_start = detail.time
        if not existing_start:
            continue

        existing_end = getattr(detail, "occupied_until", None) or detail.end_time
        if existing_end is None:
            duration = int(getattr(detail.service, "duration_minutes", 0) or 60)
            buffer_minutes = int(
                getattr(detail, "buffer_minutes", 0)
                or getattr(detail.service, "buffer_minutes", 0)
                or 0
            )
            existing_end = (
                _to_datetime(date_value, existing_start)
                + timedelta(minutes=duration + buffer_minutes)
            ).time()

        if not start_time and not end_time:
            conflicts.append(detail)
            continue

        if existing_start < end_time and existing_end > start_time:
            conflicts.append(detail)

    return conflicts


def _split_schedule_around_leave(schedule, leave_request):
    if not leave_request.start_time or not leave_request.end_time:
        return []

    segments = []

    if schedule.start_time < leave_request.start_time:
        before_end = min(schedule.end_time, leave_request.start_time)
        if schedule.start_time < before_end:
            segments.append((schedule.start_time, before_end))

    if schedule.end_time > leave_request.end_time:
        after_start = max(schedule.start_time, leave_request.end_time)
        if after_start < schedule.end_time:
            segments.append((after_start, schedule.end_time))

    return segments


def _apply_approved_leave_to_schedules(leave_request):
    """
    وقتی مرخصی تایید شد، فقط شیفت‌های همان سالن و همان روز اصلاح می‌شوند.
    اگر مرخصی تمام‌روز باشد شیفت‌ها حذف می‌شوند.
    اگر مرخصی ساعتی باشد، شیفت‌های متداخل split می‌شوند.
    """
    schedules = list(
        StylistSchedule.objects.filter(
            stylist=leave_request.stylist,
            salon=leave_request.salon,
            date=leave_request.date,
        ).select_related("service")
    )

    if not leave_request.start_time and not leave_request.end_time:
        if schedules:
            StylistSchedule.objects.filter(
                pk__in=[item.pk for item in schedules]
            ).delete()
        return

    overlapping = [
        item
        for item in schedules
        if item.start_time < leave_request.end_time
        and item.end_time > leave_request.start_time
    ]

    replacements = []
    for schedule in overlapping:
        for start_time, end_time in _split_schedule_around_leave(
            schedule, leave_request
        ):
            replacements.append(
                StylistSchedule(
                    stylist=schedule.stylist,
                    salon=schedule.salon,
                    service=schedule.service,
                    date=schedule.date,
                    start_time=start_time,
                    end_time=end_time,
                )
            )

    if overlapping:
        StylistSchedule.objects.filter(
            pk__in=[item.pk for item in overlapping]
        ).delete()

    if replacements:
        StylistSchedule.objects.bulk_create(replacements)


def _notify_manager_for_schedule_request(schedule_request, *, actor=None):
    salon = schedule_request.salon
    stylist = schedule_request.stylist
    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)

    if not manager_user:
        return None

    return create_notification(
        event_type="staff_schedule_requested",
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title="درخواست برنامه کاری متخصص",
        body=(
            f"{stylist.get_fullName()} برای مجموعه {salon.salon_name} "
            f"در تاریخ {schedule_request.date} از {schedule_request.start_time} تا {schedule_request.end_time} "
            "درخواست برنامه کاری ثبت کرد."
        ),
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        action_url=reverse("dashboards:scheduled_shifts"),
        icon="fa-regular fa-calendar-plus",
        actor=actor,
        salon=salon,
        related_object=schedule_request,
        metadata={
            "schedule_request_id": schedule_request.pk,
            "stylist_id": stylist.pk,
            "salon_id": salon.pk,
            "date": str(schedule_request.date),
            "start_time": str(schedule_request.start_time),
            "end_time": str(schedule_request.end_time),
        },
        dedupe_key=f"staff-schedule-requested-{schedule_request.pk}",
    )


def _notify_stylist_for_schedule_review(schedule_request, *, approved, actor=None):
    stylist_user = getattr(schedule_request.stylist, "user", None)
    if not stylist_user:
        return None

    if approved:
        title = "درخواست برنامه کاری تایید شد"
        body = (
            f"درخواست برنامه کاری شما برای مجموعه {schedule_request.salon.salon_name} "
            "تایید و به شیفت‌ها اضافه شد."
        )
        priority = NotificationPriority.HIGH
        icon = "fa-solid fa-calendar-check"
        event_type = "staff_schedule_approved"
    else:
        title = "درخواست برنامه کاری رد شد"
        body = f"درخواست برنامه کاری شما برای مجموعه {schedule_request.salon.salon_name} رد شد."
        if schedule_request.review_note:
            body += f" توضیح مدیر: {schedule_request.review_note}"
        priority = NotificationPriority.NORMAL
        icon = "fa-solid fa-calendar-xmark"
        event_type = "staff_schedule_rejected"

    return create_notification(
        event_type=event_type,
        category=NotificationCategory.STAFF,
        priority=priority,
        title=title,
        body=body,
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        action_url=reverse("dashboards:stylist_schedule"),
        icon=icon,
        actor=actor,
        salon=schedule_request.salon,
        related_object=schedule_request,
        metadata={
            "schedule_request_id": schedule_request.pk,
            "salon_id": schedule_request.salon_id,
            "status": schedule_request.status,
        },
        dedupe_key=f"staff-schedule-review-{schedule_request.pk}-{schedule_request.status}",
    )


def _notify_manager_for_leave_request(leave_request, *, actor=None):
    salon = leave_request.salon
    stylist = leave_request.stylist
    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)

    if not manager_user:
        return None

    return create_notification(
        event_type="staff_leave_requested",
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title="درخواست مرخصی متخصص",
        body=(
            f"{stylist.get_fullName()} برای مجموعه {salon.salon_name} "
            f"در تاریخ {leave_request.date} درخواست مرخصی ثبت کرد."
        ),
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        action_url=reverse("dashboards:scheduled_shifts"),
        icon="fa-regular fa-calendar-xmark",
        actor=actor,
        salon=salon,
        related_object=leave_request,
        metadata={
            "leave_request_id": leave_request.pk,
            "stylist_id": stylist.pk,
            "salon_id": salon.pk,
            "date": str(leave_request.date),
        },
        dedupe_key=f"staff-leave-requested-{leave_request.pk}",
    )


def _notify_stylist_for_leave_review(leave_request, *, approved, actor=None):
    stylist_user = getattr(leave_request.stylist, "user", None)
    if not stylist_user:
        return None

    if approved:
        title = "درخواست مرخصی تایید شد"
        body = (
            f"درخواست مرخصی شما برای مجموعه {leave_request.salon.salon_name} تایید شد."
        )
        priority = NotificationPriority.HIGH
        icon = "fa-solid fa-calendar-check"
        event_type = "staff_leave_approved"
    else:
        title = "درخواست مرخصی رد شد"
        body = f"درخواست مرخصی شما برای مجموعه {leave_request.salon.salon_name} رد شد."
        if leave_request.review_note:
            body += f" توضیح مدیر: {leave_request.review_note}"
        priority = NotificationPriority.NORMAL
        icon = "fa-solid fa-calendar-xmark"
        event_type = "staff_leave_rejected"

    return create_notification(
        event_type=event_type,
        category=NotificationCategory.STAFF,
        priority=priority,
        title=title,
        body=body,
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        action_url=reverse("dashboards:stylist_schedule"),
        icon=icon,
        actor=actor,
        salon=leave_request.salon,
        related_object=leave_request,
        metadata={
            "leave_request_id": leave_request.pk,
            "salon_id": leave_request.salon_id,
            "status": leave_request.status,
        },
        dedupe_key=f"staff-leave-review-{leave_request.pk}-{leave_request.status}",
    )


@dataclass(frozen=True)
class StylistDashboardContext:
    stylist: object
    salon: object | None
    membership: SalonMembership | None
    permissions: StaffDashboardPermission | None
    active_memberships: list[SalonMembership]

    def can(self, field_name: str, default: bool = False) -> bool:
        if self.permissions is None:
            return default
        return bool(getattr(self.permissions, field_name, default))


def get_active_memberships(stylist) -> list[SalonMembership]:
    if stylist is None:
        return []
    return list(
        SalonMembership.objects.filter(
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        .select_related("salon")
        .order_by("salon__salon_name", "id")
    )


def _legacy_salon_for_stylist(stylist):
    """
    فقط برای داده‌های قدیمی که هنوز SalonMembership ندارند fallback می‌زنیم.
    اگر برای سالن/متخصص قبلاً membership با وضعیت غیر فعال، ended یا cancelled وجود دارد،
    نباید با JobDetails یا legacy M2M دوباره active شود.
    """
    today = timezone.localdate()

    active_job = (
        JobDetails.objects.filter(stylist=stylist)
        .filter(Q(end_date__isnull=True) | Q(end_date__gt=today))
        .select_related("salon")
        .order_by("-start_date", "-pk")
        .first()
    )

    if active_job and active_job.salon_id:
        existing_membership = SalonMembership.objects.filter(
            salon=active_job.salon,
            stylist=stylist,
        ).first()

        if existing_membership:
            if existing_membership.status == SalonMembershipStatus.ACTIVE:
                return active_job.salon
            return None

        sync_legacy_membership(
            salon=active_job.salon,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        return active_job.salon

    salon = stylist.stylists_of_salon.order_by("id").first()
    if salon:
        existing_membership = SalonMembership.objects.filter(
            salon=salon,
            stylist=stylist,
        ).first()

        if existing_membership:
            if existing_membership.status == SalonMembershipStatus.ACTIVE:
                return salon
            return None

        sync_legacy_membership(
            salon=salon,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        return salon

    return None


def resolve_stylist_dashboard_context(request_or_user) -> StylistDashboardContext:
    request = request_or_user if hasattr(request_or_user, "user") else None
    user = request.user if request is not None else request_or_user
    stylist = getattr(user, "stylist", None)
    if stylist is None:
        return StylistDashboardContext(None, None, None, None, [])

    active_memberships = get_active_memberships(stylist)
    membership = None
    session_salon_id = None
    if request is not None:
        session_salon_id = request.session.get("active_stylist_salon_id")

    if session_salon_id:
        membership = next(
            (m for m in active_memberships if str(m.salon_id) == str(session_salon_id)),
            None,
        )

    if membership is None and active_memberships:
        membership = active_memberships[0]
        if request is not None:
            request.session["active_stylist_salon_id"] = membership.salon_id

    salon = membership.salon if membership else _legacy_salon_for_stylist(stylist)
    if membership is None and salon is not None:
        membership = (
            SalonMembership.objects.filter(
                salon=salon,
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            .select_related("salon")
            .first()
        )
        if membership:
            active_memberships = get_active_memberships(stylist)

    permissions = ensure_membership_permissions(membership) if membership else None
    return StylistDashboardContext(
        stylist, salon, membership, permissions, active_memberships
    )


def _to_datetime(date_value, time_value):
    return datetime.combine(date_value, time_value)


def validate_stylist_time_window(
    *, stylist, date_value, start_time, end_time, salon=None, exclude_schedule_id=None
):
    if not all([stylist, date_value, start_time, end_time]):
        return
    if end_time <= start_time:
        raise ValidationError("ساعت پایان باید بعد از ساعت شروع باشد.")

    schedule_conflicts = StylistSchedule.objects.filter(
        stylist=stylist, date=date_value
    )
    if salon is not None:
        schedule_conflicts = schedule_conflicts.filter(salon=salon)
    if exclude_schedule_id:
        schedule_conflicts = schedule_conflicts.exclude(pk=exclude_schedule_id)
    schedule_conflicts = schedule_conflicts.exclude(end_time__lte=start_time).exclude(
        start_time__gte=end_time
    )
    if schedule_conflicts.exists():
        raise ValidationError(
            "این بازه با برنامه کاری دیگری برای همین آرایشگر تداخل دارد."
        )

    leave_conflicts = StaffLeaveRequest.objects.filter(
        stylist=stylist,
        date=date_value,
        status__in=[
            StaffLeaveRequest.Status.PENDING,
            StaffLeaveRequest.Status.APPROVED,
        ],
    )

    if salon is not None:
        leave_conflicts = leave_conflicts.filter(salon=salon)

    leave_conflicts = leave_conflicts.filter(
        Q(start_time__isnull=True, end_time__isnull=True)
        | (Q(start_time__lt=end_time) & Q(end_time__gt=start_time))
    )
    if leave_conflicts.exists():
        raise ValidationError("این بازه با درخواست مرخصی ثبت‌شده آرایشگر تداخل دارد.")

    appointment_conflicts = OrderDetail.objects.filter(
        stylist=stylist,
        date=date_value,
        order__status__in=ACTIVE_APPOINTMENT_ORDER_STATUSES,
    ).select_related("order", "service", "salon")

    if salon is not None:
        appointment_conflicts = appointment_conflicts.filter(salon=salon)
    for existing in appointment_conflicts:
        existing_start = existing.time
        if not existing_start:
            continue
        existing_end = getattr(existing, "occupied_until", None) or existing.end_time
        if existing_end is None:
            duration = int(getattr(existing.service, "duration_minutes", 0) or 60)
            buffer_minutes = int(
                getattr(existing, "buffer_minutes", 0)
                or getattr(existing.service, "buffer_minutes", 0)
                or 0
            )
            existing_end = (
                _to_datetime(date_value, existing_start)
                + timedelta(minutes=duration + buffer_minutes)
            ).time()
        if existing_start < end_time and existing_end > start_time:
            raise ValidationError(
                "این بازه با نوبت فعال دیگری برای همین آرایشگر تداخل دارد."
            )


def _find_cross_salon_schedule_conflict(
    *,
    stylist,
    salon,
    date_value,
    start_time,
    end_time,
):
    if not all([stylist, salon, date_value, start_time, end_time]):
        return None

    return (
        StylistSchedule.objects.filter(
            stylist=stylist,
            date=date_value,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        .exclude(salon=salon)
        .select_related("salon")
        .order_by("start_time", "id")
        .first()
    )


def _cross_salon_schedule_conflict_message(conflict):
    salon_name = (
        getattr(getattr(conflict, "salon", None), "salon_name", "") or "مجموعه دیگر"
    )

    return (
        "این متخصص در همین بازه در یک مجموعه دیگر برنامه کاری دارد. "
        f"تداخل: {salon_name}، تاریخ {conflict.date}، "
        f"از {_format_time_for_message(conflict.start_time)} تا {_format_time_for_message(conflict.end_time)}. "
        "برای ثبت برنامه، بازه‌ای خارج از این ساعت انتخاب کنید."
    )


def validate_staff_schedule_request_window(
    *,
    stylist,
    salon,
    date_value,
    start_time,
    end_time,
    service=None,
    exclude_request_id=None,
):
    if not stylist or not salon:
        raise ValidationError(
            "برای ثبت درخواست برنامه کاری، متخصص و مجموعه باید مشخص باشند."
        )

    validate_salon_opening_window(
        salon=salon,
        date_value=date_value,
        start_time=start_time,
        end_time=end_time,
    )

    validate_stylist_time_window(
        stylist=stylist,
        salon=salon,
        date_value=date_value,
        start_time=start_time,
        end_time=end_time,
    )
    cross_salon_conflict = _find_cross_salon_schedule_conflict(
        stylist=stylist,
        salon=salon,
        date_value=date_value,
        start_time=start_time,
        end_time=end_time,
    )

    if cross_salon_conflict:
        raise ValidationError(
            _cross_salon_schedule_conflict_message(cross_salon_conflict)
        )

    pending_conflicts = StaffScheduleRequest.objects.filter(
        stylist=stylist,
        date=date_value,
        status=StaffScheduleRequest.Status.PENDING,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )

    if exclude_request_id:
        pending_conflicts = pending_conflicts.exclude(pk=exclude_request_id)

    if pending_conflicts.exists():
        raise ValidationError(
            "برای این متخصص در همین بازه، درخواست برنامه کاری در انتظار بررسی وجود دارد."
        )

    if service and not service.stylists.filter(pk=stylist.pk).exists():
        raise ValidationError("خدمت انتخاب‌شده برای این متخصص فعال نیست.")

    if service and not service.services_of_salon.filter(pk=salon.pk).exists():
        raise ValidationError("خدمت انتخاب‌شده برای این مجموعه فعال نیست.")


@transaction.atomic
def create_schedule_request(
    *,
    stylist,
    salon,
    date_value,
    start_time,
    end_time,
    service=None,
    note="",
):
    validate_staff_schedule_request_window(
        stylist=stylist,
        salon=salon,
        date_value=date_value,
        start_time=start_time,
        end_time=end_time,
        service=service,
    )

    schedule_request = StaffScheduleRequest.objects.create(
        stylist=stylist,
        salon=salon,
        service=service,
        date=date_value,
        start_time=start_time,
        end_time=end_time,
        note=(note or "").strip(),
        status=StaffScheduleRequest.Status.PENDING,
    )

    _notify_manager_for_schedule_request(schedule_request)

    return schedule_request


@transaction.atomic
def review_schedule_request(*, schedule_request, reviewer, approved, review_note=""):
    if schedule_request.status != StaffScheduleRequest.Status.PENDING:
        raise ValidationError("این درخواست برنامه کاری قبلاً بررسی شده است.")

    if not approved:
        schedule_request.status = StaffScheduleRequest.Status.REJECTED
        schedule_request.reviewed_by = reviewer
        schedule_request.reviewed_at = timezone.now()
        schedule_request.review_note = (review_note or "").strip()
        schedule_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "updated_at",
            ]
        )
        _notify_stylist_for_schedule_review(
            schedule_request,
            approved=False,
            actor=reviewer,
        )
        return schedule_request

    validate_staff_schedule_request_window(
        stylist=schedule_request.stylist,
        salon=schedule_request.salon,
        date_value=schedule_request.date,
        start_time=schedule_request.start_time,
        end_time=schedule_request.end_time,
        service=schedule_request.service,
        exclude_request_id=schedule_request.id,
    )

    cross_salon_conflict = _find_cross_salon_schedule_conflict(
        stylist=schedule_request.stylist,
        salon=schedule_request.salon,
        date_value=schedule_request.date,
        start_time=schedule_request.start_time,
        end_time=schedule_request.end_time,
    )

    if cross_salon_conflict:
        raise ValidationError(
            _cross_salon_schedule_conflict_message(cross_salon_conflict)
        )

    created_schedule = StylistSchedule.objects.create(
        stylist=schedule_request.stylist,
        salon=schedule_request.salon,
        service=schedule_request.service,
        date=schedule_request.date,
        start_time=schedule_request.start_time,
        end_time=schedule_request.end_time,
    )

    schedule_request.status = StaffScheduleRequest.Status.APPROVED
    schedule_request.reviewed_by = reviewer
    schedule_request.reviewed_at = timezone.now()
    schedule_request.review_note = (review_note or "").strip()
    schedule_request.created_schedule = created_schedule
    schedule_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "created_schedule",
            "updated_at",
        ]
    )
    _notify_stylist_for_schedule_review(
        schedule_request,
        approved=True,
        actor=reviewer,
    )
    return schedule_request


def build_stylist_finance_payload(stylist, salon=None):
    earnings = StaffEarning.objects.filter(stylist=stylist).select_related(
        "salon", "order_detail", "financial_snapshot"
    )
    snapshots = OrderDetailFinancialSnapshot.objects.filter(
        stylist=stylist
    ).select_related("salon", "service", "order_detail")
    payout_requests = (
        StaffPayoutRequest.objects.filter(stylist=stylist)
        .select_related("salon")
        .order_by("-requested_at", "-id")
    )
    if salon is not None:
        earnings = earnings.filter(salon=salon)
        snapshots = snapshots.filter(salon=salon)
        payout_requests = payout_requests.filter(salon=salon)

    earning_summary = earnings.aggregate(
        count=Count("id"),
        gross=Sum("gross_share"),
        deductions=Sum("material_deduction"),
        net=Sum("net_profit"),
    )
    payable_earnings = earnings.filter(
        status__in=[StaffEarning.Status.PENDING, StaffEarning.Status.PAYABLE],
        net_profit__gt=0,
    )
    payable_amount = payable_earnings.aggregate(total=Sum("net_profit"))["total"] or 0
    return {
        "staff_earnings": earnings.order_by("-calculated_at", "-created_at")[:100],
        "staff_earning_summary": earning_summary,
        "staff_payable_amount": payable_amount,
        "staff_payout_requests": payout_requests[:50],
        "staff_payable_earnings_count": payable_earnings.count(),
    }


@transaction.atomic
def create_staff_payout_request(
    *, stylist, salon, requested_by=None, amount=None, note=""
):
    if not stylist or not salon:
        raise ValidationError(
            "برای ثبت درخواست پرداخت، سالن و آرایشگر باید مشخص باشند."
        )
    earnings = list(
        StaffEarning.objects.select_for_update()
        .filter(
            stylist=stylist,
            salon=salon,
            status__in=[StaffEarning.Status.PENDING, StaffEarning.Status.PAYABLE],
            net_profit__gt=0,
        )
        .order_by("calculated_at", "created_at", "id")
    )
    total = sum(int(e.net_profit or 0) for e in earnings)
    if total <= 0 or not earnings:
        raise ValidationError(
            "در حال حاضر مطالبه قابل پرداختی برای درخواست وجود ندارد."
        )
    requested_amount = int(amount or total)
    if requested_amount <= 0:
        raise ValidationError("مبلغ درخواست باید بزرگ‌تر از صفر باشد.")
    if requested_amount > total:
        raise ValidationError("مبلغ درخواست از مطالبات قابل پرداخت بیشتر است.")

    payout = StaffPayoutRequest.objects.create(
        salon=salon,
        stylist=stylist,
        requested_amount=requested_amount,
        staff_note=(note or "").strip(),
    )
    payout.earnings.set(earnings)
    now = timezone.now()
    StaffEarning.objects.filter(pk__in=[e.pk for e in earnings]).update(
        status=StaffEarning.Status.REQUESTED,
        requested_at=now,
    )
    return payout


@transaction.atomic
def create_leave_request(
    *,
    stylist,
    salon,
    date_value,
    start_time=None,
    end_time=None,
    reason="",
    actor=None,
    auto_approve=False,
):
    if not stylist or not salon:
        raise ValidationError("برای ثبت درخواست مرخصی، متخصص و مجموعه باید مشخص باشند.")

    if date_value < timezone.localdate():
        raise ValidationError("تاریخ مرخصی نمی‌تواند در گذشته باشد.")

    if (start_time and not end_time) or (end_time and not start_time):
        raise ValidationError(
            "برای مرخصی ساعتی باید ساعت شروع و پایان را با هم وارد کنید."
        )

    if start_time and end_time and end_time <= start_time:
        raise ValidationError("ساعت پایان باید بعد از ساعت شروع باشد.")

    validate_salon_opening_window(
        salon=salon,
        date_value=date_value,
        start_time=start_time,
        end_time=end_time,
        allow_full_day=True,
    )

    appointment_conflicts = _active_appointment_conflicts_for_leave(
        stylist=stylist,
        salon=salon,
        date_value=date_value,
        start_time=start_time,
        end_time=end_time,
    )
    if appointment_conflicts:
        raise ValidationError(
            "برای این بازه نوبت فعال یا آینده وجود دارد. ابتدا نوبت را جابه‌جا، انجام یا با ذکر علت لغو کنید."
        )

    leave_conflicts = StaffLeaveRequest.objects.filter(
        stylist=stylist,
        salon=salon,
        date=date_value,
        status__in=[
            StaffLeaveRequest.Status.PENDING,
            StaffLeaveRequest.Status.APPROVED,
        ],
    ).filter(
        Q(start_time__isnull=True, end_time__isnull=True)
        | (
            Q(start_time__lt=end_time or datetime.max.time())
            & Q(end_time__gt=start_time or datetime.min.time())
        )
    )

    if leave_conflicts.exists():
        raise ValidationError(
            "برای این تاریخ یا بازه، درخواست مرخصی فعال دیگری وجود دارد."
        )

    leave_request = StaffLeaveRequest.objects.create(
        stylist=stylist,
        salon=salon,
        date=date_value,
        start_time=start_time,
        end_time=end_time,
        reason=(reason or "").strip(),
        status=(
            StaffLeaveRequest.Status.APPROVED
            if auto_approve
            else StaffLeaveRequest.Status.PENDING
        ),
        reviewed_by=actor if auto_approve else None,
        reviewed_at=timezone.now() if auto_approve else None,
        review_note="تأیید خودکار از داشبورد متخصص" if auto_approve else "",
    )

    if auto_approve:
        _apply_approved_leave_to_schedules(leave_request)
    else:
        _notify_manager_for_leave_request(leave_request, actor=actor)

    return leave_request


@transaction.atomic
def review_leave_request(*, leave_request, reviewer, approved, review_note=""):
    if leave_request.status != StaffLeaveRequest.Status.PENDING:
        raise ValidationError("این درخواست قبلاً بررسی شده است.")

    if approved:
        validate_salon_opening_window(
            salon=leave_request.salon,
            date_value=leave_request.date,
            start_time=leave_request.start_time,
            end_time=leave_request.end_time,
            allow_full_day=True,
        )

        appointment_conflicts = _active_appointment_conflicts_for_leave(
            stylist=leave_request.stylist,
            salon=leave_request.salon,
            date_value=leave_request.date,
            start_time=leave_request.start_time,
            end_time=leave_request.end_time,
        )
        if appointment_conflicts:
            raise ValidationError(
                "این مرخصی با نوبت فعال یا آینده تداخل دارد. ابتدا نوبت‌ها را جابه‌جا، انجام یا لغو کنید."
            )

    leave_request.status = (
        StaffLeaveRequest.Status.APPROVED
        if approved
        else StaffLeaveRequest.Status.REJECTED
    )
    leave_request.reviewed_by = reviewer
    leave_request.reviewed_at = timezone.now()
    leave_request.review_note = (review_note or "").strip()
    leave_request.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )

    if approved:
        _apply_approved_leave_to_schedules(leave_request)

    _notify_stylist_for_leave_review(
        leave_request,
        approved=approved,
        actor=reviewer,
    )
    return leave_request
