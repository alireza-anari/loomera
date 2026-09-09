from __future__ import annotations

from dataclasses import dataclass

from .context import LumiContext


class ToolPolicyError(PermissionError):
    code = "tool_not_allowed"


class ToolAuthenticationRequired(ToolPolicyError):
    code = "authentication_required"


class ToolRoleDenied(ToolPolicyError):
    code = "role_not_allowed"


class ToolConfirmationRequired(ToolPolicyError):
    code = "confirmation_required"


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    allowed_roles: frozenset[str]
    requires_auth: bool = False
    requires_confirmation: bool = False
    mutates_state: bool = False
    writes_database: bool = False
    idempotent: bool = True
    beta_enabled: bool = True

    @classmethod
    def read_public(cls) -> "ToolPolicy":
        return cls(
            allowed_roles=frozenset({"guest", "user", "customer", "stylist", "manager", "admin"}),
            requires_auth=False,
            requires_confirmation=False,
            mutates_state=False,
            writes_database=False,
            idempotent=True,
        )

    def check(self, context: LumiContext, *, confirmed: bool = False) -> None:
        if not self.beta_enabled:
            raise ToolPolicyError("این ابزار در نسخه بتا فعال نیست.")
        if self.requires_auth and not context.authenticated:
            raise ToolAuthenticationRequired("برای استفاده از این ابزار باید وارد حساب شوی.")
        if self.allowed_roles and not (set(context.roles) & set(self.allowed_roles)):
            raise ToolRoleDenied("نقش فعلی اجازه استفاده از این ابزار را ندارد.")
        if self.requires_confirmation and not confirmed:
            raise ToolConfirmationRequired("این عملیات قبل از اجرا به تأیید صریح کاربر نیاز دارد.")
