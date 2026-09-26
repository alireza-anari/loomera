"""Current role and salon authorization for a single user identity."""

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus


class WorkspaceSelectionRequired(Exception):
    """The manager owns multiple salons and must choose one explicitly."""


def _active_user(user):
    return bool(
        user is not None
        and user.is_authenticated
        and user.is_active
        and user.pk is not None
    )


def _positive_salon_id(salon_id):
    if isinstance(salon_id, bool):
        raise PermissionDenied("شناسه سالن نامعتبر است.")
    if isinstance(salon_id, int):
        value = salon_id
    elif isinstance(salon_id, str) and salon_id.isascii() and salon_id.isdecimal():
        try:
            value = int(salon_id)
        except ValueError as exc:
            raise PermissionDenied("شناسه سالن نامعتبر است.") from exc
        if str(value) != salon_id:
            raise PermissionDenied("شناسه سالن نامعتبر است.")
    else:
        raise PermissionDenied("شناسه سالن نامعتبر است.")
    if value <= 0:
        raise PermissionDenied("شناسه سالن نامعتبر است.")
    return value


def capabilities_for(user) -> frozenset[str]:
    """Return current profile capabilities without creating any profile."""
    if not _active_user(user):
        return frozenset()
    capabilities = {"customer"}
    if Stylist.objects.filter(user_id=user.pk).exists():
        capabilities.add("stylist")
    if SalonManager.objects.filter(user_id=user.pk).exists():
        capabilities.add("manager")
    return frozenset(capabilities)


def ensure_customer(user) -> Customer:
    """Create a customer profile on first authorized use, with no marketing opt-in."""
    if not _active_user(user):
        raise PermissionDenied("دسترسی به بخش مشتری مجاز نیست.")
    with transaction.atomic():
        customer, _ = Customer.objects.get_or_create(
            user=user,
            defaults={
                "notify_marketing_email": False,
                "notify_marketing_sms": False,
                "notify_marketing_whatsapp": False,
            },
        )
    return customer


def managed_salons(user):
    """Return all owned salons, including draft onboarding salons."""
    if not _active_user(user):
        return Salon.objects.none()
    return Salon.objects.filter(salon_manager__user_id=user.pk)


def resolve_manager_salon(user, salon_id=None) -> Salon | None:
    """Resolve an explicitly owned salon; never infer one from an ambiguous set."""
    if not _active_user(user):
        raise PermissionDenied("دسترسی به این سالن مجاز نیست.")
    # A customer identity must not be treated as an onboarding manager.
    # Query the database rather than trusting possibly stale OneToOne caches.
    if not SalonManager.objects.filter(user_id=user.pk).exists():
        raise PermissionDenied("دسترسی به این سالن مجاز نیست.")
    salons = managed_salons(user)
    if salon_id is not None:
        salon = salons.filter(pk=_positive_salon_id(salon_id)).first()
        if salon is None:
            raise PermissionDenied("دسترسی به این سالن مجاز نیست.")
        return salon
    selected = list(salons.order_by("pk")[:2])
    if not selected:
        return None
    if len(selected) > 1:
        raise WorkspaceSelectionRequired("Select a salon")
    return selected[0]


def resolve_stylist_membership(user, salon_id) -> SalonMembership:
    """Resolve only the user's ACTIVE membership in the requested salon."""
    if not _active_user(user):
        raise PermissionDenied("دسترسی متخصص مجاز نیست.")
    membership = SalonMembership.objects.filter(
        stylist__user_id=user.pk,
        salon_id=_positive_salon_id(salon_id),
        status=SalonMembershipStatus.ACTIVE,
    ).first()
    if membership is None:
        raise PermissionDenied("دسترسی متخصص مجاز نیست.")
    return membership
