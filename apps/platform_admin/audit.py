from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

from apps.main.models import AdminAuditLog


def create_admin_audit_log(*, request, action, target=None, old_value=None, new_value=None, reason="", metadata=None):
    target_ct = None
    target_id = None
    if target is not None:
        target_ct = ContentType.objects.get_for_model(target, for_concrete_model=False)
        target_id = target.pk
    return AdminAuditLog.objects.create(
        actor=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        action=action,
        target_content_type=target_ct,
        target_object_id=target_id,
        old_value=old_value or {},
        new_value=new_value or {},
        reason=reason or "",
        metadata=metadata or {},
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
    )
