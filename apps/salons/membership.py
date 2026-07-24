"""Membership helpers for connecting stylists to salons safely.

This module adds the new SalonMembership layer without removing the legacy
Salon.stylists and JobDetails relations. Keeping the legacy relations synced
lets the current dashboards and Tailwind templates keep working while the new
permission/context model is introduced gradually.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Iterable, Optional

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import CustomUser, Stylist
from apps.main.models import AdminAuditLog
from apps.services.models import Services
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
    StaffDashboardPermission,
    MembershipEvent,
    SalonVerification,
)
from apps.stylists.models import JobDetails


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_mobile(value: str | None) -> str:
    """Normalize Persian/Arabic digits and strip non-digits from mobile input."""
    value = (value or "").translate(PERSIAN_DIGITS)
    return "".join(ch for ch in value if ch.isdigit())


def default_invite_expiry(days: int = 14):
    return timezone.now() + timedelta(days=days)


def ensure_membership_permissions(membership: SalonMembership) -> StaffDashboardPermission:
    permissions, _ = StaffDashboardPermission.objects.get_or_create(membership=membership)
    return permissions


def log_membership_event(
    membership: SalonMembership,
    *,
    event_type: str,
    actor=None,
    old_status: str = "",
    new_status: str = "",
    note: str = "",
    metadata: Optional[dict] = None,
) -> MembershipEvent:
    event = MembershipEvent.objects.create(
        membership=membership,
        actor=actor,
        event_type=event_type,
        old_status=old_status or "",
        new_status=new_status or "",
        note=note or "",
        metadata=metadata or {},
    )
    return event


def audit_membership_change(
    *,
    actor,
    membership: SalonMembership,
    action: str,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    reason: str = "",
    request=None,
):
    """Create an AdminAuditLog entry for membership-sensitive changes."""
    try:
        content_type = ContentType.objects.get_for_model(SalonMembership)
        AdminAuditLog.objects.create(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            target_content_type=content_type,
            target_object_id=membership.pk,
            old_value=old_value or {},
            new_value=new_value or {},
            reason=reason or "",
            ip_address=getattr(request, "META", {}).get("REMOTE_ADDR") if request else None,
            user_agent=getattr(request, "META", {}).get("HTTP_USER_AGENT", "") if request else "",
        )
    except Exception:
        # Audit should not break operational flow.
        return None


def ensure_salon_verification(salon: Salon) -> SalonVerification:
    verification, _ = SalonVerification.objects.get_or_create(
        salon=salon,
        defaults={"status": getattr(salon, "verification_status", "unverified") or "unverified"},
    )
    return verification


@transaction.atomic
def sync_legacy_membership(
    *,
    salon: Salon,
    stylist: Stylist,
    actor=None,
    status: str = SalonMembershipStatus.ACTIVE,
    role_title: str = "",
    invited_phone: str = "",
    invited_email: str = "",
    request=None,
) -> SalonMembership:
    """Ensure a SalonMembership exists for an existing legacy salon/stylist link."""
    invited_phone = normalize_mobile(invited_phone or getattr(stylist.user, "mobile_number", ""))
    invited_email = (invited_email or getattr(stylist.user, "email", "") or "").strip().lower()
    membership, created = SalonMembership.objects.get_or_create(
        salon=salon,
        stylist=stylist,
        defaults={
            "invited_phone": invited_phone,
            "invited_email": invited_email,
            "role_title": role_title or getattr(stylist, "expert", "") or "",
            "status": status,
            "invited_by": actor if getattr(actor, "is_authenticated", False) else None,
            "accepted_at": timezone.now() if status == SalonMembershipStatus.ACTIVE else None,
            "expires_at": default_invite_expiry(),
        },
    )
    if not created:
        changed = []
        if membership.status != status and status:
            old_status = membership.status
            membership.status = status
            if status == SalonMembershipStatus.ACTIVE and not membership.accepted_at:
                membership.accepted_at = timezone.now()
            changed.append((old_status, status))
        if invited_phone and not membership.invited_phone:
            membership.invited_phone = invited_phone
        if invited_email and not membership.invited_email:
            membership.invited_email = invited_email
        if role_title and not membership.role_title:
            membership.role_title = role_title
        membership.save()
        if changed:
            old_status, new_status = changed[0]
            log_membership_event(
                membership,
                event_type="status_changed",
                actor=actor,
                old_status=old_status,
                new_status=new_status,
            )
    else:
        log_membership_event(
            membership,
            event_type="created_from_legacy_link",
            actor=actor,
            new_status=status,
        )

    ensure_membership_permissions(membership)
    ensure_salon_verification(salon)

    if not salon.stylists.filter(pk=stylist.pk).exists():
        salon.stylists.add(stylist)

    return membership


@transaction.atomic
def invite_or_attach_stylist(
    *,
    salon: Salon,
    user_data: dict,
    stylist_data: dict | None = None,
    job_data: dict | None = None,
    selected_services: Iterable[Services] | None = None,
    actor=None,
    request=None,
) -> tuple[Stylist, SalonMembership, bool]:
    """Create or attach a stylist to a salon through SalonMembership.

    Returns (stylist, membership, created_user).
    Existing users are not rejected; they are linked to the salon through a
    membership instead of creating duplicate accounts.
    """
    stylist_data = stylist_data or {}
    job_data = job_data or {}
    selected_services = list(selected_services or [])

    mobile = normalize_mobile(user_data.get("mobile_number"))
    email = (user_data.get("email") or "").strip().lower()
    user = CustomUser.objects.filter(mobile_number=mobile).first() if mobile else None
    created_user = False

    if user is None:
        user = CustomUser(
            mobile_number=mobile,
            email=email,
            name=(user_data.get("name") or "").strip(),
            family=(user_data.get("family") or "").strip(),
            is_active=True,
        )
        user.set_unusable_password()
        if not user.active_code:
            user.active_code = "team-member"
        user.save()
        created_user = True
    else:
        changed_fields = []
        if not user.name and user_data.get("name"):
            user.name = (user_data.get("name") or "").strip()
            changed_fields.append("name")
        if not user.family and user_data.get("family"):
            user.family = (user_data.get("family") or "").strip()
            changed_fields.append("family")
        if email and not user.email:
            user.email = email
            changed_fields.append("email")
        if not user.is_active:
            user.is_active = True
            changed_fields.append("is_active")
        if changed_fields:
            user.save(update_fields=changed_fields)

    stylist, stylist_created = Stylist.objects.get_or_create(
        user=user,
        defaults={
            "description": stylist_data.get("description") or "",
            "address": stylist_data.get("address") or "",
            "linkedin_link": stylist_data.get("linkedin_link") or "",
            "insta_link": stylist_data.get("insta_link") or "",
            "telegram_link": stylist_data.get("telegram_link") or "",
            "expert": stylist_data.get("expert") or "",
            "calendar_color": stylist_data.get("calendar_color") or "#6d5ef7",
            "is_active": True,
        },
    )
    if stylist_created:
        profile_image = stylist_data.get("profile_image")
        if profile_image:
            stylist.profile_image = profile_image
            stylist.save(update_fields=["profile_image"])
    elif not stylist.is_active:
        stylist.is_active = True
        stylist.save(update_fields=["is_active"])

    membership = sync_legacy_membership(
        salon=salon,
        stylist=stylist,
        actor=actor,
        status=SalonMembershipStatus.ACTIVE,
        role_title=stylist_data.get("expert") or getattr(stylist, "expert", "") or "",
        invited_phone=mobile,
        invited_email=email,
        request=request,
    )

    JobDetails.objects.get_or_create(
        salon=salon,
        stylist=stylist,
        defaults={
            "start_date": job_data.get("start_date") or timezone.localdate(),
            "end_date": job_data.get("end_date"),
            "employment_type": job_data.get("employment_type") or "",
        },
    )

    if selected_services:
        stylist.services_of_stylist.add(*selected_services)

    audit_membership_change(
        actor=actor,
        membership=membership,
        action="salon_membership_attached",
        new_value={"salon_id": salon.pk, "stylist_id": stylist.pk, "created_user": created_user},
        request=request,
    )
    return stylist, membership, created_user


@transaction.atomic
def change_membership_status(
    *,
    membership: SalonMembership,
    new_status: str,
    actor=None,
    reason: str = "",
    request=None,
) -> SalonMembership:
    old_status = membership.status
    if old_status == new_status:
        return membership

    membership.status = new_status
    if new_status == SalonMembershipStatus.ACTIVE and not membership.accepted_at:
        membership.accepted_at = timezone.now()
    if new_status in {SalonMembershipStatus.ENDED, SalonMembershipStatus.CANCELLED_BY_SALON}:
        membership.ended_at = timezone.now()
    membership.save(update_fields=["status", "accepted_at", "ended_at", "updated_at"])

    if membership.stylist_id and new_status == SalonMembershipStatus.ACTIVE:
        # Keep the legacy M2M relation synced so existing dashboards keep seeing
        # the team member. Non-active membership status is now represented on the
        # membership itself, not by disabling the global Stylist account.
        membership.salon.stylists.add(membership.stylist)

    log_membership_event(
        membership,
        event_type="status_changed",
        actor=actor,
        old_status=old_status,
        new_status=new_status,
        note=reason,
    )
    audit_membership_change(
        actor=actor,
        membership=membership,
        action="salon_membership_status_changed",
        old_value={"status": old_status},
        new_value={"status": new_status},
        reason=reason,
        request=request,
    )
    return membership


def get_active_salon_for_stylist(user, request=None) -> Salon | None:
    """Resolve active salon context for a stylist user."""
    stylist = getattr(user, "stylist", None)
    if not stylist:
        return None

    qs = SalonMembership.objects.filter(
        stylist=stylist,
        status=SalonMembershipStatus.ACTIVE,
    ).select_related("salon").order_by("salon__salon_name", "id")

    selected_id = None
    if request is not None:
        selected_id = request.session.get("active_stylist_salon_id")
    if selected_id:
        selected = qs.filter(salon_id=selected_id).first()
        if selected:
            return selected.salon

    membership = qs.first()
    if membership and request is not None:
        request.session["active_stylist_salon_id"] = membership.salon_id
    return membership.salon if membership else None
