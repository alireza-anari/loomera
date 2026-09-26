"""Derive Lumi's conversational scope from live, server-authorized workspaces.

A workspace preference and client-provided page/role/salon values are never
permission grants. A missing or revoked multi-salon choice falls back to the
customer help scope instead of silently choosing an owned salon.
"""

from apps.accounts.services.access import (
    capabilities_for,
    resolve_stylist_membership,
)
from apps.accounts.services.workspaces import available_workspaces, professional_workspaces
from apps.accounts.models import UserWorkspacePreference
from django.core.exceptions import PermissionDenied


SCOPE_KEY = "workspace_scope"


def help_workspace_scope(request) -> dict:
    """Return {role, salon_id} valid for this request; salon ID is server-verified."""
    user = request.user
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return {"role": "guest", "salon_id": None}

    spaces = available_workspaces(user)
    professional = professional_workspaces(spaces)
    preference = UserWorkspacePreference.objects.filter(user_id=user.pk).first()
    selected = None
    if preference:
        selected = next((space for space in spaces if (
            space.kind == preference.kind
            and space.salon_id == preference.salon_id
            and not (space.kind == "manager" and preference.was_salon_workspace
                     and preference.salon_id is None)
        )), None)

    # No explicit selection among several professional workspaces is not
    # authorization to pick the first salon or highest-priority role.
    if selected is None and len(professional) == 1:
        selected = professional[0]
    if selected is None:
        return {"role": "customer", "salon_id": None}
    if selected.kind == "manager":
        return {"role": "manager", "salon_id": selected.salon_id}
    if selected.kind == "stylist":
        salon_id = (getattr(request, "session", None) or {}).get("active_stylist_salon_id")
        if salon_id is not None:
            try:
                membership = resolve_stylist_membership(user, salon_id)
                salon_id = membership.salon_id
            except (PermissionDenied, ValueError, TypeError):
                salon_id = None
        return {"role": "stylist", "salon_id": salon_id}
    return {"role": "customer", "salon_id": None}


def assistant_roles_for_request(request) -> set[str]:
    """Available action categories for the *selected* live workspace.

    A profile may grant the ability to switch workspaces; it must not make a
    manager or stylist action silently run while customer workspace is open.
    """
    from apps.accounts.models import CustomUser
    from .actions.common import user_roles

    roles = user_roles(request.user)
    if not isinstance(request.user, CustomUser):
        return roles  # Preserve guest and non-DB action contexts.
    scope_role = help_workspace_scope(request)["role"]
    allowed = {"customer"} if scope_role != "guest" else {"guest"}
    if scope_role in {"manager", "stylist"}:
        allowed.add(scope_role)
    if "admin" in roles:
        allowed.add("admin")
    return allowed


def action_in_workspace(request, action, salon_id=None) -> bool:
    """Guard a retained action state / signed token against a workspace switch.

    Domain services must still re-check ownership and membership at execution.
    This additional UI-scope check never authorizes an operation on its own.
    """
    from apps.accounts.models import CustomUser

    if not isinstance(request.user, CustomUser):
        return True  # Existing guest and non-database test contexts.
    scope = help_workspace_scope(request)
    action = str(action or "")
    for role in ("manager", "stylist"):
        if action.startswith(role + "_"):
            if scope["role"] != role:
                return False
            if salon_id is not None:
                # Do not infer an absent or revoked salon from a signed token.
                return (scope["salon_id"] is not None
                        and str(salon_id) == str(scope["salon_id"]))
            return True
    return scope["role"] != "guest" if action.startswith("customer_") else True


def conversation_scope_matches(conversation, scope, *, user) -> bool:
    """Unknown historical scope may never be inferred as a professional salon."""
    metadata = conversation.metadata if isinstance(conversation.metadata, dict) else {}
    saved = metadata.get(SCOPE_KEY)
    if isinstance(saved, dict):
        return saved.get("v") == 1 and saved.get("role") == scope["role"] and (
            saved.get("salon_id") == scope["salon_id"]
        )

    # Only unequivocally public, old customer/guest conversations remain
    # readable. Legacy manager/stylist conversations carry unknown salon scope.
    if scope["salon_id"] is not None or conversation.role != scope["role"]:
        return False
    if scope["role"] == "guest":
        return conversation.user_id is None
    if scope["role"] == "customer":
        return capabilities_for(user) == frozenset({"customer"})
    return False


def conversation_history(conversation) -> list[dict]:
    """Only persisted messages from an already-authorized conversation."""
    if conversation is None:
        return []
    entries = list(conversation.messages.filter(role__in=("user", "assistant"))
                   .order_by("-created_at", "-pk")[:12])
    return [{"role": row.role, "content": row.content} for row in reversed(entries)]
