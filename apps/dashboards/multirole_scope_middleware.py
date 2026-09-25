"""Fail-closed guard for manager routes not yet made multi-salon-aware.

Phase 5A supports a strictly scoped, read-only overview for multi-salon
managers. Legacy manager routes still contain implicit .first() salon selection
and cannot safely serve these accounts until audited individually. The guard
applies to all HTTP methods, including direct URL/POST requests; it is not a
substitute for per-object authorization in future migrated endpoints.
"""

from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin


class UnscopedMultiSalonManagerGuard(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        if not match:
            return None
        view_name = match.view_name or ""
        # Legacy manager-customer views live OUTSIDE the dashboards namespace.
        # Their unscoped customer detail/note route infers a single salon and
        # their explicit add-customer route still renders a single-salon shell.
        # Until migrated, do not allow a multi-salon manager to reach them,
        # including through a direct POST. Personal customer pages are unaffected.
        legacy_account_manager_routes = {
            "accounts:add_customer",
            "accounts:detail_customer",
            "accounts:delete_customer_note",
        }
        if match.namespace != "dashboards" and view_name not in legacy_account_manager_routes:
            return None
        # ONLY audited, explicitly salon-scoped routes may bypass the legacy
        # fail-closed guard. Each corresponding view independently authorizes
        # the requested salon and any affected object.
        if view_name in {
            "dashboards:manager_communication_settings",
            "dashboards:multirole_manager_salon_overview",
            "dashboards:multirole_manager_salon_services",
            "dashboards:multirole_manager_service_toggle",
            "dashboards:multirole_manager_service_add",
            "dashboards:multirole_manager_service_edit",
            "dashboards:multirole_manager_salon_team",
            "dashboards:multirole_manager_team_invite",
            "dashboards:multirole_manager_team_invite_cancel",
            "dashboards:multirole_manager_team_member_edit",
            "dashboards:multirole_manager_salon_bookings",
            "dashboards:multirole_manager_manual_booking",
            "dashboards:multirole_manager_manual_booking_cancel",
            "dashboards:multirole_manager_salon_finance_preview",
            "dashboards:multirole_manager_salon_settlements",
            "dashboards:multirole_manager_salon_customers",
        }:
            return None
        # The stylist workspace remains independent of manager salon selection.
        # Includes /dashboards/stylist/... and the /dashboards/s/a/... alias.
        if match.namespace == "dashboards" and (
            request.path_info.startswith("/dashboards/stylist/")
            or view_name == "dashboards:stylist_appointment_sms"
        ):
            return None

        user = request.user
        if not user.is_authenticated or not user.is_active:
            return None
        from apps.salons.models import Salon

        owned = Salon.objects.filter(salon_manager__user_id=user.pk)
        if len(list(owned.values_list("pk", flat=True)[:2])) < 2:
            return None
        return HttpResponseForbidden(
            "این بخش هنوز برای مدیریت چند سالن آماده نیست؛ از انتخاب محیط فعالیت استفاده کنید."
        )
