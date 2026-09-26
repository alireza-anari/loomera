"""Workspace choices derived from current capabilities and ownership."""

from dataclasses import dataclass
from typing import Literal

from apps.accounts.services.access import capabilities_for, managed_salons


@dataclass(frozen=True)
class Workspace:
    kind: Literal["customer", "stylist", "manager"]
    salon_id: int | None
    label: str


def available_workspaces(user) -> tuple[Workspace, ...]:
    capabilities = capabilities_for(user)
    if not capabilities:
        return ()
    workspaces = [Workspace("customer", None, "Customer")]
    if "stylist" in capabilities:
        workspaces.append(Workspace("stylist", None, "Stylist"))
    if "manager" in capabilities:
        salons = list(managed_salons(user).order_by("pk").only("pk", "salon_name"))
        if salons:
            workspaces.extend(
                Workspace("manager", salon.pk, salon.salon_name) for salon in salons
            )
        else:
            workspaces.append(Workspace("manager", None, "Salon setup"))
    return tuple(workspaces)


def _preference_for(user):
    from apps.accounts.models import UserWorkspacePreference

    return UserWorkspacePreference.objects.filter(user_id=user.pk).first()


def _workspace_destination(user, workspace):
    """Map current authorization to a safe destination.

    Multi-salon managers use a separately scoped, read-only overview; legacy
    manager endpoints remain blocked until audited per salon.
    """
    if workspace.kind == "customer":
        return "accounts:customer_panel"
    if workspace.kind == "stylist":
        return "dashboards:stylist_dashboard"
    if workspace.kind == "manager":
        if managed_salons(user).count() > 1:
            if workspace.salon_id is None:
                return None
            from django.urls import reverse
            return reverse(
                "dashboards:multirole_manager_salon_overview",
                kwargs={"salon_id": workspace.salon_id},
            )
        return "dashboards:salon_manager_dashboard"
    return None


def professional_workspaces(workspaces):
    return tuple(space for space in workspaces if space.kind != "customer")


def login_workspace_destination(user):
    """Return a route name, or None when the user must choose a workspace.

    A stored preference never creates permission: available_workspaces queries
    current profiles and salon ownership on every call.
    """
    spaces = available_workspaces(user)
    if not spaces:
        return None
    professional = professional_workspaces(spaces)
    preference = _preference_for(user)

    # A former single-role visit is not an explicit choice between new roles.
    if len(professional) > 1 and not (
        preference and preference.has_chosen_multirole_workspace
    ):
        return None

    if preference:
        selected = next(
            (
                space for space in spaces
                if space.kind == preference.kind
                and space.salon_id == preference.salon_id
                and not (
                    space.kind == "manager"
                    and preference.was_salon_workspace
                    and preference.salon_id is None
                )
            ),
            None,
        )
        if selected:
            destination = _workspace_destination(user, selected)
            if destination:
                return destination

    if len(professional) == 0:
        return "accounts:customer_panel"
    if len(professional) == 1:
        return _workspace_destination(user, professional[0])
    return None


def select_workspace(user, *, kind, salon_id=""):
    """Validate and persist a choice without granting any authorization."""
    from django.core.exceptions import PermissionDenied
    from django.db import transaction
    from apps.accounts.models import UserWorkspacePreference

    if kind not in {"customer", "stylist", "manager"}:
        raise PermissionDenied("محیط فعالیت نامعتبر است.")
    if not isinstance(salon_id, str):
        raise PermissionDenied("شناسه سالن نامعتبر است.")
    if kind != "manager" and salon_id:
        raise PermissionDenied("شناسه سالن نامعتبر است.")
    if kind == "manager" and salon_id and (
        len(salon_id) > 20 or not salon_id.isascii() or not salon_id.isdecimal()
        or str(int(salon_id)) != salon_id or int(salon_id) <= 0
    ):
        raise PermissionDenied("شناسه سالن نامعتبر است.")

    parsed_id = int(salon_id) if kind == "manager" and salon_id else None
    spaces = available_workspaces(user)
    workspace = next(
        (space for space in spaces
         if space.kind == kind and space.salon_id == parsed_id),
        None,
    )
    if workspace is None:
        raise PermissionDenied("دسترسی به این محیط فعالیت مجاز نیست.")
    destination = _workspace_destination(user, workspace)
    if not destination:
        raise PermissionDenied("انتخاب سالن هنوز در دسترس نیست.")

    with transaction.atomic():
        UserWorkspacePreference.objects.update_or_create(
            user=user,
            defaults={
                "kind": workspace.kind,
                "salon_id": workspace.salon_id,
                "has_chosen_multirole_workspace": len(professional_workspaces(spaces)) > 1,
                "was_salon_workspace": workspace.kind == "manager" and workspace.salon_id is not None,
            },
        )
    return destination
