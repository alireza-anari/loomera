from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ROLE_PRIORITY = ("admin", "manager", "stylist", "customer", "user", "guest")


def _roles_for_user(user: Any) -> frozenset[str]:
    if not getattr(user, "is_authenticated", False):
        return frozenset({"guest"})

    roles: set[str] = set()
    role_attrs = (
        ("salon_manager_profile", "manager"),
        ("stylist", "stylist"),
        ("customer_profile", "customer"),
    )
    for attr, role in role_attrs:
        try:
            if getattr(user, attr, None) is not None:
                roles.add(role)
        except Exception:
            # Related-object descriptors may raise DoesNotExist. That must not
            # turn context construction into an authorization bypass.
            continue

    if getattr(user, "is_admin", False) or getattr(user, "is_superuser", False):
        roles.add("admin")
    return frozenset(roles or {"user"})


def _primary_role(roles: frozenset[str]) -> str:
    for role in ROLE_PRIORITY:
        if role in roles:
            return role
    return "user"


@dataclass(frozen=True, slots=True)
class LumiContext:
    """Minimal authority/context envelope passed to tools.

    `actor` and `request` are runtime-only references and are deliberately omitted
    from `public_dict()`, so they are never sent to an LLM by accident.
    """

    user_id: int | None
    authenticated: bool
    roles: frozenset[str]
    primary_role: str
    channel: str = "web"
    locale: str = "fa-IR"
    session_id: str = ""
    page_path: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    actor: Any = field(default=None, repr=False, compare=False)
    request: Any = field(default=None, repr=False, compare=False)

    def has_role(self, role: str) -> bool:
        return str(role or "").strip().lower() in self.roles

    def public_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "authenticated": self.authenticated,
            "roles": sorted(self.roles),
            "primary_role": self.primary_role,
            "channel": self.channel,
            "locale": self.locale,
            "session_id": self.session_id,
            "page_path": self.page_path,
            "metadata": dict(self.metadata),
        }

    def model_dict(self) -> dict[str, Any]:
        """Return the minimum non-identifying context an intent model may see.

        User/session IDs, request objects, page URLs and arbitrary metadata are
        intentionally excluded. Scope IDs stay server-side and are injected by
        the orchestrator after model classification.
        """
        metadata = self.metadata if isinstance(self.metadata, Mapping) else {}
        return {
            "authenticated": self.authenticated,
            "roles": sorted(self.roles),
            "primary_role": self.primary_role,
            "channel": self.channel,
            "locale": self.locale,
            "scope_type": str(metadata.get("scope_type") or "")[:32],
            "has_scope": bool(metadata.get("scope_type")),
            "reference_date": str(metadata.get("reference_date") or "")[:10],
        }


def build_lumi_context(
    *,
    user: Any = None,
    request: Any = None,
    channel: str = "web",
    locale: str = "fa-IR",
    session_id: str = "",
    page_path: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> LumiContext:
    if user is None and request is not None:
        user = getattr(request, "user", None)

    authenticated = bool(getattr(user, "is_authenticated", False))
    roles = _roles_for_user(user)
    user_id = getattr(user, "pk", None) if authenticated else None
    try:
        user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        user_id = None

    return LumiContext(
        user_id=user_id,
        authenticated=authenticated,
        roles=roles,
        primary_role=_primary_role(roles),
        channel=str(channel or "web")[:32],
        locale=str(locale or "fa-IR")[:32],
        session_id=str(session_id or "")[:160],
        page_path=str(page_path or "")[:500],
        metadata=dict(metadata or {}),
        actor=user,
        request=request,
    )
