from __future__ import annotations

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import (
    AdminAuditLog,
    DisputeCase,
    DisputeEvent,
    SupportAttachment,
    SupportEvent,
    SupportTicket,
    SupportTicketMessage,
)


def _request_meta(request):
    if request is None:
        return {}
    return {
        "ip_address": request.META.get("REMOTE_ADDR"),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }


def infer_requester_role(user) -> str:
    if user is None or not getattr(user, "is_authenticated", False):
        return "guest"
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return "admin"
    if hasattr(user, "salon_manager_profile"):
        return "salon_manager"
    if hasattr(user, "stylist"):
        return "stylist"
    return "customer"


def infer_category_from_issue(issue_type: str, support_reason: str = "") -> str:
    reason = (support_reason or "").lower()
    if issue_type == "appointment":
        return "booking"
    if issue_type == "account_join":
        return "salon_verification"
    if issue_type == "account_existing":
        return "account"
    if reason in {"payments", "wallet"}:
        return "payment"
    if reason in {"reviews"}:
        return "review_report"
    if reason in {"notifications"}:
        return "technical_bug"
    return "other"


def default_sla_due_at(priority: str):
    now = timezone.now()
    hours = {
        "normal": 24,
        "high": 6,
        "urgent": 2,
        "critical": 1,
    }.get(priority or "normal", 24)
    return now + timedelta(hours=hours)


@transaction.atomic
def initialize_support_ticket(ticket: SupportTicket, *, actor=None, attachment_file=None, request=None) -> SupportTicket:
    changed = []
    if not ticket.category or ticket.category == "other":
        ticket.category = infer_category_from_issue(ticket.issue_type, ticket.support_reason)
        changed.append("category")
    if not ticket.requester_role:
        ticket.requester_role = infer_requester_role(actor)
        changed.append("requester_role")
    if not ticket.subject:
        ticket.subject = ticket.support_reason or ticket.get_issue_type_display()
        changed.append("subject")
    if not ticket.sla_due_at:
        ticket.sla_due_at = default_sla_due_at(ticket.priority)
        changed.append("sla_due_at")
    if changed:
        ticket.save(update_fields=changed + ["updated_at"])

    if ticket.description:
        message, created = SupportTicketMessage.objects.get_or_create(
            ticket=ticket,
            sender=actor if getattr(actor, "is_authenticated", False) else None,
            sender_role=infer_requester_role(actor),
            message_type=SupportTicketMessage.MESSAGE_TYPE_PUBLIC,
            body=ticket.description,
        )
        if attachment_file:
            SupportAttachment.objects.get_or_create(
                ticket=ticket,
                message=message,
                uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
                defaults={"file": attachment_file, "file_type": getattr(attachment_file, "content_type", "") or ""},
            )

    SupportEvent.objects.get_or_create(
        ticket=ticket,
        event_type="created",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        defaults={"new_value": {"status": ticket.status, "category": ticket.category}, "metadata": _request_meta(request)},
    )
    return ticket


@transaction.atomic
def add_support_message(
    *,
    ticket: SupportTicket,
    sender=None,
    body: str,
    sender_role: str | None = None,
    message_type: str = SupportTicketMessage.MESSAGE_TYPE_PUBLIC,
    attachment_file=None,
    request=None,
) -> SupportTicketMessage:
    sender_role = sender_role or infer_requester_role(sender)
    message = SupportTicketMessage.objects.create(
        ticket=ticket,
        sender=sender if getattr(sender, "is_authenticated", False) else None,
        sender_role=sender_role,
        message_type=message_type,
        body=body,
    )
    if attachment_file:
        SupportAttachment.objects.create(
            ticket=ticket,
            message=message,
            uploaded_by=sender if getattr(sender, "is_authenticated", False) else None,
            file=attachment_file,
            file_type=getattr(attachment_file, "content_type", "") or "",
        )

    update_fields = ["last_response_at", "last_response_by", "updated_at"]
    ticket.last_response_at = timezone.now()
    ticket.last_response_by = sender if getattr(sender, "is_authenticated", False) else None
    if message_type == SupportTicketMessage.MESSAGE_TYPE_PUBLIC:
        if sender_role in {"admin", "support_admin", "finance_admin", "content_moderator"} and not ticket.first_response_at:
            ticket.first_response_at = timezone.now()
            update_fields.append("first_response_at")
        if sender_role in {"admin", "support_admin", "finance_admin", "content_moderator"}:
            ticket.admin_reply = body
            update_fields.append("admin_reply")
            if ticket.status in {"new", "open", "waiting_for_support", "in_progress"}:
                ticket.status = "waiting_for_user"
                update_fields.append("status")
        elif ticket.status in {"new", "waiting_for_user", "resolved", "closed"}:
            ticket.status = "waiting_for_support"
            update_fields.append("status")
    ticket.save(update_fields=list(dict.fromkeys(update_fields)))

    SupportEvent.objects.create(
        ticket=ticket,
        event_type="message_added",
        actor=sender if getattr(sender, "is_authenticated", False) else None,
        new_value={"message_id": message.pk, "message_type": message_type, "sender_role": sender_role},
        metadata=_request_meta(request),
    )
    return message


@transaction.atomic
def update_support_ticket_status(*, ticket: SupportTicket, status: str, actor=None, note: str = "", request=None):
    old = ticket.status
    ticket.status = status
    now = timezone.now()
    update_fields = ["status", "updated_at"]
    if status == "resolved" and not ticket.resolved_at:
        ticket.resolved_at = now
        update_fields.append("resolved_at")
    if status == "closed" and not ticket.closed_at:
        ticket.closed_at = now
        update_fields.append("closed_at")
    ticket.save(update_fields=update_fields)
    SupportEvent.objects.create(
        ticket=ticket,
        event_type="status_changed",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        old_value={"status": old},
        new_value={"status": status},
        note=note,
        metadata=_request_meta(request),
    )
    return ticket


@transaction.atomic
def open_dispute_case(
    *,
    dispute_type: str,
    opened_by=None,
    support_ticket: SupportTicket | None = None,
    order=None,
    order_detail=None,
    salon=None,
    stylist=None,
    customer=None,
    subject: str = "",
    description: str = "",
    priority: str = "normal",
    related_object=None,
    request=None,
) -> DisputeCase:
    content_type = None
    object_id = None
    if related_object is not None:
        content_type = ContentType.objects.get_for_model(related_object)
        object_id = related_object.pk

    case = DisputeCase.objects.create(
        opened_by=opened_by if getattr(opened_by, "is_authenticated", False) else None,
        dispute_type=dispute_type,
        priority=priority,
        support_ticket=support_ticket,
        order=order,
        order_detail=order_detail,
        salon=salon,
        stylist=stylist,
        customer=customer,
        subject=subject,
        description=description,
        related_content_type=content_type,
        related_object_id=object_id,
    )
    DisputeEvent.objects.create(
        dispute=case,
        event_type="created",
        actor=opened_by if getattr(opened_by, "is_authenticated", False) else None,
        new_status=case.status,
        note=description,
        metadata=_request_meta(request),
    )
    if support_ticket:
        SupportEvent.objects.create(
            ticket=support_ticket,
            event_type="dispute_linked",
            actor=opened_by if getattr(opened_by, "is_authenticated", False) else None,
            new_value={"dispute_id": case.pk, "dispute_type": dispute_type},
            metadata=_request_meta(request),
        )
    return case


def log_admin_support_action(*, request, action: str, target, old_value=None, new_value=None, reason: str = ""):
    try:
        AdminAuditLog.objects.create(
            actor=request.user if request and request.user.is_authenticated else None,
            action=action,
            target_content_type=ContentType.objects.get_for_model(target),
            target_object_id=target.pk,
            old_value=old_value or {},
            new_value=new_value or {},
            reason=reason,
            ip_address=request.META.get("REMOTE_ADDR") if request else None,
            user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
        )
    except Exception:
        pass
