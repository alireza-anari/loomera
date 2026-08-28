from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AppointmentEvent, DelayPolicy, Order, OrderDetail


def get_delay_policy(salon) -> DelayPolicy | None:
    if not salon:
        return None
    policy, _ = DelayPolicy.objects.get_or_create(salon=salon)
    return policy


def record_appointment_event(
    *,
    order_detail: OrderDetail,
    event_type: str,
    actor=None,
    old_status: str = "",
    new_status: str = "",
    note: str = "",
    metadata: dict | None = None,
) -> AppointmentEvent:
    return AppointmentEvent.objects.create(
        order=order_detail.order,
        order_detail=order_detail,
        salon=order_detail.salon,
        stylist=order_detail.stylist,
        event_type=event_type,
        actor=actor,
        old_status=old_status or "",
        new_status=new_status or "",
        note=note or "",
        metadata=metadata or {},
    )


def _safe_appointment_action_url(detail: OrderDetail, *, role: str = "customer") -> str:
    if not detail or not getattr(detail, "pk", None):
        return ""
    if role == "stylist":
        return f"/dashboards/stylist/appointments/{detail.pk}/"
    if role == "manager" and getattr(detail, "salon_id", None):
        return f"/dashboards/calendar/salon/{detail.salon_id}/appointment/{detail.pk}/"
    return f"/orders/appointment_detail/{detail.pk}/"


def _notification_role_value(role) -> str:
    return getattr(role, "value", str(role))


def _is_customer_role(role_value: str) -> bool:
    return str(role_value or "").lower() == "customer"


def _ensure_legacy_customer_notification(
    *,
    detail: OrderDetail,
    event_type: str,
    title: str,
    body: str,
    target_user,
    action_url: str = "",
    priority: str = "normal",
    meta: dict | None = None,
):
    """Mirror lifecycle events into the legacy customer notification center.

    The customer-facing `/notifications/` page still reads `CustomerNotification`,
    while manager/stylist dashboards read the unified notification layer.  Writing
    both records is intentional until the customer center is fully migrated.
    """
    if not getattr(target_user, "pk", None):
        return None
    try:
        with transaction.atomic():
            from apps.accounts.models import CustomerNotification
            from apps.accounts.notifications import create_customer_notification

            priority_value = (priority or "normal").lower()
            if priority_value == "high":
                legacy_priority = CustomerNotification.PRIORITY_HIGH
            elif priority_value == "low":
                legacy_priority = CustomerNotification.PRIORITY_LOW
            else:
                legacy_priority = CustomerNotification.PRIORITY_NORMAL

            metadata = {
                "dedupe_key": f"appointment-lifecycle-customer:{detail.pk}:{event_type}",
                "event_type": event_type,
                "detail_id": detail.pk,
                "order_id": getattr(detail, "order_id", None),
                "salon_id": getattr(detail, "salon_id", None),
                "stylist_id": getattr(detail, "stylist_id", None),
                "skip_unified_sync": True,
                **(meta or {}),
            }
            return create_customer_notification(
                user=target_user,
                category=CustomerNotification.CATEGORY_BOOKING,
                title=title,
                body=body,
                action_url=action_url or _safe_appointment_action_url(detail, role="customer"),
                icon="fa-regular fa-calendar-check",
                priority=legacy_priority,
                metadata=metadata,
                dedupe_key=metadata["dedupe_key"],
            )
    except Exception:
        return None


def _resolve_customer_user(detail: OrderDetail):
    order = getattr(detail, "order", None)
    customer = getattr(order, "customer", None)
    return getattr(customer, "user", None)


def _ensure_dashboard_notification(
    *,
    detail: OrderDetail,
    event_type: str,
    title: str,
    body: str,
    target_user,
    audience_role,
    actor=None,
    action_url: str = "",
    priority: str = "normal",
    meta: dict | None = None,
):
    """Persist one dashboard notification without relying on legacy sync.

    During QA the legacy appointment-notification path could show manager/stylist
    notices while the customer record was missing from the unified notification
    center. This helper writes Notification, NotificationRecipient and
    NotificationDelivery directly and idempotently for every role.
    """
    if not getattr(target_user, "pk", None):
        return None
    try:
        with transaction.atomic():
            from django.contrib.contenttypes.models import ContentType
            from apps.notifications.models import (
                Notification,
                NotificationCategory,
                NotificationChannel,
                NotificationDelivery,
                NotificationDeliveryStatus,
                NotificationPriority,
                NotificationRecipient,
            )
            from apps.notifications.services import (
                _customer_simple_bale_delivery_enabled,
                _stylist_simple_bale_delivery_enabled,
                _manager_default_messaging_actions,
                _stylist_order_detail_messaging_actions,
                notification_preference_enabled,
            )

            role_value = _notification_role_value(audience_role)
            priority_value = NotificationPriority.HIGH if priority == "high" else NotificationPriority.NORMAL
            dedupe_key = f"appointment_lifecycle:{detail.pk}:{event_type}:{role_value}:{target_user.pk}"
            metadata = {
                "detail_id": detail.pk,
                "order_id": getattr(getattr(detail, "order", None), "pk", None),
                "salon_id": getattr(detail, "salon_id", None),
                "stylist_id": getattr(detail, "stylist_id", None),
                "action_url": action_url,
                **(meta or {}),
            }
            content_type = ContentType.objects.get_for_model(detail, for_concrete_model=False)
            notification, created = Notification.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults={
                    "event_type": event_type,
                    "category": NotificationCategory.BOOKING,
                    "priority": priority_value,
                    "title": str(title or "")[:180],
                    "body": body or "",
                    "action_url": action_url or "",
                    "icon": "fa-regular fa-calendar-check",
                    "actor": actor,
                    "salon": getattr(detail, "salon", None),
                    "related_content_type": content_type,
                    "related_object_id": detail.pk,
                    "metadata": metadata,
                },
            )
            if not created:
                changed = []
                for field, value in {
                    "event_type": event_type,
                    "category": NotificationCategory.BOOKING,
                    "priority": priority_value,
                    "title": str(title or "")[:180],
                    "body": body or "",
                    "action_url": action_url or "",
                    "icon": "fa-regular fa-calendar-check",
                    "actor": actor,
                    "salon": getattr(detail, "salon", None),
                    "related_content_type": content_type,
                    "related_object_id": detail.pk,
                    "metadata": {**(notification.metadata or {}), **metadata},
                }.items():
                    if getattr(notification, field) != value:
                        setattr(notification, field, value)
                        changed.append(field)
                if changed:
                    notification.save(update_fields=changed)
            recipient, _ = NotificationRecipient.objects.get_or_create(
                notification=notification,
                user=target_user,
                audience_role=role_value,
            )
            NotificationDelivery.objects.get_or_create(
                recipient=recipient,
                channel=NotificationChannel.DASHBOARD,
                defaults={
                    "status": NotificationDeliveryStatus.SENT,
                    "scheduled_at": timezone.now(),
                    "sent_at": timezone.now(),
                },
            )

            should_queue_bale = False
            notification_metadata = dict(notification.metadata or {})
            messaging_actions = _stylist_order_detail_messaging_actions(
                role=role_value,
                related_object=detail,
                event_type=event_type,
            )
            if not messaging_actions:
                messaging_actions = _manager_default_messaging_actions(
                    role=role_value,
                    salon_id=getattr(detail, "salon_id", None),
                    event_type=event_type,
                )
            if messaging_actions:
                notification_metadata["messaging_actions"] = messaging_actions
                should_queue_bale = True
            elif _customer_simple_bale_delivery_enabled(
                role=role_value,
                notification=notification,
                related_object=detail,
                event_type=event_type,
            ):
                notification_metadata["messaging_customer_simple"] = True
                should_queue_bale = True
            elif _stylist_simple_bale_delivery_enabled(
                role=role_value,
                notification=notification,
                related_object=detail,
                event_type=event_type,
            ):
                notification_metadata["messaging_stylist_simple"] = True
                should_queue_bale = True

            if notification_metadata != (notification.metadata or {}):
                notification.metadata = notification_metadata
                notification.save(update_fields=["metadata"])

            if should_queue_bale and notification_preference_enabled(
                user=target_user,
                audience_role=role_value,
                category=notification.category,
                event_type=event_type,
                channel=NotificationChannel.BALE,
                priority=notification.priority,
            ):
                NotificationDelivery.objects.get_or_create(
                    recipient=recipient,
                    channel=NotificationChannel.BALE,
                    defaults={
                        "status": NotificationDeliveryStatus.QUEUED,
                        "scheduled_at": timezone.now(),
                    },
                )

            if _is_customer_role(role_value):
                _ensure_legacy_customer_notification(
                    detail=detail,
                    event_type=event_type,
                    title=title,
                    body=body,
                    target_user=target_user,
                    action_url=action_url,
                    priority=priority,
                    meta=meta,
                )
            return notification
    except Exception:
        return None


def _notify_appointment_lifecycle(
    *,
    detail: OrderDetail,
    event_type: str,
    title: str,
    body: str,
    actor=None,
    include_customer: bool = True,
    include_stylist: bool = True,
    include_manager: bool = True,
    priority: str = "normal",
    meta: dict | None = None,
) -> None:
    try:
        from apps.notifications.models import NotificationAudienceRole

        customer_user = _resolve_customer_user(detail)
        stylist_user = getattr(getattr(detail, "stylist", None), "user", None)
        manager_user = getattr(getattr(getattr(detail, "salon", None), "salon_manager", None), "user", None)

        recipient_rows = []
        if include_customer and customer_user:
            recipient_rows.append((customer_user, NotificationAudienceRole.CUSTOMER, _safe_appointment_action_url(detail, role="customer")))
        if include_stylist and stylist_user:
            recipient_rows.append((stylist_user, NotificationAudienceRole.STYLIST, _safe_appointment_action_url(detail, role="stylist")))
        if include_manager and manager_user:
            recipient_rows.append((manager_user, NotificationAudienceRole.MANAGER, _safe_appointment_action_url(detail, role="manager")))

        for target_user, role, action_url in recipient_rows:
            _ensure_dashboard_notification(
                detail=detail,
                event_type=event_type,
                title=title,
                body=body,
                target_user=target_user,
                audience_role=role,
                actor=actor,
                action_url=action_url,
                priority=priority,
                meta=meta,
            )
    except Exception:
        pass

def _refresh_order(order: Order) -> Order:
    order.refresh_lifecycle_from_details()
    return order


@transaction.atomic
def confirm_order_detail(
    *,
    detail: OrderDetail,
    actor=None,
    auto: bool = False,
) -> OrderDetail:
    detail = (
        OrderDetail.objects.select_for_update(of=("self",))
        .select_related("order", "service", "stylist", "salon")
        .get(pk=detail.pk)
    )
    if detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED:
        raise ValidationError("این خدمت قبلاً تایید شده است.")
    if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
        raise ValidationError("این خدمت قبلاً رد شده است.")

    sibling_details = detail.order.order_details1.select_for_update(of=("self",))
    was_fully_confirmed = not sibling_details.exclude(
        confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
    ).exists()

    old_status = detail.lifecycle_status
    detail.mark_confirmed(at=timezone.now())
    detail.recompute_schedule_snapshots()
    record_appointment_event(
        order_detail=detail,
        event_type=(
            AppointmentEvent.EventType.STATUS_CHANGED
            if auto
            else AppointmentEvent.EventType.STYLIST_CONFIRMED
        ),
        actor=actor,
        old_status=old_status,
        new_status=detail.lifecycle_status,
        note=(
            "رزرو نهایی‌شده بدون نیاز به تأیید دستی متخصص قطعی شد."
            if auto
            else ""
        ),
        metadata={"auto_confirmed": bool(auto)},
    )

    is_fully_confirmed = not detail.order.order_details1.exclude(
        confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
    ).exists()
    notify_customer = is_fully_confirmed and not was_fully_confirmed

    # Auto-confirm is the normal booking path now. The booking-created
    # notification/SMS already describes the reservation as final, so emitting a
    # second "stylist confirmed" notification here would duplicate the customer
    # message. Manual confirm remains supported for legacy/admin flows.
    if not auto:
        _notify_appointment_lifecycle(
            detail=detail,
            event_type="stylist_confirmed",
            title="نوبت توسط آرایشگر تأیید شد",
            body=(
                "همه خدمات این رزرو تأیید شد و نوبت شما در برنامه کاری سالن قرار گرفت."
                if notify_customer
                else "این نوبت توسط آرایشگر تأیید شد و در برنامه کاری سالن قرار گرفت."
            ),
            actor=actor,
            include_customer=notify_customer,
            include_stylist=True,
            include_manager=True,
            meta={"order_fully_confirmed": notify_customer},
        )

        if notify_customer:
            from apps.orders.lifecycle import (
                queue_customer_booking_confirmed_sms,
            )

            queue_customer_booking_confirmed_sms(
                detail.order,
                order_detail=detail,
            )

    _refresh_order(detail.order)
    return detail


@transaction.atomic
def auto_confirm_order_details(*, order: Order, actor=None) -> list[OrderDetail]:
    """Confirm every pending item after the booking itself is finalized."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == "cancelled":
        return []

    pending_details = list(
        order.order_details1.select_for_update(of=("self",))
        .filter(confirmation_status=OrderDetail.ConfirmationStatus.PENDING)
        .order_by("id")
    )

    confirmed = []
    for detail in pending_details:
        confirmed.append(
            confirm_order_detail(
                detail=detail,
                actor=actor,
                auto=True,
            )
        )

    order.refresh_from_db()
    return confirmed


@transaction.atomic
def reject_order_detail(
    *, detail: OrderDetail, actor=None, reason: str = ""
) -> OrderDetail:
    detail = (
        OrderDetail.objects.select_for_update(of=("self",))
        .select_related("order", "service", "stylist", "salon", "order__customer__user")
        .get(pk=detail.pk)
    )

    if detail.order.status == "cancelled":
        raise ValidationError("این رزرو قبلاً لغو شده است.")

    if (
        detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED
        and (
            detail.customer_arrived_at
            or detail.service_started_at
            or detail.service_completed_at
            or detail.no_show_pending_at
            or detail.no_show_confirmed_at
        )
    ):
        raise ValidationError(
            "بعد از حضور مشتری یا شروع فرایند خدمت، این نوبت از این مسیر قابل لغو نیست."
        )

    if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
        raise ValidationError("این خدمت قبلاً رد شده است.")

    reject_reason = reason or "متخصص اعلام کرد امکان انجام این نوبت را ندارد"
    old_status = detail.lifecycle_status

    detail.mark_rejected(reason=reject_reason, at=timezone.now())

    record_appointment_event(
        order_detail=detail,
        event_type=AppointmentEvent.EventType.STYLIST_REJECTED,
        actor=actor,
        old_status=old_status,
        new_status=detail.lifecycle_status,
        note=reject_reason,
        metadata={"will_cancel_order": True},
    )

    from apps.payments.finance import cancel_order_with_financials

    cancellation = cancel_order_with_financials(
        order=detail.order,
        reason="لغو نوبت به دلیل عدم امکان انجام توسط متخصص",
        refund_reason="عدم امکان انجام نوبت توسط متخصص",
        payment=detail.order.payment_order.order_by("-id").first(),
    )

    try:
        from apps.orders.lifecycle import cancel_order_reminder

        cancel_order_reminder(detail.order)
    except Exception:
        pass

    refund_amount = int(getattr(cancellation, "refund_amount", 0) or 0)

    refund_text = ""
    if refund_amount:
        refund_text = f" مبلغ {refund_amount:,} تومان به کیف پول شما برگشت داده شد."

    service_name = (
        detail.service.service_name if detail.service_id else "خدمت انتخاب‌شده"
    )

    _notify_appointment_lifecycle(
        detail=detail,
        event_type="stylist_rejected_cancelled",
        title="نوبت شما لغو شد",
        body=(
            f"متخصص برای نوبت {service_name} اعلام کرد امکان انجام خدمت را ندارد و رزرو لغو شد."
            f"{refund_text}"
        ),
        actor=actor,
        include_customer=True,
        include_stylist=True,
        include_manager=True,
        priority="high",
        meta={
            "cancelled_by": "stylist_rejection",
            "refund_amount": refund_amount,
            "reason": reject_reason,
        },
    )

    from apps.orders.lifecycle import queue_customer_booking_cancelled_sms

    queue_customer_booking_cancelled_sms(
        detail.order,
        event_type="stylist_rejected_cancelled",
        order_detail=detail,
    )

    detail.order.refresh_from_db()
    return detail


@transaction.atomic
def mark_client_late(*, detail: OrderDetail, actor=None, minutes: int | None = None, note: str = "") -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    if detail.customer_arrived_at:
        raise ValidationError("رسیدن مشتری قبلاً ثبت شده است.")
    if detail.no_show_confirmed_at:
        raise ValidationError("برای این نوبت عدم حضور تایید شده است.")
    if detail.client_late_recorded_at:
        raise ValidationError("تأخیر مشتری برای این نوبت قبلاً ثبت شده است.")
    old_status = detail.lifecycle_status
    start_dt = detail.appointment_start_datetime()
    policy = get_delay_policy(detail.salon)
    grace_minutes = int(policy.grace_period_minutes if policy else 10)
    now = timezone.now()
    if start_dt and now < start_dt + timedelta(minutes=grace_minutes):
        raise ValidationError(f"ثبت تأخیر فقط بعد از شروع نوبت و گذشت {grace_minutes} دقیقه مهلت مجاز امکان‌پذیر است.")
    if minutes is None:
        minutes = max(int((now - start_dt).total_seconds() // 60), 0) if start_dt else 0
    detail.mark_client_late(minutes=minutes, note=note, at=now)
    record_appointment_event(order_detail=detail, event_type=AppointmentEvent.EventType.CLIENT_LATE, actor=actor, old_status=old_status, new_status=detail.lifecycle_status, note=note, metadata={"minutes": detail.client_late_minutes})
    _notify_appointment_lifecycle(
        detail=detail,
        event_type="client_late",
        title="تأخیر مشتری ثبت شد",
        body="تأخیر مشتری برای این نوبت ثبت شد و در تایم‌لاین نوبت قابل پیگیری است.",
        actor=actor,
        include_customer=True,
        include_stylist=True,
        include_manager=True,
        meta={"minutes": detail.client_late_minutes},
    )
    _refresh_order(detail.order)
    return detail


@transaction.atomic
def mark_customer_arrived(*, detail: OrderDetail, actor=None) -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    if detail.confirmation_status != OrderDetail.ConfirmationStatus.CONFIRMED:
        raise ValidationError("ابتدا باید این خدمت توسط آرایشگر تایید شود.")
    if detail.customer_arrived_at:
        raise ValidationError("رسیدن مشتری برای این خدمت قبلاً ثبت شده است.")
    if detail.no_show_confirmed_at:
        raise ValidationError("برای این نوبت عدم حضور تایید شده است.")
    old_status = detail.lifecycle_status
    start_dt = detail.appointment_start_datetime()
    late_minutes = max(int((timezone.now() - start_dt).total_seconds() // 60), 0) if start_dt else 0
    detail.mark_customer_arrived(at=timezone.now())
    if late_minutes and not detail.client_late_minutes:
        detail.client_late_minutes = late_minutes
        detail.client_late_recorded_at = timezone.now()
        detail.save(update_fields=["client_late_minutes", "client_late_recorded_at"])
    record_appointment_event(order_detail=detail, event_type=AppointmentEvent.EventType.CUSTOMER_ARRIVED, actor=actor, old_status=old_status, new_status=detail.lifecycle_status, metadata={"late_minutes": late_minutes})
    _refresh_order(detail.order)
    return detail


@transaction.atomic
def start_service(*, detail: OrderDetail, actor=None) -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    if not detail.customer_arrived_at:
        raise ValidationError("ابتدا باید رسیدن مشتری ثبت شود.")
    if detail.service_started_at:
        raise ValidationError("شروع این خدمت قبلاً ثبت شده است.")
    old_status = detail.lifecycle_status
    detail.mark_service_started(at=timezone.now())
    record_appointment_event(order_detail=detail, event_type=AppointmentEvent.EventType.SERVICE_STARTED, actor=actor, old_status=old_status, new_status=detail.lifecycle_status, metadata={"expected_completed_at": detail.expected_service_completed_at.isoformat() if detail.expected_service_completed_at else None})
    _refresh_order(detail.order)
    return detail


@transaction.atomic
def mark_service_overrun(*, detail: OrderDetail, actor=None, minutes: int | None = None, reason: str = "") -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    if not detail.service_started_at:
        raise ValidationError("ابتدا باید شروع کار ثبت شود.")
    if detail.service_completed_at:
        raise ValidationError("این خدمت قبلاً پایان یافته است.")
    if detail.service_overrun_recorded_at:
        raise ValidationError("طولانی‌شدن این خدمت قبلاً ثبت شده است.")
    old_status = detail.lifecycle_status
    now = timezone.now()
    expected = detail.expected_service_completed_at
    if expected and now < expected:
        raise ValidationError("ثبت طولانی‌شدن خدمت فقط بعد از عبور از زمان مورد انتظار پایان خدمت امکان‌پذیر است.")
    if minutes is None:
        minutes = max(int((now - expected).total_seconds() // 60), 0) if expected else 0
    if int(minutes or 0) <= 0:
        raise ValidationError("برای ثبت طولانی‌شدن خدمت، باید حداقل یک دقیقه از زمان پایان مورد انتظار گذشته باشد.")
    detail.mark_service_overrun(minutes=minutes, reason=reason, at=now)
    record_appointment_event(order_detail=detail, event_type=AppointmentEvent.EventType.SERVICE_OVERRUN, actor=actor, old_status=old_status, new_status=detail.lifecycle_status, note=reason, metadata={"minutes": detail.service_overrun_minutes})
    _refresh_order(detail.order)
    return detail


@transaction.atomic
def complete_service(*, detail: OrderDetail, actor=None) -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    if not detail.service_started_at:
        raise ValidationError("ابتدا باید شروع کار ثبت شود.")
    if detail.service_completed_at:
        raise ValidationError("پایان این خدمت قبلاً ثبت شده است.")
    old_status = detail.lifecycle_status
    detail.mark_service_completed(at=timezone.now())
    record_appointment_event(order_detail=detail, event_type=AppointmentEvent.EventType.SERVICE_COMPLETED, actor=actor, old_status=old_status, new_status=detail.lifecycle_status, metadata={"overrun_minutes": detail.service_overrun_minutes})
    _refresh_order(detail.order)
    return detail


@transaction.atomic
def mark_no_show_pending(
    *,
    detail: OrderDetail,
    actor=None,
    note: str = "",
    notify: bool = True,
) -> OrderDetail:
    detail = (
        OrderDetail.objects.select_for_update(of=("self",))
        .select_related("order", "service", "stylist", "salon")
        .get(pk=detail.pk)
    )
    if detail.customer_arrived_at:
        raise ValidationError("برای نوبتی که حضور مشتری ثبت شده، عدم حضور قابل ثبت نیست.")
    if detail.service_started_at:
        raise ValidationError("برای نوبتی که خدمت شروع شده، عدم حضور قابل ثبت نیست.")
    if detail.no_show_pending_at:
        raise ValidationError("عدم حضور برای این نوبت قبلاً در انتظار بررسی ثبت شده است.")

    policy = get_delay_policy(detail.salon)
    start_dt = detail.appointment_start_datetime()
    threshold_minutes = int(policy.no_show_after_minutes if policy else 20)
    if start_dt and timezone.now() < start_dt + timedelta(minutes=threshold_minutes):
        raise ValidationError(
            f"ثبت عدم حضور فقط بعد از گذشت {threshold_minutes} دقیقه از زمان نوبت امکان‌پذیر است."
        )

    dispute_until = timezone.now() + timedelta(
        hours=int(policy.no_show_dispute_window_hours if policy else 12)
    )
    old_status = detail.lifecycle_status
    detail.mark_no_show_pending(
        dispute_until=dispute_until,
        note=note,
        at=timezone.now(),
    )
    record_appointment_event(
        order_detail=detail,
        event_type=AppointmentEvent.EventType.NO_SHOW_PENDING,
        actor=actor,
        old_status=old_status,
        new_status=detail.lifecycle_status,
        note=note,
        metadata={"dispute_until": dispute_until.isoformat()},
    )

    if notify:
        _notify_appointment_lifecycle(
            detail=detail,
            event_type="no_show_pending_review",
            title="عدم حضور مشتری در انتظار بررسی ثبت شد",
            body="برای این نوبت عدم حضور مشتری ثبت شده و تا پایان مهلت بررسی قابل پیگیری است.",
            actor=actor,
            include_customer=True,
            include_stylist=True,
            include_manager=True,
            priority="high",
            meta={"dispute_until": dispute_until.isoformat()},
        )

    _refresh_order(detail.order)
    return detail

def _get_active_no_show_policy(detail: OrderDetail):
    try:
        from django.db.models import Q
        from apps.payments.models import CancellationPolicy

        now = timezone.now()
        return (
            CancellationPolicy.objects.filter(salon=detail.salon, is_enabled=True)
            .filter(Q(service=detail.service) | Q(service__isnull=True))
            .filter(Q(effective_from__isnull=True) | Q(effective_from__lte=now))
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=now))
            .order_by("-service_id", "-id")
            .first()
        )
    except Exception:
        return None


def _calculate_no_show_penalty_amount(detail: OrderDetail, *, paid_amount: int) -> int:
    policy = _get_active_no_show_policy(detail)
    item_amount = max(int(getattr(detail, "price", 0) or 0), 0)
    if not policy:
        # If no explicit no-show/cancellation policy is configured, do not keep
        # money by default.  The previous fallback used salon-level
        # cancellation_refund_percent where a blank/zero value could mean a full
        # penalty and therefore no wallet refund, which is unsafe for QA and
        # for unconfigured salons.
        return 0

    penalty_type = getattr(policy, "no_show_penalty_type", "none") or "none"
    value = max(int(getattr(policy, "no_show_penalty_value", 0) or 0), 0)
    if penalty_type == "fixed_amount":
        penalty = value
    elif penalty_type == "percentage_of_service_price":
        penalty = int((item_amount * value) / 100)
    elif penalty_type == "deposit_amount":
        # If no explicit deposit model is present, the digital amount already paid
        # is the safest cap for a deposit-equivalent penalty.
        penalty = min(paid_amount, item_amount or paid_amount)
    else:
        penalty = 0
    return max(min(penalty, item_amount or paid_amount), 0)


def _resolve_no_show_paid_amount(detail: OrderDetail, order: Order) -> dict:
    """Return the refundable paid context for a confirmed no-show.

    Online payments in Loomera can be represented in either the legacy Payment
    table, the newer PaymentTransaction table, or only on the Order flags in
    older test data.  The previous implementation only looked at
    Payment(is_finally=True), so successful wallet/online payments could be
    missed and no wallet refund was created.
    """
    try:
        from django.db.models import Q, Sum
        from apps.payments.finance import DIGITAL_PAYMENT_METHODS
        from apps.payments.models import Payment, PaymentTransaction

        digital_methods = set(DIGITAL_PAYMENT_METHODS) | {"online", "wallet"}
        method = (getattr(order, "selected_payment_method", "") or "").strip()

        paid_amount = 0
        payment = None
        payment_transaction = None
        source = ""

        digital_tx_qs = PaymentTransaction.objects.filter(order=order).filter(
            status=PaymentTransaction.Status.PAID,
        ).exclude(method=PaymentTransaction.Method.PAY_AT_VENUE)
        detail_tx_qs = digital_tx_qs.filter(Q(order_detail=detail) | Q(order_detail__isnull=True))
        tx_amount = int(detail_tx_qs.aggregate(total=Sum("amount")).get("total") or 0)
        payment_transaction = detail_tx_qs.order_by("-paid_at", "-id").first()
        if tx_amount > 0:
            paid_amount = tx_amount
            source = "payment_transaction"

        if paid_amount <= 0:
            payment_qs = (
                Payment.objects.filter(order=order)
                .filter(Q(is_finally=True) | Q(state=Payment.State.SUCCESS) | Q(verified_at__isnull=False) | Q(ref_id__isnull=False))
                .exclude(provider=Payment.Provider.MANUAL)
            )
            payment = payment_qs.order_by("-verified_at", "-register_date", "-id").first()
            if payment:
                paid_amount = int(payment.amount or 0)
                source = "payment"

        if paid_amount <= 0 and getattr(order, "is_paid", False) and method in digital_methods:
            paid_amount = int(getattr(order, "total_amount", 0) or 0)
            source = "order_flags"

        is_digital_paid = bool(paid_amount > 0 and (method in digital_methods or payment or payment_transaction))
        return {
            "is_digital_paid": is_digital_paid,
            "paid_amount": int(paid_amount or 0),
            "payment": payment,
            "payment_transaction": payment_transaction,
            "source": source,
            "method": method,
        }
    except Exception as exc:
        return {"is_digital_paid": False, "paid_amount": 0, "error": str(exc), "source": "error"}


def _find_existing_no_show_wallet_refund(*, order: Order):
    try:
        from apps.payments.models import WalletTransaction

        customer_user = getattr(getattr(order, "customer", None), "user", None)
        if not customer_user:
            return None
        return (
            WalletTransaction.objects.filter(
                wallet__user=customer_user,
                order=order,
                transaction_type=WalletTransaction.TransactionType.REFUND,
            )
            .filter(description__icontains="عدم حضور")
            .order_by("-id")
            .first()
        )
    except Exception:
        return None


def _sync_refund_request(*, order: Order, amount: int, actor=None, payment_transaction=None, status=None):
    from apps.payments.models import RefundRequest

    reason = "بازگشت وجه خودکار پس از تأیید عدم حضور مشتری طبق قوانین کنسلی سالن"
    refund_request = (
        RefundRequest.objects.filter(order=order, reason=reason)
        .order_by("-id")
        .first()
    )
    if not refund_request:
        refund_request = RefundRequest.objects.create(
            order=order,
            amount=max(int(amount or 0), 0),
            reason=reason,
            status=status or (RefundRequest.Status.REFUNDED if int(amount or 0) > 0 else RefundRequest.Status.APPROVED),
            requested_by=actor,
            reviewed_by=actor,
            payment_transaction=payment_transaction,
        )
        return refund_request

    changed = []
    desired = {
        "amount": max(int(amount or 0), 0),
        "status": status or (RefundRequest.Status.REFUNDED if int(amount or 0) > 0 else RefundRequest.Status.APPROVED),
        "reviewed_by": actor or refund_request.reviewed_by,
        "payment_transaction": payment_transaction or refund_request.payment_transaction,
    }
    for field, value in desired.items():
        if getattr(refund_request, field) != value:
            setattr(refund_request, field, value)
            changed.append(field)
    if changed:
        changed.append("updated_at")
        refund_request.save(update_fields=changed)
    return refund_request


def _calculate_no_show_refund_amount(detail: OrderDetail, *, paid_amount: int) -> dict:
    """Calculate the wallet refund target for a confirmed no-show.

    For the user-facing no-show flow we use the salon cancellation refund
    percentage as the authoritative fallback rule because that is what managers
    configure in the salon dashboard.  A dedicated CancellationPolicy only
    overrides it when an explicit no-show penalty is configured.
    """
    paid_amount = max(int(paid_amount or 0), 0)
    item_amount = max(int(getattr(detail, "price", 0) or 0), 0) or paid_amount
    refund_base = min(paid_amount, item_amount or paid_amount)

    policy = _get_active_no_show_policy(detail)
    if policy and (getattr(policy, "no_show_penalty_type", "none") or "none") != "none":
        penalty_type = getattr(policy, "no_show_penalty_type", "none") or "none"
        value = max(int(getattr(policy, "no_show_penalty_value", 0) or 0), 0)
        if penalty_type == "fixed_amount":
            penalty_amount = value
        elif penalty_type == "percentage_of_service_price":
            penalty_amount = int((item_amount * value) / 100)
        elif penalty_type == "deposit_amount":
            # In the current product there is no separate deposit amount model
            # on the order detail. Treat this as the item amount cap, not the
            # whole order amount, so one item no-show cannot swallow unrelated
            # services.
            penalty_amount = item_amount
        else:
            penalty_amount = 0
        penalty_amount = max(min(int(penalty_amount or 0), refund_base), 0)
        return {
            "refund_base": refund_base,
            "penalty_amount": penalty_amount,
            "refund_amount": max(refund_base - penalty_amount, 0),
            "policy_source": "cancellation_policy",
            "penalty_type": penalty_type,
        }

    refund_percent = 100
    try:
        refund_percent = int(getattr(detail.salon, "cancellation_refund_percent", 100) or 0)
    except Exception:
        refund_percent = 100
    refund_percent = max(min(refund_percent, 100), 0)
    refund_amount = int((refund_base * refund_percent) / 100)
    return {
        "refund_base": refund_base,
        "penalty_amount": max(refund_base - refund_amount, 0),
        "refund_amount": max(min(refund_amount, refund_base), 0),
        "policy_source": "salon_cancellation_refund_percent",
        "refund_percent": refund_percent,
    }


def _existing_wallet_refund_total(*, order: Order, customer_user=None) -> int:
    try:
        from django.db.models import Sum
        from apps.payments.models import WalletTransaction

        customer_user = customer_user or getattr(getattr(order, "customer", None), "user", None)
        if not customer_user:
            return 0
        total = (
            WalletTransaction.objects.filter(
                wallet__user=customer_user,
                order=order,
                transaction_type=WalletTransaction.TransactionType.REFUND,
            )
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        return max(int(total or 0), 0)
    except Exception:
        return 0


def _credit_no_show_refund_delta(*, order: Order, target_amount: int, actor=None) -> dict:
    """Make wallet refund idempotent by crediting only the missing delta."""
    from apps.payments.models import Wallet, WalletTransaction

    customer_user = getattr(getattr(order, "customer", None), "user", None)
    if not customer_user:
        return {"credited": 0, "existing_wallet_refund": 0, "reason": "missing_customer_user"}

    target_amount = max(int(target_amount or 0), 0)
    existing_amount = _existing_wallet_refund_total(order=order, customer_user=customer_user)
    delta = max(target_amount - existing_amount, 0)

    if delta > 0:
        wallet, _ = Wallet.objects.get_or_create(user=customer_user)
        wallet.deposit(
            amount=delta,
            description=f"بازگشت وجه عدم حضور رزرو {getattr(order, 'order_number', order.pk)} طبق قوانین کنسلی سالن",
            transaction_type=WalletTransaction.TransactionType.REFUND,
            order=order,
        )
        existing_amount += delta

    if target_amount > 0 or existing_amount > 0:
        order.refunded_to_wallet_amount = max(target_amount, existing_amount)
        order.refunded_to_wallet_at = order.refunded_to_wallet_at or timezone.now()
        order.save(update_fields=["refunded_to_wallet_amount", "refunded_to_wallet_at", "update_date"])

    return {"credited": delta, "existing_wallet_refund": existing_amount}


def apply_no_show_refund_policy(*, detail: OrderDetail, actor=None, force_full_refund: bool = False) -> dict:
    """Refund the customer's wallet after confirmed no-show.

    This is intentionally idempotent: it computes the target refund amount and
    deposits only the missing delta, so repeated UI clicks or repair commands do
    not double-credit the customer.
    """
    try:
        with transaction.atomic():
            detail = OrderDetail.objects.select_related("salon", "service").get(pk=detail.pk)
            # Lock only the Order row. PostgreSQL does not allow FOR UPDATE on
            # the nullable side of OUTER JOINs; using select_related() here can
            # create exactly that join for customer/user on some databases.
            order = Order.objects.select_for_update(of=("self",)).get(pk=detail.order_id)
            customer_user = getattr(getattr(order, "customer", None), "user", None)
            if not customer_user:
                return {"eligible": False, "refund_amount": 0, "reason": "missing_customer_user"}

            paid_context = _resolve_no_show_paid_amount(detail, order)
            if not paid_context.get("is_digital_paid"):
                return {
                    "eligible": False,
                    "refund_amount": 0,
                    "reason": "not_digital_paid",
                    **paid_context,
                }

            paid_amount = int(paid_context.get("paid_amount") or 0)
            if paid_amount <= 0:
                return {"eligible": False, "refund_amount": 0, "reason": "no_paid_amount", **paid_context}

            if force_full_refund:
                amounts = {
                    "refund_base": paid_amount,
                    "penalty_amount": 0,
                    "refund_amount": paid_amount,
                    "policy_source": "force_full_refund",
                }
            else:
                amounts = _calculate_no_show_refund_amount(detail, paid_amount=paid_amount)

            refund_amount = int(amounts.get("refund_amount") or 0)
            refund_request = _sync_refund_request(
                order=order,
                amount=refund_amount,
                actor=actor,
                payment_transaction=paid_context.get("payment_transaction"),
            )
            credit_result = _credit_no_show_refund_delta(
                order=order,
                target_amount=refund_amount,
                actor=actor,
            )

            credited_amount = int(credit_result.get("credited") or 0)

            # No-show wallet refunds are customer-facing compensations.  They
            # must not be synced as salon/stylist cost reversals, otherwise the
            # refund appears in salon and stylist finance screens as a cost.
            # Settlement sync is intentionally skipped here; cancellation
            # refunds still use the normal settlement path elsewhere.
            if credited_amount > 0:
                _notify_appointment_lifecycle(
                    detail=detail,
                    event_type="no_show_wallet_refund",
                    title="بازگشت وجه به کیف پول شما انجام شد",
                    body=f"مبلغ {credited_amount:,} تومان بابت عدم حضور و طبق قوانین کنسلی سالن به کیف پول شما برگشت داده شد.",
                    actor=actor,
                    include_customer=True,
                    include_stylist=False,
                    include_manager=False,
                    priority="high",
                    meta={
                        "refund_amount": credited_amount,
                        "refund_request_id": getattr(refund_request, "pk", None),
                        "reason": "no_show_refund",
                    },
                )

            return {
                "eligible": True,
                "refund_amount": refund_amount,
                "credited": credited_amount,
                "existing_wallet_refund": int(credit_result.get("existing_wallet_refund") or 0),
                "penalty_amount": int(amounts.get("penalty_amount") or 0),
                "refund_base": int(amounts.get("refund_base") or 0),
                "refund_request_id": getattr(refund_request, "pk", None),
                "source": paid_context.get("source"),
                "method": paid_context.get("method"),
                "policy_source": amounts.get("policy_source"),
                "refund_percent": amounts.get("refund_percent"),
            }
    except Exception as exc:
        return {"eligible": False, "refund_amount": 0, "error": str(exc), "error_type": exc.__class__.__name__}

@transaction.atomic
def confirm_no_show(*, detail: OrderDetail, actor=None, note: str = "") -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    if not detail.no_show_pending_at:
        raise ValidationError("ابتدا باید عدم حضور در انتظار بررسی ثبت شود.")

    already_confirmed = bool(detail.no_show_confirmed_at)
    old_status = detail.lifecycle_status
    if not already_confirmed:
        detail.mark_no_show_confirmed(confirmed_by=actor, note=note, at=timezone.now())

    # Important: refund must also run for no-show records that were confirmed
    # before the latest refund patch.  Previously the function returned early
    # when no_show_confirmed_at already existed, so legacy confirmed no-shows
    # could never be repaired from the UI or shell.
    refund_result = apply_no_show_refund_policy(detail=detail, actor=actor)

    if not already_confirmed:
        record_appointment_event(
            order_detail=detail,
            event_type=AppointmentEvent.EventType.NO_SHOW_CONFIRMED,
            actor=actor,
            old_status=old_status,
            new_status=detail.lifecycle_status,
            note=note,
            metadata={"refund": refund_result},
        )

    refund_amount = int(refund_result.get("refund_amount") or 0)
    refund_note = f" مبلغ {refund_amount:,} تومان طبق قوانین سالن به کیف پول شما برگشت داده شد." if refund_amount > 0 else " اگر مبلغی برای این نوبت قابل بازگشت باشد، طبق قوانین سالن در بخش مالی پیگیری می‌شود."
    _notify_appointment_lifecycle(
        detail=detail,
        event_type="no_show_confirmed",
        title="عدم حضور مشتری تأیید شد",
        body="عدم حضور مشتری برای این نوبت تأیید شد." + refund_note,
        actor=actor,
        include_customer=True,
        include_stylist=True,
        include_manager=True,
        priority="high",
        meta={"refund": refund_result},
    )
    _refresh_order(detail.order)
    return detail


@transaction.atomic
def mark_disputed(*, detail: OrderDetail, actor=None, note: str = "") -> OrderDetail:
    detail = OrderDetail.objects.select_for_update(of=("self",)).select_related("order", "service", "stylist", "salon").get(pk=detail.pk)
    old_status = detail.lifecycle_status
    detail.mark_disputed(note=note, at=timezone.now())
    record_appointment_event(order_detail=detail, event_type=AppointmentEvent.EventType.DISPUTED, actor=actor, old_status=old_status, new_status=detail.lifecycle_status, note=note)
    _notify_appointment_lifecycle(
        detail=detail,
        event_type="appointment_disputed",
        title="پرونده اختلاف برای نوبت ایجاد شد",
        body="این نوبت برای بررسی اختلاف علامت‌گذاری شد و از بخش پشتیبانی قابل پیگیری است.",
        actor=actor,
        include_customer=True,
        include_stylist=True,
        include_manager=True,
        priority="high",
    )
    try:
        from apps.main.models import DisputeCase
        from apps.main.support_services import open_dispute_case

        if not DisputeCase.objects.filter(order_detail=detail, dispute_type="no_show").exists():
            open_dispute_case(
                dispute_type="no_show" if detail.no_show_pending_at else "general",
                opened_by=actor,
                order=detail.order,
                order_detail=detail,
                salon=detail.salon,
                stylist=detail.stylist,
                customer=getattr(detail.order, "customer", None),
                subject="اختلاف مربوط به نوبت",
                description=note or "پرونده اختلاف از چرخه نوبت ایجاد شد.",
            )
    except Exception:
        pass
    order = detail.order
    order.status = "disputed"
    order.save(update_fields=["status", "update_date"])
    return detail
