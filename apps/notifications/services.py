from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    Notification,
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationPreference,
    NotificationPriority,
    NotificationRecipient,
    NotificationTemplate,
)
from django.core.exceptions import ObjectDoesNotExist


class SafeDict(dict):
    def __missing__(self, key):
        return ""


@dataclass
class RecipientSpec:
    user: Any
    audience_role: str = NotificationAudienceRole.CUSTOMER
    channels: tuple[str, ...] = (NotificationChannel.DASHBOARD,)


def _format_template(value: str, context: dict[str, Any] | None) -> str:
    if not value:
        return ""
    try:
        return str(value).format_map(SafeDict(context or {}))
    except Exception:
        return str(value)


def get_active_template(*, event_type: str, audience_role: str, channel: str):
    return (
        NotificationTemplate.objects.filter(
            event_type=event_type,
            channel=channel,
            is_active=True,
        )
        .filter(audience_role__in=[audience_role or "", ""])
        .order_by("-audience_role", "-id")
        .first()
    )


def render_notification_payload(
    *,
    event_type: str,
    audience_role: str,
    channel: str = NotificationChannel.DASHBOARD,
    title: str = "",
    body: str = "",
    action_url: str = "",
    icon: str = "",
    category: str = NotificationCategory.SYSTEM,
    priority: str = NotificationPriority.NORMAL,
    context: dict[str, Any] | None = None,
):
    template = get_active_template(
        event_type=event_type, audience_role=audience_role, channel=channel
    )
    if not template:
        return {
            "title": title,
            "body": body,
            "action_url": action_url,
            "icon": icon or "fa-regular fa-bell",
            "category": category,
            "priority": priority,
        }

    return {
        "title": _format_template(template.title_template, context) or title,
        "body": _format_template(template.body_template, context) or body,
        "action_url": _format_template(template.action_url_template, context)
        or action_url,
        "icon": template.icon or icon or "fa-regular fa-bell",
        "category": template.category or category,
        "priority": template.priority or priority,
    }


def _legacy_customer_preference_enabled(
    *,
    user,
    audience_role: str,
    category: str,
    channel: str,
) -> bool | None:
    if audience_role != NotificationAudienceRole.CUSTOMER:
        return None

    appointment_categories = {
        NotificationCategory.BOOKING,
        NotificationCategory.PAYMENT,
        NotificationCategory.FINANCE,
    }

    field_name = None

    if category in appointment_categories:
        field_name = {
            NotificationChannel.EMAIL: "notify_appointment_email",
            NotificationChannel.SMS: "notify_appointment_sms",
            NotificationChannel.WHATSAPP: "notify_appointment_whatsapp",
        }.get(channel)

    elif category == NotificationCategory.MARKETING:
        field_name = {
            NotificationChannel.EMAIL: "notify_marketing_email",
            NotificationChannel.SMS: "notify_marketing_sms",
            NotificationChannel.WHATSAPP: "notify_marketing_whatsapp",
        }.get(channel)

    if not field_name:
        return None

    try:
        customer = user.customer_profile
    except (AttributeError, ObjectDoesNotExist):
        return None

    return bool(getattr(customer, field_name, True))


def notification_preference_enabled(
    *,
    user,
    audience_role: str,
    category: str,
    event_type: str,
    channel: str,
    priority: str,
) -> bool:
    if channel in {NotificationChannel.DASHBOARD, NotificationChannel.SYSTEM}:
        return True

    if priority == NotificationPriority.CRITICAL:
        return True

    qs = NotificationPreference.objects.filter(user=user, channel=channel)
    candidates = [
        {"audience_role": audience_role, "event_type": event_type},
        {"audience_role": audience_role, "category": category, "event_type": ""},
        {"audience_role": audience_role, "category": "", "event_type": ""},
        {"audience_role": "", "category": category, "event_type": ""},
        {"audience_role": "", "category": "", "event_type": ""},
    ]
    for filters in candidates:
        pref = qs.filter(**filters).order_by("-id").first()
        if pref is not None:
            return bool(pref.is_enabled)

    legacy_enabled = _legacy_customer_preference_enabled(
        user=user,
        audience_role=audience_role,
        category=category,
        channel=channel,
    )

    if legacy_enabled is not None:
        return legacy_enabled

    return True


def _related_content_type(related_object):
    if related_object is None:
        return None, None
    return (
        ContentType.objects.get_for_model(related_object, for_concrete_model=False),
        related_object.pk,
    )


def _normalize_recipients(
    recipients: Iterable[RecipientSpec | dict | Any], default_channels
):
    specs = []
    for item in recipients or []:
        if isinstance(item, RecipientSpec):
            specs.append(item)
            continue
        if isinstance(item, dict):
            user = item.get("user")
            if user:
                specs.append(
                    RecipientSpec(
                        user=user,
                        audience_role=item.get("audience_role")
                        or item.get("role")
                        or NotificationAudienceRole.CUSTOMER,
                        channels=tuple(item.get("channels") or default_channels),
                    )
                )
            continue
        if item:
            specs.append(RecipientSpec(user=item, channels=tuple(default_channels)))
    return specs


@transaction.atomic
def create_notification(
    *,
    event_type: str,
    title: str,
    body: str = "",
    recipients: Iterable[RecipientSpec | dict | Any],
    category: str = NotificationCategory.SYSTEM,
    priority: str = NotificationPriority.NORMAL,
    action_url: str = "",
    icon: str = "",
    channels: Iterable[str] = (NotificationChannel.DASHBOARD,),
    actor=None,
    salon=None,
    related_object=None,
    metadata: dict[str, Any] | None = None,
    dedupe_key: str = "",
    template_context: dict[str, Any] | None = None,
) -> Notification:
    default_channels = tuple(channels or (NotificationChannel.DASHBOARD,))
    recipient_specs = _normalize_recipients(recipients, default_channels)
    related_ct, related_id = _related_content_type(related_object)
    notification_metadata = dict(metadata or {})

    if dedupe_key:
        notification_metadata["dedupe_key"] = dedupe_key
        notification, _ = Notification.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "event_type": event_type,
                "category": category,
                "priority": priority,
                "title": str(title or "")[:180],
                "body": body or "",
                "action_url": action_url or "",
                "icon": icon or "fa-regular fa-bell",
                "actor": actor,
                "salon": salon,
                "related_content_type": related_ct,
                "related_object_id": related_id,
                "metadata": notification_metadata,
            },
        )
    else:
        notification = Notification.objects.create(
            event_type=event_type,
            category=category,
            priority=priority,
            title=str(title or "")[:180],
            body=body or "",
            action_url=action_url or "",
            icon=icon or "fa-regular fa-bell",
            actor=actor,
            salon=salon,
            related_content_type=related_ct,
            related_object_id=related_id,
            metadata=notification_metadata,
        )

    for spec in recipient_specs:
        if not getattr(spec.user, "pk", None):
            continue

        payload = render_notification_payload(
            event_type=event_type,
            audience_role=spec.audience_role,
            channel=NotificationChannel.DASHBOARD,
            title=notification.title,
            body=notification.body,
            action_url=notification.action_url,
            icon=notification.icon,
            category=notification.category,
            priority=notification.priority,
            context=template_context or notification_metadata,
        )
        if (
            payload["title"] != notification.title
            or payload["body"] != notification.body
        ):
            # Keep the canonical notification close to dashboard rendering for the first recipient.
            notification.title = payload["title"][:180]
            notification.body = payload["body"]
            notification.action_url = payload["action_url"]
            notification.icon = payload["icon"]
            notification.category = payload["category"]
            notification.priority = payload["priority"]
            notification.save(
                update_fields=[
                    "title",
                    "body",
                    "action_url",
                    "icon",
                    "category",
                    "priority",
                ]
            )

        recipient, _ = NotificationRecipient.objects.get_or_create(
            notification=notification,
            user=spec.user,
            audience_role=spec.audience_role,
        )

        channels_for_recipient = list(tuple(spec.channels or default_channels))
        manager_actions = _manager_object_messaging_actions(
            role=spec.audience_role,
            related_object=related_object,
            event_type=event_type,
        )
        if not manager_actions:
            manager_actions = _manager_default_messaging_actions(
                role=spec.audience_role,
                salon_id=getattr(salon, "pk", None),
                event_type=event_type,
            )
        if manager_actions:
            current_metadata = dict(notification.metadata or {})
            if not current_metadata.get("messaging_actions"):
                current_metadata["messaging_actions"] = manager_actions
                notification.metadata = current_metadata
                notification.save(update_fields=["metadata"])
            if NotificationChannel.BALE not in channels_for_recipient:
                channels_for_recipient.append(NotificationChannel.BALE)

        if _customer_simple_bale_delivery_enabled(
            role=spec.audience_role,
            notification=notification,
            related_object=related_object,
            event_type=event_type,
        ):
            current_metadata = dict(notification.metadata or {})
            if not current_metadata.get("messaging_customer_simple"):
                current_metadata["messaging_customer_simple"] = True
                notification.metadata = current_metadata
                notification.save(update_fields=["metadata"])
            if NotificationChannel.BALE not in channels_for_recipient:
                channels_for_recipient.append(NotificationChannel.BALE)

        for channel in tuple(channels_for_recipient):
            if not notification_preference_enabled(
                user=spec.user,
                audience_role=spec.audience_role,
                category=notification.category,
                event_type=event_type,
                channel=channel,
                priority=notification.priority,
            ):
                continue
            status = (
                NotificationDeliveryStatus.SENT
                if channel
                in {NotificationChannel.DASHBOARD, NotificationChannel.SYSTEM}
                else NotificationDeliveryStatus.QUEUED
            )
            try:
                NotificationDelivery.objects.get_or_create(
                    recipient=recipient,
                    channel=channel,
                    defaults={
                        "status": status,
                        "scheduled_at": timezone.now(),
                        "sent_at": (
                            timezone.now()
                            if status == NotificationDeliveryStatus.SENT
                            else None
                        ),
                    },
                )
            except IntegrityError:
                pass

    return notification


def unread_count(user, *, audience_role: str | None = None) -> int:
    qs = NotificationRecipient.objects.filter(
        user=user, is_read=False, is_archived=False
    )
    if audience_role:
        qs = qs.filter(audience_role=audience_role)
    return qs.count()


def list_user_notifications(
    user, *, audience_role: str | None = None, filter_status: str = "all"
):
    qs = NotificationRecipient.objects.select_related("notification").filter(
        user=user, is_archived=False
    )
    if audience_role:
        qs = qs.filter(audience_role=audience_role)
    if filter_status == "unread":
        qs = qs.filter(is_read=False)
    elif filter_status == "read":
        qs = qs.filter(is_read=True)
    return qs.order_by("-created_at", "-id")


def mark_recipient_read(recipient: NotificationRecipient):
    recipient.mark_as_read()
    return recipient


def mark_all_read(user, *, audience_role: str | None = None) -> int:
    qs = NotificationRecipient.objects.filter(user=user, is_read=False)
    if audience_role:
        qs = qs.filter(audience_role=audience_role)
    return qs.update(is_read=True, read_at=timezone.now())


def _customer_simple_bale_delivery_enabled(
    *, role: str, notification, related_object, event_type: str
) -> bool:
    """Queue simple Bale deliveries for customer-facing booking/payment notices.

    This deliberately does not create messaging_actions. Customer-side booking,
    payment, cancellation and review flows remain links to the website in stage 9.
    """

    if str(role or "") != NotificationAudienceRole.CUSTOMER:
        return False

    metadata = dict(getattr(notification, "metadata", None) or {})
    if metadata.get("messaging_disable_bale"):
        return False

    category = str(getattr(notification, "category", "") or "")
    if category in {NotificationCategory.BOOKING, NotificationCategory.PAYMENT}:
        return True

    event_text = str(event_type or "").lower()
    customer_keywords = (
        "appointment",
        "booking",
        "reservation",
        "payment",
        "reminder",
        "review",
        "cancel",
        "refund",
        "order",
    )
    if any(keyword in event_text for keyword in customer_keywords):
        return True

    try:
        from apps.orders.models import Order, OrderDetail

        return isinstance(related_object, (Order, OrderDetail))
    except Exception:
        return False


def _stylist_order_detail_messaging_actions(
    *, role: str, related_object, event_type: str
) -> list[dict[str, Any]]:
    """Build safe bot action specs for stylist appointment notifications.

    The actual execution still happens in apps.messaging action handlers, where
    token ownership, stylist ownership, active salon membership and permissions
    are checked again at click time.
    """

    if str(role or "") != NotificationAudienceRole.STYLIST:
        return []

    try:
        from apps.orders.models import OrderDetail
        from apps.messaging.stylist_actions import (
            ACTION_COMPLETE_SERVICE,
            ACTION_CONFIRM_APPOINTMENT,
            ACTION_REJECT_APPOINTMENT,
            ACTION_START_SERVICE,
        )
    except Exception:
        return []

    if not isinstance(related_object, OrderDetail):
        return []

    detail = related_object
    try:
        if getattr(getattr(detail, "order", None), "status", "") == "cancelled":
            return []

        common = {
            "audience_role": NotificationAudienceRole.STYLIST,
            "salon_id": detail.salon_id,
            "metadata": {
                "order_detail_id": detail.pk,
                "source": "appointment_notification",
            },
        }

        if detail.confirmation_status == OrderDetail.ConfirmationStatus.PENDING:
            return [
                {
                    "type": "action",
                    "key": ACTION_CONFIRM_APPOINTMENT,
                    "label": "تایید",
                    **common,
                },
                {
                    "type": "action",
                    "key": ACTION_REJECT_APPOINTMENT,
                    "label": "رد",
                    **common,
                },
            ]

        if detail.confirmation_status != OrderDetail.ConfirmationStatus.CONFIRMED:
            return []

        if detail.customer_arrived_at and not detail.service_started_at:
            return [
                {
                    "type": "action",
                    "key": ACTION_START_SERVICE,
                    "label": "شروع خدمت",
                    **common,
                },
            ]

        if detail.service_started_at and not detail.service_completed_at:
            return [
                {
                    "type": "action",
                    "key": ACTION_COMPLETE_SERVICE,
                    "label": "اتمام خدمت",
                    **common,
                },
            ]
    except Exception:
        return []

    return []


def _manager_object_messaging_actions(
    *, role: str, related_object, event_type: str
) -> list[dict[str, Any]]:
    """Build safe bot action specs for manager-side staff notifications."""

    if str(role or "") != NotificationAudienceRole.MANAGER:
        return []

    try:
        from apps.messaging.manager_actions import (
            ACTION_MANAGER_AVAILABLE_SLOTS,
            ACTION_MANAGER_LEAVE_APPROVE,
            ACTION_MANAGER_LEAVE_REJECT,
            ACTION_MANAGER_MEMBERSHIP_ACCEPT,
            ACTION_MANAGER_MEMBERSHIP_PROFILE,
            ACTION_MANAGER_MEMBERSHIP_REJECT,
            ACTION_MANAGER_PENDING_REQUESTS,
            ACTION_MANAGER_SCHEDULE_APPROVE,
            ACTION_MANAGER_SCHEDULE_REJECT,
            ACTION_MANAGER_SHIFTS_OVERVIEW,
            ACTION_MANAGER_TODAY_CALENDAR,
            ACTION_MANAGER_TODAY_SUMMARY,
        )
        from apps.salons.models import SalonMembership, SalonMembershipStatus
        from apps.stylists.models import StaffLeaveRequest, StaffScheduleRequest
    except Exception:
        return []

    common_salon_id = getattr(related_object, "salon_id", None)
    common = {
        "audience_role": NotificationAudienceRole.MANAGER,
        "salon_id": common_salon_id,
        "metadata": {
            "source": "manager_staff_notification",
            "event_type": event_type,
        },
    }

    if isinstance(related_object, SalonMembership):
        if (
            related_object.status != SalonMembershipStatus.PENDING_ACCEPTANCE
            or not related_object.stylist_id
        ):
            return []
        metadata = {**common["metadata"], "membership_id": related_object.pk}
        return [
            {
                "type": "action",
                "key": ACTION_MANAGER_MEMBERSHIP_ACCEPT,
                "label": "تایید",
                **common,
                "metadata": metadata,
            },
            {
                "type": "action",
                "key": ACTION_MANAGER_MEMBERSHIP_REJECT,
                "label": "رد",
                **common,
                "metadata": metadata,
            },
            {
                "type": "view",
                "key": ACTION_MANAGER_MEMBERSHIP_PROFILE,
                "label": "مشاهده پروفایل",
                **common,
                "metadata": metadata,
            },
            {
                "type": "view",
                "key": ACTION_MANAGER_PENDING_REQUESTS,
                "label": "درخواست‌های دیگر",
                **common,
                "metadata": metadata,
            },
        ]

    if isinstance(related_object, StaffLeaveRequest):
        if related_object.status != StaffLeaveRequest.Status.PENDING:
            return []
        metadata = {**common["metadata"], "leave_request_id": related_object.pk}
        return [
            {
                "type": "action",
                "key": ACTION_MANAGER_LEAVE_APPROVE,
                "label": "تایید مرخصی",
                **common,
                "metadata": metadata,
            },
            {
                "type": "action",
                "key": ACTION_MANAGER_LEAVE_REJECT,
                "label": "رد مرخصی",
                **common,
                "metadata": metadata,
            },
            {
                "type": "view",
                "key": ACTION_MANAGER_SHIFTS_OVERVIEW,
                "label": "بررسی شیفت‌ها",
                **common,
                "metadata": metadata,
            },
        ]

    if isinstance(related_object, StaffScheduleRequest):
        if related_object.status != StaffScheduleRequest.Status.PENDING:
            return []
        metadata = {**common["metadata"], "schedule_request_id": related_object.pk}
        return [
            {
                "type": "action",
                "key": ACTION_MANAGER_SCHEDULE_APPROVE,
                "label": "تایید شیفت",
                **common,
                "metadata": metadata,
            },
            {
                "type": "action",
                "key": ACTION_MANAGER_SCHEDULE_REJECT,
                "label": "رد شیفت",
                **common,
                "metadata": metadata,
            },
            {
                "type": "view",
                "key": ACTION_MANAGER_AVAILABLE_SLOTS,
                "label": "وقت خالی",
                **common,
                "metadata": metadata,
            },
        ]

    return []


def _manager_default_messaging_actions(
    *, role: str, salon_id: int | None, event_type: str
) -> list[dict[str, Any]]:
    if str(role or "") != NotificationAudienceRole.MANAGER or not salon_id:
        return []
    try:
        from apps.messaging.manager_actions import (
            ACTION_MANAGER_SHIFTS_OVERVIEW,
            ACTION_MANAGER_TODAY_CALENDAR,
            ACTION_MANAGER_TODAY_SUMMARY,
        )
    except Exception:
        return []
    common = {
        "type": "view",
        "audience_role": NotificationAudienceRole.MANAGER,
        "salon_id": salon_id,
        "metadata": {
            "source": "manager_default_notification",
            "event_type": event_type,
        },
    }
    return [
        {"key": ACTION_MANAGER_TODAY_CALENDAR, "label": "تقویم امروز", **common},
        {"key": ACTION_MANAGER_TODAY_SUMMARY, "label": "خلاصه امروز", **common},
        {"key": ACTION_MANAGER_SHIFTS_OVERVIEW, "label": "بررسی شیفت‌ها", **common},
    ]


def sync_legacy_customer_notification(customer_notification):
    user = getattr(customer_notification, "user", None)
    if not user:
        return None
    return create_notification(
        event_type=f"legacy_customer_{customer_notification.category}",
        category=customer_notification.category,
        priority=(
            customer_notification.priority
            if customer_notification.priority in NotificationPriority.values
            else NotificationPriority.NORMAL
        ),
        title=customer_notification.title,
        body=customer_notification.body,
        action_url=customer_notification.action_url,
        icon=customer_notification.icon,
        recipients=[
            {
                "user": user,
                "audience_role": NotificationAudienceRole.CUSTOMER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        related_object=customer_notification,
        metadata={
            "legacy_model": "CustomerNotification",
            "legacy_id": customer_notification.pk,
            **(customer_notification.metadata or {}),
        },
        dedupe_key=f"legacy_customer_notification:{customer_notification.pk}",
    )


def sync_legacy_appointment_notification(appointment_notification):
    user = getattr(appointment_notification, "target_user", None)
    if user is None and getattr(appointment_notification, "customer_id", None):
        user = getattr(
            getattr(appointment_notification, "customer", None), "user", None
        )
    if user is None and getattr(appointment_notification, "stylist_id", None):
        user = getattr(getattr(appointment_notification, "stylist", None), "user", None)
    if user is None:
        return None

    role = appointment_notification.audience_role or NotificationAudienceRole.CUSTOMER
    channel = appointment_notification.channel or NotificationChannel.DASHBOARD
    category = NotificationCategory.BOOKING
    if str(appointment_notification.event_type or "").startswith("payment"):
        category = NotificationCategory.PAYMENT
    elif "financial" in str(appointment_notification.event_type or ""):
        category = NotificationCategory.FINANCE

    related_object = (
        appointment_notification.order_detail or appointment_notification.order
    )
    metadata = {
        "legacy_model": "AppointmentNotification",
        "legacy_id": appointment_notification.pk,
        **(appointment_notification.meta or {}),
    }
    # Legacy rows can be created once per transport (dashboard/email/sms).
    # Only dashboard/system legacy rows may add Bale actions; otherwise the same
    # subject can fan out into multiple Bale deliveries via email/sms mirrors.
    legacy_channel = str(channel or "")
    dashboard_channel = getattr(
        NotificationChannel.DASHBOARD, "value", NotificationChannel.DASHBOARD
    )
    if legacy_channel not in {str(dashboard_channel), "dashboard", "system", ""}:
        metadata.setdefault("messaging_disable_bale", True)

    messaging_actions = []
    if not metadata.get("messaging_disable_bale"):
        messaging_actions = _stylist_order_detail_messaging_actions(
            role=role,
            related_object=related_object,
            event_type=appointment_notification.event_type,
        )
    channels = [channel]
    if messaging_actions:
        metadata["messaging_actions"] = messaging_actions
        if NotificationChannel.BALE not in channels:
            channels.append(NotificationChannel.BALE)

    return create_notification(
        event_type=appointment_notification.event_type,
        category=category,
        priority=(
            NotificationPriority.HIGH
            if appointment_notification.event_type
            in {"no_show_confirmed", "appointment_disputed"}
            else NotificationPriority.NORMAL
        ),
        title=appointment_notification.title,
        body=appointment_notification.body,
        action_url=(appointment_notification.meta or {}).get("action_url", ""),
        recipients=[{"user": user, "audience_role": role, "channels": channels}],
        salon=getattr(appointment_notification, "salon", None),
        related_object=related_object,
        metadata=metadata,
        dedupe_key=f"legacy_appointment_notification:{appointment_notification.pk}",
    )
