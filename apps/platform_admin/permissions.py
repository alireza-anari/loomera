from __future__ import annotations

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from apps.main.models import AdminRoleAssignment


ROLE_SUPER = AdminRoleAssignment.Role.SUPER_ADMIN
ROLE_SUPPORT = AdminRoleAssignment.Role.SUPPORT_ADMIN
ROLE_FINANCE = AdminRoleAssignment.Role.FINANCE_ADMIN
ROLE_CONTENT = AdminRoleAssignment.Role.CONTENT_MODERATOR
ROLE_VERIFY = AdminRoleAssignment.Role.VERIFICATION_ADMIN
ROLE_READ_ONLY = AdminRoleAssignment.Role.READ_ONLY_ADMIN


def user_admin_roles(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    if getattr(user, "is_superuser", False):
        return {ROLE_SUPER}
    return set(
        AdminRoleAssignment.objects.filter(user=user, is_active=True).values_list("role", flat=True)
    )


def is_platform_admin(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_admin", False) or getattr(user, "is_staff", False):
        return True
    return bool(user_admin_roles(user))


def has_platform_role(user, *roles):
    if not is_platform_admin(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    current = user_admin_roles(user)
    if ROLE_SUPER in current:
        return True
    if not roles:
        return bool(current) or getattr(user, "is_admin", False) or getattr(user, "is_staff", False)
    if getattr(user, "is_admin", False) and not current:
        # Legacy admins keep broad access until explicit role assignments are configured.
        return True
    return bool(current.intersection(set(roles)))


class PlatformAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    required_roles: tuple[str, ...] = ()

    def test_func(self):
        return has_platform_role(self.request.user, *self.required_roles)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect("accounts:login")
        raise PermissionDenied("شما به این بخش از پنل ادمین Loomera دسترسی ندارید.")


def require_platform_role(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not has_platform_role(request.user, *roles):
                raise PermissionDenied("شما به این عملیات دسترسی ندارید.")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
