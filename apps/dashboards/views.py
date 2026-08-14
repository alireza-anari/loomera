import json
import logging
from urllib.parse import quote
from collections import defaultdict
from datetime import date, datetime
from datetime import time as dt_time
from datetime import timedelta
import jdatetime
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.gis.geos import Point, Polygon
from django.db import models, transaction
from django.db.models import Avg, Q, Sum, Value, Count, Case, When, IntegerField, Max, F
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse, Http404
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from khayyam import JalaliDate
from decimal import Decimal
from apps.accounts.forms import AddCustomerForm, SalonManagerUpdateProfileForm
from apps.dashboards.appointment_management import (
    apply_bulk_appointment_action,
    apply_partner_appointment_action,
    build_appointment_management_context,
    build_manager_appointment_detail_context,
)
from apps.dashboards.home_components import build_dashboard_home_context
from apps.dashboards.readiness import build_salon_readiness_checklist
from apps.dashboards.forms import (
    DashboardManualBookingForm,
    StylistSelfBookingForm,
    StylistSelfScheduleForm,
    StylistSelfTimeOffForm,
)
from apps.dashboards.layout import build_dashboard_context
from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
    format_jalali_with_weekday,
    format_time_fa,
    parse_jalali_input,
    to_persian_digits,
)
from apps.dashboards.reports_components import (
    build_reports_context,
    build_reports_csv_response,
)
from apps.accounts.models import (
    Customer,
    SalonManager,
    Stylist,
    CustomUser,
    WorkSamples,
)
from apps.orders.booking_utils import get_available_slots_for_service
from apps.orders.models import (
    AppointmentMaterialUsage,
    BookingQuickLink,
    Order,
    OrderDetail,
)
from apps.orders.quick_link_management import (
    change_booking_quick_link_status,
    clone_booking_quick_link,
    update_booking_quick_link_metadata,
)
from apps.locations.models import Neighborhood
from apps.orders.quick_links import (
    MAX_AGE_SECONDS,
    build_quick_link_url,
    create_booking_quick_link,
    normalize_booking_payload,
    update_booking_quick_link_status,
)
from apps.orders.quick_link_stats import build_booking_quick_link_stats
from apps.orders.quick_link_qr import (
    generate_booking_quick_link_qr,
    get_booking_quick_link_qr_warnings,
)
from apps.orders.lifecycle import (
    mark_review_requested,
    notify_operational_milestone,
)
from apps.orders.appointment_lifecycle import (
    confirm_no_show,
    confirm_order_detail,
    complete_service as complete_order_detail_service,
    mark_client_late,
    mark_customer_arrived as mark_order_detail_customer_arrived,
    mark_disputed as mark_order_detail_disputed,
    mark_no_show_pending,
    mark_service_overrun,
    reject_order_detail,
    start_service as start_order_detail_service,
)
from apps.salons.forms import (
    SalonDescriptionForm,
    SalonOpeningHoursForm,
    SalonProfileStep1Form,
    SalonProfileStep2Form,
    SalonsGalleryForm,
)
from apps.salons.models import (
    Salon,
    SalonOpeningHours,
    SalonsGallery,
    SupplementaryInfoView,
    CustomerNote,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.salons.membership import (
    change_membership_status,
    ensure_membership_permissions,
    get_active_salon_for_stylist,
    invite_or_attach_stylist,
    log_membership_event,
    sync_legacy_membership,
    default_invite_expiry,
    normalize_mobile,
)
from apps.services.forms import StylistServiceForm
from apps.services.models import (
    GroupServices,
    MaterialItem,
    Services,
    ServiceMaterialTemplate,
    ServicePrice,
)
from apps.main.models import DisputeCase, SupportTicket
from apps.stylists.forms import (
    EmergencyInfoForm,
    JobDetailsForm,
    StylistProfileForm,
    StylistUserForm,
    StylistTimeOffForm,
    WorkSamplesForm,
)
from apps.stylists.models import (
    EmergencyInfo,
    JobDetails,
    StylistSchedule,
    StylistTimeOff,
    StaffLeaveRequest,
    StaffScheduleRequest,
)
from apps.stylists.dashboard_services import (
    build_stylist_finance_payload,
    create_leave_request,
    create_schedule_request,
    create_staff_payout_request,
    resolve_stylist_dashboard_context,
    review_schedule_request,
    review_leave_request,
)
from apps.stylists.profile_services import (
    get_completed_appointment_count,
    get_public_work_samples,
    get_stylist_rating_summary,
    get_stylist_services_for_salon,
)
from apps.dashboards.finance_forms import AppointmentMaterialUsageForm
from apps.payments.finance import (
    confirm_pay_in_salon_cash_payment,
    finalize_order_detail_financials,
    get_pay_in_salon_cash_confirmation_state,
    release_eligible_stylist_wallet_funds_for_salon,
)
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
    StylistWallet,
    StaffPayoutRequest,
)
from django.db.models.functions import TruncDate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from jdatetime import date as jdate, timedelta as jtimedelta
from django.core.exceptions import ValidationError
from django.conf import settings
from functools import wraps
from django.utils.html import strip_tags
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import IntegrityError
from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
)
from apps.notifications.services import create_notification
from apps.accounts.notifications import notify_support_ticket_created


def _user_role_access_label(user):
    if hasattr(user, "salon_manager_profile") and hasattr(user, "stylist"):
        return "مدیر سالن/متخصص"
    if hasattr(user, "salon_manager_profile"):
        return "مدیر سالن"
    if hasattr(user, "stylist"):
        return "متخصص"
    if hasattr(user, "customer_profile"):
        return "مشتری"
    if getattr(user, "is_admin", False):
        return "ادمین"
    return "کاربر"


def _add_wrong_area_message(request, *, target_area, redirect_area=None):
    role_label = _user_role_access_label(request.user)
    message = (
        f"این لینک مربوط به {target_area} است و با حساب {role_label} قابل دسترسی نیست."
    )
    if redirect_area:
        message += f" شما به {redirect_area} منتقل شدید."
    messages.error(request, message)


def _redirect_if_non_dashboard_user(request):
    user = request.user

    if not getattr(user, "is_authenticated", False):
        messages.warning(request, "برای مشاهده این بخش ابتدا وارد حساب کاربری شوید.")
        return redirect("accounts:login")

    if hasattr(user, "salon_manager_profile") or hasattr(user, "stylist"):
        return None

    if hasattr(user, "customer_profile"):
        _add_wrong_area_message(
            request,
            target_area="داشبورد سالن",
            redirect_area="پنل مشتری",
        )
        return redirect("accounts:customer_panel")

    if getattr(user, "is_admin", False):
        _add_wrong_area_message(
            request,
            target_area="داشبورد سالن",
            redirect_area="پنل ادمین",
        )
        return redirect("/admin/")

    messages.error(request, "حساب کاربری شما به هیچ نقش فعال در داشبورد متصل نیست.")
    return redirect("accounts:login")


def _redirect_if_non_manager_user(request):
    if not getattr(request.user, "is_authenticated", False):
        messages.warning(request, "برای مشاهده این بخش ابتدا وارد حساب کاربری شوید.")
        return redirect("accounts:login")

    if hasattr(request.user, "salon_manager_profile"):
        return None

    if hasattr(request.user, "stylist"):
        _add_wrong_area_message(
            request,
            target_area="داشبورد مدیر سالن",
            redirect_area="داشبورد متخصص",
        )
        return redirect("dashboards:stylist_dashboard")

    if hasattr(request.user, "customer_profile"):
        _add_wrong_area_message(
            request,
            target_area="داشبورد مدیر سالن",
            redirect_area="پنل مشتری",
        )
        return redirect("accounts:customer_panel")

    messages.error(
        request, "حساب کاربری شما اجازه دسترسی به داشبورد مدیر سالن را ندارد."
    )
    return redirect("accounts:login")


def _redirect_if_non_stylist_user(request):
    if not getattr(request.user, "is_authenticated", False):
        messages.warning(request, "برای مشاهده این بخش ابتدا وارد حساب کاربری شوید.")
        return redirect("accounts:login")

    if hasattr(request.user, "stylist"):
        return None

    if hasattr(request.user, "salon_manager_profile"):
        _add_wrong_area_message(
            request,
            target_area="داشبورد متخصص",
            redirect_area="داشبورد سالن",
        )
        return redirect("dashboards:salon_manager_dashboard")

    if hasattr(request.user, "customer_profile"):
        _add_wrong_area_message(
            request,
            target_area="داشبورد متخصص",
            redirect_area="پنل مشتری",
        )
        return redirect("accounts:customer_panel")

    messages.error(request, "حساب کاربری شما اجازه دسترسی به داشبورد متخصص را ندارد.")
    return redirect("accounts:login")


def _get_stylist_dashboard_context(request_or_user):
    return resolve_stylist_dashboard_context(request_or_user)


def _get_stylist_dashboard_objects(request_or_user):
    ctx = _get_stylist_dashboard_context(request_or_user)
    return ctx.stylist, ctx.salon


def _stylist_context_payload(ctx):
    return {
        "stylist_obj": ctx.stylist,
        "stylist_salon": ctx.salon,
        "stylist_membership": ctx.membership,
        "stylist_permissions": ctx.permissions,
        "stylist_active_memberships": ctx.active_memberships,
        "stylist_can_complete_appointments": ctx.can("can_complete_appointments", True),
        "stylist_can_view_own_finance": ctx.can("can_view_own_finance", True),
        "stylist_can_request_payout": ctx.can("can_request_payout", True),
        "stylist_can_view_own_clients": ctx.can("can_view_own_clients", True),
        "stylist_can_create_own_bookings": ctx.can("can_create_own_bookings", True),
        "stylist_can_view_client_phone": ctx.can("can_view_client_phone", False),
        "stylist_can_manage_own_schedule": ctx.can("can_manage_own_schedule", False),
        "stylist_can_request_leave": ctx.can("can_request_leave", True),
        "stylist_can_manage_own_portfolio": ctx.can("can_manage_own_portfolio", True),
    }


def _stylist_base_appointments_qs(stylist, salon=None):
    qs = (
        OrderDetail.objects.filter(stylist=stylist)
        .select_related("order", "service", "salon", "order__customer__user")
        .order_by("date", "time", "id")
    )
    if salon is not None:
        qs = qs.filter(salon=salon)
    return qs


@login_required
def set_stylist_active_salon(request):
    redirect_response = _redirect_if_non_stylist_user(request)
    if redirect_response:
        return redirect_response

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or reverse("dashboards:stylist_dashboard")
    )
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        next_url = reverse("dashboards:stylist_dashboard")

    if request.method != "POST":
        return redirect(next_url)

    salon_id = (request.POST.get("salon_id") or "").strip()
    stylist = getattr(request.user, "stylist", None)

    if not salon_id.isdigit() or not stylist:
        messages.error(request, "سالن انتخاب‌شده معتبر نیست.")
        return redirect(next_url)

    membership = (
        SalonMembership.objects.select_related("salon")
        .filter(
            salon_id=int(salon_id),
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
        )
        .first()
    )

    if membership is None:
        messages.error(request, "به این سالن دسترسی فعال ندارید.")
        return redirect(next_url)

    request.session["active_stylist_salon_id"] = str(membership.salon_id)
    request.session.modified = True

    messages.success(
        request,
        f"نمای داشبورد روی سالن {membership.salon.salon_name} تنظیم شد.",
    )
    return redirect(next_url)


class StylistDashboardGuardMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        redirect_response = _redirect_if_non_stylist_user(request)
        if redirect_response:
            return redirect_response
        return super().dispatch(request, *args, **kwargs)


def manager_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        redirect_response = _redirect_if_non_manager_user(request)
        if redirect_response:
            return redirect_response
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


def _dashboard_currency(value):
    return f"{to_persian_digits(f'{int(value or 0):,}')} تومان"


def _stylist_item_pricing_meta(detail):
    order = detail.order
    base_price = int(detail.price or 0)
    subtotal_amount = int(order.subtotal_amount or base_price or 0)
    discount_amount = int(order.discount_amount or 0)
    discount_amount = max(min(discount_amount, subtotal_amount), 0)

    item_discount = 0
    if base_price > 0 and subtotal_amount > 0 and discount_amount > 0:
        item_discount = round((discount_amount * base_price) / subtotal_amount)

    item_discount = max(min(int(item_discount or 0), base_price), 0)
    final_price = max(base_price - item_discount, 0)

    return {
        "base_price_label": _dashboard_currency(base_price),
        "discount_label": _dashboard_currency(item_discount),
        "final_price_label": _dashboard_currency(final_price),
        "has_discount": item_discount > 0,
    }


def _stylist_detail_status_meta(detail):
    if detail.order.status == "cancelled":
        return {"label": "لغو شده", "badge_class": "bg-rose-100 text-rose-700"}

    if detail.confirmation_status == detail.ConfirmationStatus.REJECTED:
        return {"label": "رد شده", "badge_class": "bg-rose-100 text-rose-700"}

    mapping = {
        detail.ServiceLifecycleStatus.AWAITING_CONFIRMATION: {
            "label": "در انتظار تایید",
            "badge_class": "bg-amber-100 text-amber-700",
        },
        detail.ServiceLifecycleStatus.CONFIRMED: {
            "label": "تایید شده",
            "badge_class": "bg-indigo-100 text-indigo-700",
        },
        detail.ServiceLifecycleStatus.ARRIVED: {
            "label": "مشتری رسید",
            "badge_class": "bg-cyan-100 text-cyan-700",
        },
        detail.ServiceLifecycleStatus.IN_SERVICE: {
            "label": "در حال انجام",
            "badge_class": "bg-violet-100 text-violet-700",
        },
        detail.ServiceLifecycleStatus.COMPLETED: {
            "label": "تکمیل شده",
            "badge_class": "bg-emerald-100 text-emerald-700",
        },
        detail.ServiceLifecycleStatus.DISPUTED: {
            "label": "دارای اختلاف",
            "badge_class": "bg-slate-100 text-slate-700",
        },
    }

    return mapping.get(
        detail.lifecycle_status,
        {"label": "در انتظار تایید", "badge_class": "bg-amber-100 text-amber-700"},
    )


def _safe_jalali_label(value, formatter=format_jalali_numeric, fallback="—"):
    if not value:
        return fallback
    try:
        return formatter(value)
    except Exception:
        return str(value)


def calculate_percentage_change(current, previous):
    current = current or 0
    previous = previous or 0

    if previous == 0:
        return 100.0 if current > 0 else 0.0

    return round(((current - previous) / previous) * 100, 1)


def _safe_jalali_datetime_label(value, fallback="—"):
    if not value:
        return fallback
    try:
        local_value = timezone.localtime(value) if timezone.is_aware(value) else value
    except Exception:
        local_value = value

    try:
        return f"{format_jalali_with_weekday(local_value.date())} • {format_time_fa(local_value.time())}"
    except Exception:
        return fallback


def _percentage_label(value):
    sign = "+" if value > 0 else ""
    return (
        f"{sign}{to_persian_digits(value)}٪"
        if isinstance(value, int)
        else f"{sign}{value}٪"
    )


ONBOARDING_STEP_ORDER = {
    "dashboards:salon_profile_creator_step1": 1,
    "dashboards:salon_profile_creator_step2": 2,
    "dashboards:salon_profile_creator_step3": 3,
    "dashboards:salon_profile_creator_step6": 4,
    "dashboards:delete_salon_image": 4,
    "dashboards:salon_profile_creator_step7": 5,
    "dashboards:salon_profile_creator_step8": 6,
    "dashboards:salon_profile_creator_step9": 7,
    "dashboards:salon_profile_creator_step10": 8,
    "dashboards:salon_profile_creator_finalStep": 9,
}

ONBOARDING_FLOW_URL_NAMES = set(ONBOARDING_STEP_ORDER.keys()) | {
    "dashboards:salon_profile_creator",
}


def _get_manager_salon(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if not hasattr(user, "salon_manager_profile"):
        return None

    return (
        Salon.objects.select_related("salon_manager__user")
        .prefetch_related("opening_hours", "gallery_images", "supplementary_info")
        .filter(salon_manager__user=user)
        .first()
    )


def _manager_placeholder_salon_name(user):
    display_name = (getattr(user, "get_fullName", lambda: "")() or "").strip()
    if not display_name:
        display_name = (
            f"{getattr(user, 'name', '')} {getattr(user, 'family', '')}".strip()
        )
    if not display_name:
        display_name = getattr(user, "mobile_number", "") or f"{user.pk}"
    return f"مجموعه {display_name}"[:50]


def _get_or_create_manager_salon(user):
    """Return the manager's draft salon, creating it for fresh signups.

    New salon-manager accounts can reach onboarding step 1 before any Salon row
    exists. Step 1 itself is responsible for collecting the real salon name and
    phone, so the draft must be safe, inactive and incomplete.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    if not hasattr(user, "salon_manager_profile"):
        return None

    salon = _get_manager_salon(user)
    if salon is not None:
        return salon

    manager, _ = SalonManager.objects.get_or_create(user=user)
    return Salon.objects.create(
        salon_manager=manager,
        salon_name=_manager_placeholder_salon_name(user),
        phone_number=None,
        is_active=False,
    )


def _ensure_memberships_for_legacy_salon_staff(salon, *, actor=None, request=None):
    """Backfill SalonMembership and permissions for legacy salon.stylists links.

    This is intentionally conservative: existing membership statuses are not
    overwritten, so pausing/ending a collaboration stays local to that salon and
    does not reactivate by just opening a dashboard page.
    """
    if salon is None:
        return {}

    stylists = list(salon.stylists.select_related("user").all())
    if not stylists:
        return {}

    existing = {
        membership.stylist_id: membership
        for membership in SalonMembership.objects.filter(
            salon=salon,
            stylist_id__in=[stylist.pk for stylist in stylists],
        )
    }

    status_map = {}
    for stylist in stylists:
        membership = existing.get(stylist.pk)
        if membership is None:
            membership = sync_legacy_membership(
                salon=salon,
                stylist=stylist,
                actor=actor,
                status=(
                    SalonMembershipStatus.ACTIVE
                    if stylist.is_active
                    else SalonMembershipStatus.PAUSED
                ),
                role_title=getattr(stylist, "expert", "") or "",
                invited_phone=getattr(stylist.user, "mobile_number", "") or "",
                invited_email=getattr(stylist.user, "email", "") or "",
                request=request,
            )
        else:
            ensure_membership_permissions(membership)
        status_map[stylist.pk] = membership.status

    return status_map


def _ensure_active_staff_membership_for_salon(
    salon, stylist, *, actor=None, request=None
):
    """Persist the salon/stylist membership and dashboard permission immediately.

    This is used after the add-stylist flow so the new membership is visible in
    the DB without waiting for a later backfill command or dashboard page load.
    It is intentionally idempotent and reactivates only because the manager has
    explicitly added/attached this stylist to this salon.
    """
    if salon is None or stylist is None:
        raise ValidationError("مجموعه یا متخصص برای ساخت عضویت مشخص نیست.")

    membership = SalonMembership.objects.filter(salon=salon, stylist=stylist).first()
    if membership is None:
        membership = sync_legacy_membership(
            salon=salon,
            stylist=stylist,
            actor=actor,
            status=SalonMembershipStatus.ACTIVE,
            role_title=getattr(stylist, "expert", "") or "",
            invited_phone=getattr(getattr(stylist, "user", None), "mobile_number", "")
            or "",
            invited_email=getattr(getattr(stylist, "user", None), "email", "") or "",
            request=request,
        )
    else:
        update_fields = []
        if membership.status != SalonMembershipStatus.ACTIVE:
            membership.status = SalonMembershipStatus.ACTIVE
            update_fields.append("status")
        if not membership.accepted_at:
            membership.accepted_at = timezone.now()
            update_fields.append("accepted_at")
        if (
            actor is not None
            and getattr(actor, "is_authenticated", False)
            and not membership.invited_by_id
        ):
            membership.invited_by = actor
            update_fields.append("invited_by")
        if update_fields:
            update_fields.append("updated_at")
            membership.save(update_fields=update_fields)

        if not salon.stylists.filter(pk=stylist.pk).exists():
            salon.stylists.add(stylist)
        ensure_membership_permissions(membership)

    permission = ensure_membership_permissions(membership)

    if not SalonMembership.objects.filter(
        pk=membership.pk, salon=salon, stylist=stylist
    ).exists():
        raise ValidationError("عضویت متخصص در مجموعه ذخیره نشد.")
    if permission is None:
        raise ValidationError("دسترسی داشبورد متخصص ذخیره نشد.")

    return membership


def _is_step1_complete(salon):
    if salon is None:
        return False
    name_ok = bool((salon.salon_name or "").strip())
    explicit_contacts_ok = bool(
        (getattr(salon, "mobile_phone", "") or "").strip()
        and (getattr(salon, "landline_phone", "") or "").strip()
    )
    # Existing production salons may only have the legacy contact field.
    legacy_contact_ok = bool(getattr(salon, "phone_number", None))
    return bool(name_ok and (explicit_contacts_ok or legacy_contact_ok))


def _is_step2_complete(salon):
    if salon is None:
        return False
    return bool(
        salon.zone
        and salon.neighborhood_id
        and (salon.address or "").strip()
        and salon.location
    )


def _is_step3_complete(salon):
    if salon is None:
        return False
    return salon.opening_hours.count() >= 7


def _is_step6_complete(salon):
    if salon is None:
        return False
    return salon.gallery_images.exists()


def _is_step7_complete(salon):
    if salon is None:
        return False
    return salon.supplementary_info.filter(is_active=True).exists()


def _is_step8_complete(salon):
    if salon is None:
        return False
    return bool((salon.description or "").strip())


def _is_step10_complete(salon):
    if salon is None:
        return False
    return bool(salon.is_active)


def _get_required_onboarding_view_name(user):
    salon = _get_manager_salon(user)

    if salon is None or not _is_step1_complete(salon):
        return "dashboards:salon_profile_creator_step1"

    if not _is_step2_complete(salon):
        return "dashboards:salon_profile_creator_step2"

    if not _is_step3_complete(salon):
        return "dashboards:salon_profile_creator_step3"

    # Gallery is optional and never blocks dashboard access.

    if not _is_step7_complete(salon):
        return "dashboards:salon_profile_creator_step7"

    if not _is_step8_complete(salon):
        return "dashboards:salon_profile_creator_step8"

    # Public activation is a post-onboarding readiness action.
    return None


def _redirect_to_required_onboarding(request):
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return None

    if not hasattr(user, "salon_manager_profile"):
        return None

    target_view_name = _get_required_onboarding_view_name(user)
    if not target_view_name:
        return None

    current_view_name = ""
    if getattr(request, "resolver_match", None):
        current_view_name = request.resolver_match.view_name or ""

    target_rank = ONBOARDING_STEP_ORDER.get(target_view_name, 0)
    current_rank = ONBOARDING_STEP_ORDER.get(current_view_name, 0)

    if current_view_name in ONBOARDING_FLOW_URL_NAMES:
        if current_view_name == target_view_name:
            return None

        if current_rank and current_rank <= target_rank:
            return None

        return redirect(target_view_name)

    messages.info(
        request,
        "برای دسترسی به بخش‌های داشبورد، ابتدا پروفایل مجموعه را کامل کنید.",
        "info",
    )
    return redirect(target_view_name)


class SalonManagerOnboardingGuardMixin:
    def dispatch(self, request, *args, **kwargs):
        access_redirect = _redirect_if_non_manager_user(request)
        if access_redirect:
            return access_redirect

        redirect_response = _redirect_to_required_onboarding(request)
        if redirect_response:
            return redirect_response

        return super().dispatch(request, *args, **kwargs)


# -- ----------------------------------------------------------------
class SalonManagerDashboardView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    def get(self, request, *args, **kwargs):
        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="overview",
            page_title="داشبورد مجموعه",
        )
        context.update(build_dashboard_home_context(request.user))
        return render(request, "dashboards/salonManager_dashboard.html", context)


# -------------------------------------------------------------------
def salonManagerHeader(request, salon_manager=None):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return redirect_response
    context = build_dashboard_context(
        request.user,
        nav_active="home",
        sidebar_active="overview",
        page_title="داشبورد مجموعه",
    )
    return render(request, "partials/dashboard/header.html", context)


# -------------------------------------------------------------------
class DashboardHomeView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="overview",
            page_title="خانه داشبورد",
        )
        context.update(build_dashboard_home_context(request.user))
        return render(request, "dashboards/home.html", context)


# -------------------------------------------------------------------
def recently_sales(request, salon):

    # =================================================================
    # ۱. آماده‌سازی تاریخ‌های شمسی
    # =================================================================

    try:
        today_shamsi = jdatetime.date.today()
        seven_days_ago_shamsi = today_shamsi - jdatetime.timedelta(days=6)

        # تبدیل به فرمت رشته برای مقایسه در دیتابیس
        today_shamsi_str = today_shamsi.strftime("%Y-%m-%d")
        seven_days_ago_shamsi_str = seven_days_ago_shamsi.strftime("%Y-%m-%d")

    except Exception as e:

        return render(
            request,
            "dashboards/partials/recently_sales.html",
            {"error": "خطا در تبدیل تاریخ"},
        )

    # =================================================================
    # ۲. بررسی وجود داده
    # =================================================================

    all_orders = OrderDetail.objects.filter(salon=salon)

    finalized_orders = OrderDetail.objects.filter(salon=salon, order__is_finally=True)

    # =================================================================
    # ۳. کوئری با تاریخ شمسی
    # =================================================================

    # فرض کنیم فیلد date در دیتابیس رشته تاریخ شمسی است
    date_filtered_query = finalized_orders.filter(
        date__gte=seven_days_ago_shamsi_str, date__lte=today_shamsi_str
    )

    # اگر هنوز هیچ رکوردی پیدا نشد، احتمالاً فرمت تاریخ متفاوت است
    if date_filtered_query.count() == 0:

        # تست فرمت‌های مختلف
        sample_dates = all_orders.values_list("date", flat=True)[:5]

        # اگر تاریخ‌ها در قالب 1404/06/20 هستند
        seven_days_ago_slash = seven_days_ago_shamsi.strftime("%Y-%m-%d")
        today_slash = today_shamsi.strftime("%Y-%m-%d")

        date_filtered_query = finalized_orders.filter(
            date__gte=seven_days_ago_slash, date__lte=today_slash
        )

        if date_filtered_query.count() == 0:
            # تست با بازه گسترده‌تر (30 روز)
            thirty_days_ago = today_shamsi - jdatetime.timedelta(days=30)
            thirty_days_ago_str = thirty_days_ago.strftime("%Y-%m-%d")

            date_filtered_query = finalized_orders.filter(
                date__gte=thirty_days_ago_str, date__lte=today_shamsi_str
            )

            if date_filtered_query.count() == 0:
                thirty_days_ago_slash = thirty_days_ago.strftime("%Y-%m-%d")
                date_filtered_query = finalized_orders.filter(
                    date__gte=thirty_days_ago_slash, date__lte=today_slash
                )

    # کوئری نهایی
    daily_sales_data = (
        date_filtered_query.values("date")
        .annotate(
            sales=Sum("price"),
            appointments=Count("pk"),
        )
        .order_by("date")
    )

    # =================================================================
    # ۴. پردازش داده‌ها
    # =================================================================

    sales_dict = {}
    for item in daily_sales_data:
        date_str = str(item["date"])
        # تبدیل فرمت تاریخ اگر لازم باشد
        if "/" in date_str:
            date_str = date_str.replace("/", "-")

        sales_dict[date_str] = item

    # آماده‌سازی داده‌ها برای چارت
    total_sales = 0
    appointment_count = 0
    chart_data = []

    for i in range(7):
        current_day_shamsi = today_shamsi - jdatetime.timedelta(days=6 - i)
        current_day_str = current_day_shamsi.strftime("%Y-%m-%d")

        day_data = sales_dict.get(current_day_str, {"sales": 0, "appointments": 0})

        daily_sales = day_data.get("sales") or 0
        daily_appointments = day_data.get("appointments") or 0

        chart_data.append(
            {
                "date": current_day_str,
                "date_display": current_day_shamsi.strftime("%m-%d"),
                "sales": round(daily_sales, 2),
                "appointments": daily_appointments,
            }
        )

        total_sales += daily_sales
        appointment_count += daily_appointments

    context = {
        "total_sales": round(total_sales, 2),
        "appointment_count": appointment_count,
        "appointments_value": sum(
            (item.get("sales") or 0) for item in sales_dict.values()
        ),
        "chart_data": json.dumps(chart_data, ensure_ascii=False),
        "salon": salon,
    }

    return render(request, "dashboards/partials/recently_sales.html", context)


# ----------------------------------------------------------------------
def upcoming_appointments(request, salon):
    # =================================================================
    # ۲. آماده‌سازی تاریخ‌های شمسی - اصلاح شده
    # =================================================================

    today_jalali = jdate.today()
    seven_days_later_jalali = today_jalali + jtimedelta(days=7)

    # تبدیل به string برای استفاده در کوئری Django
    today_jalali_str = today_jalali.strftime("%Y-%m-%d")
    seven_days_later_jalali_str = seven_days_later_jalali.strftime("%Y-%m-%d")

    # فیلتر با تاریخ‌های string
    upcoming_appointments_qs = OrderDetail.objects.filter(
        date__gte=today_jalali_str,
        date__lte=seven_days_later_jalali_str,
        salon=salon,
    )

    # =================================================================
    # ۳. محاسبه شمارش کل
    # =================================================================

    total_counts = upcoming_appointments_qs.aggregate(
        confirmed_count=Count(
            "id", filter=Q(order__stylist_approved=True, order__is_finally=True)
        ),
        canceled_count=Count("id", filter=Q(order__is_finally=False)),
    )

    # =================================================================
    # ۴. آماده‌سازی داده‌های نمودار - روش جایگزین
    # =================================================================

    # روش ۱: استفاده از کوئری ساده و پردازش در Python
    all_appointments = upcoming_appointments_qs.select_related("order").values(
        "date", "order__stylist_approved", "order__is_finally"
    )

    # ایجاد دیکشنری برای محاسبه روزانه
    daily_counts = {}

    # مقداردهی اولیه برای تمام روزها
    for i in range(7):
        current_date = today_jalali + jtimedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        daily_counts[date_str] = {"confirmed": 0, "canceled": 0}

    # شمارش داده‌ها
    for appointment in all_appointments:
        appointment_date = appointment["date"]

        # تبدیل به string اگر لازم باشد
        if hasattr(appointment_date, "strftime"):
            date_str = appointment_date.strftime("%Y-%m-%d")
        else:
            date_str = str(appointment_date)

        # بررسی اینکه آیا تاریخ در محدوده ۷ روز است
        if date_str in daily_counts:
            # بررسی وضعیت سفارش
            is_confirmed = (
                appointment["order__stylist_approved"] == True
                and appointment["order__is_finally"] == True
            )
            is_canceled = appointment["order__is_finally"] == False

            if is_confirmed:
                daily_counts[date_str]["confirmed"] += 1
            elif is_canceled:
                daily_counts[date_str]["canceled"] += 1

    # ساخت ساختار داده نهایی
    appointments_chart_data = []
    for i in range(7):
        current_date = today_jalali + jtimedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")

        appointments_chart_data.append(
            {
                "date": date_str,
                "date_display": current_date.strftime("%m-%d"),  # MM-DD برای نمایش
                "confirmed": daily_counts[date_str]["confirmed"],
                "canceled": daily_counts[date_str]["canceled"],
            }
        )

    context = {
        "confirmed_count": total_counts["confirmed_count"],
        "canceled_count": total_counts["canceled_count"],
        "appointments_chart_data": json.dumps(appointments_chart_data),
    }

    return render(request, "dashboards/partials/upcoming_appointments.html", context)


# ----------------------------------------------------------------------
def get_popular_services(request, salon):
    # =================================================================
    # ۱. محاسبه محدوده تاریخ شمسی به صورت رشته
    # =================================================================
    today_jalali = JalaliDate.today()

    # تبدیل تاریخ‌ها به فرمت رشته (مثال: "1403-06-15")
    start_of_current_month_str = f"{today_jalali.year:04d}-{today_jalali.month:02d}-01"

    # ماه بعدی
    if today_jalali.month == 12:
        next_year = today_jalali.year + 1
        next_month = 1
    else:
        next_year = today_jalali.year
        next_month = today_jalali.month + 1
    start_of_next_month_str = f"{next_year:04d}-{next_month:02d}-01"

    # ماه قبلی
    if today_jalali.month == 1:
        last_year = today_jalali.year - 1
        last_month = 12
    else:
        last_year = today_jalali.year
        last_month = today_jalali.month - 1
    start_of_last_month_str = f"{last_year:04d}-{last_month:02d}-01"

    # =================================================================
    # ۲. کوئری با استفاده از تاریخ‌های رشته‌ای
    # =================================================================
    popular_services_data = (
        OrderDetail.objects.filter(
            salon=salon,
            order__is_finally=True,
            date__gte=start_of_last_month_str,
            date__lt=start_of_next_month_str,
        )
        .values("service__pk", "service__service_name")
        .annotate(
            current_month_count=Count(
                Case(
                    When(
                        Q(
                            date__gte=start_of_current_month_str,
                            date__lt=start_of_next_month_str,
                        ),
                        then=1,
                    ),
                    output_field=IntegerField(),
                )
            ),
            last_month_count=Count(
                Case(
                    When(
                        Q(
                            date__gte=start_of_last_month_str,
                            date__lt=start_of_current_month_str,
                        ),
                        then=1,
                    ),
                    output_field=IntegerField(),
                )
            ),
            total_count=Count("id"),
        )
        .filter(total_count__gt=0)
        .order_by("-current_month_count", "-last_month_count", "-total_count")[:10]
    )

    # محاسبه درصد تغییر
    services_with_change = []
    for service in popular_services_data:
        current = service["current_month_count"]
        last = service["last_month_count"]

        if last > 0:
            change_percent = round(((current - last) / last) * 100, 1)
        elif current > 0:
            change_percent = 100
        else:
            change_percent = 0

        service["change_percent"] = change_percent
        service["is_growing"] = current > last
        services_with_change.append(service)

    context = {
        "popular_services": services_with_change,
        "current_month": f"{today_jalali.year}/{today_jalali.month}",
    }

    return render(request, "dashboards/partials/popular_services.html", context)


# ---------------------------------------------------------------------
def get_popular_stylists(request, salon):
    # =================================================================
    # ۱. محاسبه محدوده تاریخ شمسی به صورت رشته
    # =================================================================
    today_jalali = JalaliDate.today()

    # تبدیل تاریخ‌ها به فرمت رشته (مثال: "1403-06-15")
    start_of_current_month_str = f"{today_jalali.year:04d}-{today_jalali.month:02d}-01"

    # ماه بعدی
    if today_jalali.month == 12:
        next_year = today_jalali.year + 1
        next_month = 1
    else:
        next_year = today_jalali.year
        next_month = today_jalali.month + 1
    start_of_next_month_str = f"{next_year:04d}-{next_month:02d}-01"

    # ماه قبلی
    if today_jalali.month == 1:
        last_year = today_jalali.year - 1
        last_month = 12
    else:
        last_year = today_jalali.year
        last_month = today_jalali.month - 1
    start_of_last_month_str = f"{last_year:04d}-{last_month:02d}-01"

    # =================================================================
    # ۲. کوئری با استفاده از تاریخ‌های رشته‌ای
    # =================================================================
    popular_stylist_data = (
        OrderDetail.objects.filter(
            salon=salon,
            order__is_finally=True,
            date__gte=start_of_last_month_str,
            date__lt=start_of_next_month_str,
        )
        .values("stylist__user__id", "stylist__user__name", "stylist__user__family")
        .annotate(
            current_month_count=Count(
                Case(
                    When(
                        Q(
                            date__gte=start_of_current_month_str,
                            date__lt=start_of_next_month_str,
                        ),
                        then=1,
                    ),
                    output_field=IntegerField(),
                )
            ),
            last_month_count=Count(
                Case(
                    When(
                        Q(
                            date__gte=start_of_last_month_str,
                            date__lt=start_of_current_month_str,
                        ),
                        then=1,
                    ),
                    output_field=IntegerField(),
                )
            ),
            total_count=Count("id"),
        )
        .filter(total_count__gt=0)
        .order_by("-current_month_count", "-last_month_count", "-total_count")[:10]
    )

    # محاسبه درصد تغییر
    stylists_with_change = []
    for stylist in popular_stylist_data:
        current = stylist["current_month_count"]
        last = stylist["last_month_count"]

        if last > 0:
            change_percent = round(((current - last) / last) * 100, 1)
        elif current > 0:
            change_percent = 100
        else:
            change_percent = 0

        stylist["change_percent"] = change_percent
        stylist["is_growing"] = current > last
        stylists_with_change.append(stylist)

    context = {
        "popular_stylists": stylists_with_change,
        "current_month": f"{today_jalali.year}/{today_jalali.month}",
    }

    return render(request, "dashboards/partials/popular_stylists.html", context)


# ---------------------------------------------------------------------
def today_appointment(request, salon):

    today_jalali = JalaliDate.today()
    today_str = today_jalali.strftime("%Y-%m-%d")
    current_time = datetime.now().time()

    today_appointments = (
        OrderDetail.objects.filter(date=today_str, salon=salon, time__gte=current_time)
        .select_related("service", "order__customer__user", "stylist__user")
        .order_by("time")
    )

    context = {
        "today_appointments": today_appointments,
    }
    return render(request, "dashboards/partials/today_appointment.html", context)


# ---------------------------------------------------------------------
def appointments_activity(request, salon):

    today_jalali = JalaliDate.today()
    # اگر تاریخ شما DateField است، از today_jalali.todate() استفاده کنید
    # اگر رشته است، از today_jalali.strftime("%Y-%m-%d")
    today_str = today_jalali.strftime("%Y-%m-%d")

    # ✅ بهینه‌سازی اصلی: واکشی تمام اطلاعات مرتبط در یک کوئری جامع
    upcoming_appointments = (
        OrderDetail.objects.filter(salon=salon, date__gte=today_str)
        .select_related("service", "order__customer__user", "stylist__user")
        .order_by("date", "time")
    )

    # ✅ بهینه‌سازی: گروه‌بندی در پایتون با defaultdict که خواناتر و بهینه‌تر است
    appointments_by_date = defaultdict(list)
    for appointment in upcoming_appointments:
        # تمام اطلاعات از قبل واکشی شده و هیچ کوئری جدیدی زده نمی‌شود
        appointments_by_date[appointment.date.strftime("%Y-%m-%d")].append(
            {
                "id": appointment.pk,
                "service_name": appointment.service.service_name,
                "customer_name": appointment.order.customer.get_fullName(),
                "time": appointment.time,
                "duration": f"{appointment.service.duration_minutes}min",
                "stylist_name": appointment.stylist.get_fullName(),
                "price": appointment.price,
                "status": (
                    "تأیید شده"
                    if appointment.order.stylist_approved
                    else "در انتظار تأیید"
                ),
                "date": appointment.date,
            }
        )

    context = {
        # تبدیل defaultdict به dict معمولی برای ارسال به تمپلیت
        "appointments_by_date": dict(appointments_by_date),
    }

    return render(request, "dashboards/partials/appointments_activity.html", context)


# ----------------------------------------------------------------------
CUSTOMER_WORKSPACE_SORT_MAP = {
    "recent": ("-last_visit", "-user__pk"),
    "top_spend": ("-total_spent", "-appointments_count"),
    "appointments": ("-appointments_count", "-last_visit"),
    "name": ("user__family", "user__name"),
}


def _build_salon_customers_queryset(
    *,
    salon,
    query="",
    sort_by="recent",
):
    """Return salon-scoped customers with all workspace annotations.

    The returned queryset is lazy and must execute as one database query when
    evaluated. All customer workspace cards and summary metrics can then be
    built from the resulting in-memory objects.
    """

    customer_ids_from_orders = (
        OrderDetail.objects.filter(
            salon=salon,
        )
        .values_list(
            "order__customer__user_id",
            flat=True,
        )
        .distinct()
    )

    queryset = (
        Customer.objects.filter(
            Q(user_id__in=customer_ids_from_orders)
            | Q(added_by_salon=salon)
        )
        .select_related("user")
        .annotate(
            appointments_count=Count(
                "orders__order_details1",
                filter=Q(
                    orders__order_details1__salon=salon,
                ),
                distinct=True,
            ),
            total_spent=Coalesce(
                Sum(
                    "orders__order_details1__price",
                    filter=Q(
                        orders__order_details1__salon=salon,
                        orders__status__in=[
                            "confirmed",
                            "paid",
                            "completed",
                        ],
                    ),
                ),
                Value(0),
            ),
            last_visit=Max(
                "orders__order_details1__date",
                filter=Q(
                    orders__order_details1__salon=salon,
                ),
            ),
            notes_count=Count(
                "customer_note",
                filter=Q(
                    customer_note__salon=salon,
                ),
                distinct=True,
            ),
        )
        .distinct()
    )

    normalized_query = (query or "").strip()

    if normalized_query:
        queryset = queryset.filter(
            Q(user__name__icontains=normalized_query)
            | Q(user__family__icontains=normalized_query)
            | Q(user__mobile_number__icontains=normalized_query)
            | Q(user__email__icontains=normalized_query)
        )

    return queryset.order_by(
        *CUSTOMER_WORKSPACE_SORT_MAP.get(
            sort_by,
            CUSTOMER_WORKSPACE_SORT_MAP["recent"],
        )
    )


def _build_customer_workspace_metrics(
    customers,
    *,
    today,
):
    """Calculate customer workspace summaries without database queries."""

    recent_threshold = today - timedelta(days=30)
    dormant_threshold = today - timedelta(days=90)

    total_customers = 0
    with_appointments = 0
    vip_customers = 0
    recent_customers = 0
    needs_follow_up = 0

    for customer in customers:
        total_customers += 1

        appointments_count = int(customer.appointments_count or 0)
        total_spent = customer.total_spent or 0
        last_visit = customer.last_visit

        if appointments_count > 0:
            with_appointments += 1

        # Preserve the existing workspace definition exactly.
        if total_spent > 0:
            vip_customers += 1

        if last_visit is not None and last_visit >= recent_threshold:
            recent_customers += 1

        if last_visit is None or last_visit < dormant_threshold:
            needs_follow_up += 1

    return {
        "total_customers": total_customers,
        "with_appointments": with_appointments,
        "vip_customers": vip_customers,
        "recent_customers": recent_customers,
        "needs_follow_up": needs_follow_up,
    }


class SalonsCustomersPageView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    main_template = "dashboards/salonsCustomersPage.html"
    partial_template = "dashboards/partials/salons_customers.html"

    def _serialize_customer(self, customer, salon, today):
        full_name = (
            customer.get_fullName() or customer.user.get_fullName() or "مشتری بدون نام"
        )
        mobile = customer.user.mobile_number or ""
        email = customer.user.email or ""
        appointments_count = customer.appointments_count or 0
        total_spent = customer.total_spent or 0
        notes_count = customer.notes_count or 0
        last_visit = customer.last_visit

        if total_spent > 0 and appointments_count >= 3:
            segment_label = "مشتری ارزشمند"
            segment_badge_class = "bg-loomera-primarySoft text-loomera-primaryText"
        elif last_visit and last_visit >= (today - timedelta(days=30)):
            segment_label = "مشتری فعال"
            segment_badge_class = "bg-emerald-100 text-emerald-700"
        elif appointments_count == 0:
            segment_label = "بدون رزرو"
            segment_badge_class = "bg-slate-100 text-slate-700"
        else:
            segment_label = "نیازمند پیگیری"
            segment_badge_class = "bg-amber-100 text-amber-700"

        return {
            "id": customer.pk,
            "full_name": full_name,
            "initial": (full_name[:1] or "م"),
            "mobile": mobile,
            "email": email,
            "appointments_count": appointments_count,
            "appointments_count_label": to_persian_digits(appointments_count),
            "total_spent_label": _dashboard_currency(total_spent),
            "total_spent_value": total_spent,
            "notes_count_label": to_persian_digits(notes_count),
            "last_visit_label": _safe_jalali_label(
                last_visit, formatter=format_jalali_with_weekday
            ),
            "last_visit_short_label": _safe_jalali_label(last_visit),
            "last_visit_raw": last_visit,
            "segment_label": segment_label,
            "segment_badge_class": segment_badge_class,
            "detail_url": reverse(
                "dashboards:customer_detail", kwargs={"customer_id": customer.pk}
            ),
            "appointments_url": f"{reverse('dashboards:appointment_calendar', kwargs={'salon_id': salon.id})}?q={mobile or full_name}",
            "call_url": f"tel:{mobile}" if mobile else "",
            "has_profile_image": bool(getattr(customer, "profile_image", None)),
            "profile_image": getattr(customer, "profile_image", None),
        }

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        q = (request.GET.get("q") or "").strip()
        sort_by = (request.GET.get("sort_by") or "recent").strip()
        today = timezone.localdate()

        customers_qs = _build_salon_customers_queryset(
            salon=salon,
            query=q,
            sort_by=sort_by,
        )

        customers = list(customers_qs)

        customer_cards = [
            self._serialize_customer(
                customer,
                salon,
                today,
            )
            for customer in customers
        ]

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return render(
                request,
                self.partial_template,
                {
                    "customer_cards": customer_cards,
                    "salon": salon,
                },
            )

        customer_metrics = _build_customer_workspace_metrics(
            customers,
            today=today,
        )

        sort_labels = {
            "recent": "آخرین مراجعه",
            "top_spend": "بیشترین هزینه",
            "appointments": "بیشترین رزرو",
            "name": "نام",
        }

        active_filter_chips = []
        if q:
            active_filter_chips.append({"label": "جستجو", "value": q})
        if sort_by and sort_by != "recent":
            active_filter_chips.append(
                {"label": "مرتب‌سازی", "value": sort_labels.get(sort_by, "پیش‌فرض")}
            )

        workspace = {
            "page_title": f"مشتریان مجموعه {salon.salon_name}",
            "query": q,
            "sort_by": sort_by,
            "total_customers": customer_metrics[
                "total_customers"
            ],
            "with_appointments": customer_metrics[
                "with_appointments"
            ],
            "vip_customers": customer_metrics[
                "vip_customers"
            ],
            "recent_customers": customer_metrics[
                "recent_customers"
            ],
            "needs_follow_up": customer_metrics[
                "needs_follow_up"
            ],
            "active_filter_chips": active_filter_chips,
            "result_count_label": (
                f"{to_persian_digits(customer_metrics['total_customers'])} مشتری"
            ),
            "sort_label": sort_labels.get(sort_by, "آخرین مراجعه"),
            "add_customer_url": reverse(
                "accounts:add_customer", kwargs={"salon_id": salon.id}
            ),
            "calendar_url": reverse(
                "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
            ),
            "dashboard_url": reverse("dashboards:salon_manager_dashboard"),
        }

        context = {
            "salon": salon,
            "form": AddCustomerForm(),
            "customer_workspace": workspace,
            "customer_cards": customer_cards,
        }
        return render(request, self.main_template, context)


class CustomerDetailView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/customer_detail.html"

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

    def _get_customer(self, salon, customer_id):
        customer = get_object_or_404(
            Customer.objects.select_related("user").prefetch_related("addresses"),
            pk=customer_id,
        )
        has_relation = (
            customer.added_by_salon_id == salon.id
            or OrderDetail.objects.filter(
                salon=salon, order__customer=customer
            ).exists()
        )
        if not has_relation:
            raise Http404("Customer not found for this salon")
        return customer

    def _status_meta(self, order):
        status = getattr(order, "status", "") or "pending"
        mapping = {
            "pending": {
                "label": "در انتظار تایید",
                "badge_class": "bg-amber-100 text-amber-700",
            },
            "confirmed": {
                "label": "تایید شده",
                "badge_class": "bg-loomera-primarySoft text-loomera-primaryText",
            },
            "paid": {
                "label": "پرداخت شده",
                "badge_class": "bg-emerald-100 text-emerald-700",
            },
            "completed": {
                "label": "انجام شده",
                "badge_class": "bg-sky-100 text-sky-700",
            },
            "cancelled": {
                "label": "لغو شده",
                "badge_class": "bg-rose-100 text-rose-700",
            },
        }
        return mapping.get(status, mapping["pending"])

    def _serialize_appointment(self, item, salon):
        status_meta = self._status_meta(item.order)

        return {
            "id": item.id,
            "service_name": (
                item.service.service_name if item.service_id else "خدمت ثبت نشده"
            ),
            "stylist_name": (
                item.stylist.get_fullName() if item.stylist_id else "بدون متخصص"
            ),
            "date_label": _safe_jalali_label(
                item.date, formatter=format_jalali_with_weekday
            ),
            "time_label": format_time_fa(item.time) if item.time else "—",
            "price_label": _dashboard_currency(item.price),
            "description": getattr(item.order, "description", "") or "",
            "status_label": status_meta["label"],
            "status_badge_class": status_meta["badge_class"],
            "detail_url": reverse(
                "dashboards:appointment_detail",
                kwargs={"salon_id": salon.id, "appointment_id": item.id},
            ),
        }

    def _serialize_note(self, note):
        created_date = note.created_at.date() if note.created_at else None
        created_time = note.created_at.time() if note.created_at else None
        timestamp = _safe_jalali_label(
            created_date, formatter=format_jalali_with_weekday
        )
        if created_time:
            timestamp = f"{timestamp} • {format_time_fa(created_time)}"

        return {
            "text": note.note,
            "created_label": timestamp,
            "created_by": (
                note.created_by.get_fullName() if note.created_by else "تیم مجموعه"
            ),
        }

    def _serialize_favorite_service(self, item):
        return {
            "title": item.get("service__service_name") or "خدمت بدون نام",
            "count_label": to_persian_digits(item.get("count") or 0),
            "revenue_label": _dashboard_currency(item.get("revenue") or 0),
        }

    def post(self, request, customer_id, *args, **kwargs):
        salon = self._get_salon(request)
        customer = self._get_customer(salon, customer_id)
        note_text = (request.POST.get("note") or "").strip()
        if not note_text:
            messages.error(request, "برای ثبت یادداشت، متن یادداشت را وارد کنید.")
            return redirect("dashboards:customer_detail", customer_id=customer.pk)

        CustomerNote.objects.create(
            salon=salon,
            customer=customer,
            created_by=request.user,
            note=note_text,
        )
        messages.success(request, "یادداشت مشتری با موفقیت ثبت شد.")
        return redirect("dashboards:customer_detail", customer_id=customer.pk)

    def get(self, request, customer_id, *args, **kwargs):
        salon = self._get_salon(request)
        customer = self._get_customer(salon, customer_id)
        today = timezone.localdate()

        appointment_qs = (
            OrderDetail.objects.filter(salon=salon, order__customer=customer)
            .select_related("order", "service", "stylist__user", "salon")
            .order_by("-date", "-time", "-id")
        )
        appointments = list(appointment_qs[:12])

        stats = appointment_qs.aggregate(
            total_spent=Coalesce(
                Sum(
                    "price",
                    filter=Q(order__status__in=["confirmed", "paid", "completed"]),
                ),
                Value(0),
            ),
            appointments_count=Count("id"),
            completed_count=Count("id", filter=Q(order__status="completed")),
            upcoming_count=Count(
                "id",
                filter=Q(date__gte=today) & ~Q(order__status="cancelled"),
            ),
            last_visit=Max("date"),
        )

        favorite_services = list(
            appointment_qs.values("service__service_name")
            .annotate(count=Count("id"), revenue=Coalesce(Sum("price"), Value(0)))
            .order_by("-count", "-revenue")[:4]
        )

        notes = list(
            CustomerNote.objects.filter(salon=salon, customer=customer)
            .select_related("created_by")
            .order_by("-created_at")[:8]
        )

        primary_address = (
            customer.addresses.filter(is_default=True).first()
            or customer.addresses.first()
        )

        total_spent = stats.get("total_spent") or 0
        appointments_count = stats.get("appointments_count") or 0
        completed_count = stats.get("completed_count") or 0
        upcoming_count = stats.get("upcoming_count") or 0
        last_visit = stats.get("last_visit")

        if total_spent > 0 and appointments_count >= 3:
            customer_segment_label = "مشتری ارزشمند"
            customer_segment_badge_class = (
                "bg-loomera-primarySoft text-loomera-primaryText"
            )
        elif last_visit and last_visit >= (today - timedelta(days=30)):
            customer_segment_label = "مشتری فعال"
            customer_segment_badge_class = "bg-emerald-100 text-emerald-700"
        elif appointments_count == 0:
            customer_segment_label = "بدون رزرو"
            customer_segment_badge_class = "bg-slate-100 text-slate-700"
        else:
            customer_segment_label = "نیازمند پیگیری"
            customer_segment_badge_class = "bg-amber-100 text-amber-700"

        quick_actions = []
        if customer.user.mobile_number:
            quick_actions.append(
                {
                    "label": "تماس با مشتری",
                    "url": f"tel:{customer.user.mobile_number}",
                    "tone": "border",
                    "icon": "fa-solid fa-phone",
                }
            )

        focus_items = []
        if appointments_count == 0:
            focus_items.append(
                {
                    "title": "هنوز رزروی برای این مشتری ثبت نشده",
                    "value": "بدون داده",
                    "description": "وقتی اولین رزرو ثبت شود، ارزش مشتری و الگوی مراجعه دقیق‌تر قابل تحلیل خواهد شد.",
                    "tone": "warning",
                }
            )
        if upcoming_count == 0 and appointments_count > 0:
            focus_items.append(
                {
                    "title": "نوبت آینده‌ای ثبت نشده",
                    "value": "قابل پیگیری",
                    "description": "این مشتری در حال حاضر رزرو آینده ندارد و می‌تواند برای بازگشت دوباره پیگیری شود.",
                    "tone": "primary",
                }
            )
        if len(notes) == 0:
            focus_items.append(
                {
                    "title": "یادداشت عملیاتی برای مشتری ثبت نشده",
                    "value": "قابل بهبود",
                    "description": "ثبت نکته‌های ترجیحی، حساسیت‌ها و سابقه تعامل به تیم در مراجعات بعدی کمک می‌کند.",
                    "tone": "neutral",
                }
            )

        if not focus_items:
            focus_items = [
                {
                    "title": "پروفایل مشتری در وضعیت خوبی است",
                    "value": "آماده",
                    "description": "تاریخچه مراجعه، یادداشت‌ها و تصویر کلی مشتری برای تصمیم‌گیری تیم مناسب است.",
                    "tone": "success",
                }
            ]

        context = {
            "salon": salon,
            "customer": customer,
            "customer_primary_address": primary_address,
            "customer_workspace": {
                "segment_label": customer_segment_label,
                "segment_badge_class": customer_segment_badge_class,
                "total_spent_label": _dashboard_currency(total_spent),
                "appointments_count": to_persian_digits(appointments_count),
                "completed_count": to_persian_digits(completed_count),
                "upcoming_count": to_persian_digits(upcoming_count),
                "last_visit_label": _safe_jalali_label(
                    last_visit, formatter=format_jalali_with_weekday
                ),
                "last_visit_short_label": _safe_jalali_label(last_visit),
                "note_count": to_persian_digits(len(notes)),
                "favorite_services": [
                    self._serialize_favorite_service(item) for item in favorite_services
                ],
                "appointments": [
                    self._serialize_appointment(item, salon) for item in appointments
                ],
                "notes": [self._serialize_note(item) for item in notes],
                "quick_actions": quick_actions,
                "focus_items": focus_items,
                "address_title": (
                    primary_address.title if primary_address else "ثبت نشده"
                ),
                "address_label": (
                    primary_address.full_address
                    if primary_address
                    else customer.address or "آدرسی ثبت نشده است."
                ),
            },
        }
        return render(request, self.template_name, context)


# ----------------------------------------------------------------------------------------
QUICK_LINK_AVAILABILITY_HORIZON_DAYS = 45


def _quick_link_stylists_for_service(salon, service):
    return list(
        service.stylists.filter(is_active=True, stylists_of_salon=salon)
        .select_related("user")
        .distinct()
        .order_by("user__name", "user__family")
    )


def _quick_link_availability_days(
    *, salon, service, stylist, horizon_days=QUICK_LINK_AVAILABILITY_HORIZON_DAYS
):
    days = []
    start_date = timezone.localdate()
    for offset in range(max(int(horizon_days or 0), 1)):
        target_date = start_date + timedelta(days=offset)
        slots = get_available_slots_for_service(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=target_date,
        )
        if not slots:
            continue
        days.append(
            {
                "value": target_date.isoformat(),
                "label": format_jalali_with_weekday(target_date),
                "times": [start.strftime("%H:%M") for start, _ in slots],
            }
        )
    return days


class OnlineBookingQuickLinkOptionsView(LoginRequiredMixin, View):
    """Manager-scoped options for dependent quick-link fields.

    The endpoint deliberately reuses the canonical booking availability engine,
    so the dashboard never advertises a date/time that customer booking would
    reject later.
    """

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )
        service_id = (request.GET.get("service_id") or "").strip()
        stylist_id = (request.GET.get("stylist_id") or "").strip()
        if not service_id:
            return JsonResponse({"stylists": [], "availability": []})

        service = salon.services.filter(is_active=True, pk=service_id).first()
        if not service:
            return JsonResponse({"error": "خدمت انتخاب‌شده معتبر نیست."}, status=400)

        stylists = _quick_link_stylists_for_service(salon, service)
        payload = {
            "stylists": [
                {"id": stylist.pk, "name": stylist.get_fullName()}
                for stylist in stylists
            ],
            "availability": [],
        }

        if not stylist_id:
            return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})

        stylist = next((item for item in stylists if str(item.pk) == stylist_id), None)
        if stylist is None:
            return JsonResponse(
                {"error": "این متخصص خدمت انتخاب‌شده را ارائه نمی‌دهد."},
                status=400,
            )

        payload["availability"] = _quick_link_availability_days(
            salon=salon, service=service, stylist=stylist
        )
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})


class OnlineBookingView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    def _build_quick_booking_workspace(
        self,
        request,
        salon,
        *,
        generated_link=None,
        generated_payload=None,
        generator_errors=None,
    ):
        services = list(
            salon.services.filter(
                is_active=True, duration_minutes__gt=0
            ).order_by("service_name")[:50]
        )
        stylists = list(
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .order_by("user__name", "user__family")[:50]
        )
        payload = generated_payload or {}
        payload_services = payload.get("service_ids") or []

        raw_selected_date = (
            request.POST.get("appointment_date")
            or request.GET.get("appointment_date")
            or payload.get("date")
            or timezone.localdate().isoformat()
        )
        selected_date_obj = (
            parse_jalali_input(raw_selected_date, fallback=timezone.localdate())
            or timezone.localdate()
        )
        return {
            "mode_options": [
                {"value": "salon", "label": "صفحه اصلی سالن"},
                {"value": "service", "label": "خدمت"},
                {"value": "stylist", "label": "متخصص"},
                {"value": "service_stylist", "label": "خدمت + متخصص"},
                {
                    "value": "service_stylist_time",
                    "label": "خدمت + متخصص + زمان مشخص",
                },
            ],
            "services": services,
            "stylists": stylists,
            "options_url": reverse("dashboards:online_booking_quick_link_options"),
            "generated_link": generated_link,
            "generated_payload": payload,
            "errors": generator_errors or [],
            "default_date_jalali": format_jalali_numeric(timezone.localdate()),
            "current_mode": (
                request.POST.get("quick_link_mode")
                or request.GET.get("quick_link_mode")
                or payload.get("mode")
                or "service"
            ).strip(),
            "selected_service": str(
                request.POST.get("service_id")
                or (payload_services[0] if payload_services else "")
                or ""
            ).strip(),
            "selected_stylist": str(
                request.POST.get("stylist_id") or payload.get("stylist_user_id") or ""
            ).strip(),
            "selected_date_jalali": format_jalali_numeric(selected_date_obj),
            "selected_date_iso": selected_date_obj.isoformat(),
            "quick_link_title": (request.POST.get("quick_link_title") or "").strip(),
            "is_permanent": request.POST.get("is_permanent") == "on",
            "selected_time": str(
                request.POST.get("appointment_time") or payload.get("time") or ""
            ).strip(),
        }

    def _generate_quick_link(self, request, salon):
        mode = (request.POST.get("quick_link_mode") or "service").strip()
        service_id = (request.POST.get("service_id") or "").strip()
        stylist_id = (request.POST.get("stylist_id") or "").strip()
        raw_appointment_date = (request.POST.get("appointment_date") or "").strip()
        appointment_time = (request.POST.get("appointment_time") or "").strip()

        # Preserve the tested Production defaults/validation for every ordinary
        # quick-link mode. The UX refactor only needs different validation for
        # an explicitly timed link.
        placement = (
            request.POST.get("placement")
            or BookingQuickLink.Placement.DIRECT
        ).strip()
        campaign_name = (request.POST.get("campaign_name") or "").strip()
        internal_note = (request.POST.get("internal_note") or "").strip()

        appointment_date_obj = parse_jalali_input(raw_appointment_date)
        appointment_date = (
            appointment_date_obj.isoformat() if appointment_date_obj else ""
        )
        errors = []

        valid_placements = {
            value
            for value, _label in BookingQuickLink.Placement.choices
        }
        if placement not in valid_placements:
            errors.append(
                "محل استفاده انتخاب‌شده برای لینک معتبر نیست."
            )

        campaign_field = BookingQuickLink._meta.get_field("campaign_name")
        internal_note_field = BookingQuickLink._meta.get_field("internal_note")
        if (
            campaign_field.max_length
            and len(campaign_name) > campaign_field.max_length
        ):
            errors.append("نام کمپین از طول مجاز بیشتر است.")
        if (
            internal_note_field.max_length
            and len(internal_note) > internal_note_field.max_length
        ):
            errors.append("یادداشت داخلی از طول مجاز بیشتر است.")

        payload = {"mode": mode, "salon_id": salon.id}
        service_obj = None
        stylist_obj = None

        if mode in {"service", "service_stylist", "service_stylist_time"}:
            if not service_id:
                errors.append("برای این نوع لینک باید خدمت انتخاب شود.")
            else:
                service_obj = salon.services.filter(
                    is_active=True,
                    pk=service_id,
                ).first()
                if not service_obj:
                    errors.append(
                        "خدمت انتخاب‌شده برای این مجموعه معتبر نیست."
                    )
                else:
                    payload["service_ids"] = [service_obj.pk]

        if mode in {"stylist", "service_stylist", "service_stylist_time"}:
            if not stylist_id:
                errors.append("برای این نوع لینک باید متخصص انتخاب شود.")
            else:
                stylist_obj = (
                    salon.stylists.filter(is_active=True, pk=stylist_id)
                    .select_related("user")
                    .first()
                )
                if not stylist_obj:
                    errors.append(
                        "متخصص انتخاب‌شده برای این مجموعه معتبر نیست."
                    )
                else:
                    payload["stylist_user_id"] = stylist_obj.pk

        pair_is_valid = True
        if (
            service_obj is not None
            and stylist_obj is not None
            and not service_obj.stylists.filter(pk=stylist_obj.pk).exists()
        ):
            pair_is_valid = False
            errors.append("این خدمت توسط متخصص انتخاب‌شده ارائه نمی‌شود.")

        if mode == "service_stylist_time":
            if not appointment_date_obj or not appointment_time:
                errors.append(
                    "برای لینک زمان‌دار، تاریخ و ساعت را مشخص کن."
                )
            elif appointment_date_obj < timezone.localdate():
                errors.append(
                    "برای لینک زمان‌دار باید تاریخ امروز یا آینده را انتخاب کنی."
                )
            elif (
                service_obj is not None
                and stylist_obj is not None
                and pair_is_valid
            ):
                # UX requirement: timed links must be validated against the same
                # engine as customer booking (schedule, leave, collisions and
                # service duration), not merely salon opening hours.
                available_starts = {
                    start_time.strftime("%H:%M")
                    for start_time, _ in get_available_slots_for_service(
                        salon=salon,
                        stylist=stylist_obj,
                        service=service_obj,
                        date_value=appointment_date_obj,
                    )
                }
                if not available_starts:
                    errors.append(
                        "برای این خدمت و متخصص در تاریخ انتخاب‌شده زمان آزادی وجود ندارد."
                    )
                elif appointment_time not in available_starts:
                    errors.append(
                        "این ساعت برای خدمت و متخصص انتخاب‌شده آزاد نیست؛ زمان دیگری را انتخاب کن."
                    )

            payload["date"] = appointment_date
            payload["time"] = appointment_time

        if errors:
            return None, payload, errors

        try:
            payload = normalize_booking_payload(payload)
        except Exception as exc:
            return None, payload, [str(exc)]

        payload["summary"] = {
            "service": (
                "صفحه اصلی سالن"
                if mode == BookingQuickLink.Mode.SALON
                else (
                    service_obj.service_name
                    if service_obj
                    else "—"
                )
            ),
            "stylist": stylist_obj.get_fullName() if stylist_obj else "—",
            "date": (
                format_jalali_numeric(appointment_date_obj)
                if appointment_date_obj
                else "—"
            ),
            "time": appointment_time or "—",
        }

        is_permanent = request.POST.get("is_permanent") == "on"
        default_title = (
            f"صفحه اصلی {salon.salon_name}"
            if mode == BookingQuickLink.Mode.SALON
            else (
                payload["summary"]["service"]
                or "لینک سریع رزرو"
            )
        )
        title = request.POST.get("quick_link_title") or default_title

        try:
            _quick_link, link = create_booking_quick_link(
                request=request,
                creator=request.user,
                salon=salon,
                payload=payload,
                service_obj=service_obj,
                stylist_obj=stylist_obj,
                title=title,
                is_permanent=is_permanent,
                placement=placement,
                campaign_name=campaign_name,
                internal_note=internal_note,
            )
        except ValidationError as exc:
            return (
                None,
                payload,
                list(getattr(exc, "messages", [str(exc)])),
            )

        return link, payload, []

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user", "neighborhood"),
            salon_manager__user=request.user,
        )
        # Beta UX: Online Booking uses the same canonical readiness payload as
        # onboarding and Dashboard Home. Do not create a parallel readiness score.
        readiness = build_salon_readiness_checklist(salon)
        booking_items_before_activation = [
            item
            for item in readiness["booking_items"]
            if item["key"] != "public_active"
        ]
        ready_for_activation = all(
            item["is_done"] for item in booking_items_before_activation
        )
        profile_quality_missing = [
            item for item in readiness["profile_quality_items"] if not item["is_done"]
        ]

        public_booking_url = salon.get_absolute_url()

        if readiness["is_ready"]:
            status = {
                "label": "آماده رزرو",
                "tone": "success",
                "title": "صفحه عمومی آماده دریافت نوبت است",
                "description": "صفحه عمومی آماده دریافت نوبت است؛ لینک‌های رزرو، QR و آمار هر مسیر را از بخش «لینک‌های رزرو» مدیریت کن.",
            }
        elif ready_for_activation and not salon.is_active:
            status = {
                "label": "آماده فعال‌سازی",
                "tone": "primary",
                "title": "همه چیز برای انتشار آماده است",
                "description": "صفحه سالن را فعال کن و یک رزرو آزمایشی انجام بده.",
            }
        else:
            status = {
                "label": "نیازمند تکمیل",
                "tone": "warning",
                "title": "رزرو آنلاین هنوز یک قدم ضروری دارد",
                "description": readiness["summary"],
            }

        context = {
            "salon": salon,
            "online_booking_workspace": {
                "page_title": "صفحه سالن و رزرو آنلاین",
                "readiness": readiness,
                "status": status,
                "ready_for_activation": ready_for_activation,
                "public_booking_url": public_booking_url,
                "public_is_active": bool(salon.is_active),
                "profile_quality_items": readiness["profile_quality_items"],
                "profile_quality_missing_count": to_persian_digits(
                    len(profile_quality_missing)
                ),
            },
        }
        return render(request, "dashboards/online_booking.html", context)

    def post(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user", "neighborhood"),
            salon_manager__user=request.user,
        )
        quick_link_action = request.POST.get("quick_link_action")
        if quick_link_action in {"enable", "disable", "delete"}:
            try:
                message = update_booking_quick_link_status(
                    salon=salon,
                    creator=request.user,
                    link_id=request.POST.get("quick_link_id"),
                    action=quick_link_action,
                )
                messages.success(request, message)
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect("dashboards:quick_links")

        generated_link, generated_payload, generator_errors = self._generate_quick_link(
            request, salon
        )
        request.session["dashboard_quick_booking_result"] = {
            "generated_link": generated_link,
            "generated_payload": generated_payload,
            "errors": generator_errors,
        }
        if generated_link:
            messages.success(request, "لینک سریع رزرو ساخته شد.")
        else:
            messages.error(request, "برای ساخت لینک، موارد مشخص‌شده را اصلاح کن.")
        return redirect("dashboards:quick_links")


# -----------------------------------------------------------------------------------------
@login_required
@manager_required
def salon_profile_creator(request):
    if not hasattr(request.user, "salon_manager_profile"):
        return redirect("dashboards:salon_manager_dashboard")

    required_step = _get_required_onboarding_view_name(request.user)
    if required_step:
        return redirect(required_step)

    return redirect("dashboards:salon_profile")


def _get_or_create_auto_neighborhood(name, *, latitude=None, longitude=None):
    name = (name or "").strip()
    if not name:
        return None

    neighborhood = Neighborhood.objects.filter(name__iexact=name).first()
    if neighborhood:
        return neighborhood

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        lat = 35.699739
        lon = 51.338097

    delta = 0.002
    polygon = Polygon(
        (
            (lon - delta, lat - delta),
            (lon + delta, lat - delta),
            (lon + delta, lat + delta),
            (lon - delta, lat + delta),
            (lon - delta, lat - delta),
        ),
        srid=4326,
    )
    return Neighborhood.objects.create(name=name, polygon=polygon)


def _parse_zone_number(value):
    if value in (None, ""):
        return None
    digits = "".join(
        ch
        for ch in str(value).translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        if ch.isdigit()
    )
    if not digits:
        return None
    try:
        number = int(digits)
    except ValueError:
        return None
    return number if 1 <= number <= 99 else None


# ------------------------------------------------------------------------------------------
# مرحله 1: ساخت اولیه مجموعه (نام و شماره)
class SalonProfileCreatorStep1View(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/salon_profile_creator_step1.html"

    def get(self, request, *args, **kwargs):
        salon = _get_or_create_manager_salon(request.user)
        if salon is None:
            raise Http404("No salon manager profile found.")
        form = SalonProfileStep1Form(instance=salon)
        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        if (
            not profile_edit_mode
            and salon.salon_name == _manager_placeholder_salon_name(request.user)
        ):
            form.initial["salon_name"] = ""
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "form": form,
            "salon": salon,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        salon = _get_or_create_manager_salon(request.user)
        if salon is None:
            raise Http404("No salon manager profile found.")
        form = SalonProfileStep1Form(request.POST, instance=salon)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات پایه مجموعه ذخیره شد.")
            return redirect(
                _get_required_onboarding_view_name(request.user)
                or "dashboards:salon_profile"
            )

        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "form": form,
            "salon": salon,
        }
        messages.error(request, "لطفاً خطاهای فرم را بررسی کنید.")
        return render(request, self.template_name, context)


# ------------------------------------------------------------------------------------------
# مرحله 2: ثبت اطلاعات لوکیشن
class SalonProfileCreatorStep2View(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/salon_profile_creator_step2.html"

    def get(self, request, *args, **kwargs):
        user = request.user
        salon_manager = get_object_or_404(SalonManager, user=user)
        salon = get_object_or_404(Salon, salon_manager=salon_manager)

        initial = {}
        if salon.location:
            try:
                initial["latitude"] = salon.location.y
                initial["longitude"] = salon.location.x
            except Exception:
                pass

        form = SalonProfileStep2Form(instance=salon, initial=initial)
        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "form": form,
            "salon": salon,
            "map_provider_enabled": getattr(settings, "MAP_PROVIDER_ENABLED", False),
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user", "neighborhood"),
            salon_manager__user=request.user,
        )
        form = SalonProfileStep2Form(request.POST, instance=salon)
        if form.is_valid():
            salon = form.save(commit=False)
            latitude = form.cleaned_data.get("latitude")
            longitude = form.cleaned_data.get("longitude")
            if latitude is not None and longitude is not None:
                salon.location = Point(float(longitude), float(latitude))

            zone_number = _parse_zone_number(form.cleaned_data.get("zone"))
            if zone_number is None:
                zone_number = _parse_zone_number(form.cleaned_data.get("zone_label"))
            salon.zone = zone_number

            neighborhood_name = form.cleaned_data.get("neighborhood_name")
            auto_neighborhood = _get_or_create_auto_neighborhood(
                neighborhood_name,
                latitude=latitude,
                longitude=longitude,
            )
            if auto_neighborhood is not None:
                salon.neighborhood = auto_neighborhood

            salon.save()
            messages.success(request, "اطلاعات موقعیت مجموعه ذخیره شد.")
            return redirect(
                _get_required_onboarding_view_name(request.user)
                or "dashboards:salon_profile"
            )

        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "form": form,
            "salon": salon,
            "map_provider_enabled": getattr(settings, "MAP_PROVIDER_ENABLED", False),
        }
        messages.error(request, "لطفاً خطاهای فرم لوکیشن را بررسی کنید.")
        return render(request, self.template_name, context)


# ------------------------------------------------------------------------------------------
class SalonProfileCreatorStep3View(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    form_class = SalonOpeningHoursForm
    template_name = "dashboards/salon_profile_creator_step3.html"

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        opening_hours = SalonOpeningHours.objects.filter(salon=salon)
        initial_data = {}
        for oh in opening_hours:
            day_num = oh.day_of_week
            initial_data[f"day_{day_num}_active"] = not oh.is_closed
            if not oh.is_closed:
                initial_data[f"day_{day_num}_open_time"] = oh.open_time
                initial_data[f"day_{day_num}_close_time"] = oh.close_time

        form = self.form_class(initial=initial_data)

        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "form": form,
            "salon": salon,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )
        form = self.form_class(request.POST)
        if form.is_valid():
            with transaction.atomic():
                for day_num, _day_name in form.days:
                    is_active = form.cleaned_data.get(f"day_{day_num}_active")
                    open_time = form.cleaned_data.get(f"day_{day_num}_open_time")
                    close_time = form.cleaned_data.get(f"day_{day_num}_close_time")
                    SalonOpeningHours.objects.update_or_create(
                        salon=salon,
                        day_of_week=day_num,
                        defaults={
                            "is_closed": not bool(is_active),
                            "open_time": open_time if is_active else None,
                            "close_time": close_time if is_active else None,
                        },
                    )
            if _is_manager_profile_edit_mode(request.user):
                messages.success(request, "ساعات کاری مجموعه ذخیره شد.")
                return redirect("dashboards:salon_profile")

            messages.success(
                request,
                "اطلاعات اولیه مجموعه آماده شد. حالا می‌توانی از داشبورد ادامه بدهی.",
            )
            return redirect("dashboards:salon_manager_dashboard")

        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "form": form,
            "salon": salon,
        }
        messages.error(request, "لطفاً خطاهای ساعت کاری را بررسی کنید.")
        return render(request, self.template_name, context)


# ------------------------------------------------------------------------------------------
@login_required
@manager_required
def salon_profile_creator_step4(request):
    return redirect("dashboards:salon_profile_creator_step6")


# ------------------------------------------------------------------------------------------
@login_required
@manager_required
def salon_profile_creator_step5(request):
    return redirect("dashboards:salon_profile_creator_step6")


# -------------------------------------------------------------------------------------------
MAX_SALON_GALLERY_IMAGES = 3


class SalonProfileCreatorStep6View(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    form_class = SalonsGalleryForm
    template_name = "dashboards/salon_profile_creator_step6.html"

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        cover_id = request.GET.get("set_cover")
        if cover_id:
            return self.handle_set_cover(request, salon, cover_id)

        gallery_images = SalonsGallery.objects.filter(salon=salon).order_by(
            "-is_cover", "order"
        )
        form = self.form_class()

        gallery_count = gallery_images.count()
        gallery_limit_reached = gallery_count >= MAX_SALON_GALLERY_IMAGES

        profile_edit_mode = _is_manager_profile_edit_mode(request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "salon": salon,
            "gallery_images": gallery_images,
            "form": form,
            "gallery_count": gallery_count,
            "gallery_limit_reached": gallery_limit_reached,
            "max_gallery_images": MAX_SALON_GALLERY_IMAGES,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        gallery_count = SalonsGallery.objects.filter(salon=salon).count()
        if gallery_count >= MAX_SALON_GALLERY_IMAGES:
            messages.warning(
                request,
                f"حداکثر {to_persian_digits(MAX_SALON_GALLERY_IMAGES)} تصویر برای گالری مجموعه مجاز است.",
            )
            return redirect("dashboards:salon_profile_creator_step6")

        form = self.form_class(request.POST, request.FILES)
        if not form.is_valid():
            gallery_images = SalonsGallery.objects.filter(salon=salon).order_by(
                "-is_cover", "order"
            )
            profile_edit_mode = _is_manager_profile_edit_mode(request.user)
            context = {
                "hide_dashboardNavbar": not profile_edit_mode,
                "profile_edit_mode": profile_edit_mode,
                "salon_profile_url": reverse("dashboards:salon_profile"),
                "salon": salon,
                "gallery_images": gallery_images,
                "form": form,
                "gallery_count": gallery_count,
                "gallery_limit_reached": gallery_count >= MAX_SALON_GALLERY_IMAGES,
                "max_gallery_images": MAX_SALON_GALLERY_IMAGES,
            }
            messages.error(request, "لطفاً تصویر معتبر برای گالری مجموعه انتخاب کنید.")
            return render(request, self.template_name, context)

        image = form.save(commit=False)
        image.salon = salon
        image.order = (
            SalonsGallery.objects.filter(salon=salon)
            .aggregate(max_order=Max("order"))
            .get("max_order")
            or 0
        ) + 1
        image.is_cover = not SalonsGallery.objects.filter(
            salon=salon, is_cover=True
        ).exists()
        image.save()

        if image.is_cover:
            salon.banner_image = image.salon_image
            salon.save(update_fields=["banner_image"])

        messages.success(request, "تصویر مجموعه با موفقیت اضافه شد.")
        return redirect("dashboards:salon_profile_creator_step6")

    @transaction.atomic
    def handle_set_cover(self, request, salon, cover_id):
        image = get_object_or_404(SalonsGallery, id=cover_id, salon=salon)

        SalonsGallery.objects.filter(salon=salon, is_cover=True).exclude(
            id=image.id
        ).update(is_cover=False)

        if not image.is_cover:
            image.is_cover = True
            image.save(update_fields=["is_cover"])

        if salon.banner_image != image.salon_image:
            salon.banner_image = image.salon_image
            salon.save(update_fields=["banner_image"])

        messages.success(request, "تصویر کاور مجموعه با موفقیت تغییر کرد.")
        return redirect("dashboards:salon_profile_creator_step6")


@manager_required
@transaction.atomic
def delete_salon_image(request, image_id):
    if request.method == "POST":
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )
        image = get_object_or_404(SalonsGallery, id=image_id, salon=salon)

        was_cover = image.is_cover
        image.delete()

        if was_cover:
            first_image = (
                SalonsGallery.objects.filter(salon=salon).order_by("order").first()
            )
            if first_image:
                first_image.is_cover = True
                first_image.save(update_fields=["is_cover"])
                salon.banner_image = first_image.salon_image
            else:
                salon.banner_image = None

            salon.save(update_fields=["banner_image"])

        messages.success(request, "تصویر با موفقیت حذف شد.")
    return redirect("dashboards:salon_profile_creator_step6")


# -------------------------------------------------------------------------------------------
class SalonProfileCreatorStep7View(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/salon_profile_creator_step7.html"

    categories = {
        "highlights": [
            {
                "title": "مناسب حیوانات خانگی",
                "icon_class": "fas fa-paw",
                "description": "مجموعه ما از حیوانات خانگی استقبال می‌کند و محیطی دوستانه برای آنها فراهم می‌کند",
            },
            {
                "title": "فقط بزرگسالان",
                "icon_class": "fas fa-users",
                "description": "این مکان مخصوص افراد بالای ۱۸ سال است",
            },
            {
                "title": "مناسب کودکان",
                "icon_class": "fas fa-child",
                "description": "محیطی امن و مناسب برای خدمات‌رسانی به کودکان",
            },
            {
                "title": "دسترسی با ویلچر",
                "icon_class": "fas fa-wheelchair",
                "description": "مجهز به امکانات دسترسی برای افراد دارای معلولیت جسمی",
            },
        ],
        "values": [
            {
                "title": "فقط محصولات ارگانیک",
                "icon_class": "fas fa-leaf",
                "description": "استفاده از محصولات کاملاً طبیعی و ارگانیک",
            },
            {
                "title": "فقط محصولات گیاهی",
                "icon_class": "fas fa-seedling",
                "description": "استفاده انحصاری از محصولات با منشأ گیاهی",
            },
            {
                "title": "دوستدار محیط زیست",
                "icon_class": "fas fa-recycle",
                "description": "متعهد به حفظ محیط زیست و استفاده از محصولات سازگار با طبیعت",
            },
        ],
        "amenities": [
            {
                "title": "پارکینگ",
                "icon_class": "fas fa-car",
                "description": "دارای پارکینگ اختصاصی برای مراجعه‌کنندگان",
            },
            {
                "title": "نزدیک به حمل و نقل عمومی",
                "icon_class": "fas fa-bus",
                "description": "دسترسی آسان به وسایل حمل و نقل عمومی",
            },
            {
                "title": "دوش",
                "icon_class": "fas fa-shower",
                "description": "مجهز به امکانات دوش",
            },
            {
                "title": "کمد قفل‌دار",
                "icon_class": "fas fa-lock",
                "description": "دارای کمدهای امن برای نگهداری وسایل شخصی",
            },
            {
                "title": "حوله حمام",
                "icon_class": "fas fa-bath",
                "description": "ارائه حوله تمیز به مراجعه‌کنندگان",
            },
            {
                "title": "استخر شنا",
                "icon_class": "fas fa-swimming-pool",
                "description": "دارای استخر شنا مجهز",
            },
            {
                "title": "سونا",
                "icon_class": "fas fa-hot-tub",
                "description": "مجهز به سونای خشک و بخار",
            },
        ],
    }

    category_labels = {
        "highlights": "نکات برجسته",
        "values": "ارزش‌ها و هویت برند",
        "amenities": "امکانات و تسهیلات",
    }

    custom_icon_choices = [
        {"label": "درخشش", "icon_class": "fa-solid fa-sparkles"},
        {"label": "ستاره", "icon_class": "fa-solid fa-star"},
        {"label": "قلب", "icon_class": "fa-solid fa-heart"},
        {"label": "تاج", "icon_class": "fa-solid fa-crown"},
        {"label": "الماس", "icon_class": "fa-solid fa-gem"},
        {"label": "برگ", "icon_class": "fa-solid fa-leaf"},
        {"label": "آتش", "icon_class": "fa-solid fa-fire"},
        {"label": "چک", "icon_class": "fa-solid fa-circle-check"},
    ]

    default_custom_icon_class = "fa-solid fa-sparkles"

    def get_salon(self):
        if not hasattr(self.request, "_cached_salon"):
            self.request._cached_salon = get_object_or_404(
                Salon.objects.select_related("salon_manager__user"),
                salon_manager__user=self.request.user,
            )
        return self.request._cached_salon

    def _normalize_custom_title(self, raw_value):
        title = " ".join((raw_value or "").split()).strip()
        title = title.replace("|", "").replace("::", "")
        return title[:50]

    def _normalize_custom_description(self, raw_value):
        description = " ".join((raw_value or "").split()).strip()
        description = description.replace("|", "").replace("::", "")
        return description[:180]

    def _is_allowed_custom_icon(self, icon_class):
        return icon_class in {item["icon_class"] for item in self.custom_icon_choices}

    def _builtin_title_map(self):
        builtins = {}
        for _, items in self.categories.items():
            for item in items:
                builtins[item["title"]] = item
        return builtins

    def _build_category_sections(self):
        sections = []
        for key, items in self.categories.items():
            sections.append(
                {
                    "key": key,
                    "label": self.category_labels.get(key, key),
                    "items": [
                        {
                            **item,
                            "value": f"builtin::{item['title']}|{item['icon_class']}",
                        }
                        for item in items
                    ],
                }
            )
        return sections

    def _serialize_custom_item(
        self, title, icon_class=None, description="ویژگی سفارشی اضافه‌شده توسط شما"
    ):
        normalized_title = self._normalize_custom_title(title)
        normalized_description = self._normalize_custom_description(description)
        icon_class = (
            icon_class
            if self._is_allowed_custom_icon(icon_class)
            else self.default_custom_icon_class
        )
        return {
            "title": normalized_title,
            "description": normalized_description,
            "icon_class": icon_class,
            "value": f"custom::{normalized_title}|{icon_class}|{normalized_description}",
        }

    def _get_existing_state(self, salon):
        builtin_map = self._builtin_title_map()
        selected_item_values = set()
        custom_items = []

        existing_info = SupplementaryInfoView.objects.filter(
            salon=salon, is_active=True
        ).order_by("id")

        for info in existing_info:
            if info.title in builtin_map:
                builtin_item = builtin_map[info.title]
                selected_item_values.add(
                    f"builtin::{builtin_item['title']}|{builtin_item['icon_class']}"
                )
            else:
                custom_item = self._serialize_custom_item(
                    info.title,
                    info.icon_class or self.default_custom_icon_class,
                    info.description or "ویژگی سفارشی اضافه‌شده توسط شما",
                )
                custom_items.append(custom_item)
                selected_item_values.add(custom_item["value"])

        return selected_item_values, custom_items

    def _build_context(self, salon, selected_item_values=None, custom_items=None):
        if selected_item_values is None or custom_items is None:
            selected_item_values, custom_items = self._get_existing_state(salon)

        profile_edit_mode = _is_manager_profile_edit_mode(self.request.user)
        return {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "salon": salon,
            "category_sections": self._build_category_sections(),
            "custom_icon_choices": self.custom_icon_choices,
            "default_custom_icon_class": self.default_custom_icon_class,
            "custom_items": custom_items,
            "selected_item_values": selected_item_values,
            "selected_count": len(selected_item_values),
        }

    def get(self, request, *args, **kwargs):
        salon = self.get_salon()
        context = self._build_context(salon)
        return render(request, self.template_name, context)

    def _parse_feature_value(self, raw_value):
        raw_value = (raw_value or "").strip()
        if not raw_value or "::" not in raw_value:
            return None

        item_type, payload = raw_value.split("::", 1)
        parts = payload.split("|", 2)
        title = parts[0] if len(parts) > 0 else ""
        icon_class = parts[1] if len(parts) > 1 else ""
        description = parts[2] if len(parts) > 2 else ""

        title = self._normalize_custom_title(title)
        icon_class = (icon_class or "").strip() or self.default_custom_icon_class
        description = self._normalize_custom_description(description)

        if not title:
            return None

        builtin_map = self._builtin_title_map()

        if item_type == "builtin":
            builtin = builtin_map.get(title)
            if not builtin:
                return None

            return {
                "title": builtin["title"],
                "description": builtin["description"],
                "icon_class": builtin["icon_class"],
            }

        if item_type == "custom":
            if not self._is_allowed_custom_icon(icon_class):
                icon_class = self.default_custom_icon_class

            if not description:
                return None

            return {
                "title": title,
                "description": description,
                "icon_class": icon_class,
            }

        return None

    def post(self, request, *args, **kwargs):
        salon = self.get_salon()
        selected_values = request.POST.getlist("selected_items")
        submit_action = request.POST.get("submit_action") or "continue"

        parsed_items = []
        seen_titles = set()

        for raw_value in selected_values:
            item = self._parse_feature_value(raw_value)
            if not item:
                continue

            title_key = item["title"].strip()
            if title_key in seen_titles:
                continue

            seen_titles.add(title_key)
            parsed_items.append(item)

        with transaction.atomic():
            SupplementaryInfoView.objects.filter(salon=salon).update(is_active=False)

            for item in parsed_items:
                info, _created = SupplementaryInfoView.objects.update_or_create(
                    salon=salon,
                    title=item["title"],
                    defaults={
                        "description": item["description"],
                        "icon_class": item["icon_class"],
                        "is_active": True,
                    },
                )

        if parsed_items:
            messages.success(request, "ویژگی‌ها و امکانات مجموعه ذخیره شد.")
        else:
            messages.warning(
                request,
                "هیچ ویژگی‌ای انتخاب نشد. می‌توانی هر زمان از پروفایل مجموعه آن‌ها را اضافه کنی.",
            )

        if _is_manager_profile_edit_mode(request.user):
            return redirect("dashboards:salon_profile")

        if submit_action == "save":
            selected_item_values, custom_items = self._get_existing_state(salon)
            context = self._build_context(
                salon,
                selected_item_values=selected_item_values,
                custom_items=custom_items,
            )
            return render(request, self.template_name, context)

        return redirect("dashboards:salon_profile_creator_step8")


# --------------------------------------------------------------------------------------------
class SalonProfileCreatorStep8View(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    form_class = SalonDescriptionForm
    template_name = "dashboards/salon_profile_creator_step8.html"

    def get_salon(self):
        if not hasattr(self.request, "_cached_salon"):
            self.request._cached_salon = get_object_or_404(
                Salon.objects.select_related("salon_manager__user"),
                salon_manager__user=self.request.user,
            )
        return self.request._cached_salon

    def get_context_data(self, **kwargs):
        profile_edit_mode = _is_manager_profile_edit_mode(self.request.user)
        context = {
            "hide_dashboardNavbar": not profile_edit_mode,
            "profile_edit_mode": profile_edit_mode,
            "salon_profile_url": reverse("dashboards:salon_profile"),
            "salon": self.get_salon(),
        }
        context.update(kwargs)
        return context

    def get(self, request, *args, **kwargs):
        salon = self.get_salon()
        form = self.form_class(instance=salon)
        context = self.get_context_data(form=form)
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        salon = self.get_salon()
        form = self.form_class(request.POST, instance=salon)
        if form.is_valid():
            form.save()
            messages.success(request, "توضیحات مجموعه ذخیره شد.")
            if _is_manager_profile_edit_mode(request.user):
                return redirect("dashboards:salon_profile")

            return redirect("dashboards:salon_manager_dashboard")

        context = self.get_context_data(form=form)
        messages.error(request, "لطفاً توضیحات مجموعه را تکمیل کنید.")
        return render(request, self.template_name, context)


# --------------------------------------------------------------------------------------------
@login_required
@manager_required
def salon_profile_creator_step9(request):
    return redirect("dashboards:salon_profile_creator_step10")


# ---------------------------------------------------------------------------------------------
class SalonProfileCreatorStep10View(
    SalonManagerOnboardingGuardMixin,
    LoginRequiredMixin,
    View,
):
    """Compatibility endpoint for the legacy public-activation step."""

    def get(self, request, *args, **kwargs):
        return redirect(
            f'{reverse("dashboards:salon_profile")}?tab=public'
        )

    def post(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related(
                "salon_manager__user",
                "neighborhood",
            ),
            salon_manager__user=request.user,
        )

        target = _activate_salon_public_page(
            request,
            salon,
        )

        if target:
            return redirect(target)

        return redirect(
            f'{reverse("dashboards:salon_profile")}?tab=public'
        )


# ---------------------------------------------------------------------------------------------
@login_required
@manager_required
@login_required
@manager_required
def salon_profile_creator_finalStep(request):
    """Compatibility route for legacy onboarding links."""
    return redirect(
        f'{reverse("dashboards:salon_profile")}?tab=public'
    )


# ----------------------------------------------------------------------------------------------
class SalonProfileView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):

    def post(self, request):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user", "neighborhood"),
            salon_manager__user=request.user,
        )
        action = (request.POST.get("action") or "").strip()
        if action == "activate_public_page":
            target = _activate_salon_public_page(request, salon)
            if target:
                return redirect(target)
            return redirect(f'{reverse("dashboards:salon_profile")}?tab=public')

        messages.error(request, "عملیات پروفایل مجموعه نامعتبر است.")
        return redirect("dashboards:salon_profile")

    def get(self, request):
        salon_with_stats = get_object_or_404(
            Salon.objects.select_related(
                "salon_manager__user", "neighborhood"
            ).annotate(
                avg_score=Avg(
                    "comments_salon__scoring__score",
                    filter=Q(comments_salon__is_active=True),
                ),
                reviews_count=Count(
                    "comments_salon",
                    filter=Q(comments_salon__is_active=True),
                ),
            ),
            salon_manager__user=request.user,
        )

        open_days_count = SalonOpeningHours.objects.filter(
            salon=salon_with_stats,
            is_closed=False,
        ).count()
        gallery_count = salon_with_stats.gallery_images.count()
        features_count = salon_with_stats.supplementary_info.filter(
            is_active=True
        ).count()
        description_length = len((salon_with_stats.description or "").strip())

        avg_score_value = float(salon_with_stats.avg_score or 0)
        avg_score_label = (
            to_persian_digits(f"{avg_score_value:.1f}") if avg_score_value else "—"
        )
        reviews_count_label = to_persian_digits(salon_with_stats.reviews_count or 0)

        profile_items = [
            {
                "key": "identity",
                "title": "نام و شماره تماس",
                "description": "نام مجموعه و شماره‌ای که مشتری برای تماس می‌بیند.",
                "meta": salon_with_stats.phone_number or "شماره تماس ثبت نشده",
                "is_ready": bool(
                    (salon_with_stats.salon_name or "").strip()
                    and (salon_with_stats.phone_number or "").strip()
                ),
                "url": reverse("dashboards:salon_profile_creator_step1"),
                "cta_label": "ویرایش اطلاعات",
                "icon": "fa-solid fa-store",
            },
            {
                "key": "location",
                "title": "آدرس و موقعیت",
                "description": "نشانی و نقطه روی نقشه برای مسیریابی دقیق مشتری.",
                "meta": (
                    salon_with_stats.neighborhood.name
                    if salon_with_stats.neighborhood_id
                    else (f"منطقه {to_persian_digits(salon_with_stats.zone)}" if salon_with_stats.zone else "موقعیت کامل نشده")
                ),
                "is_ready": bool(
                    (salon_with_stats.address or "").strip()
                    and salon_with_stats.location
                ),
                "url": reverse("dashboards:salon_profile_creator_step2"),
                "cta_label": "ویرایش موقعیت",
                "icon": "fa-solid fa-location-dot",
            },
            {
                "key": "hours",
                "title": "ساعات کاری",
                "description": "روزها و ساعت‌هایی که مجموعه برای مشتری باز است.",
                "meta": (
                    f"{to_persian_digits(open_days_count)} روز کاری"
                    if open_days_count
                    else "ساعت کاری ثبت نشده"
                ),
                "is_ready": open_days_count > 0,
                "url": reverse("dashboards:salon_profile_creator_step3"),
                "cta_label": "ویرایش ساعات کاری",
                "icon": "fa-regular fa-clock",
            },
            {
                "key": "gallery",
                "title": "تصاویر مجموعه",
                "description": "تصاویر واقعی فضا و نمونه‌کارهایی که در صفحه عمومی دیده می‌شوند.",
                "meta": f"{to_persian_digits(gallery_count)} تصویر",
                "is_ready": gallery_count > 0,
                "url": reverse("dashboards:salon_profile_creator_step6"),
                "cta_label": "مدیریت تصاویر",
                "icon": "fa-regular fa-images",
            },
            {
                "key": "features",
                "title": "ویژگی‌ها و امکانات",
                "description": "مزیت‌ها و امکاناتی که به تصمیم مشتری کمک می‌کنند.",
                "meta": f"{to_persian_digits(features_count)} ویژگی",
                "is_ready": features_count > 0,
                "url": reverse("dashboards:salon_profile_creator_step7"),
                "cta_label": "ویرایش ویژگی‌ها",
                "icon": "fa-solid fa-sparkles",
            },
            {
                "key": "description",
                "title": "معرفی مجموعه",
                "description": "متن کوتاهی که سبک، تجربه و فضای مجموعه را معرفی می‌کند.",
                "meta": f"{to_persian_digits(description_length)} از ۶۰۰ کاراکتر",
                "is_ready": description_length >= 200,
                "url": reverse("dashboards:salon_profile_creator_step8"),
                "cta_label": "ویرایش معرفی",
                "icon": "fa-regular fa-file-lines",
            },
        ]

        ready_count = sum(1 for item in profile_items if item["is_ready"])
        total_count = len(profile_items)
        profile_progress = int((ready_count / total_count) * 100) if total_count else 0
        incomplete_items = [item for item in profile_items if not item["is_ready"]]
        next_incomplete_item = incomplete_items[0] if incomplete_items else None

        if profile_progress == 100:
            profile_quality_label = "پروفایل کامل"
        elif profile_progress >= 67:
            profile_quality_label = "تقریباً کامل"
        else:
            profile_quality_label = "نیازمند تکمیل"

        booking_readiness = build_salon_readiness_checklist(salon_with_stats)
        activation_items = [
            item for item in booking_readiness["booking_items"]
            if item["key"] != "public_active"
        ]
        activation_prerequisites_met = all(item["is_done"] for item in activation_items)
        next_activation_item = next(
            (item for item in activation_items if not item["is_done"]),
            None,
        )

        context = {
            "salon": salon_with_stats,
            "profile_items": profile_items,
            "incomplete_profile_items": incomplete_items,
            "next_incomplete_item": next_incomplete_item,
            "salon_profile_workspace": {
                "page_title": salon_with_stats.salon_name,
                "customer_preview_url": salon_with_stats.get_absolute_url(),
                "online_booking_url": reverse("dashboards:online_booking"),
                "ready_count": to_persian_digits(ready_count),
                "total_checks": to_persian_digits(total_count),
                "profile_progress": profile_progress,
                "profile_progress_label": to_persian_digits(profile_progress),
                "profile_quality_label": profile_quality_label,
                "avg_score_label": avg_score_label,
                "reviews_count_label": reviews_count_label,
                "phone_label": salon_with_stats.phone_number or "—",
                "neighborhood_label": (
                    salon_with_stats.neighborhood.name
                    if salon_with_stats.neighborhood_id
                    else "—"
                ),
                "address_label": salon_with_stats.address or "—",
                "booking_readiness": booking_readiness,
                "activation_prerequisites_met": activation_prerequisites_met,
                "next_activation_item": next_activation_item,
            },
        }
        return render(request, "dashboards/salon_profile_view.html", context)


def _get_manager_dashboard_salon(user):
    if not hasattr(user, "salon_manager_profile"):
        return None
    return (
        Salon.objects.select_related("salon_manager__user", "neighborhood")
        .prefetch_related("services__service_group", "stylists__user")
        .filter(salon_manager__user=user)
        .first()
    )


def _build_partner_workspace_snapshot(salon):
    today = timezone.localdate()
    default = {
        "services_count": 0,
        "active_services_count": 0,
        "inactive_services_count": 0,
        "service_groups_count": 0,
        "team_count": 0,
        "active_team_count": 0,
        "opening_days_count": 0,
        "gallery_count": 0,
        "supplementary_count": 0,
        "total_bookings_count": 0,
        "upcoming_bookings_count": 0,
        "recent_bookings_count": 0,
        "completed_bookings_count": 0,
        "cancelled_bookings_count": 0,
        "services_with_team_count": 0,
        "avg_service_duration": 0,
        "top_groups": [],
        "top_services": [],
    }
    if salon is None:
        return default

    services_qs = salon.services.all().prefetch_related("service_group")
    services = list(services_qs)
    active_team_qs = salon.stylists.filter(is_active=True)

    group_map = {}
    for service in services:
        for group in service.service_group.all():
            payload = group_map.setdefault(
                group.id,
                {
                    "label": group.group_title,
                    "services_count": 0,
                    "active_count": 0,
                },
            )
            payload["services_count"] += 1
            if service.is_active:
                payload["active_count"] += 1

    top_groups = sorted(
        group_map.values(),
        key=lambda item: (-item["services_count"], item["label"]),
    )[:3]

    recent_service_signals = list(
        OrderDetail.objects.filter(
            salon=salon,
            date__gte=today - timedelta(days=60),
        )
        .values("service__service_name")
        .annotate(bookings=Count("id"), revenue=Coalesce(Sum("price"), 0))
        .order_by("-bookings", "service__service_name")[:4]
    )

    services_with_team_count = (
        services_qs.filter(
            stylists__stylists_of_salon=salon,
            stylists__is_active=True,
        )
        .distinct()
        .count()
    )

    avg_service_duration = (
        services_qs.aggregate(avg=Avg("duration_minutes")).get("avg") or 0
    )

    return {
        "services_count": len(services),
        "active_services_count": sum(1 for service in services if service.is_active),
        "inactive_services_count": sum(
            1 for service in services if not service.is_active
        ),
        "service_groups_count": len(group_map),
        "team_count": salon.stylists.count(),
        "active_team_count": active_team_qs.count(),
        "opening_days_count": SalonOpeningHours.objects.filter(
            salon=salon,
            is_closed=False,
        ).count(),
        "gallery_count": salon.gallery_images.count(),
        "supplementary_count": salon.supplementary_info.filter(is_active=True).count(),
        "total_bookings_count": OrderDetail.objects.filter(salon=salon).count(),
        "upcoming_bookings_count": OrderDetail.objects.filter(
            salon=salon,
            date__gte=today,
        ).count(),
        "recent_bookings_count": OrderDetail.objects.filter(
            salon=salon,
            date__gte=today - timedelta(days=30),
        ).count(),
        "completed_bookings_count": OrderDetail.objects.filter(
            salon=salon,
            order__status="completed",
        ).count(),
        "cancelled_bookings_count": OrderDetail.objects.filter(
            salon=salon,
            order__status="cancelled",
        ).count(),
        "services_with_team_count": services_with_team_count,
        "avg_service_duration": int(avg_service_duration or 0),
        "top_groups": top_groups,
        "top_services": [
            {
                "label": item["service__service_name"],
                "bookings_count": item["bookings"],
                "bookings_label": to_persian_digits(item["bookings"]),
                "revenue_label": _dashboard_currency(item["revenue"]),
            }
            for item in recent_service_signals
        ],
    }


# --------------------------------------------------------------------------------------------
class CatalogView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    def get(self, request):
        salon = _get_manager_dashboard_salon(request.user)
        snapshot = _build_partner_workspace_snapshot(salon)

        services_ready = snapshot["active_services_count"] > 0
        team_coverage_ready = (
            snapshot["services_with_team_count"] >= snapshot["active_services_count"]
            if snapshot["active_services_count"]
            else False
        )
        online_ready = (
            snapshot["active_services_count"] > 0
            and snapshot["active_team_count"] > 0
            and snapshot["opening_days_count"] > 0
        )

        sections = [
            {
                "title": "منوی خدمات",
                "description": "خدمات، قیمت، مدت‌زمان و دسته‌بندی‌ها را در یک workspace اصلی و آماده رزرو نگه می‌دارد.",
                "icon": "fa-solid fa-scissors",
                "url": reverse("dashboards:service_menu"),
                "badge": f'{to_persian_digits(snapshot["services_count"])} خدمت',
                "status_label": "آماده" if services_ready else "نیازمند تکمیل",
                "status_tone": "success" if services_ready else "warning",
            },
            {
                "title": "اعضای تیم و پوشش خدمت",
                "description": "برای اینکه کاتالوگ در رزرو آنلاین usable باشد، هر خدمت باید به تیم فعال و ظرفیت واقعی وصل شود.",
                "icon": "fa-solid fa-user-group",
                "url": reverse("dashboards:team_member"),
                "badge": f'{to_persian_digits(snapshot["services_with_team_count"])} خدمت پوشش‌دار',
                "status_label": "پوشش خوب" if team_coverage_ready else "قابل بهبود",
                "status_tone": "success" if team_coverage_ready else "warning",
            },
            {
                "title": "محصولات و موجودی",
                "description": "برای retail و stock discipline در کنار خدمات؛ حتی قبل از inventory engine کامل، مسیر و وضعیت operational را روشن می‌کند.",
                "icon": "fa-solid fa-box-open",
                "url": reverse("dashboards:products"),
                "badge": "Inventory layer",
                "status_label": "در حال آماده‌سازی",
                "status_tone": "primary",
            },
            {
                "title": "رزرو آنلاین",
                "description": "ارتباط مستقیم کاتالوگ با discoverability عمومی، readiness صفحه مجموعه و امکان رزرو مشتری.",
                "icon": "fa-solid fa-globe",
                "url": reverse("dashboards:online_booking"),
                "badge": f'{to_persian_digits(snapshot["opening_days_count"])} روز کاری',
                "status_label": "آماده" if online_ready else "نیازمند تکمیل",
                "status_tone": "success" if online_ready else "warning",
            },
        ]

        context = {
            "salon": salon,
            "catalog_workspace": {
                "hero_badges": [
                    {
                        "icon": "fa-solid fa-scissors",
                        "label": f'{to_persian_digits(snapshot["services_count"])} خدمت',
                    },
                    {
                        "icon": "fa-solid fa-layer-group",
                        "label": f'{to_persian_digits(snapshot["service_groups_count"])} گروه',
                    },
                    {
                        "icon": "fa-solid fa-user-group",
                        "label": f'{to_persian_digits(snapshot["active_team_count"])} عضو فعال',
                    },
                    {
                        "icon": "fa-regular fa-calendar-check",
                        "label": f'{to_persian_digits(snapshot["opening_days_count"])} روز کاری',
                    },
                ],
                "stats": [
                    {
                        "title": "خدمات فعال",
                        "value": to_persian_digits(snapshot["active_services_count"]),
                        "meta": "خدماتی که می‌توانند در رزرو و صفحه عمومی دیده شوند.",
                        "icon": "fa-solid fa-scissors",
                        "tone": "primary",
                    },
                    {
                        "title": "گروه‌های خدمت",
                        "value": to_persian_digits(snapshot["service_groups_count"]),
                        "meta": "برای ساخت catalog تمیز و قابل جست‌وجو در dashboard.",
                        "icon": "fa-solid fa-layer-group",
                        "tone": "neutral",
                    },
                    {
                        "title": "پوشش تیم",
                        "value": f'{to_persian_digits(snapshot["services_with_team_count"])} / {to_persian_digits(snapshot["active_services_count"])}',
                        "meta": "چند خدمت فعال واقعاً به تیم و ظرفیت رزرو متصل شده‌اند.",
                        "icon": "fa-solid fa-user-check",
                        "tone": "success",
                    },
                    {
                        "title": "رزروهای ۳۰ روز اخیر",
                        "value": to_persian_digits(snapshot["recent_bookings_count"]),
                        "meta": "برای فهم demand فعلی خدمات و اولویت کاتالوگ.",
                        "icon": "fa-regular fa-calendar-check",
                        "tone": "primary",
                    },
                ],
                "sections": sections,
                "lanes": [
                    {
                        "title": "هستهٔ کاتالوگ",
                        "items": [
                            "ساختار گروه‌بندی خدمات و قیمت‌ها",
                            "پوشش اعضای تیم برای هر خدمت",
                            "آمادگی نمایش در رزرو آنلاین",
                        ],
                    },
                    {
                        "title": "گسترش retail و inventory",
                        "items": [
                            "تعریف محصولات و state آن‌ها",
                            "آماده‌سازی موجودی‌گیری و stock discipline",
                            "هم‌راستاسازی با فروش درون‌مجموعه و مکمل خدمات",
                        ],
                    },
                ],
                "top_groups": [
                    {
                        "label": item["label"],
                        "meta": f'{to_persian_digits(item["services_count"])} خدمت • {to_persian_digits(item["active_count"])} فعال',
                    }
                    for item in snapshot["top_groups"]
                ],
                "top_services": snapshot["top_services"],
            },
        }
        return render(request, "dashboards/catalog.html", context)


# ----------------------------------------------------------------------------------------------
from django.db.models import (
    Exists,
    Min,
    Max,
    OuterRef,
    Prefetch,
    Subquery,
)
from collections import defaultdict


# =================================================================
# VIEW اصلی منوی خدمات (کاملاً بازنویسی شده)
# =================================================================
def _build_created_service_setup_handoff(*, request, salon):
    """Build a scoped next-step card after a salon service is created.

    The service id comes from the query string and is therefore untrusted.
    Only a service belonging to the active manager's salon may be returned.
    """
    raw_service_id = (request.GET.get("created_service") or "").strip()
    if not raw_service_id.isdigit():
        return None

    service = (
        Services.objects.filter(
            pk=int(raw_service_id),
            services_of_salon=salon,
        )
        .prefetch_related("stylists__user")
        .first()
    )
    if service is None:
        return None

    has_public_active_stylist = service.stylists.filter(
        stylists_of_salon=salon,
        is_active=True,
        public_visibility__in=(
            Stylist.PublicVisibility.PUBLIC,
            Stylist.PublicVisibility.SALON_ONLY,
        ),
    ).exists()

    edit_service_url = reverse(
        "dashboards:edit_service",
        kwargs={"service_id": service.pk},
    )
    team_member_url = reverse("dashboards:team_member")
    scheduled_shifts_url = reverse("dashboards:scheduled_shifts")
    service_menu_url = reverse("dashboards:service_menu")

    if has_public_active_stylist:
        return {
            "service_id": service.pk,
            "service_name": service.service_name,
            "title": "خدمت اضافه شد؛ حالا برنامه کاری را تکمیل کن",
            "description": (
                "حداقل یک متخصص قابل‌نمایش به این خدمت متصل است. "
                "برای قابل رزرو شدن خدمت، برای همان متخصص در این سالن "
                "شیفت جاری یا آینده ثبت کن."
            ),
            "status_label": "متخصص متصل است",
            "status_tone": "success",
            "primary_label": "تنظیم برنامه کاری",
            "primary_url": scheduled_shifts_url,
            "secondary_label": "بازبینی خدمت",
            "secondary_url": edit_service_url,
            "dismiss_url": service_menu_url,
        }

    return {
        "service_id": service.pk,
        "service_name": service.service_name,
        "title": "خدمت اضافه شد؛ حالا متخصص ارائه‌دهنده را مشخص کن",
        "description": (
            "این خدمت هنوز متخصص فعال و قابل‌نمایشی ندارد. "
            "ابتدا متخصص ارائه‌دهنده و قیمت او را به خدمت متصل کن؛ "
            "بعد از آن برنامه کاری همان متخصص را بساز."
        ),
        "status_label": "بدون پوشش تیم",
        "status_tone": "warning",
        "primary_label": "اتصال متخصص به خدمت",
        "primary_url": edit_service_url,
        "secondary_label": "مدیریت اعضای تیم",
        "secondary_url": team_member_url,
        "dismiss_url": service_menu_url,
    }

_ACTIVE_SERVICE_BOOKING_STATUSES = (
    "pending",
    "confirmed",
    "paid",
    "disputed",
)

def _build_service_menu_queryset(
    *,
    salon,
    today=None,
):
    """Return service-menu rows with a fixed three-query budget.

    Booking counters are calculated through correlated database expressions,
    avoiding one count/exists query for every service.
    """

    today = today or timezone.localdate()

    future_booking_counts = (
        OrderDetail.objects.filter(
            salon=salon,
            service_id=OuterRef("pk"),
            order__status__in=(
                _ACTIVE_SERVICE_BOOKING_STATUSES
            ),
            date__gte=today,
        )
        .order_by()
        .values("service_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )

    booking_history = OrderDetail.objects.filter(
        salon=salon,
        service_id=OuterRef("pk"),
    )

    return (
        Services.objects.filter(
            services_of_salon=salon,
        )
        .prefetch_related(
            "service_group",
            Prefetch(
                "stylists",
                queryset=(
                    salon.stylists.filter(
                        is_active=True,
                    )
                    .select_related("user")
                    .order_by("pk")
                ),
                to_attr="dashboard_active_stylists",
            ),
        )
        .annotate(
            min_price=Min(
                "service_prices__price"
            ),
            max_price=Max(
                "service_prices__price"
            ),
            team_count=Count(
                "stylists",
                filter=Q(
                    stylists__stylists_of_salon=salon,
                    stylists__is_active=True,
                ),
                distinct=True,
            ),
            all_team_count=Count(
                "stylists",
                distinct=True,
            ),
            future_active_booking_count=Coalesce(
                Subquery(
                    future_booking_counts,
                    output_field=IntegerField(),
                ),
                Value(0),
            ),
            booking_history_exists=Exists(
                booking_history
            ),
        )
        .order_by(
            "service_name",
            "pk",
        )
    )
def _apply_service_menu_booking_state(service):
    """Attach booking-state fields from prepared annotations."""

    future_booking_count = int(
        getattr(
            service,
            "future_active_booking_count",
            0,
        )
        or 0
    )

    service.future_active_booking_count = (
        future_booking_count
    )
    service.future_active_booking_count_label = (
        to_persian_digits(
            future_booking_count
        )
    )
    service.has_future_active_bookings = (
        future_booking_count > 0
    )
    service.has_booking_history = bool(
        getattr(
            service,
            "booking_history_exists",
            False,
        )
    )

    return service

def _build_service_menu_workspace_stats(services):
    """Build service workspace metrics without database queries."""

    durations = [
        int(service.duration_minutes)
        for service in services
        if service.duration_minutes is not None
    ]

    avg_duration = (
        int(sum(durations) / len(durations))
        if durations
        else 0
    )

    return {
        "avg_duration": avg_duration,
        "priced_count": sum(
            1
            for service in services
            if service.min_price is not None
        ),
        "active_count": sum(
            1
            for service in services
            if service.is_active is True
        ),
        "archived_count": sum(
            1
            for service in services
            if service.is_active is False
        ),
        # Preserve the existing definition: no stylist relation at all.
        "unassigned_count": sum(
            1
            for service in services
            if int(
                getattr(
                    service,
                    "all_team_count",
                    0,
                )
                or 0
            )
            == 0
        ),
    }

class ServiceMenuView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    def get(self, request):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        service_setup_handoff = _build_created_service_setup_handoff(
            request=request,
            salon=salon,
        )

        services = list(
            _build_service_menu_queryset(
                salon=salon,
            )
        )

        services_by_group = defaultdict(lambda: {"group": None, "services": []})
        uncategorized_label = "دسته‌بندی نشده"

        for service in services:
            assigned_team_names = [
                member.get_fullName()
                for member in getattr(service, "dashboard_active_stylists", [])
            ]

            short_description = strip_tags(
                service.summery_description or service.description or ""
            ).strip()
            if len(short_description) > 90:
                short_description = short_description[:90].rstrip() + "…"

            display_min_price = service.min_price
            display_max_price = service.max_price
            if display_min_price is None and getattr(service, "base_price", 0):
                display_min_price = service.base_price
                display_max_price = service.base_price

            if display_min_price is not None and display_max_price is not None:
                if display_min_price == display_max_price:
                    price_label = _dashboard_currency(display_min_price)
                else:
                    price_label = (
                        f"{_dashboard_currency(display_min_price)} تا "
                        f"{_dashboard_currency(display_max_price)}"
                    )
            else:
                price_label = "ثبت نشده"

            service.name = service.service_name
            service.image = service.service_image
            service.short_description = (
                short_description or "برای این خدمت هنوز توضیح کوتاهی ثبت نشده است."
            )
            service.duration_label = (
                f"{to_persian_digits(service.duration_minutes or 0)} دقیقه"
            )
            service.team_count_label = to_persian_digits(service.team_count or 0)
            _apply_service_menu_booking_state(service)
            service.price_label = price_label
            service.assigned_team_names = assigned_team_names[:2]
            service.has_more_team = len(assigned_team_names) > 2
            service.extra_team_count_label = to_persian_digits(
                max(len(assigned_team_names) - 2, 0)
            )

            if service.is_active:
                service.status_label = "فعال"
                service.status_badge_class = "bg-emerald-100 text-emerald-700"
            else:
                service.status_label = "غیرفعال"
                service.status_badge_class = "bg-slate-200 text-slate-600"

            if assigned_team_names:
                service.coverage_label = "دارای پوشش"
                service.coverage_badge_class = "bg-emerald-100 text-emerald-700"
            else:
                service.coverage_label = "بدون پوشش"
                service.coverage_badge_class = "bg-amber-100 text-amber-700"

            service.edit_url = reverse(
                "dashboards:edit_service", kwargs={"service_id": service.id}
            )
            service.archive_url = reverse(
                "dashboards:archieve_service", kwargs={"service_id": service.id}
            )
            service.remove_url = reverse(
                "dashboards:remove_service", kwargs={"service_id": service.id}
            )
            service.toggle_url = reverse(
                "dashboards:toggle_service_status", kwargs={"service_id": service.id}
            )

            groups = list(service.service_group.all())
            if not groups:
                services_by_group[uncategorized_label]["services"].append(service)
            else:
                for group in groups:
                    services_by_group[group.pk]["group"] = group
                    services_by_group[group.pk]["services"].append(service)

        service_sections = []
        for key, payload in services_by_group.items():
            group = payload["group"]
            label = group.group_title if group else uncategorized_label
            services = payload["services"]

            active_count = sum(1 for service in services if service.is_active)
            unassigned_count = sum(
                1
                for service in services
                if not getattr(service, "assigned_team_names", [])
            )

            service_sections.append(
                {
                    "label": label,
                    "group": group,
                    "count": len(services),
                    "count_label": to_persian_digits(len(services)),
                    "services": services,
                    "active_count": active_count,
                    "active_count_label": to_persian_digits(active_count),
                    "unassigned_count": unassigned_count,
                    "unassigned_count_label": to_persian_digits(unassigned_count),
                }
            )

        service_sections.sort(
            key=lambda item: (item["label"] == uncategorized_label, item["label"])
        )

        workspace_stats = (
            _build_service_menu_workspace_stats(
                services
            )
        )

        context = {
            "salon": salon,
            "service_sections": service_sections,
            "service_setup_handoff": service_setup_handoff,
            "service_workspace": {
                "total_services_count": to_persian_digits(
                    len(services)
                ),
                "total_groups_count": to_persian_digits(len(service_sections)),
                "avg_duration": to_persian_digits(
                    int(workspace_stats.get("avg_duration") or 0)
                ),
                "priced_services_count": to_persian_digits(
                    workspace_stats.get("priced_count") or 0
                ),
                "active_services_count": to_persian_digits(
                    workspace_stats.get("active_count") or 0
                ),
                "archived_services_count": to_persian_digits(
                    workspace_stats.get("archived_count") or 0
                ),
                "unassigned_services_count": to_persian_digits(
                    workspace_stats.get("unassigned_count") or 0
                ),
                "focus_items": [
                    {
                        "title": "خدمات فعال",
                        "value": to_persian_digits(
                            workspace_stats.get("active_count") or 0
                        ),
                        "description": "این خدمات در منوی رزرو و flowهای عملیاتی قابل استفاده‌اند.",
                        "tone": "success",
                    },
                    {
                        "title": "خدمات بدون پوشش تیم",
                        "value": to_persian_digits(
                            workspace_stats.get("unassigned_count") or 0
                        ),
                        "description": "برای این خدمات هنوز متخصص یا عضو تیم فعالی متصل نشده است.",
                        "tone": "warning",
                    },
                    {
                        "title": "دارای قیمت‌گذاری",
                        "value": to_persian_digits(
                            workspace_stats.get("priced_count") or 0
                        ),
                        "description": "خدماتی که برای حداقل یک عضو تیم قیمت ثبت‌شده دارند.",
                        "tone": "primary",
                    },
                ],
            },
            "add_service_url": reverse("dashboards:add_service"),
        }
        return render(request, "dashboards/service_menu.html", context)


# =================================================================
def _catalog_service_display_sections(queryset=None):
    """Group platform services under root service groups for manager selection."""

    services = list(
        (queryset or Services.objects.filter(is_active=True, is_platform_catalog=True))
        .prefetch_related("service_group__group_parent")
        .order_by("service_name", "id")
    )
    sections = defaultdict(list)
    seen_ids = set()
    for service in services:
        if service.pk in seen_ids:
            continue
        seen_ids.add(service.pk)
        groups = list(service.service_group.all())
        primary_group = groups[0] if groups else None
        root_group = (
            primary_group.group_parent
            if primary_group and primary_group.group_parent_id
            else primary_group
        )
        root_title = root_group.group_title if root_group else "بدون دسته‌بندی"
        subgroup_title = (
            primary_group.group_title
            if primary_group and primary_group.group_parent_id
            else "خدمات اصلی"
        )
        sections[root_title].append(
            {
                "id": service.pk,
                "title": service.service_name,
                "subgroup_title": subgroup_title,
                "duration": service.duration_minutes,
                "base_price": service.base_price,
            }
        )
    return [
        {
            "label": label,
            "services": sorted(
                items, key=lambda item: (item["subgroup_title"], item["title"])
            ),
        }
        for label, items in sorted(sections.items(), key=lambda item: item[0])
    ]


def _catalog_service_selection_tree(queryset=None):
    """Build a three-level selection tree: parent group -> subgroup -> service."""

    services = list(
        (queryset or Services.objects.filter(is_active=True, is_platform_catalog=True))
        .prefetch_related("service_group__group_parent")
        .order_by("service_name", "id")
    )
    roots = {}
    seen_pairs = set()

    for service in services:
        groups = list(service.service_group.all())
        if not groups:
            root_key = "ungrouped"
            child_key = "ungrouped-child"
            roots.setdefault(
                root_key,
                {"id": root_key, "label": "بدون دسته‌بندی", "children": {}},
            )
            child = roots[root_key]["children"].setdefault(
                child_key,
                {"id": child_key, "label": "خدمات بدون زیرگروه", "services": []},
            )
            pair_key = (child_key, service.pk)
            if pair_key not in seen_pairs:
                child["services"].append(
                    {
                        "id": service.pk,
                        "title": service.service_name,
                        "duration": service.duration_minutes or 30,
                        "base_price": service.base_price or 0,
                    }
                )
                seen_pairs.add(pair_key)
            continue

        for group in groups:
            root_group = group.group_parent if group.group_parent_id else group
            root_key = str(root_group.pk)
            roots.setdefault(
                root_key,
                {"id": root_group.pk, "label": root_group.group_title, "children": {}},
            )
            if group.group_parent_id:
                child_id = group.pk
                child_label = group.group_title
            else:
                child_id = f"root-{root_group.pk}"
                child_label = "خدمات اصلی"
            child_key = str(child_id)
            child = roots[root_key]["children"].setdefault(
                child_key,
                {"id": child_id, "label": child_label, "services": []},
            )
            pair_key = (child_key, service.pk)
            if pair_key in seen_pairs:
                continue
            child["services"].append(
                {
                    "id": service.pk,
                    "title": service.service_name,
                    "duration": service.duration_minutes or 30,
                    "base_price": service.base_price or 0,
                }
            )
            seen_pairs.add(pair_key)

    tree = []
    for root in sorted(roots.values(), key=lambda item: item["label"]):
        children = []
        for child in sorted(root["children"].values(), key=lambda item: item["label"]):
            child["services"] = sorted(
                child["services"], key=lambda item: item["title"]
            )
            if child["services"]:
                children.append(child)
        if children:
            tree.append(
                {"id": root["id"], "label": root["label"], "children": children}
            )
    return tree


def _service_group_display_sections(service):
    groups = (
        list(service.service_group.select_related("group_parent").all())
        if service
        else []
    )
    sections = defaultdict(list)
    for group in groups:
        if group.group_parent_id:
            sections[group.group_parent.group_title].append(group.group_title)
        else:
            sections[group.group_title]
    return [
        {"label": label, "children": sorted(children)}
        for label, children in sorted(sections.items(), key=lambda item: item[0])
    ]


class AddServicesView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    form_class = StylistServiceForm
    template_name = "dashboards/add_services.html"

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

    def _build_context(self, *, salon, form):
        return {
            "form": form,
            "salon": salon,
            "catalog_sections": _catalog_service_display_sections(
                form.fields["catalog_service"].queryset
            ),
            "catalog_tree_json": json.dumps(
                _catalog_service_selection_tree(
                    form.fields["catalog_service"].queryset
                ),
                ensure_ascii=False,
            ),
            "selected_catalog_service_id": str(form["catalog_service"].value() or ""),
            "request_service_url": reverse("dashboards:request_service"),
            "service_menu_url": reverse("dashboards:service_menu"),
            "team_member_url": reverse("dashboards:team_member"),
        }

    def get(self, request):
        salon = self._get_salon(request)
        form = self.form_class(salon=salon)
        return render(
            request, self.template_name, self._build_context(salon=salon, form=form)
        )

    def post(self, request):
        salon = self._get_salon(request)
        form = self.form_class(request.POST, request.FILES, salon=salon)

        if form.is_valid():
            service = form.save(commit=True, salon=salon)
            messages.success(
                request,
                f"خدمت «{service.service_name}» برای همین مجموعه اضافه شد.",
            )
            service_menu_url = reverse("dashboards:service_menu")
            return redirect(f"{service_menu_url}?created_service={service.pk}")

        messages.error(request, "لطفاً خطاهای فرم را برطرف کن.")
        return render(
            request, self.template_name, self._build_context(salon=salon, form=form)
        )


class RequestServiceView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/request_service.html"

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

    def _get_request_tickets(self, *, request, salon):
        return SupportTicket.objects.filter(
            user=request.user,
            salon=salon,
            requester_role="salon_manager",
            sub_category="service_request",
        ).order_by("-updated_at", "-created_at")[:12]

    def _build_context(self, *, request, salon, **extra):
        context = {
            "salon": salon,
            "service_menu_url": reverse("dashboards:service_menu"),
            "request_tickets": self._get_request_tickets(request=request, salon=salon),
        }
        context.update(extra)
        return context

    def get(self, request):
        salon = self._get_salon(request)
        return render(
            request,
            self.template_name,
            self._build_context(request=request, salon=salon),
        )

    def post(self, request):
        salon = self._get_salon(request)
        name = (request.POST.get("service_name") or "").strip()
        group_hint = (request.POST.get("group_hint") or "").strip()
        duration_hint = (request.POST.get("duration_hint") or "").strip()
        description = (request.POST.get("description") or "").strip()

        errors = []
        if not name:
            errors.append("نام خدمت را وارد کن.")
        if len(name) > 180:
            errors.append("نام خدمت خیلی طولانی است.")
        if not description:
            errors.append("توضیح کوتاهی درباره خدمت وارد کن.")

        if errors:
            return render(
                request,
                self.template_name,
                self._build_context(
                    request=request,
                    salon=salon,
                    errors=errors,
                    form_data=request.POST,
                ),
            )

        user = request.user
        ticket_description = "\n".join(
            [
                "درخواست ایجاد خدمت جدید از داشبورد مجموعه",
                f"مجموعه: {salon.salon_name} (ID: {salon.pk})",
                f"نام خدمت پیشنهادی: {name}",
                f"گروه/دسته پیشنهادی: {group_hint or '-'}",
                f"مدت زمان پیشنهادی: {duration_hint or '-'}",
                "",
                "توضیحات مدیر مجموعه:",
                description,
            ]
        )

        ticket = SupportTicket.objects.create(
            user=user,
            email=user.email or f"user-{user.pk}@loomera.local",
            full_name=(
                user.get_fullName() if hasattr(user, "get_fullName") else str(user)
            ),
            mobile=getattr(user, "mobile_number", "") or "",
            issue_type="other",
            category="content_report",
            sub_category="service_request",
            support_reason="درخواست ایجاد خدمت جدید",
            subject=f"درخواست خدمت جدید: {name}",
            description=ticket_description,
            requester_role="salon_manager",
            assigned_team="content_moderation",
            status="waiting_for_admin_review",
            priority="normal",
            salon=salon,
            metadata={
                "source": "dashboard_request_service",
                "service_name": name,
                "group_hint": group_hint,
                "duration_hint": duration_hint,
            },
        )

        transaction.on_commit(
            lambda ticket=ticket, user=user: notify_support_ticket_created(
                user=user,
                ticket=ticket,
                action_url=reverse("dashboards:request_service"),
            )
        )

        messages.success(
            request,
            "درخواست خدمت جدید ثبت شد و از همین صفحه قابل پیگیری است.",
        )
        return redirect("dashboards:request_service")


# =================================================================
# VIEW ویرایش خدمت (بهینه شده)
# =================================================================
class EditServiceView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    form_class = StylistServiceForm
    template_name = "dashboards/edit_service.html"

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

    def _clone_catalog_service_for_salon(self, *, salon, service):
        """Protect platform catalog records from manager edits.

        If a legacy salon is still linked directly to a catalog service, clone it
        before opening the edit page and keep the clone attached to the salon.
        """

        clone = Services.objects.create(
            service_name=service.service_name,
            summery_description=service.summery_description,
            description=service.description,
            service_image=service.service_image,
            duration_minutes=service.duration_minutes,
            base_price=service.base_price,
            buffer_minutes=service.buffer_minutes,
            is_active=True,
            allow_indexing=False,
            is_platform_catalog=False,
            catalog_source=service,
        )
        clone.service_group.set(service.service_group.all())
        clone.stylists.set(service.stylists.filter(stylists_of_salon=salon))
        salon.services.remove(service)
        salon.services.add(clone)
        for price in service.service_prices.filter(stylist__stylists_of_salon=salon):
            ServicePrice.objects.create(
                service=clone, stylist=price.stylist, price=price.price
            )
        return clone

    def _get_service(self, salon, service_id):
        service = get_object_or_404(
            Services.objects.prefetch_related(
                "service_group__group_parent", "stylists", "service_prices"
            ),
            id=service_id,
            services_of_salon=salon,
        )
        if service.is_platform_catalog:
            service = self._clone_catalog_service_for_salon(
                salon=salon, service=service
            )
        return service

    def _build_stylist_cards(self, salon, form):
        selected_ids = {str(item) for item in (form["stylists"].value() or [])}
        cards = []

        stylists = salon.stylists.select_related("user").order_by(
            "user__family", "user__name"
        )
        for stylist in stylists:
            field_name = f"price_for_stylist_{stylist.pk}"
            price_field = form[field_name] if field_name in form.fields else None
            if stylist.is_active:
                status_label = "فعال"
                status_badge_class = "bg-emerald-100 text-emerald-700"
            else:
                status_label = "غیرفعال"
                status_badge_class = "bg-slate-200 text-slate-600"
            cards.append(
                {
                    "id": stylist.pk,
                    "full_name": stylist.get_fullName(),
                    "expert": stylist.expert or "عضو تیم",
                    "profile_image_url": (
                        stylist.profile_image.url if stylist.profile_image else None
                    ),
                    "is_selected": str(stylist.pk) in selected_ids,
                    "status_label": status_label,
                    "status_badge_class": status_badge_class,
                    "price_field": price_field,
                }
            )
        return cards

    def _build_context(self, *, salon, service, form):
        source_service = service.catalog_source or service
        stylist_cards = self._build_stylist_cards(salon, form)
        selected_stylist_count = sum(1 for item in stylist_cards if item["is_selected"])
        base_price_value = form["base_price"].value() or service.base_price or 0
        base_price_label = _dashboard_currency(int(base_price_value or 0))
        service_status_label = "فعال" if service.is_active else "آرشیو شده"
        service_status_badge_class = (
            "bg-emerald-100 text-emerald-700"
            if service.is_active
            else "bg-slate-200 text-slate-600"
        )

        return {
            "salon": salon,
            "service": service,
            "source_service": source_service,
            "form": form,
            "group_sections": _service_group_display_sections(source_service),
            "stylist_cards": stylist_cards,
            "edit_service_workspace": {
                "service_status_label": service_status_label,
                "service_status_badge_class": service_status_badge_class,
                "groups_count_label": to_persian_digits(
                    len(_service_group_display_sections(source_service))
                ),
                "selected_groups_count_label": to_persian_digits(
                    len(source_service.service_group.all())
                ),
                "stylists_count_label": to_persian_digits(len(stylist_cards)),
                "selected_stylists_count_label": to_persian_digits(
                    selected_stylist_count
                ),
                "duration_label": to_persian_digits(
                    form["duration_minutes"].value() or service.duration_minutes or 0
                ),
                "base_price_label": base_price_label,
                "focus_items": [
                    {
                        "title": "تنظیمات این خدمت فقط برای همین مجموعه ذخیره می‌شود",
                        "value": "اختصاصی مجموعه",
                        "description": "نام، تصویر و دسته‌بندی از کاتالوگ پلتفرم می‌آید؛ مدت، بافر، قیمت، توضیح و تیم برای این مجموعه قابل تنظیم است.",
                        "tone": "success",
                    }
                ],
                "service_menu_url": reverse("dashboards:service_menu"),
                "add_service_url": reverse("dashboards:add_service"),
                "team_member_url": reverse("dashboards:team_member"),
            },
        }

    def get(self, request, service_id):
        salon = self._get_salon(request)
        service = self._get_service(salon, service_id)

        # A platform-catalog service is cloned on first edit. Redirect to the
        # canonical URL of the salon-owned clone so refresh and form submission
        # never continue using the detached catalog service ID.
        if service.pk != service_id:
            return redirect(
                "dashboards:edit_service",
                service_id=service.pk,
            )

        form = self.form_class(instance=service, salon=salon)
        context = self._build_context(
            salon=salon,
            service=service,
            form=form,
        )
        return render(request, self.template_name, context)

    def post(self, request, service_id):
        salon = self._get_salon(request)
        service = self._get_service(salon, service_id)
        form = self.form_class(
            request.POST, request.FILES, instance=service, salon=salon
        )
        if form.is_valid():
            form.save(commit=True, salon=salon)
            messages.success(request, "تنظیمات خدمت برای همین مجموعه ذخیره شد.")
            return redirect("dashboards:service_menu")
        messages.error(request, "لطفاً خطاهای فرم را برطرف کن.")
        context = self._build_context(salon=salon, service=service, form=form)
        return render(request, self.template_name, context)


def _service_future_active_booking_qs(*, salon, service):
    return OrderDetail.objects.filter(
        salon=salon,
        service=service,
        order__status__in=_ACTIVE_SERVICE_BOOKING_STATUSES,
        date__gte=timezone.localdate(),
    )


def _service_has_future_active_bookings(*, salon, service):
    return _service_future_active_booking_qs(salon=salon, service=service).exists()


def _service_has_booking_history(*, salon, service):
    return OrderDetail.objects.filter(
        salon=salon,
        service=service,
    ).exists()


def _service_future_booking_block_message(service, count=None):
    count_text = ""
    if count is not None:
        count_text = f" ({to_persian_digits(count)} نوبت فعال/آینده)"
    return (
        f"خدمت «{service.service_name}» نوبت فعال یا آینده دارد{count_text}. "
        "برای جلوگیری از خراب شدن نوبت‌ها، ابتدا نوبت‌ها را انجام، جابه‌جا یا با ذکر علت لغو کنید."
    )


# =================================================================
# VIEW های آرشیو و حذف (بهینه شده)
# =================================================================
@login_required
@manager_required
def archieve_service(request, service_id):
    if request.method != "POST":
        return redirect("dashboards:service_menu")

    salon = get_object_or_404(Salon, salon_manager__user=request.user)
    service = get_object_or_404(Services, id=service_id, services_of_salon=salon)

    future_booking_count = _service_future_active_booking_qs(
        salon=salon,
        service=service,
    ).count()

    if future_booking_count:
        messages.error(
            request,
            _service_future_booking_block_message(service, future_booking_count),
        )
        return redirect("dashboards:service_menu")

    if service.is_platform_catalog:
        salon.services.remove(service)
        messages.success(request, "خدمت با موفقیت از منوی این مجموعه خارج شد.")
    else:
        service.is_active = False
        service.save(update_fields=["is_active", "updated_date"])
        messages.success(request, "خدمت با موفقیت آرشیو و از رزروهای جدید خارج شد.")

    return redirect("dashboards:service_menu")


@login_required
@manager_required
def remove_service(request, service_id):
    if request.method != "POST":
        return redirect("dashboards:service_menu")

    salon = get_object_or_404(Salon, salon_manager__user=request.user)
    service = get_object_or_404(Services, id=service_id, services_of_salon=salon)

    future_booking_count = _service_future_active_booking_qs(
        salon=salon,
        service=service,
    ).count()

    if future_booking_count:
        messages.error(
            request,
            _service_future_booking_block_message(service, future_booking_count),
        )
        return redirect("dashboards:service_menu")

    if service.is_platform_catalog:
        salon.services.remove(service)
        messages.success(
            request,
            "خدمت از منوی این مجموعه خارج شد. سوابق نوبت‌های قبلی دست‌نخورده باقی می‌ماند.",
        )
        return redirect("dashboards:service_menu")

    if _service_has_booking_history(salon=salon, service=service):
        service.is_active = False
        service.save(update_fields=["is_active", "updated_date"])
        messages.warning(
            request,
            "این خدمت سابقه نوبت دارد؛ برای حفظ سوابق، حذف فیزیکی انجام نشد و خدمت به‌صورت امن آرشیو شد.",
        )
        return redirect("dashboards:service_menu")

    service.delete()
    messages.success(request, "خدمت با موفقیت از مجموعه حذف شد.")
    return redirect("dashboards:service_menu")


@manager_required
def toggle_service_status(request, service_id):
    if request.method != "POST":
        return redirect("dashboards:service_menu")

    salon = get_object_or_404(Salon, salon_manager__user=request.user)
    service = get_object_or_404(Services, id=service_id, services_of_salon=salon)

    if service.is_active:
        future_booking_count = _service_future_active_booking_qs(
            salon=salon,
            service=service,
        ).count()

        if future_booking_count:
            messages.error(
                request,
                _service_future_booking_block_message(service, future_booking_count),
            )
            return redirect("dashboards:service_menu")

    if service.is_platform_catalog:
        # رکورد کاتالوگ اصلی را تغییر نمی‌دهیم؛ برای تغییر وضعیت، نسخه اختصاصی می‌سازیم.
        service = EditServiceView()._clone_catalog_service_for_salon(
            salon=salon,
            service=service,
        )

    service.is_active = not bool(service.is_active)
    service.save(update_fields=["is_active", "updated_date"])

    if service.is_active:
        messages.success(
            request, "خدمت دوباره فعال شد و در رزروهای جدید قابل استفاده است."
        )
    else:
        messages.success(
            request, "خدمت غیرفعال شد و در رزروهای جدید نمایش داده نمی‌شود."
        )

    return redirect("dashboards:service_menu")


@manager_required
def toggle_stylist_status(request, stylist_id):
    salon = get_object_or_404(Salon, salon_manager__user=request.user)
    stylist = get_object_or_404(Stylist, user_id=stylist_id, stylists_of_salon=salon)
    membership = SalonMembership.objects.filter(salon=salon, stylist=stylist).first()
    if membership is None:
        membership = sync_legacy_membership(
            salon=salon,
            stylist=stylist,
            actor=request.user,
            status=(
                SalonMembershipStatus.ACTIVE
                if stylist.is_active
                else SalonMembershipStatus.PAUSED
            ),
            request=request,
        )

    if request.method == "POST":
        next_status = (
            SalonMembershipStatus.PAUSED
            if membership.status == SalonMembershipStatus.ACTIVE
            else SalonMembershipStatus.ACTIVE
        )
        change_membership_status(
            membership=membership,
            new_status=next_status,
            actor=request.user,
            reason="تغییر وضعیت عضو تیم از داشبورد مجموعه",
            request=request,
        )
        if next_status == SalonMembershipStatus.ACTIVE and not stylist.is_active:
            stylist.is_active = True
            stylist.save(update_fields=["is_active"])
        messages.success(
            request, "وضعیت همکاری عضو تیم در این مجموعه با موفقیت به‌روزرسانی شد."
        )

    return redirect("dashboards:team_member")


# --------------------------------------------------------------------------------------------
@login_required
@manager_required
def membership(request):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return redirect_response

    salon = _get_manager_dashboard_salon(request.user)
    snapshot = _build_partner_workspace_snapshot(salon)

    profile_ready = bool(
        salon
        and salon.salon_name
        and salon.address
        and (salon.description or "").strip()
    )
    booking_ready = (
        snapshot["active_services_count"] > 0
        and snapshot["active_team_count"] > 0
        and snapshot["opening_days_count"] > 0
    )
    payout_ready = bool(salon and salon.payout_profile_complete)
    trust_ready = snapshot["gallery_count"] > 0 and snapshot["supplementary_count"] > 0

    readiness_items = [
        {
            "title": "پروفایل و برند مجموعه",
            "description": "اطلاعات پایهٔ برند و صفحهٔ عمومی برای استفاده از workspace partner باید روشن و قابل‌اعتماد باشند.",
            "is_ready": profile_ready,
            "meta": (
                "پروفایل عمومی" if profile_ready else "نام، آدرس یا توضیحات ناقص است"
            ),
            "cta_label": "پروفایل مجموعه",
            "cta_url": reverse("dashboards:salon_profile"),
        },
        {
            "title": "رزرو و عملیات روزانه",
            "description": "برای اینکه plan عملی باشد، خدمات، تیم و ساعت کاری باید رزروپذیر و operational باشند.",
            "is_ready": booking_ready,
            "meta": f'{to_persian_digits(snapshot["active_services_count"])} خدمت فعال • {to_persian_digits(snapshot["active_team_count"])} عضو فعال',
            "cta_label": "رزرو آنلاین",
            "cta_url": reverse("dashboards:online_booking"),
        },
        {
            "title": "تسویه و اطلاعات مالی",
            "description": "موتور subscription هنوز فعال نیست، اما readiness اطلاعات تسویه و policyهای پایه باید مشخص باشند.",
            "is_ready": payout_ready,
            "meta": salon.cancellation_policy_summary if salon else "—",
            "cta_label": "مالی",
            "cta_url": reverse("dashboards:finance_withdraw"),
        },
        {
            "title": "اعتماد صفحه و محتوای تکمیلی",
            "description": "تصاویر و ویژگی‌های تکمیلی برای کیفیت تجربه partner و public booking اهمیت دارند.",
            "is_ready": trust_ready,
            "meta": f'{to_persian_digits(snapshot["gallery_count"])} تصویر • {to_persian_digits(snapshot["supplementary_count"])} آیتم تکمیلی',
            "cta_label": "پروفایل مجموعه",
            "cta_url": reverse("dashboards:salon_profile"),
        },
    ]
    ready_count = sum(1 for item in readiness_items if item["is_ready"])
    readiness_progress = (
        int((ready_count / len(readiness_items)) * 100) if readiness_items else 0
    )

    plan_cards = [
        {
            "title": "Starter Partner",
            "badge": "پایه",
            "description": "برای راه‌اندازی رزرو آنلاین، مدیریت خدمات و visibility پایه روی عملیات روزانه.",
            "is_current": True,
            "included": ["رزرو آنلاین", "تقویم و نوبت‌ها", "پروفایل و تیم"],
        },
        {
            "title": "Growth Workspace",
            "badge": "بعداً",
            "description": "برای deepening گزارش‌ها، automationها و capability gating سطح بالاتر در فازهای بعد.",
            "is_current": False,
            "included": ["گزارش‌های عمیق‌تر", "اعلان‌های گسترده‌تر", "پیکربندی plan"],
        },
    ]

    capability_groups = [
        {
            "title": "قابلیت‌های active در plan فعلی",
            "items": [
                "عملیات نوبت و planner",
                "رزرو آنلاین و quick booking",
                "مالی و کیف پول مجموعه",
            ],
        },
        {
            "title": "قابلیت‌های framing شده برای بعد",
            "items": [
                "billing engine واقعی",
                "limit-based plan enforcement",
                "invoice و renewal زنده",
            ],
        },
    ]

    membership_workspace = {
        "hero_badges": [
            {"icon": "fa-solid fa-briefcase", "label": "Partner Workspace"},
            {
                "icon": "fa-solid fa-credit-card",
                "label": "Billing engine: هنوز متصل نشده",
            },
            {
                "icon": "fa-solid fa-shield-heart",
                "label": f"{to_persian_digits(ready_count)} از {to_persian_digits(len(readiness_items))} حوزه آماده",
            },
        ],
        "plan_name": "Partner Workspace",
        "plan_state_label": "بدون موتور subscription زنده",
        "plan_state_tone": "primary",
        "billing_status_label": "هنوز صورتحساب خودکار فعال نشده",
        "renewal_label": "تاریخ تمدید بعداً با billing engine تعریف می‌شود",
        "invoice_label": "در این مرحله فاکتور subscription ثبت نمی‌شود",
        "usage_summary": [
            {
                "title": "رزروهای ۳۰ روز اخیر",
                "value": to_persian_digits(snapshot["recent_bookings_count"]),
                "meta": "سیگنال استفاده واقعی از workspace و خدمات.",
                "icon": "fa-regular fa-calendar-check",
                "tone": "primary",
            },
            {
                "title": "خدمات فعال",
                "value": to_persian_digits(snapshot["active_services_count"]),
                "meta": "آنچه امروز در عملیات و رزرو روی آن تکیه می‌کنی.",
                "icon": "fa-solid fa-scissors",
                "tone": "success",
            },
            {
                "title": "اعضای فعال تیم",
                "value": to_persian_digits(snapshot["active_team_count"]),
                "meta": "ظرفیت واقعی برای پاسخ‌گویی به رزرو و اجرای خدمت.",
                "icon": "fa-solid fa-user-group",
                "tone": "neutral",
            },
            {
                "title": "پیشرفت آمادگی",
                "value": f"{to_persian_digits(readiness_progress)}٪",
                "meta": "خوانش product-level از آماده‌بودن پنل برای beta/public readiness.",
                "icon": "fa-solid fa-signal",
                "tone": "primary",
            },
        ],
        "readiness_items": readiness_items,
        "readiness_progress": readiness_progress,
        "ready_count_label": to_persian_digits(ready_count),
        "total_checks_label": to_persian_digits(len(readiness_items)),
        "included_surfaces": [
            "dashboard partner-side و surfaceهای مدیریتی فعلی",
            "رزرو آنلاین، پروفایل مجموعه و readiness page",
            "کاتالوگ خدمات، تیم و gapهای inventory در همین فاز",
            "finance layer فعلی بدون redesign billing/subscription engine",
        ],
        "billing_placeholders": [
            "طرح فعلی به‌صورت operational status نمایش داده می‌شود، نه صورتحساب واقعی.",
            "invoice و renewal هنوز به backend اشتراک متصل نشده‌اند.",
            "upgrade/downgrade در این فاز به‌صورت affordance محصولی و راهبری workflow دیده می‌شود.",
        ],
        "plan_cards": plan_cards,
        "capability_groups": capability_groups,
        "actions": [
            {"label": "رزرو آنلاین", "url": reverse("dashboards:online_booking")},
            {"label": "کاتالوگ", "url": reverse("dashboards:catalog")},
            {"label": "مالی", "url": reverse("dashboards:finance_withdraw")},
        ],
    }

    context = {"salon": salon, "membership_workspace": membership_workspace}
    return render(request, "dashboards/membership.html", context)


# --------------------------------------------------------------------------------------------
@login_required
@manager_required
def products(request):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return redirect_response

    salon = _get_manager_dashboard_salon(request.user)
    snapshot = _build_partner_workspace_snapshot(salon)
    has_inventory_engine = False

    demand_signals = snapshot["top_services"] or [
        {
            "label": "هنوز دادهٔ کافی برای سیگنال تقاضا ثبت نشده",
            "bookings_label": to_persian_digits(0),
            "revenue_label": _dashboard_currency(0),
        }
    ]

    products_workspace = {
        "hero_badges": [
            {"icon": "fa-solid fa-box-open", "label": "Products workspace"},
            {
                "icon": "fa-solid fa-layer-group",
                "label": f'{to_persian_digits(snapshot["service_groups_count"])} گروه خدمت به‌عنوان سیگنال کاتالوگ',
            },
            {"icon": "fa-solid fa-store", "label": "Retail engine: در حال آماده‌سازی"},
        ],
        "state_label": "Inventory layer هنوز initialize نشده",
        "state_tone": "warning",
        "summary": [
            {
                "title": "تقاضای ۳۰ روز اخیر",
                "value": to_persian_digits(snapshot["recent_bookings_count"]),
                "meta": "به‌عنوان ورودی اولیه برای تصمیم دربارهٔ محصولات مکمل و retail.",
                "icon": "fa-regular fa-calendar-check",
                "tone": "primary",
            },
            {
                "title": "خدمات فعال",
                "value": to_persian_digits(snapshot["active_services_count"]),
                "meta": "هرچه catalog خدمات روشن‌تر باشد، ساخت retail layer هدفمندتر می‌شود.",
                "icon": "fa-solid fa-scissors",
                "tone": "success",
            },
            {
                "title": "اعضای فعال تیم",
                "value": to_persian_digits(snapshot["active_team_count"]),
                "meta": "برای فروش درون‌مجموعه و استفادهٔ داخلی از کالاها، ظرفیت تیم مهم است.",
                "icon": "fa-solid fa-user-group",
                "tone": "neutral",
            },
            {
                "title": "وضعیت فعلی",
                "value": "پایه",
                "meta": "صفحه usable است اما هنوز به مدل محصول و stock engine کامل متصل نشده.",
                "icon": "fa-solid fa-seedling",
                "tone": "primary",
            },
        ],
        "empty_state": {
            "title": "هنوز محصولی برای این مجموعه تعریف نشده است",
            "description": "در نسخهٔ فعلی پروژه مدل کامل product/inventory وجود ندارد؛ این workspace اکنون برای راهبری setup، دید عملیاتی و بستن gapهای partner-side استفاده می‌شود.",
            "points": [
                "تعریف دسته‌بندی و منطق retail در کنار catalog خدمات",
                "روشن‌کردن state محصول، قیمت و وضعیت قابل‌فروش بودن",
                "آماده‌سازی برای low-stock tracking و stocktake workflow",
            ],
        },
        "signals": demand_signals,
        "setup_steps": [
            "دسته‌بندی محصول، برند و کد داخلی کالا را مشخص کن.",
            "قیمت خرید، قیمت فروش و وضعیت قابل‌فروش بودن را تعریف کن.",
            "برای کالاهای مصرفی یا retail، سیاست low stock و reorder را روشن کن.",
            "Products را به stocktakes و catalog به‌عنوان یک family واحد operational وصل نگه دار.",
        ],
        "relationship_cards": [
            {
                "title": "Catalog",
                "description": "از اینجا می‌فهمی محصولات قرار است کنار کدام خدمات و گروه‌ها معنا پیدا کنند.",
                "url": reverse("dashboards:catalog"),
            },
            {
                "title": "Stocktakes",
                "description": "بعد از تعریف products، موجودی‌گیری و اختلاف شمارش در این بخش دنبال می‌شود.",
                "url": reverse("dashboards:stocktakes"),
            },
            {
                "title": "Online booking",
                "description": "اگر retail یا معرفی مکمل‌ها بعداً به صفحه عمومی وصل شود، از readiness رزرو جدا نخواهد بود.",
                "url": reverse("dashboards:online_booking"),
            },
        ],
        "actions": [
            {"label": "کاتالوگ", "url": reverse("dashboards:catalog")},
            {"label": "موجودی‌گیری", "url": reverse("dashboards:stocktakes")},
            {"label": "رزرو آنلاین", "url": reverse("dashboards:online_booking")},
        ],
        "has_inventory_engine": has_inventory_engine,
    }
    context = {"salon": salon, "products_workspace": products_workspace}
    return render(request, "dashboards/products.html", context)


# --------------------------------------------------------------------------------------------
@login_required
@manager_required
def stocktakes(request):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return redirect_response

    salon = _get_manager_dashboard_salon(request.user)
    snapshot = _build_partner_workspace_snapshot(salon)

    stocktakes_workspace = {
        "hero_badges": [
            {"icon": "fa-solid fa-clipboard-check", "label": "Stocktakes workspace"},
            {"icon": "fa-solid fa-boxes-stacked", "label": "شمارش و بازبینی دوره‌ای"},
            {
                "icon": "fa-solid fa-triangle-exclamation",
                "label": "Inventory engine: هنوز کامل نشده",
            },
        ],
        "status_cards": [
            {
                "title": "وضعیت فعلی موجودی‌گیری",
                "value": "Setup-oriented",
                "meta": "Flow موجودی‌گیری آمادهٔ استفادهٔ product-like شده، اما هنوز به ثبت محصول و stock ledger کامل متصل نیست.",
                "icon": "fa-solid fa-clipboard-check",
                "tone": "primary",
            },
            {
                "title": "سیگنال عملیات",
                "value": to_persian_digits(snapshot["recent_bookings_count"]),
                "meta": "رزروهای ۳۰ روز اخیر به تصمیم دربارهٔ تعداد شمارش، کالاهای مصرفی و نقاط حساس کمک می‌کنند.",
                "icon": "fa-regular fa-calendar-check",
                "tone": "success",
            },
            {
                "title": "آمادگی تیم",
                "value": to_persian_digits(snapshot["active_team_count"]),
                "meta": "برای اجرای stocktake، نقش‌ها و مسئولیت شمارش باید روشن باشند.",
                "icon": "fa-solid fa-user-group",
                "tone": "neutral",
            },
        ],
        "steps": [
            {
                "title": "شروع موجودی‌گیری",
                "description": "بازهٔ شمارش، محل/دامنه و هدف stocktake را مشخص کن تا تیم بداند چه چیزی باید بازبینی شود.",
            },
            {
                "title": "شمارش و ثبت",
                "description": "اقلام را بشمار، مقادیر واقعی را ثبت کن و مواردی که هنوز شمرده نشده‌اند را از موارد تکمیل‌شده جدا نگه دار.",
            },
            {
                "title": "مرور اختلاف و تکمیل",
                "description": "اختلاف‌ها، اقلام خارج از شمارش و اقدام بعدی تیم را مرور کن و بعد stocktake را نهایی کن.",
            },
        ],
        "readiness_items": [
            {
                "title": "ساختار محصولات",
                "state": "هنوز نیازمند تعریف مدل product است",
                "tone": "warning",
                "description": "قبل از stocktake کامل، باید حداقل دسته‌بندی، state و هویت کالا روشن باشد.",
            },
            {
                "title": "سیاست low stock و reorder",
                "state": "به setup بعدی نیاز دارد",
                "tone": "warning",
                "description": "برای inventory discipline بهتر است آستانهٔ کمبود و منطق سفارش مجدد از قبل مشخص باشد.",
            },
            {
                "title": "چرخهٔ شمارش",
                "state": "آماده برای تعریف cadence",
                "tone": "primary",
                "description": "می‌توان موجودی‌گیری را به‌صورت هفتگی، ماهانه یا مقطعی برای اقلام حساس تعریف کرد.",
            },
        ],
        "empty_state": {
            "title": "هنوز stocktake فعالی ثبت نشده است",
            "description": "این صفحه حالا مفهوم stocktake، مسیر عمل و entry pointهای بعدی را روشن می‌کند تا وقتی engine موجودی کامل شد، surface خام و رهاشده نباشد.",
        },
        "actions": [
            {"label": "محصولات", "url": reverse("dashboards:products")},
            {"label": "کاتالوگ", "url": reverse("dashboards:catalog")},
            {"label": "رزرو آنلاین", "url": reverse("dashboards:online_booking")},
        ],
    }
    context = {"salon": salon, "stocktakes_workspace": stocktakes_workspace}
    return render(request, "dashboards/stocktakes.html", context)


# --------------------------------------------------------------------------------------------
@login_required
@manager_required
def team_managment(request):
    """Legacy route kept for backwards compatibility; team management now lives on one page."""
    return redirect("dashboards:team_member")


# --------------------------------------------------------------------------------------------
def _build_created_stylist_setup_handoff(*, request, salon):
    """Build the next setup step for a newly added salon team member.

    The stylist identifier comes from the query string and is untrusted.
    Only an active stylist with an active membership in the current manager's
    salon may be exposed.
    """
    raw_stylist_id = (request.GET.get("created_stylist") or "").strip()
    if not raw_stylist_id.isdigit():
        return None

    stylist = (
        Stylist.objects.select_related("user")
        .filter(
            user_id=int(raw_stylist_id),
            stylists_of_salon=salon,
            is_active=True,
        )
        .first()
    )
    if stylist is None:
        return None

    has_active_membership = SalonMembership.objects.filter(
        salon=salon,
        stylist=stylist,
        status=SalonMembershipStatus.ACTIVE,
    ).exists()
    if not has_active_membership:
        return None

    edit_url = reverse(
        "dashboards:edit_stylist",
        kwargs={"stylist_id": stylist.user_id},
    )
    overview_url = reverse(
        "dashboards:stylist_overview",
        kwargs={"stylist_id": stylist.user_id},
    )
    scheduled_shifts_url = reverse("dashboards:scheduled_shifts")
    team_member_url = reverse("dashboards:team_member")

    base = {
        "stylist_id": stylist.user_id,
        "stylist_name": stylist.get_fullName(),
        "edit_url": edit_url,
        "overview_url": overview_url,
        "scheduled_shifts_url": scheduled_shifts_url,
        "dismiss_url": team_member_url,
    }

    if not stylist.is_visible_on_salon_pages:
        return {
            **base,
            "title": "عضو اضافه شد؛ وضعیت نمایش او را بررسی کن",
            "description": (
                "این عضو اکنون در صفحات عمومی سالن قابل‌نمایش نیست. "
                "برای اینکه مشتری بتواند او را هنگام رزرو انتخاب کند، "
                "وضعیت نمایش پروفایل را اصلاح کن."
            ),
            "status_label": "پروفایل عمومی غیرفعال",
            "status_tone": "warning",
            "primary_label": "ویرایش وضعیت نمایش",
            "primary_url": edit_url,
            "secondary_label": "مشاهده عضو",
            "secondary_url": overview_url,
        }

    bookable_services = stylist.services_of_stylist.filter(
        services_of_salon=salon,
        is_active=True,
        base_price__gt=0,
        duration_minutes__gt=0,
    ).distinct()

    bookable_service_ids = list(bookable_services.values_list("pk", flat=True))

    if not bookable_service_ids:
        return {
            **base,
            "title": "عضو اضافه شد؛ خدمات او را مشخص کن",
            "description": (
                "این عضو هنوز به خدمت فعال، قیمت‌گذاری‌شده و دارای مدت "
                "در همین سالن متصل نیست. ابتدا خدمات قابل ارائه او را مشخص کن."
            ),
            "status_label": "بدون خدمت قابل رزرو",
            "status_tone": "warning",
            "primary_label": "اتصال خدمات عضو",
            "primary_url": edit_url,
            "secondary_label": "مشاهده عضو",
            "secondary_url": overview_url,
        }

    has_future_schedule = (
        StylistSchedule.objects.filter(
            salon=salon,
            stylist=stylist,
            date__gte=timezone.localdate(),
        )
        .filter(Q(service__isnull=True) | Q(service_id__in=bookable_service_ids))
        .exists()
    )

    if not has_future_schedule:
        return {
            **base,
            "title": "خدمات عضو آماده است؛ حالا برنامه کاری را ثبت کن",
            "description": (
                "عضو به خدمت قابل رزرو متصل شده است، اما هنوز برای همان "
                "خدمات در این سالن شیفت جاری یا آینده ندارد."
            ),
            "status_label": "منتظر برنامه کاری",
            "status_tone": "primary",
            "primary_label": "تنظیم برنامه کاری",
            "primary_url": scheduled_shifts_url,
            "secondary_label": "بازبینی خدمات عضو",
            "secondary_url": edit_url,
        }

    return {
        **base,
        "title": "راه‌اندازی اولیه عضو کامل است",
        "description": (
            "عضو قابل‌نمایش است، خدمت قابل رزرو دارد و برنامه کاری جاری "
            "یا آینده برای او ثبت شده است."
        ),
        "status_label": "آماده رزرو",
        "status_tone": "success",
        "primary_label": "مشاهده پروفایل عضو",
        "primary_url": overview_url,
        "secondary_label": "مدیریت برنامه کاری",
        "secondary_url": scheduled_shifts_url,
    }

TEAM_MEMBER_SERVICES_ATTR = "_team_member_salon_services"


def _team_member_services_prefetch(*, salon):
    """Prefetch only services belonging to the active manager salon."""

    return Prefetch(
        "services_of_stylist",
        queryset=(
            Services.objects.filter(
                services_of_salon=salon,
            )
            .order_by(
                "service_name",
                "pk",
            )
            .distinct()
        ),
        to_attr=TEAM_MEMBER_SERVICES_ATTR,
    )

def _build_team_member_stylists_queryset(salon):
    """Return team members with fixed-query card data."""

    return (
        salon.stylists.select_related("user")
        .prefetch_related(
            _team_member_services_prefetch(
                salon=salon,
            )
        )
        .annotate(
            avg_score_annotation=Coalesce(
                Avg("scoring_stylist__score"),
                Value(0.0),
            ),
            services_count=Count(
                "services_of_stylist",
                filter=Q(
                    services_of_stylist__services_of_salon=salon,
                ),
                distinct=True,
            ),
            upcoming_count=Count(
                "order_details_stylist",
                filter=(
                    Q(
                        order_details_stylist__salon=salon,
                        order_details_stylist__date__gte=(
                            timezone.localdate()
                        ),
                    )
                    & ~Q(
                        order_details_stylist__order__status__in=[
                            "cancelled",
                            "completed",
                            "no_show",
                        ]
                    )
                ),
                distinct=True,
            ),
        )
    )

class TeamMemberView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/team_member.html"

    def _serialize_stylist(self, stylist, salon):
        prepared_services = getattr(
            stylist,
            TEAM_MEMBER_SERVICES_ATTR,
            None,
        )

        services_qs = None

        if prepared_services is not None:
            services = list(prepared_services[:3])
        else:
            # Backward compatibility for callers that pass an unprepared Stylist.
            services_qs = (
                stylist.services_of_stylist.filter(
                    services_of_salon=salon,
                )
                .distinct()
                .order_by(
                    "service_name",
                    "pk",
                )
            )
            services = list(services_qs[:3])

        membership_status = getattr(
            stylist,
            "membership_status_for_salon",
            SalonMembershipStatus.ACTIVE,
        )

        service_names = [
            service.service_name for service in services if service.service_name
        ]

        services_count = getattr(
            stylist,
            "services_count",
            None,
        )

        if services_count is None:
            if prepared_services is not None:
                services_count = len(prepared_services)
            else:
                services_count = services_qs.count()

        upcoming_count = getattr(stylist, "upcoming_count", None)
        if upcoming_count is None:
            upcoming_count = (
                OrderDetail.objects.filter(
                    salon=salon,
                    stylist=stylist,
                    date__gte=timezone.localdate(),
                )
                .exclude(order__status__in=["cancelled", "completed", "no_show"])
                .count()
            )

        extra_services_count = max((services_count or 0) - len(service_names), 0)

        is_active_in_this_salon = (
            stylist.is_active and membership_status == SalonMembershipStatus.ACTIVE
        )

        if not is_active_in_this_salon:
            status_label = (
                "غیرفعال در این سالن"
                if membership_status != SalonMembershipStatus.ACTIVE
                else "غیرفعال"
            )
            status_badge_class = "bg-slate-200 text-slate-600"
        elif (upcoming_count or 0) > 0:
            status_label = "دارای نوبت آینده"
            status_badge_class = "bg-loomera-primarySoft text-loomera-primaryText"
        else:
            status_label = "آماده پذیرش"
            status_badge_class = "bg-emerald-100 text-emerald-700"

        avg_score = float(getattr(stylist, "avg_score_annotation", 0) or 0)
        if avg_score >= 4.5:
            rating_label = "عالی"
        elif avg_score >= 3:
            rating_label = "خوب"
        elif avg_score > 0:
            rating_label = "متوسط"
        else:
            rating_label = "بدون امتیاز"

        return {
            "id": stylist.user_id,
            "full_name": stylist.get_fullName(),
            "initial": (stylist.get_fullName()[:1] or "ا"),
            "expert": stylist.expert or "بدون تخصص ثبت‌شده",
            "mobile": stylist.user.mobile_number or "",
            "is_active": is_active_in_this_salon,
            "membership_status": membership_status,
            "status_label": status_label,
            "status_badge_class": status_badge_class,
            # فقط مربوط به همین سالن
            "services_count": services_count or 0,
            "services_count_label": to_persian_digits(services_count or 0),
            "upcoming_count": upcoming_count or 0,
            "upcoming_count_label": to_persian_digits(upcoming_count or 0),
            "avg_score": avg_score,
            "avg_score_label": (
                to_persian_digits(f"{avg_score:.1f}") if avg_score else "۰"
            ),
            "rating_label": rating_label,
            "service_names": service_names,
            "extra_services_count_label": to_persian_digits(extra_services_count),
            "has_more_services": extra_services_count > 0,
            "profile_image": (
                stylist.profile_image
                if getattr(stylist, "profile_image", None)
                else None
            ),
            "overview_url": reverse(
                "dashboards:stylist_overview",
                kwargs={"stylist_id": stylist.user.id},
            ),
            "edit_url": reverse(
                "dashboards:edit_stylist",
                kwargs={"stylist_id": stylist.user.id},
            ),
            "toggle_url": reverse(
                "dashboards:toggle_stylist_status",
                kwargs={"stylist_id": stylist.user.id},
            ),
            "can_end_collaboration": is_active_in_this_salon,
            "end_collaboration_url": reverse(
                "dashboards:end_stylist_collaboration",
                kwargs={"stylist_id": stylist.user.id},
            ),
        }

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        stylist_setup_handoff = _build_created_stylist_setup_handoff(
            request=request,
            salon=salon,
        )

        applied_sort_by = request.GET.get("sort_by", "name_asc")
        applied_expertise_ids = [
            int(eid) for eid in request.GET.getlist("expertise") if eid.isdigit()
        ]
        applied_status = request.GET.get("status_filter", "all")
        query = (request.GET.get("q") or "").strip()

        stylists_qs = _build_team_member_stylists_queryset(salon)

        if query:
            stylists_qs = stylists_qs.filter(
                Q(user__name__icontains=query)
                | Q(user__family__icontains=query)
                | Q(user__mobile_number__icontains=query)
                | Q(expert__icontains=query)
            )

        if applied_expertise_ids:
            stylists_qs = stylists_qs.filter(
                services_of_stylist__services_of_salon=salon,
                services_of_stylist__service_group__id__in=applied_expertise_ids,
            ).distinct()

        membership_status_map = _ensure_memberships_for_legacy_salon_staff(
            salon,
            actor=request.user,
            request=request,
        )

        active_membership_ids = SalonMembership.objects.filter(
            salon=salon,
            status=SalonMembershipStatus.ACTIVE,
            stylist__isnull=False,
        ).values_list("stylist_id", flat=True)

        if applied_status == "all":
            stylists_qs = stylists_qs.filter(
                is_active=True,
                pk__in=active_membership_ids,
            )
        elif applied_status == "active":
            stylists_qs = stylists_qs.filter(
                is_active=True, pk__in=active_membership_ids
            )
        elif applied_status == "inactive":
            inactive_membership_ids = (
                SalonMembership.objects.filter(
                    salon=salon,
                    stylist__isnull=False,
                )
                .exclude(status=SalonMembershipStatus.ACTIVE)
                .values_list("stylist_id", flat=True)
            )
            stylists_qs = stylists_qs.filter(
                Q(is_active=False) | Q(pk__in=inactive_membership_ids)
            )
        elif applied_status == "busy":
            stylists_qs = stylists_qs.filter(
                is_active=True, pk__in=active_membership_ids, upcoming_count__gt=0
            )

        sort_map = {
            "name_asc": ("user__family", "user__name"),
            "name_desc": ("-user__family", "-user__name"),
            "rating_asc": ("avg_score_annotation", "user__family"),
            "rating_desc": ("-avg_score_annotation", "user__family"),
            "newest": ("-user__pk",),
            "oldest": ("user__pk",),
            "upcoming_desc": ("-upcoming_count", "user__family"),
        }
        order_by_fields = sort_map.get(applied_sort_by, ("user__family", "user__name"))
        stylists_qs = stylists_qs.order_by(*order_by_fields)

        all_group_services = GroupServices.objects.filter(is_active=True).order_by(
            "group_title"
        )

        stylist_list = list(stylists_qs)
        for stylist in stylist_list:
            stylist.membership_status_for_salon = membership_status_map.get(
                stylist.pk,
                (
                    SalonMembershipStatus.ACTIVE
                    if stylist.is_active
                    else SalonMembershipStatus.PAUSED
                ),
            )

        stylist_cards = [
            self._serialize_stylist(stylist, salon) for stylist in stylist_list
        ]

        membership_request_cards = _build_manager_membership_requests(salon)

        sent_invite_cards = _build_manager_sent_invites(salon)

        today = timezone.localdate()
        upcoming_time_offs_raw = list(
            StylistTimeOff.objects.filter(
                stylist__stylists_of_salon=salon,
                date__gte=today,
            )
            .select_related("stylist__user")
            .order_by("date", "start_time")[:12]
        )
        upcoming_time_offs = []
        for item in upcoming_time_offs_raw:
            if item.start_time and item.end_time:
                time_label = (
                    f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
                )
            elif item.start_time:
                time_label = format_time_fa(item.start_time)
            else:
                time_label = "تمام روز"

            upcoming_time_offs.append(
                {
                    "stylist_name": item.stylist.get_fullName(),
                    "date_label": _safe_jalali_label(
                        item.date, formatter=format_jalali_with_weekday
                    ),
                    "time_label": time_label,
                    "reason": item.reason or "بدون توضیح",
                    "profile_url": reverse(
                        "dashboards:stylist_overview",
                        kwargs={"stylist_id": item.stylist.user.id},
                    ),
                }
            )

        service_coverage_raw = list(
            GroupServices.objects.filter(services_of_group__services_of_salon=salon)
            .annotate(
                services_count=Count(
                    "services_of_group",
                    filter=Q(services_of_group__services_of_salon=salon),
                    distinct=True,
                ),
                stylists_count=Count(
                    "services_of_group__stylists",
                    filter=Q(
                        services_of_group__stylists__stylists_of_salon=salon,
                        services_of_group__stylists__is_active=True,
                    ),
                    distinct=True,
                ),
            )
            .order_by("group_title")
            .distinct()
        )
        service_coverage = []
        for group in service_coverage_raw:
            has_coverage = (group.stylists_count or 0) > 0
            service_coverage.append(
                {
                    "group_title": group.group_title,
                    "services_count_label": to_persian_digits(
                        group.services_count or 0
                    ),
                    "stylists_count_label": to_persian_digits(
                        group.stylists_count or 0
                    ),
                    "coverage_label": (
                        "پوشش دارد" if has_coverage else "بدون پوشش"
                    ),
                    "coverage_badge_class": (
                        "bg-emerald-100 text-emerald-700"
                        if has_coverage
                        else "bg-amber-100 text-amber-700"
                    ),
                }
            )
        coverage_gap_count = sum(
            1 for group in service_coverage_raw if (group.stylists_count or 0) == 0
        )

        sort_labels = {
            "name_asc": "نام (الف تا ی)",
            "name_desc": "نام (ی تا الف)",
            "rating_asc": "کمترین امتیاز",
            "rating_desc": "بیشترین امتیاز",
            "newest": "جدیدترین",
            "oldest": "قدیمی‌ترین",
            "upcoming_desc": "بیشترین نوبت آینده",
        }

        status_labels = {
            "all": "همه وضعیت‌ها",
            "active": "فعال",
            "inactive": "غیرفعال",
            "busy": "دارای نوبت آینده",
        }

        active_filter_chips = []
        if query:
            active_filter_chips.append({"label": "جستجو", "value": query})
        if applied_status != "all":
            active_filter_chips.append(
                {"label": "وضعیت", "value": status_labels.get(applied_status, "همه")}
            )
        if applied_sort_by != "name_asc":
            active_filter_chips.append(
                {
                    "label": "مرتب‌سازی",
                    "value": sort_labels.get(applied_sort_by, "پیش‌فرض"),
                }
            )
        for group in all_group_services:
            if str(group.id) in [str(eid) for eid in applied_expertise_ids]:
                active_filter_chips.append(
                    {"label": "گروه خدمات", "value": group.group_title}
                )

        total_count = len(stylist_list)
        active_count = sum(
            1
            for stylist in stylist_list
            if stylist.is_active
            and stylist.membership_status_for_salon == SalonMembershipStatus.ACTIVE
        )
        busy_count = sum(
            1
            for stylist in stylist_list
            if stylist.is_active
            and stylist.membership_status_for_salon == SalonMembershipStatus.ACTIVE
            and (stylist.upcoming_count or 0) > 0
        )
        high_rated_count = sum(
            1 for stylist in stylist_list if (stylist.avg_score_annotation or 0) >= 4
        )

        context = {
            "salon": salon,
            "stylist_setup_handoff": stylist_setup_handoff,
            "stylists": stylist_list,
            "membership_request_cards": membership_request_cards,
            "stylist_cards": stylist_cards,
            "all_group_services": all_group_services,
            "sent_invite_cards": sent_invite_cards,
            "team_workspace": {
                "total": total_count,
                "active": active_count,
                "busy_upcoming": busy_count,
                "high_rated": high_rated_count,
                "pending_requests": len(membership_request_cards),
                "pending_requests_label": to_persian_digits(
                    len(membership_request_cards)
                ),
                "sent_invites": len(sent_invite_cards),
                "sent_invites_label": to_persian_digits(len(sent_invite_cards)),
                "upcoming_time_offs": upcoming_time_offs,
                "upcoming_time_off_count": len(upcoming_time_offs_raw),
                "upcoming_time_off_count_label": to_persian_digits(
                    len(upcoming_time_offs_raw)
                ),
                "service_coverage": service_coverage,
                "coverage_gap_count": coverage_gap_count,
                "coverage_gap_count_label": to_persian_digits(coverage_gap_count),
                "query": query,
                "result_count_label": f"{to_persian_digits(total_count)} عضو",
                "sort_label": sort_labels.get(applied_sort_by, "نام (الف تا ی)"),
                "active_filter_chips": active_filter_chips,
            },
            "applied_filters": {
                "sort_by": applied_sort_by,
                "expertise": [str(eid) for eid in applied_expertise_ids],
                "status_filter": applied_status,
                "q": query,
            },
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------------------
class ManagerCreateStylistInviteView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    def post(self, request, *args, **kwargs):
        return _create_manager_stylist_invite(request)


class ManagerCancelStylistInviteView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    def post(self, request, membership_id, *args, **kwargs):
        return _cancel_manager_stylist_invite(request, membership_id)


# -----------------------------------------------------------------------------------------
class ManagerEndStylistCollaborationView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    def post(self, request, stylist_id, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        stylist = get_object_or_404(
            Stylist.objects.select_related("user"),
            user_id=stylist_id,
        )

        membership = (
            SalonMembership.objects.select_related("salon", "stylist__user")
            .filter(
                salon=salon,
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            .first()
        )

        if not membership:
            messages.warning(
                request,
                "برای این متخصص عضویت فعال در این مجموعه پیدا نشد یا همکاری قبلاً پایان یافته است.",
            )
            return redirect("dashboards:team_member")

        stylist_name = stylist.get_fullName()

        future_appointments_count = _active_future_appointment_count_for_membership(
            membership
        )
        if future_appointments_count:
            messages.error(
                request,
                _membership_future_appointment_block_message(membership),
            )
            return redirect("dashboards:team_member")

        closed_membership = _close_membership_access(
            membership=membership,
            actor=request.user,
            request=request,
            new_status=SalonMembershipStatus.CANCELLED_BY_SALON,
            event_type="ended_by_manager",
            reason="اتمام همکاری متخصص توسط مدیر سالن",
            metadata={
                "ended_by_manager": True,
                "ended_by_stylist": False,
            },
        )

        try:
            _notify_stylist_about_collaboration_closed(
                membership=closed_membership,
                actor=request.user,
                ended_by_manager=True,
            )
        except Exception:
            logger.exception(
                "Failed to notify stylist about collaboration ended by manager. membership_id=%s",
                closed_membership.pk,
            )

        messages.success(
            request,
            f"همکاری {stylist_name} با این مجموعه پایان یافت و دسترسی‌های او بسته شد.",
        )
        return redirect("dashboards:team_member")


# -------------------------------------------------------------------------------------------
class ManagerMembershipRequestActionView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    def post(self, request, membership_id, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        membership = get_object_or_404(
            SalonMembership.objects.select_related("salon", "stylist__user"),
            pk=membership_id,
            salon=salon,
            status=SalonMembershipStatus.PENDING_ACCEPTANCE,
            stylist__isnull=False,
        )

        action = (request.POST.get("action") or "").strip()

        if action not in {"accept", "reject"}:
            messages.error(request, "عملیات انتخاب‌شده برای درخواست همکاری معتبر نیست.")
            return redirect("dashboards:team_member")

        if action == "accept":
            with transaction.atomic():
                change_membership_status(
                    membership=membership,
                    new_status=SalonMembershipStatus.ACTIVE,
                    actor=request.user,
                    reason="تایید درخواست همکاری متخصص توسط مدیر سالن",
                    request=request,
                )
                ensure_membership_permissions(membership)

                if (
                    membership.stylist
                    and not salon.stylists.filter(pk=membership.stylist.pk).exists()
                ):
                    salon.stylists.add(membership.stylist)
                if membership.stylist:
                    accepted_date = (
                        timezone.localtime(membership.accepted_at).date()
                        if membership.accepted_at
                        else timezone.localdate()
                    )

                    job_detail, _ = JobDetails.objects.get_or_create(
                        stylist=membership.stylist,
                        salon=salon,
                        defaults={
                            "start_date": accepted_date,
                            "employment_type": "",
                        },
                    )

                    if job_detail.start_date != accepted_date:
                        job_detail.start_date = accepted_date
                        job_detail.save(update_fields=["start_date"])

                    if not EmergencyInfo.objects.filter(
                        stylist=membership.stylist,
                    ).exists():
                        EmergencyInfo.objects.create(
                            stylist=membership.stylist,
                            emergency_contact="",
                            relationship="",
                            full_name="",
                        )
            try:
                _notify_stylist_about_membership_request_review(
                    membership=membership,
                    actor=request.user,
                    accepted=True,
                )
            except Exception:
                logger.exception(
                    "Failed to notify stylist about accepted membership request. membership_id=%s",
                    membership.pk,
                )

            messages.success(
                request,
                f"درخواست همکاری {membership.stylist.get_fullName()} تایید شد. حالا می‌توانید خدمات، شیفت‌ها و دسترسی‌های او را تنظیم کنید.",
            )
            return redirect("dashboards:team_member")

        membership = change_membership_status(
            membership=membership,
            new_status=SalonMembershipStatus.REJECTED,
            actor=request.user,
            reason="رد درخواست همکاری متخصص توسط مدیر سالن",
            request=request,
        )

        try:
            _notify_stylist_about_membership_request_review(
                membership=membership,
                actor=request.user,
                accepted=False,
            )
        except Exception:
            logger.exception(
                "Failed to notify stylist about rejected membership request. membership_id=%s",
                membership.pk,
            )

        messages.success(request, "درخواست همکاری متخصص رد شد.")
        return redirect("dashboards:team_member")


# ---------------------------------------------------------------------------------------------
class StylistOverviewView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/stylist_overview.html"

    def _serialize_upcoming_appointment(self, item):
        return {
            "customer_name": (
                item.order.customer.get_fullName()
                if item.order and item.order.customer
                else "مشتری ثبت نشده"
            ),
            "service_name": (
                item.service.service_name if item.service_id else "خدمت ثبت نشده"
            ),
            "date_label": _safe_jalali_label(
                item.date, formatter=format_jalali_with_weekday
            ),
            "time_label": format_time_fa(item.time) if item.time else "—",
            "status_label": getattr(item.order, "status", "") or "pending",
        }

    def _serialize_time_off(self, item):
        if item.start_time and item.end_time:
            time_label = (
                f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
            )
        elif item.start_time:
            time_label = format_time_fa(item.start_time)
        else:
            time_label = "تمام روز"

        return {
            "date_label": _safe_jalali_label(
                item.date, formatter=format_jalali_with_weekday
            ),
            "time_label": time_label,
            "reason": item.reason or "بدون توضیح",
        }

    def _serialize_schedule_row(self, row):
        return {
            "date_label": _safe_jalali_label(
                row.date, formatter=format_jalali_with_weekday
            ),
            "time_label": f"{format_time_fa(row.start_time)} تا {format_time_fa(row.end_time)}",
            "service_name": (
                row.service.service_name if row.service_id else "تمام خدمات"
            ),
        }

    def get(self, request, stylist_id):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        stylist = get_object_or_404(
            Stylist.objects.select_related("user").prefetch_related(
                "job_details__salon",
                "services_of_stylist__service_group",
                "stylists_of_salon",
            ),
            user_id=stylist_id,
            stylists_of_salon=salon,
        )

        today_jalali = JalaliDate.today()
        start_current_month = JalaliDate(
            today_jalali.year, today_jalali.month, 1
        ).todate()

        if today_jalali.month == 1:
            start_last_month = JalaliDate(today_jalali.year - 1, 12, 1).todate()
        else:
            start_last_month = JalaliDate(
                today_jalali.year, today_jalali.month - 1, 1
            ).todate()

        stats = OrderDetail.objects.filter(
            salon=salon,
            stylist=stylist,
            order__is_finally=True,
            order__stylist_approved=True,
            date__gte=start_last_month,
        ).aggregate(
            current_sales=Coalesce(
                Sum("price", filter=Q(date__gte=start_current_month)),
                Value(0),
            ),
            current_appointments=Count("id", filter=Q(date__gte=start_current_month)),
            current_unique_clients=Count(
                "order__customer",
                distinct=True,
                filter=Q(date__gte=start_current_month),
            ),
            prev_sales=Coalesce(
                Sum(
                    "price",
                    filter=Q(date__lt=start_current_month, date__gte=start_last_month),
                ),
                Value(0),
            ),
            prev_appointments=Count(
                "id",
                filter=Q(date__lt=start_current_month, date__gte=start_last_month),
            ),
            prev_unique_clients=Count(
                "order__customer",
                distinct=True,
                filter=Q(date__lt=start_current_month, date__gte=start_last_month),
            ),
        )

        sales_change = calculate_percentage_change(
            stats["current_sales"], stats["prev_sales"]
        )
        appointments_change = calculate_percentage_change(
            stats["current_appointments"],
            stats["prev_appointments"],
        )
        clients_change = calculate_percentage_change(
            stats["current_unique_clients"],
            stats["prev_unique_clients"],
        )

        upcoming_appointments_qs = (
            OrderDetail.objects.filter(
                salon=salon,
                stylist=stylist,
                date__gte=timezone.localdate(),
            )
            .exclude(order__status="cancelled")
            .select_related("service", "order__customer__user")
            .order_by("date", "time", "id")[:5]
        )

        upcoming_time_offs_qs = list(
            StaffLeaveRequest.objects.filter(
                stylist=stylist,
                salon=salon,
                status=StaffLeaveRequest.Status.APPROVED,
                date__gte=timezone.localdate(),
            ).order_by("date", "start_time")[:5]
        )
        schedule_rows_qs = list(
            StylistSchedule.objects.filter(
                stylist=stylist, salon=salon, date__gte=timezone.localdate()
            )
            .select_related("service")
            .order_by("date", "start_time")[:7]
        )

        job_detail = stylist.job_details.filter(salon=salon).first()
        current_salon_services_qs = (
            stylist.services_of_stylist.filter(services_of_salon=salon)
            .prefetch_related("service_group")
            .distinct()
        )

        service_groups = sorted(
            {
                group.group_title
                for service in current_salon_services_qs
                for group in service.service_group.all()
            }
        )

        current_salon_services_count = current_salon_services_qs.count()
        current_salon_services = list(
            current_salon_services_qs.order_by("service_name")
        )
        monthly_workload = stats["current_appointments"] or 0
        workload_hint = "سبک"
        if monthly_workload >= 25:
            workload_hint = "پُرتقاضا"
        elif monthly_workload >= 10:
            workload_hint = "متعادل"

        avg_score_value = float(stylist.get_average_score() or 0)
        avg_score_label = (
            to_persian_digits(f"{avg_score_value:.1f}") if avg_score_value else "۰"
        )
        rating_label = "بدون امتیاز"
        if avg_score_value >= 4.5:
            rating_label = "عالی"
        elif avg_score_value >= 3:
            rating_label = "خوب"
        elif avg_score_value > 0:
            rating_label = "متوسط"

        member_status_label = "غیرفعال"
        member_status_badge_class = "bg-slate-200 text-slate-600"
        if stylist.is_active and upcoming_appointments_qs.count() > 0:
            member_status_label = "دارای نوبت آینده"
            member_status_badge_class = (
                "bg-loomera-primarySoft text-loomera-primaryText"
            )
        elif stylist.is_active:
            member_status_label = "فعال"
            member_status_badge_class = "bg-emerald-100 text-emerald-700"

        focus_items = []
        if not stylist.is_active:
            focus_items.append(
                {
                    "title": "این عضو تیم غیرفعال است",
                    "value": "نیازمند بررسی",
                    "description": "تا زمانی که عضو فعال نشود، در  برنامه ریزی و رزروها پوشش واقعی نخواهد داشت.",
                    "tone": "warning",
                }
            )
        if current_salon_services_count == 0:
            focus_items.append(
                {
                    "title": "خدمتی به این عضو تیم متصل نشده",
                    "value": "قابل بهبود",
                    "description": "برای استفاده مؤثر در رزروها بهتر است خدمات قابل پوشش این عضو مشخص شوند.",
                    "tone": "primary",
                }
            )
        if len(schedule_rows_qs) == 0:
            focus_items.append(
                {
                    "title": "شیفت آینده‌ای ثبت نشده",
                    "value": " برنامه ریزی",
                    "description": "برای دید بهتر ظرفیت این عضو، بهتر است شیفت‌های آینده ثبت یا بازبینی شوند.",
                    "tone": "neutral",
                }
            )
        if len(upcoming_time_offs_qs) > 0:
            focus_items.append(
                {
                    "title": "مرخصی آینده ثبت شده",
                    "value": to_persian_digits(len(upcoming_time_offs_qs)),
                    "description": "برای جلوگیری از تداخل ظرفیت، مرخصی‌های ثبت‌شده این عضو را در  برنامه ریزی در نظر بگیر.",
                    "tone": "primary",
                }
            )

        if not focus_items:
            focus_items = [
                {
                    "title": "پروفایل این عضو تیم در وضعیت خوبی است",
                    "value": "آماده",
                    "description": "خدمات، عملکرد و برنامه آینده این عضو برای مدیریت روزانه تصویر مناسبی ارائه می‌کند.",
                    "tone": "success",
                }
            ]

        edit_stylist_url = reverse(
            "dashboards:edit_stylist", kwargs={"stylist_id": stylist.user.id}
        )
        scheduled_shifts_url = reverse("dashboards:scheduled_shifts")
        team_member_url = reverse("dashboards:team_member")
        set_regular_shifts_url = reverse(
            "dashboards:set_regular_shifts",
            kwargs={"stylist_id": stylist.user.id, "salon_id": salon.id},
        )

        context = {
            "salon": salon,
            "stylist": stylist,
            "job_detail": job_detail,
            "service_groups": service_groups,
            "current_salon_services": current_salon_services,
            "workload_hint": workload_hint,
            "upcoming_appointments": [
                self._serialize_upcoming_appointment(item)
                for item in upcoming_appointments_qs
            ],
            "upcoming_time_offs": [
                self._serialize_time_off(item) for item in upcoming_time_offs_qs
            ],
            "schedule_rows": [
                self._serialize_schedule_row(item) for item in schedule_rows_qs
            ],
            "stats": {
                "sales": _dashboard_currency(stats["current_sales"]),
                "sales_change": sales_change,
                "appointments": to_persian_digits(stats["current_appointments"]),
                "appointments_change": appointments_change,
                "clients": to_persian_digits(stats["current_unique_clients"]),
                "clients_change": clients_change,
                "avg_score": avg_score_label,
                "rating_label": rating_label,
            },
            "stylist_workspace": {
                "member_status_label": member_status_label,
                "member_status_badge_class": member_status_badge_class,
                "job_start_label": (
                    _safe_jalali_label(job_detail.start_date)
                    if job_detail and job_detail.start_date
                    else "—"
                ),
                "employment_type_label": (
                    job_detail.employment_type
                    if job_detail and job_detail.employment_type
                    else "ثبت نشده"
                ),
                "service_count_label": to_persian_digits(current_salon_services_count),
                "group_count_label": to_persian_digits(len(service_groups)),
                "upcoming_appointments_count": to_persian_digits(
                    len(upcoming_appointments_qs)
                ),
                "upcoming_time_off_count": to_persian_digits(
                    len(upcoming_time_offs_qs)
                ),
                "schedule_count": to_persian_digits(len(schedule_rows_qs)),
                "focus_items": focus_items,
                "edit_url": edit_stylist_url,
                "scheduled_shifts_url": scheduled_shifts_url,
                "team_member_url": team_member_url,
                "set_regular_shifts_url": set_regular_shifts_url,
            },
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------------------------
logger = logging.getLogger(__name__)

STYLIST_FORM_GROUP_SERVICES_ATTR = "_stylist_form_salon_services"


def _build_salon_service_group_cards(*, salon):
    """Build stylist-form service groups with a fixed two-query budget.

    The group query loads only groups connected to services in the active
    salon. A single scoped prefetch then loads the services required by all
    cards.

    Inactive services intentionally remain included because the existing
    add/edit forms did not filter them out.
    """

    salon_services = (
        Services.objects.filter(
            services_of_salon=salon,
        )
        .order_by(
            "service_name",
            "pk",
        )
        .distinct()
    )

    groups = list(
        GroupServices.objects.filter(
            services_of_group__services_of_salon=salon,
        )
        .prefetch_related(
            Prefetch(
                "services_of_group",
                queryset=salon_services,
                to_attr=STYLIST_FORM_GROUP_SERVICES_ATTR,
            )
        )
        .distinct()
        .order_by(
            "group_title",
            "pk",
        )
    )

    cards = []

    for group in groups:
        services = list(
            getattr(
                group,
                STYLIST_FORM_GROUP_SERVICES_ATTR,
                [],
            )
        )

        if not services:
            continue

        cards.append(
            {
                "id": group.pk,
                "title": group.group_title,
                "services": services,
                "services_count_label": (to_persian_digits(len(services))),
            }
        )

    return cards


class AddStylistView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/add_stylist.html"

    def _get_salon(self, request):
        salon_manager = get_object_or_404(SalonManager, user=request.user)
        return get_object_or_404(Salon, salon_manager=salon_manager)

    def _get_service_group_cards(self, salon):
        return _build_salon_service_group_cards(
            salon=salon,
        )

    def _extract_selected_service_ids(self, request):
        selected_ids = []
        raw_json = (request.POST.get("selected_services_input") or "").strip()

        if raw_json:
            try:
                selected_ids = [str(int(item)) for item in json.loads(raw_json)]
            except (ValueError, TypeError, json.JSONDecodeError):
                selected_ids = []

        checkbox_ids = [
            str(int(item))
            for item in request.POST.getlist("selected_services")
            if str(item).isdigit()
        ]

        if checkbox_ids:
            selected_ids = checkbox_ids

        # dedupe while preserving order
        selected_ids = list(dict.fromkeys(selected_ids))
        return selected_ids

    def _build_context(
        self,
        *,
        salon,
        user_form,
        profile_form,
        job_form,
        emergency_form,
        selected_service_ids=None,
    ):
        selected_service_ids = selected_service_ids or []
        service_group_cards = self._get_service_group_cards(salon)

        total_services_count = sum(
            len(group["services"]) for group in service_group_cards
        )

        selected_groups_count = 0
        selected_set = set(selected_service_ids)
        for group in service_group_cards:
            group_service_ids = {str(service.id) for service in group["services"]}
            if group_service_ids.intersection(selected_set):
                selected_groups_count += 1

        focus_items = []
        if not service_group_cards:
            focus_items.append(
                {
                    "title": "برای این مجموعه هنوز خدمت فعالی ثبت نشده",
                    "value": "نیازمند اقدام",
                    "description": "برای اینکه عضو جدید سریع‌تر وارد  برنامه ریزی واقعی شود، بهتر است ابتدا منوی خدمات مجموعه کامل باشد.",
                    "tone": "warning",
                }
            )
        else:
            focus_items.append(
                {
                    "title": "بعد از ثبت عضو می‌توانی مستقیم وارد  برنامه ریزی شوی",
                    "value": "Flow",
                    "description": "بعد از ساخت عضو تیم، می‌توانی از صفحه اعضا، شیفت‌ها یا شیفت منظم ادامه setup را انجام بدهی.",
                    "tone": "primary",
                }
            )

        if selected_service_ids:
            focus_items.append(
                {
                    "title": "برای این عضو خدمت انتخاب شده است",
                    "value": to_persian_digits(len(selected_service_ids)),
                    "description": "این خدمات بعد از ثبت به عضو تیم متصل می‌شوند و برای coverage و  برنامه ریزی قابل استفاده خواهند بود.",
                    "tone": "success",
                }
            )
        else:
            focus_items.append(
                {
                    "title": "انتخاب خدمت اختیاری است اما توصیه می‌شود",
                    "value": "قابل بهبود",
                    "description": "اگر از همین حالا خدمات عضو را مشخص کنی، بعداً در تقویم و  برنامه ریزی اصطکاک کمتری خواهی داشت.",
                    "tone": "neutral",
                }
            )

        return {
            "salon": salon,
            "user_form": user_form,
            "profile_form": profile_form,
            "job_form": job_form,
            "emergency_form": emergency_form,
            "service_group_cards": service_group_cards,
            "selected_service_ids": selected_service_ids,
            "add_stylist_workspace": {
                "group_count_label": to_persian_digits(len(service_group_cards)),
                "services_count_label": to_persian_digits(total_services_count),
                "selected_services_count_label": to_persian_digits(
                    len(selected_service_ids)
                ),
                "selected_groups_count_label": to_persian_digits(selected_groups_count),
                "focus_items": focus_items,
                "team_member_url": reverse("dashboards:team_member"),
                "scheduled_shifts_url": reverse("dashboards:scheduled_shifts"),
                "service_menu_url": reverse("dashboards:service_menu"),
            },
        }

    def get(self, request):
        salon = self._get_salon(request)

        context = self._build_context(
            salon=salon,
            user_form=StylistUserForm(allow_existing_mobile=True),
            profile_form=StylistProfileForm(),
            job_form=JobDetailsForm(),
            emergency_form=EmergencyInfoForm(),
            selected_service_ids=[],
        )
        return render(request, self.template_name, context)

    def post(self, request):
        salon = self._get_salon(request)

        user_form = StylistUserForm(request.POST, allow_existing_mobile=True)
        profile_form = StylistProfileForm(request.POST, request.FILES)
        job_form = JobDetailsForm(request.POST)
        emergency_form = EmergencyInfoForm(request.POST)
        selected_service_ids = self._extract_selected_service_ids(request)

        forms_valid = all(
            [
                user_form.is_valid(),
                profile_form.is_valid(),
                job_form.is_valid(),
                emergency_form.is_valid(),
            ]
        )

        if forms_valid:
            try:
                with transaction.atomic():
                    selected_services = list(
                        Services.objects.filter(
                            id__in=selected_service_ids,
                            services_of_salon=salon,
                        ).distinct()
                    )
                    stylist_data = dict(profile_form.cleaned_data)
                    stylist, membership, created_user = invite_or_attach_stylist(
                        salon=salon,
                        user_data=user_form.cleaned_data,
                        stylist_data=stylist_data,
                        job_data=job_form.cleaned_data,
                        selected_services=selected_services,
                        actor=request.user,
                        request=request,
                    )
                    membership = _ensure_active_staff_membership_for_salon(
                        salon,
                        stylist,
                        actor=request.user,
                        request=request,
                    )

                    emergency_name = (
                        emergency_form.cleaned_data.get("emergency_contact_name", "") or ""
                    ).strip()
                    emergency_family = (
                        emergency_form.cleaned_data.get("emergency_contact_family", "") or ""
                    ).strip()
                    phone = (
                        emergency_form.cleaned_data.get("emergency_phone", "") or ""
                    ).strip()
                    relationship = (
                        emergency_form.cleaned_data.get("relationship", "") or ""
                    ).strip()

                    if any([emergency_name, emergency_family, phone, relationship]):
                        emergency = emergency_form.save(commit=False)
                        emergency.stylist = stylist
                        emergency.full_name = f"{emergency_name} {emergency_family}".strip()
                        emergency.emergency_contact = phone
                        emergency.relationship = relationship
                        emergency.save()

                if selected_services:
                    messages.success(
                        request,
                        "عضو تیم و خدمات او با موفقیت ثبت شد.",
                    )
                else:
                    messages.success(
                        request,
                        "عضو تیم با موفقیت ثبت شد.",
                    )
                team_member_url = reverse("dashboards:team_member")
                return redirect(
                    f"{team_member_url}?created_stylist={stylist.user_id}"
                )

            except IntegrityError:
                messages.error(
                    request,
                    "اطلاعات این عضو با داده‌های موجود تداخل دارد. شماره موبایل و اطلاعات ثبت‌شده را بررسی کن.",
                )
            except Exception as e:
                logger.error(f"Error creating stylist: {str(e)}", exc_info=True)
                messages.error(
                    request,
                    "در ثبت عضو تیم خطایی رخ داد. لطفاً اطلاعات فرم را دوباره بررسی کن.",
                )
        else:
            messages.error(
                request,
                "بعضی فیلدهای فرم نیاز به اصلاح دارند. بخش‌های دارای خطا را بررسی کن.",
            )

        context = self._build_context(
            salon=salon,
            user_form=user_form,
            profile_form=profile_form,
            job_form=job_form,
            emergency_form=emergency_form,
            selected_service_ids=selected_service_ids,
        )
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class EditStylistView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/edit_stylist.html"

    def _job_form_initial(self, job_detail):
        return {
            "start_date": (
                format_jalali_numeric(job_detail.start_date)
                if job_detail and job_detail.start_date
                else ""
            ),
            "end_date": (
                format_jalali_numeric(job_detail.end_date)
                if job_detail and job_detail.end_date
                else ""
            ),
        }

    def _get_membership(self, salon, stylist):
        return (
            SalonMembership.objects.filter(
                salon=salon,
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            .order_by("-accepted_at", "-id")
            .first()
        )

    def _get_membership_permissions(self, membership):
        if not membership:
            return None
        return ensure_membership_permissions(membership)

    def _save_membership_permissions_from_post(self, *, membership, request):
        if not membership:
            return None

        permissions = ensure_membership_permissions(membership)

        permission_fields = [
            "can_complete_appointments",
            "can_create_own_bookings",
            "can_view_own_clients",
            "can_view_client_phone",
            "can_view_own_finance",
            "can_request_payout",
            "can_request_leave",
            "can_manage_own_schedule",
            "can_manage_own_portfolio",
            "can_submit_posts",
            "can_submit_stories",
        ]

        for field_name in permission_fields:
            setattr(permissions, field_name, request.POST.get(field_name) == "on")

        permissions.save(update_fields=[*permission_fields, "updated_at"])
        return permissions

    def _is_request_added_member(self, membership):
        metadata = getattr(membership, "metadata", {}) or {}
        return bool(metadata.get("requested_by_stylist"))

    def _get_job_detail(self, stylist, salon):
        job_detail = (
            JobDetails.objects.filter(stylist=stylist, salon=salon)
            .order_by("id")
            .first()
        )

        if job_detail:
            return job_detail

        return JobDetails.objects.create(
            stylist=stylist,
            salon=salon,
            start_date=timezone.localdate(),
            employment_type="",
        )

    def _get_emergency_info(self, stylist):
        return EmergencyInfo.objects.filter(stylist=stylist).order_by("id").first()

    def _lock_form_fields(self, *forms):
        for form in forms:
            if not form:
                continue

            for field in form.fields.values():
                field.disabled = True

                css_class = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = (
                    f"{css_class} cursor-not-allowed bg-slate-100 text-slate-500"
                ).strip()
                field.widget.attrs["disabled"] = "disabled"

    def _lock_job_start_date(self, job_form):
        field = job_form.fields.get("start_date")
        if not field:
            return

        field.disabled = True
        field.required = False
        field.widget.attrs["readonly"] = "readonly"
        field.widget.attrs["disabled"] = "disabled"

        css_class = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = (
            f"{css_class} cursor-not-allowed bg-slate-100 text-slate-500"
        ).strip()
        field.widget.attrs["title"] = (
            "تاریخ شروع همکاری برابر تاریخ تایید درخواست است و قابل ویرایش نیست."
        )

    def _get_salon(self, request):
        salon_manager = get_object_or_404(SalonManager, user=request.user)
        return get_object_or_404(Salon, salon_manager=salon_manager)

    def _get_stylist(self, salon, stylist_id):
        return get_object_or_404(
            Stylist.objects.select_related("user").prefetch_related(
                "services_of_stylist"
            ),
            user_id=stylist_id,
            stylists_of_salon=salon,
        )

    def _get_job_detail(self, stylist, salon):
        job_detail = (
            JobDetails.objects.filter(stylist=stylist, salon=salon)
            .order_by("id")
            .first()
        )

        if job_detail:
            return job_detail

        return JobDetails.objects.create(
            stylist=stylist,
            salon=salon,
            start_date=timezone.localdate(),
            employment_type="",
        )

    def _get_emergency_info(self, stylist):
        emergency_info = (
            EmergencyInfo.objects.filter(stylist=stylist).order_by("id").first()
        )

        if emergency_info:
            return emergency_info

        return EmergencyInfo.objects.create(
            stylist=stylist,
            emergency_contact="",
            relationship="",
            full_name="",
        )

    def _get_service_group_cards(self, salon):
        return _build_salon_service_group_cards(
            salon=salon,
        )
    
    def _extract_selected_service_ids(self, request):
        selected_ids = []
        raw_json = (request.POST.get("selected_services_input") or "").strip()

        if raw_json:
            try:
                selected_ids = [str(int(item)) for item in json.loads(raw_json)]
            except (ValueError, TypeError, json.JSONDecodeError):
                selected_ids = []

        checkbox_ids = [
            str(int(item))
            for item in request.POST.getlist("selected_services")
            if str(item).isdigit()
        ]

        if checkbox_ids:
            selected_ids = checkbox_ids

        return list(dict.fromkeys(selected_ids))

    def _get_selected_service_ids_for_salon(self, stylist, salon):
        return [
            str(service_id)
            for service_id in stylist.services_of_stylist.filter(
                services_of_salon=salon
            ).values_list("id", flat=True)
        ]

    def _sync_stylist_services_for_salon(self, *, stylist, salon, selected_service_ids):
        """
        فقط خدمات همین سالن را برای متخصص تغییر می‌دهد.
        خدمات سالن‌های دیگر متخصص دست‌نخورده باقی می‌مانند.
        """

        selected_services_for_current_salon = list(
            Services.objects.filter(
                id__in=selected_service_ids,
                services_of_salon=salon,
                is_active=True,
            ).distinct()
        )

        services_from_other_salons = list(
            stylist.services_of_stylist.exclude(
                services_of_salon=salon,
            ).distinct()
        )

        stylist.services_of_stylist.set(
            services_from_other_salons + selected_services_for_current_salon
        )

    def _split_emergency_full_name(self, full_name):
        full_name = (full_name or "").strip()
        if not full_name:
            return "", ""

        parts = full_name.split()
        if len(parts) == 1:
            return parts[0], ""

        return parts[0], " ".join(parts[1:])

    def _split_emergency_phone(self, phone):
        phone = (phone or "").strip()
        prefixes = ["+98", "+1", "+44"]

        for prefix in prefixes:
            if phone.startswith(prefix):
                return prefix, phone[len(prefix) :].strip()

        return "+98", phone

    def _build_context(
        self,
        *,
        salon,
        stylist,
        user_form,
        profile_form,
        job_form,
        emergency_form,
        selected_service_ids=None,
        membership=None,
    ):
        selected_service_ids = selected_service_ids or []
        service_group_cards = self._get_service_group_cards(salon)

        total_services_count = sum(
            len(group["services"]) for group in service_group_cards
        )

        selected_groups_count = 0
        selected_set = set(selected_service_ids)
        for group in service_group_cards:
            group_service_ids = {str(service.id) for service in group["services"]}
            if group_service_ids.intersection(selected_set):
                selected_groups_count += 1

        if stylist.is_active:
            member_status_label = "فعال"
            member_status_badge_class = "bg-emerald-100 text-emerald-700"
        else:
            member_status_label = "غیرفعال"
            member_status_badge_class = "bg-slate-200 text-slate-600"

        focus_items = []
        if not service_group_cards:
            focus_items.append(
                {
                    "title": "برای این مجموعه هنوز خدمت فعالی ثبت نشده",
                    "value": "نیازمند اقدام",
                    "description": "اگر بخواهی coverage عضو را دقیق‌تر مدیریت کنی، بهتر است ابتدا منوی خدمات مجموعه کامل باشد.",
                    "tone": "warning",
                }
            )
        if selected_service_ids:
            focus_items.append(
                {
                    "title": "خدمات عضو تیم آماده بازبینی هستند",
                    "value": to_persian_digits(len(selected_service_ids)),
                    "description": " پس از ذخیره، این عضو با همین خدمات قابل ارائه در برنامه‌ریزی و بخش اعضای تیم نمایش داده می‌شود.",
                    "tone": "success",
                }
            )
        else:
            focus_items.append(
                {
                    "title": "هیچ خدمتی برای این عضو انتخاب نشده",
                    "value": "قابل بهبود",
                    "description": "عضو بدون خدمت هم ذخیره می‌شود، اما برای برنامه‌ریزی و رزرو بهتر است coverage او مشخص باشد.",
                    "tone": "primary",
                }
            )
        is_request_added_member = self._is_request_added_member(membership)

        membership_permissions = self._get_membership_permissions(membership)

        return {
            "salon": salon,
            "stylist": stylist,
            "user_form": user_form,
            "profile_form": profile_form,
            "job_form": job_form,
            "emergency_form": emergency_form,
            "service_group_cards": service_group_cards,
            "selected_service_ids": selected_service_ids,
            "membership_permissions": membership_permissions,
            "edit_stylist_workspace": {
                "member_status_label": member_status_label,
                "member_status_badge_class": member_status_badge_class,
                "group_count_label": to_persian_digits(len(service_group_cards)),
                "services_count_label": to_persian_digits(total_services_count),
                "selected_services_count_label": to_persian_digits(
                    len(selected_service_ids)
                ),
                "selected_groups_count_label": to_persian_digits(selected_groups_count),
                "focus_items": focus_items,
                "team_member_url": reverse("dashboards:team_member"),
                "scheduled_shifts_url": reverse("dashboards:scheduled_shifts"),
                "service_menu_url": reverse("dashboards:service_menu"),
                "profile_url": reverse(
                    "dashboards:stylist_overview",
                    kwargs={"stylist_id": stylist.user.id},
                ),
                "is_request_added_member": is_request_added_member,
                "personal_fields_locked": is_request_added_member,
                "personal_fields_lock_message": (
                    "این متخصص با درخواست خودش به سالن اضافه شده است؛ اطلاعات شخصی، رزومه و تماس اضطراری فقط توسط خود متخصص قابل ویرایش است."
                    if is_request_added_member
                    else ""
                ),
                "start_date_lock_message": (
                    "تاریخ شروع همکاری برابر تاریخ تایید درخواست است و قابل ویرایش نیست."
                    if is_request_added_member
                    else ""
                ),
            },
        }

    def get(self, request, stylist_id):
        salon = self._get_salon(request)
        stylist = self._get_stylist(salon, stylist_id)

        membership = self._get_membership(salon, stylist)
        is_request_added_member = self._is_request_added_member(membership)

        job_detail = self._get_job_detail(stylist, salon)
        emergency_info = self._get_emergency_info(stylist)
        emergency_name, emergency_family = self._split_emergency_full_name(
            emergency_info.full_name
        )
        emergency_prefix, emergency_phone = self._split_emergency_phone(
            emergency_info.emergency_contact
        )

        user_form = StylistUserForm(instance=stylist.user)
        profile_form = StylistProfileForm(instance=stylist)
        job_form = JobDetailsForm(
            instance=job_detail,
            initial=self._job_form_initial(job_detail),
        )
        emergency_form = EmergencyInfoForm(
            instance=emergency_info,
            initial={
                "emergency_contact_name": emergency_name,
                "emergency_contact_family": emergency_family,
                "emergency_phone_prefix": emergency_prefix,
                "emergency_phone": emergency_phone,
            },
        )
        if is_request_added_member:
            self._lock_form_fields(user_form, profile_form, emergency_form)
            self._lock_job_start_date(job_form)

        selected_service_ids = self._get_selected_service_ids_for_salon(
            stylist,
            salon,
        )

        context = self._build_context(
            salon=salon,
            stylist=stylist,
            user_form=user_form,
            profile_form=profile_form,
            job_form=job_form,
            emergency_form=emergency_form,
            selected_service_ids=selected_service_ids,
            membership=membership,
        )
        return render(request, self.template_name, context)

    def post(self, request, stylist_id):
        salon = self._get_salon(request)
        stylist = self._get_stylist(salon, stylist_id)

        membership = self._get_membership(salon, stylist)
        is_request_added_member = self._is_request_added_member(membership)

        job_detail = self._get_job_detail(stylist, salon)
        emergency_info = self._get_emergency_info(stylist)

        selected_service_ids = self._extract_selected_service_ids(request)

        if is_request_added_member:
            user_form = StylistUserForm(instance=stylist.user)
            profile_form = StylistProfileForm(instance=stylist)
            emergency_form = EmergencyInfoForm(instance=emergency_info)
            job_form = JobDetailsForm(
                request.POST,
                instance=job_detail,
                initial=self._job_form_initial(job_detail),
            )
            self._lock_form_fields(user_form, profile_form, emergency_form)
            self._lock_job_start_date(job_form)

            forms_valid = job_form.is_valid()
        else:
            user_form = StylistUserForm(request.POST, instance=stylist.user)
            profile_form = StylistProfileForm(
                request.POST,
                request.FILES,
                instance=stylist,
            )
            job_form = JobDetailsForm(
                request.POST,
                instance=job_detail,
                initial=self._job_form_initial(job_detail),
            )
            emergency_form = EmergencyInfoForm(request.POST, instance=emergency_info)

            forms_valid = all(
                [
                    user_form.is_valid(),
                    profile_form.is_valid(),
                    job_form.is_valid(),
                    emergency_form.is_valid(),
                ]
            )

        if forms_valid:
            try:
                with transaction.atomic():
                    if not is_request_added_member:
                        user_obj = user_form.save()

                        stylist = profile_form.save(commit=False)
                        stylist.user = user_obj
                        if not stylist.calendar_color:
                            stylist.calendar_color = "#6d5ef7"
                        stylist.save()

                        emergency = emergency_form.save(commit=False)
                        emergency.stylist = stylist
                        emergency.full_name = (
                            f"{emergency_form.cleaned_data.get('emergency_contact_name', '')} "
                            f"{emergency_form.cleaned_data.get('emergency_contact_family', '')}"
                        ).strip()

                        prefix = (
                            emergency_form.cleaned_data.get(
                                "emergency_phone_prefix", ""
                            )
                            or ""
                        ).strip()
                        phone = (
                            emergency_form.cleaned_data.get("emergency_phone", "") or ""
                        ).strip()
                        relationship = (
                            emergency_form.cleaned_data.get("relationship", "") or ""
                        ).strip()

                        emergency.emergency_contact = (
                            f"{prefix}{phone}" if phone else ""
                        )
                        emergency.relationship = relationship
                        emergency.save()

                    job = job_form.save(commit=False)
                    job.stylist = stylist
                    job.salon = salon

                    if is_request_added_member:
                        # متخصصی که با درخواست خودش تایید شده، تاریخ شروعش همان تاریخ تایید است.
                        # مدیر نباید بتواند این تاریخ را تغییر دهد.
                        accepted_date = (
                            timezone.localtime(membership.accepted_at).date()
                            if membership and membership.accepted_at
                            else job_detail.start_date or timezone.localdate()
                        )
                        job.start_date = accepted_date

                    job.save()

                    self._sync_stylist_services_for_salon(
                        stylist=stylist,
                        salon=salon,
                        selected_service_ids=selected_service_ids,
                    )

                    self._save_membership_permissions_from_post(
                        membership=membership,
                        request=request,
                    )

                if is_request_added_member:
                    messages.success(
                        request,
                        "اطلاعات همکاری، خدمات و تنظیمات قابل مدیریت توسط سالن ذخیره شد. اطلاعات شخصی متخصص تغییر نکرد.",
                    )
                else:
                    messages.success(request, "اطلاعات عضو تیم با موفقیت ویرایش شد.")

                return redirect("dashboards:team_member")

            except IntegrityError:
                messages.error(
                    request,
                    "اطلاعات این عضو با داده‌های موجود تداخل دارد. شماره موبایل و اطلاعات ثبت‌شده را بررسی کن.",
                )
            except Exception as e:
                logger.error(f"Error updating stylist: {str(e)}", exc_info=True)
                messages.error(
                    request,
                    "در ویرایش عضو تیم خطایی رخ داد. لطفاً اطلاعات فرم را دوباره بررسی کن.",
                )
        else:
            messages.error(
                request,
                "بعضی فیلدهای فرم نیاز به اصلاح دارند. بخش‌های دارای خطا را بررسی کن.",
            )

        context = self._build_context(
            salon=salon,
            stylist=stylist,
            user_form=user_form,
            profile_form=profile_form,
            job_form=job_form,
            emergency_form=emergency_form,
            selected_service_ids=selected_service_ids,
            membership=membership,
        )
        return render(request, self.template_name, context)


# ----------------------------------------------------------------------------------------------------------------
def _get_manager_owned_salon_for_services(request):
    salon_manager = getattr(request.user, "salon_manager_profile", None)
    if salon_manager is None:
        return None, JsonResponse({"error": "access_denied"}, status=403)

    salons = Salon.objects.filter(
        salon_manager=salon_manager,
        is_active=True,
    )

    requested_salon_id = (request.GET.get("salon_id") or "").strip()
    if requested_salon_id:
        if not requested_salon_id.isdigit():
            return None, JsonResponse({"error": "invalid_salon_id"}, status=400)

        salons = salons.filter(pk=int(requested_salon_id))
        salon = salons.first()
        if salon is None:
            return None, JsonResponse({"error": "access_denied"}, status=403)

        return salon, None

    salon = salons.order_by("pk").first()
    if salon is None:
        return None, JsonResponse({"error": "salon_not_found"}, status=404)

    return salon, None


@require_GET
@login_required
def get_services_list(request):
    """
    Return active services for a salon owned by the authenticated salon manager.

    The optional salon_id query parameter is accepted only when that salon belongs
    to the current manager. This keeps the endpoint safe for multi-salon accounts.
    """
    salon, error_response = _get_manager_owned_salon_for_services(request)
    if error_response is not None:
        return error_response

    try:
        salon_services = salon.services.filter(is_active=True).prefetch_related(
            "service_group",
            "service_prices",
        )

        services_data = []
        for service in salon_services:
            first_group = service.service_group.first()
            group_id_for_service = None
            group_title_for_service = "سایر خدمات"

            if first_group:
                group_id_for_service = first_group.id
                group_title_for_service = first_group.group_title

            first_price = service.service_prices.first()
            service_data_item = {
                "id": service.id,
                "name": service.service_name,
                "duration": service.duration_minutes,
                "price": (
                    first_price.price
                    if first_price is not None
                    else (getattr(service, "base_price", 0) or None)
                ),
                "description": service.description if service.description else "",
                "groupId": group_id_for_service,
                "groupTitle": group_title_for_service,
            }
            services_data.append(service_data_item)

        return JsonResponse({"services": services_data})

    except Exception as exc:
        logger.error("Error in get_services_list", exc_info=exc)
        return JsonResponse({"error": "services_list_unavailable"}, status=500)


# ----------------------------------------------------------------------------------------------------------------
# ثابت‌های مورد نیاز برای نمایش تاریخ شمسی
MONTHS_FA = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]
PERSIAN_WEEKDAY_NAMES = [
    "شنبه",
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
]


def _leave_request_status_meta(status):
    mapping = {
        StaffLeaveRequest.Status.PENDING: {
            "label": "در انتظار بررسی",
            "badge_class": "bg-amber-100 text-amber-700",
        },
        StaffLeaveRequest.Status.APPROVED: {
            "label": "تأیید شده",
            "badge_class": "bg-emerald-100 text-emerald-700",
        },
        StaffLeaveRequest.Status.REJECTED: {
            "label": "رد شده",
            "badge_class": "bg-rose-100 text-rose-700",
        },
        StaffLeaveRequest.Status.CANCELLED: {
            "label": "لغو شده",
            "badge_class": "bg-slate-100 text-slate-600",
        },
    }
    return mapping.get(
        status,
        {
            "label": "نامشخص",
            "badge_class": "bg-slate-100 text-slate-600",
        },
    )


def _leave_request_time_label(item):
    if item.start_time and item.end_time:
        return f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
    return "تمام روز"


def _serialize_manager_leave_request(item):
    status_meta = _leave_request_status_meta(item.status)
    stylist = item.stylist

    return {
        "id": item.id,
        "stylist_name": stylist.get_fullName() if stylist else "متخصص حذف‌شده",
        "date_label": (
            format_jalali_with_weekday(item.date) if item.date else "بدون تاریخ"
        ),
        "time_label": _leave_request_time_label(item),
        "reason": item.reason or "بدون توضیح",
        "status": item.status,
        "status_label": status_meta["label"],
        "status_badge_class": status_meta["badge_class"],
        "created_label": (
            format_jalali_with_weekday(item.created_at) if item.created_at else "—"
        ),
        "review_note": item.review_note or "",
        "action_url": reverse(
            "dashboards:staff_leave_request_action",
            kwargs={"request_id": item.id},
        ),
    }


def _build_manager_leave_requests(salon):
    pending_qs = (
        StaffLeaveRequest.objects.select_related("stylist__user", "salon")
        .filter(
            salon=salon,
            status=StaffLeaveRequest.Status.PENDING,
        )
        .order_by("date", "start_time", "created_at")
    )

    recent_qs = (
        StaffLeaveRequest.objects.select_related(
            "stylist__user", "salon", "reviewed_by"
        )
        .filter(salon=salon)
        .exclude(status=StaffLeaveRequest.Status.PENDING)
        .order_by("-reviewed_at", "-updated_at", "-id")[:12]
    )

    return {
        "pending": [_serialize_manager_leave_request(item) for item in pending_qs[:30]],
        "recent": [_serialize_manager_leave_request(item) for item in recent_qs],
        "pending_count": pending_qs.count(),
        "pending_count_label": to_persian_digits(pending_qs.count()),
    }


def _notify_manager_about_leave_request(*, leave_request, actor=None):
    salon = leave_request.salon
    stylist = leave_request.stylist

    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)
    if not manager_user or not stylist:
        logger.warning(
            "Leave request manager notification skipped. leave_request_id=%s",
            leave_request.id,
        )
        return None

    action_url = f"{reverse('dashboards:scheduled_shifts')}#scheduled-shifts-section-leave-requests"

    return create_notification(
        event_type="staff_leave_requested",
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title="درخواست مرخصی جدید",
        body=f"{stylist.get_fullName()} برای {format_jalali_with_weekday(leave_request.date)} درخواست مرخصی ثبت کرده است.",
        action_url=action_url,
        icon="fa-regular fa-calendar-xmark",
        channels=[NotificationChannel.DASHBOARD],
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=leave_request,
        metadata={
            "leave_request_id": leave_request.id,
            "stylist_id": stylist.user_id,
            "salon_id": salon.id,
            "date": leave_request.date.isoformat() if leave_request.date else "",
        },
        dedupe_key=f"staff_leave_requested:{leave_request.id}",
    )


def _notify_stylist_about_leave_review(*, leave_request, actor=None):
    stylist = leave_request.stylist
    salon = leave_request.salon

    stylist_user = getattr(stylist, "user", None)
    if not stylist_user:
        logger.warning(
            "Leave request stylist notification skipped. leave_request_id=%s",
            leave_request.id,
        )
        return None

    approved = leave_request.status == StaffLeaveRequest.Status.APPROVED
    status_label = "تأیید شد" if approved else "رد شد"
    priority = NotificationPriority.HIGH if approved else NotificationPriority.NORMAL
    icon = "fa-solid fa-circle-check" if approved else "fa-solid fa-circle-xmark"

    action_url = f"{reverse('dashboards:stylist_schedule')}#stylist-leave-requests"

    return create_notification(
        event_type="staff_leave_reviewed",
        category=NotificationCategory.STAFF,
        priority=priority,
        title=f"درخواست مرخصی شما {status_label}",
        body=f"درخواست مرخصی شما برای {format_jalali_with_weekday(leave_request.date)} در مجموعه {salon.salon_name} {status_label}.",
        action_url=action_url,
        icon=icon,
        channels=[NotificationChannel.DASHBOARD],
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=leave_request,
        metadata={
            "leave_request_id": leave_request.id,
            "stylist_id": stylist.user_id,
            "salon_id": salon.id,
            "status": leave_request.status,
            "review_note": leave_request.review_note or "",
        },
        dedupe_key=f"staff_leave_reviewed:{leave_request.id}:{leave_request.status}",
    )


def _schedule_request_status_meta(status):
    mapping = {
        StaffScheduleRequest.Status.PENDING: {
            "label": "در انتظار بررسی",
            "badge_class": "bg-amber-100 text-amber-700",
        },
        StaffScheduleRequest.Status.APPROVED: {
            "label": "تأیید شده",
            "badge_class": "bg-emerald-100 text-emerald-700",
        },
        StaffScheduleRequest.Status.REJECTED: {
            "label": "رد شده",
            "badge_class": "bg-rose-100 text-rose-700",
        },
        StaffScheduleRequest.Status.CANCELLED: {
            "label": "لغو شده",
            "badge_class": "bg-slate-100 text-slate-600",
        },
    }
    return mapping.get(
        status,
        {
            "label": "نامشخص",
            "badge_class": "bg-slate-100 text-slate-600",
        },
    )


def _serialize_staff_schedule_request(item):
    status_meta = _schedule_request_status_meta(item.status)
    stylist = item.stylist
    service = item.service

    return {
        "id": item.id,
        "stylist_name": stylist.get_fullName() if stylist else "متخصص حذف‌شده",
        "service_name": (
            service.service_name if service else "همه خدمات / بدون خدمت مشخص"
        ),
        "date_label": (
            format_jalali_with_weekday(item.date) if item.date else "بدون تاریخ"
        ),
        "time_label": f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}",
        "note": item.note or "بدون توضیح",
        "status": item.status,
        "status_label": status_meta["label"],
        "status_badge_class": status_meta["badge_class"],
        "created_label": (
            format_jalali_with_weekday(item.created_at) if item.created_at else "—"
        ),
        "review_note": item.review_note or "",
        "action_url": reverse(
            "dashboards:staff_schedule_request_action",
            kwargs={"request_id": item.id},
        ),
    }


def _build_manager_schedule_requests(salon):
    pending_qs = (
        StaffScheduleRequest.objects.select_related("stylist__user", "salon", "service")
        .filter(
            salon=salon,
            status=StaffScheduleRequest.Status.PENDING,
        )
        .order_by("date", "start_time", "created_at")
    )

    recent_qs = (
        StaffScheduleRequest.objects.select_related(
            "stylist__user",
            "salon",
            "service",
            "reviewed_by",
        )
        .filter(salon=salon)
        .exclude(status=StaffScheduleRequest.Status.PENDING)
        .order_by("-reviewed_at", "-updated_at", "-id")[:12]
    )

    return {
        "pending": [
            _serialize_staff_schedule_request(item) for item in pending_qs[:30]
        ],
        "recent": [_serialize_staff_schedule_request(item) for item in recent_qs],
        "pending_count": pending_qs.count(),
        "pending_count_label": to_persian_digits(pending_qs.count()),
    }


def _build_team_capacity_setup_workspace(*, salon):
    """Build persistent setup gaps for active members of one salon.

    A member is considered ready for public booking only when the same active
    and visible stylist has at least one bookable service in this salon and a
    current or future general/service-specific schedule in the same salon.
    """
    bookable_services_qs = Services.objects.filter(
        services_of_salon=salon,
        is_active=True,
        base_price__gt=0,
        duration_minutes__gt=0,
    ).order_by("pk")

    stylists = list(
        Stylist.objects.filter(
            stylists_of_salon=salon,
            is_active=True,
            salon_memberships__salon=salon,
            salon_memberships__status=SalonMembershipStatus.ACTIVE,
        )
        .select_related("user")
        .prefetch_related(
            Prefetch(
                "services_of_stylist",
                queryset=bookable_services_qs,
                to_attr="bookable_services_for_capacity_setup",
            )
        )
        .distinct()
        .order_by("user__name", "user__family", "pk")
    )

    stylist_ids = [stylist.pk for stylist in stylists]

    schedule_pairs = set(
        StylistSchedule.objects.filter(
            salon=salon,
            stylist_id__in=stylist_ids,
            date__gte=timezone.localdate(),
        ).values_list("stylist_id", "service_id")
    )

    general_schedule_stylist_ids = {
        stylist_id for stylist_id, service_id in schedule_pairs if service_id is None
    }

    gaps = []
    ready_members = []

    for stylist in stylists:
        edit_url = reverse(
            "dashboards:edit_stylist",
            kwargs={"stylist_id": stylist.user_id},
        )
        overview_url = reverse(
            "dashboards:stylist_overview",
            kwargs={"stylist_id": stylist.user_id},
        )
        regular_shift_url = reverse(
            "dashboards:set_regular_shifts",
            kwargs={
                "stylist_id": stylist.pk,
                "salon_id": salon.pk,
            },
        )

        base = {
            "stylist_id": stylist.pk,
            "stylist_user_id": stylist.user_id,
            "stylist_name": stylist.get_fullName(),
            "profile_url": overview_url,
            "edit_url": edit_url,
            "regular_shift_url": regular_shift_url,
        }

        if not stylist.is_visible_on_salon_pages:
            gaps.append(
                {
                    **base,
                    "key": "visibility",
                    "title": "پروفایل برای رزرو عمومی قابل‌نمایش نیست",
                    "description": (
                        "وضعیت نمایش این عضو را روی «فقط در سالن‌های فعال» "
                        "یا «عمومی در Loomera» قرار بده."
                    ),
                    "status_label": "نمایش غیرفعال",
                    "status_tone": "warning",
                    "action_label": "اصلاح وضعیت نمایش",
                    "action_url": edit_url,
                }
            )
            continue

        bookable_services = list(
            getattr(
                stylist,
                "bookable_services_for_capacity_setup",
                [],
            )
        )
        bookable_service_ids = {service.pk for service in bookable_services}

        if not bookable_service_ids:
            gaps.append(
                {
                    **base,
                    "key": "service",
                    "title": "خدمت قابل رزرو ندارد",
                    "description": (
                        "حداقل یک خدمت فعال، قیمت‌گذاری‌شده و دارای مدت "
                        "را در همین سالن به این عضو متصل کن."
                    ),
                    "status_label": "بدون خدمت",
                    "status_tone": "warning",
                    "action_label": "اتصال خدمات",
                    "action_url": edit_url,
                }
            )
            continue

        has_matching_schedule = stylist.pk in general_schedule_stylist_ids or any(
            (stylist.pk, service_id) in schedule_pairs
            for service_id in bookable_service_ids
        )

        if not has_matching_schedule:
            gaps.append(
                {
                    **base,
                    "key": "schedule",
                    "title": "شیفت جاری یا آینده ندارد",
                    "description": (
                        "برای این عضو یک برنامه عمومی یا برنامه مخصوص "
                        "یکی از خدمات قابل رزرو او ثبت کن."
                    ),
                    "status_label": "بدون ظرفیت آینده",
                    "status_tone": "primary",
                    "action_label": "تنظیم برنامه کاری",
                    "action_url": regular_shift_url,
                }
            )
            continue

        ready_members.append(
            {
                **base,
                "service_count": len(bookable_services),
                "service_count_label": to_persian_digits(len(bookable_services)),
            }
        )

    return {
        "members_count": len(stylists),
        "members_count_label": to_persian_digits(len(stylists)),
        "ready_count": len(ready_members),
        "ready_count_label": to_persian_digits(len(ready_members)),
        "incomplete_count": len(gaps),
        "incomplete_count_label": to_persian_digits(len(gaps)),
        "is_ready": bool(stylists) and not gaps,
        "gaps": gaps,
        "ready_members": ready_members,
        "team_member_url": reverse("dashboards:team_member"),
        "service_menu_url": reverse("dashboards:service_menu"),
    }


class ScheduledShiftsView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/scheduled_shifts.html"

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        team_capacity_setup = _build_team_capacity_setup_workspace(
            salon=salon,
        )

        start_date_str = request.GET.get("start_date")
        if start_date_str:
            try:
                start_date_gregorian = datetime.strptime(
                    start_date_str, "%Y-%m-%d"
                ).date()
            except ValueError:
                start_date_gregorian = jdatetime.date.today().togregorian()
        else:
            today_jalali = jdatetime.date.today()
            start_of_week_jalali = today_jalali - timedelta(days=today_jalali.weekday())
            start_date_gregorian = start_of_week_jalali.togregorian()

        end_date_gregorian = start_date_gregorian + timedelta(days=6)
        all_gregorian_dates_in_range = [
            start_date_gregorian + timedelta(days=i) for i in range(7)
        ]

        today_jalali = jdatetime.date.today()
        current_week_start_jalali = today_jalali - timedelta(
            days=today_jalali.weekday()
        )
        current_week_start_gregorian = current_week_start_jalali.togregorian()

        stylists_qs = (
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .prefetch_related(
                Prefetch(
                    "stylist_schedules",
                    queryset=StylistSchedule.objects.filter(
                        salon=salon,
                        date__range=[start_date_gregorian, end_date_gregorian],
                    ).select_related("service"),
                    to_attr="schedules_in_range",
                ),
                Prefetch(
                    "time_offs",
                    queryset=StylistTimeOff.objects.filter(
                        date__range=[start_date_gregorian, end_date_gregorian]
                    ),
                    to_attr="time_offs_in_range",
                ),
                Prefetch(
                    "leave_requests",
                    queryset=StaffLeaveRequest.objects.filter(
                        salon=salon,
                        status=StaffLeaveRequest.Status.APPROVED,
                        date__range=[start_date_gregorian, end_date_gregorian],
                    ),
                    to_attr="approved_leave_requests_in_range",
                ),
            )
        )

        stylists_data = []
        schedule_by_day_dict = {day: [] for day in all_gregorian_dates_in_range}

        total_work_events = 0
        total_time_off_events = 0

        for stylist in stylists_qs:
            schedules_in_range = stylist.schedules_in_range
            time_offs_in_range = stylist.time_offs_in_range
            approved_leaves_in_range = getattr(
                stylist, "approved_leave_requests_in_range", []
            )
            total_duration_seconds = sum(
                (
                    datetime.combine(s.date, s.end_time)
                    - datetime.combine(s.date, s.start_time)
                ).total_seconds()
                for s in schedules_in_range
            )
            total_hours = round(total_duration_seconds / 3600)

            work_events_count = len(schedules_in_range)
            time_off_count = len(time_offs_in_range) + len(approved_leaves_in_range)
            active_days_count = 0

            total_work_events += work_events_count
            total_time_off_events += time_off_count

            schedules_by_date = defaultdict(list)
            for sched in schedules_in_range:
                schedules_by_date[sched.date].append(sched)

            time_off_by_date = defaultdict(list)
            for tof in time_offs_in_range:
                time_off_by_date[tof.date].append(tof)
            for leave in approved_leaves_in_range:
                time_off_by_date[leave.date].append(leave)

            stylist_daily_schedules = []
            for day in all_gregorian_dates_in_range:
                jalali_day = jdatetime.date.fromgregorian(date=day)
                formatted_date = f"{PERSIAN_WEEKDAY_NAMES[jalali_day.weekday()]}، {jalali_day.day} {MONTHS_FA[jalali_day.month - 1]}"

                day_events = []
                work_count_for_day = 0
                off_count_for_day = 0

                if day in schedules_by_date:
                    for shift in sorted(
                        schedules_by_date[day], key=lambda s: s.start_time
                    ):
                        work_count_for_day += 1
                        day_events.append(
                            {
                                "type": "work",
                                "start_time": shift.start_time,
                                "display": f"{shift.start_time.strftime('%H:%M')} - {shift.end_time.strftime('%H:%M')}",
                                "service_name": (
                                    shift.service.service_name
                                    if shift.service_id
                                    else "تمام خدمات"
                                ),
                                "badge_class": "bg-emerald-100 text-emerald-700",
                                "icon": "fa-regular fa-clock",
                            }
                        )

                if day in time_off_by_date:
                    for time_off in time_off_by_date[day]:
                        off_count_for_day += 1
                        display_text = time_off.reason or "مرخصی"
                        if isinstance(time_off, StaffLeaveRequest):
                            display_text = f"{display_text} • تاییدشده"

                        if time_off.start_time and time_off.end_time:
                            display_text += f" ({format_time_fa(time_off.start_time)} - {format_time_fa(time_off.end_time)})"

                        day_events.append(
                            {
                                "type": "off",
                                "start_time": time_off.start_time or dt_time.min,
                                "display": display_text,
                                "service_name": "",
                                "badge_class": "bg-rose-100 text-rose-700",
                                "icon": "fa-solid fa-umbrella-beach",
                            }
                        )

                day_events.sort(key=lambda x: x["start_time"])

                if day_events:
                    active_days_count += 1
                    schedule_by_day_dict[day].append(
                        {
                            "id": stylist.pk,
                            "user_id": stylist.user.id,
                            "full_name": stylist.get_fullName(),
                            "profile_image_url": (
                                stylist.profile_image.url
                                if stylist.profile_image
                                else None
                            ),
                            "events": day_events,
                            "events_count_label": to_persian_digits(len(day_events)),
                            "profile_url": reverse(
                                "dashboards:stylist_overview",
                                kwargs={"stylist_id": stylist.user.id},
                            ),
                        }
                    )

                stylist_daily_schedules.append(
                    {
                        "formatted_date": formatted_date,
                        "weekday_label": PERSIAN_WEEKDAY_NAMES[jalali_day.weekday()],
                        "raw_date_iso": day.isoformat(),
                        "events": day_events,
                        "has_events": bool(day_events),
                        "work_count_label": to_persian_digits(work_count_for_day),
                        "off_count_label": to_persian_digits(off_count_for_day),
                        "edit_url": reverse(
                            "dashboards:edit_day_schedule",
                            kwargs={
                                "stylist_pk": stylist.pk,
                                "salon_pk": salon.id,
                                "date_iso": day.isoformat(),
                            },
                        ),
                        "time_off_url": reverse(
                            "dashboards:add_time_off",
                            kwargs={
                                "stylist_id": stylist.pk,
                                "date_iso": day.isoformat(),
                                "salon_id": salon.id,
                            },
                        ),
                    }
                )

            stylists_data.append(
                {
                    "id": stylist.pk,
                    "user_id": stylist.user.id,
                    "full_name": stylist.get_fullName(),
                    "profile_image_url": (
                        stylist.profile_image.url if stylist.profile_image else None
                    ),
                    "total_hours": total_hours,
                    "total_hours_label": to_persian_digits(total_hours),
                    "active_days_count_label": to_persian_digits(active_days_count),
                    "work_events_count_label": to_persian_digits(work_events_count),
                    "time_off_count_label": to_persian_digits(time_off_count),
                    "profile_url": reverse(
                        "dashboards:stylist_overview",
                        kwargs={"stylist_id": stylist.user.id},
                    ),
                    "regular_shift_url": reverse(
                        "dashboards:set_regular_shifts",
                        kwargs={"stylist_id": stylist.pk, "salon_id": salon.id},
                    ),
                    "daily_schedules": stylist_daily_schedules,
                }
            )

        schedule_by_day = []
        days_with_schedule_count = 0
        for day, working_stylists in schedule_by_day_dict.items():
            jalali_day = jdatetime.date.fromgregorian(date=day)
            has_schedule = bool(working_stylists)
            if has_schedule:
                days_with_schedule_count += 1

            schedule_by_day.append(
                {
                    "raw_date_iso": day.isoformat(),
                    "formatted_date": f"{PERSIAN_WEEKDAY_NAMES[jalali_day.weekday()]}، {jalali_day.day} {MONTHS_FA[jalali_day.month - 1]}",
                    "weekday_label": PERSIAN_WEEKDAY_NAMES[jalali_day.weekday()],
                    "has_schedule": has_schedule,
                    "stylists_working": working_stylists,
                    "working_count_label": to_persian_digits(len(working_stylists)),
                    "events_count_label": to_persian_digits(
                        sum(len(item["events"]) for item in working_stylists)
                    ),
                }
            )

        start_date_jalali = jdatetime.date.fromgregorian(date=start_date_gregorian)
        end_date_jalali = jdatetime.date.fromgregorian(date=end_date_gregorian)
        date_range_display = (
            f"{start_date_jalali.day} {MONTHS_FA[start_date_jalali.month - 1]} "
            f"تا {end_date_jalali.day} {MONTHS_FA[end_date_jalali.month - 1]} {start_date_jalali.year}"
        )

        prev_week_start_iso = (start_date_gregorian - timedelta(days=7)).isoformat()
        next_week_start_iso = (start_date_gregorian + timedelta(days=7)).isoformat()
        current_week_start_iso = current_week_start_gregorian.isoformat()

        focus_items = []
        if len(stylists_data) == 0:
            focus_items.append(
                {
                    "title": "هیچ عضو فعالی برای برنامه‌ریزی وجود ندارد",
                    "value": "نیازمند اقدام",
                    "description": "برای استفاده از planner هفتگی، ابتدا باید حداقل یک عضو فعال تیم داشته باشی.",
                    "tone": "warning",
                }
            )
        if days_with_schedule_count == 0 and len(stylists_data) > 0:
            focus_items.append(
                {
                    "title": "در این هفته شیفت ثبت نشده است",
                    "value": " برنامه ریزی",
                    "description": "برای دیدن ظرفیت واقعی تیم، باید برای اعضا شیفت روزانه یا منظم ثبت شود.",
                    "tone": "primary",
                }
            )
        if total_time_off_events > 0:
            focus_items.append(
                {
                    "title": "مرخصی در این بازه ثبت شده است",
                    "value": to_persian_digits(total_time_off_events),
                    "description": "مرخصی‌های ثبت‌شده را در زمان‌بندی و ظرفیت رزرو این هفته در نظر بگیر.",
                    "tone": "neutral",
                }
            )

        if not focus_items:
            focus_items = [
                {
                    "title": "planner هفتگی در وضعیت خوبی است",
                    "value": "آماده",
                    "description": "شیفت‌ها و توزیع برنامه اعضای تیم برای این بازه تصویر مناسبی از ظرفیت کاری ارائه می‌کند.",
                    "tone": "success",
                }
            ]

        leave_request_workspace = _build_manager_leave_requests(salon)
        schedule_request_workspace = _build_manager_schedule_requests(salon)

        # Keep the setup journey moving after the first real schedule is created.
        setup_readiness = build_salon_readiness_checklist(salon)
        setup_next_action = (
            setup_readiness.get("next_action") if not salon.is_active else None
        )

        context = {
            "salon": salon,
            "stylists_with_hours": stylists_data,
            "schedule_by_day": schedule_by_day,
            "team_capacity_setup": team_capacity_setup,
            "setup_readiness": setup_readiness,
            "setup_next_action": setup_next_action,
            "date_range_display": date_range_display,
            "prev_week_start_iso": prev_week_start_iso,
            "next_week_start_iso": next_week_start_iso,
            "current_week_start_iso": current_week_start_iso,
            "leave_request_workspace": leave_request_workspace,
            "schedule_request_workspace": schedule_request_workspace,
            "shifts_workspace": {
                "pending_schedule_requests_count": schedule_request_workspace[
                    "pending_count"
                ],
                "pending_schedule_requests_count_label": schedule_request_workspace[
                    "pending_count_label"
                ],
                "active_stylists_count_label": to_persian_digits(len(stylists_data)),
                "days_with_schedule_count_label": to_persian_digits(
                    days_with_schedule_count
                ),
                "pending_leave_requests_count": leave_request_workspace[
                    "pending_count"
                ],
                "pending_leave_requests_count_label": leave_request_workspace[
                    "pending_count_label"
                ],
                "work_events_count_label": to_persian_digits(total_work_events),
                "time_off_events_count_label": to_persian_digits(total_time_off_events),
                "focus_items": focus_items,
                "prev_week_url": f"?start_date={prev_week_start_iso}",
                "next_week_url": f"?start_date={next_week_start_iso}",
                "current_week_url": f"?start_date={current_week_start_iso}",
            },
        }
        return render(request, self.template_name, context)


# --------------------------------------------------------------------------------------
class ManagerStaffScheduleRequestActionView(
    SalonManagerOnboardingGuardMixin,
    LoginRequiredMixin,
    View,
):
    def post(self, request, request_id, *args, **kwargs):
        try:
            action = _clean_dashboard_schedule_action(request)
            review_note = _clean_dashboard_schedule_review_note(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:scheduled_shifts")

        try:
            with transaction.atomic():
                schedule_request = get_object_or_404(
                    StaffScheduleRequest.objects.select_for_update(),
                    pk=request_id,
                    salon__salon_manager__user=request.user,
                    status=StaffScheduleRequest.Status.PENDING,
                )

                reviewed = review_schedule_request(
                    schedule_request=schedule_request,
                    reviewer=request.user,
                    approved=(action == "approve"),
                    review_note=review_note,
                )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:scheduled_shifts")

        if reviewed.status == StaffScheduleRequest.Status.APPROVED:
            messages.success(
                request,
                f"درخواست برنامه کاری {reviewed.stylist.get_fullName()} تأیید و به شیفت‌های همین مجموعه اضافه شد.",
            )
        else:
            messages.success(
                request,
                f"درخواست برنامه کاری {reviewed.stylist.get_fullName()} رد شد.",
            )

        return redirect("dashboards:scheduled_shifts")


# ---------------------------------------------------------------------------------------
class ManagerStaffLeaveRequestActionView(
    SalonManagerOnboardingGuardMixin,
    LoginRequiredMixin,
    View,
):
    def post(self, request, request_id, *args, **kwargs):
        try:
            action = _clean_dashboard_schedule_action(request)
            review_note = _clean_dashboard_schedule_review_note(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:scheduled_shifts")

        try:
            with transaction.atomic():
                leave_request = get_object_or_404(
                    StaffLeaveRequest.objects.select_for_update(),
                    pk=request_id,
                    salon__salon_manager__user=request.user,
                    status=StaffLeaveRequest.Status.PENDING,
                )

                reviewed = review_leave_request(
                    leave_request=leave_request,
                    reviewer=request.user,
                    approved=(action == "approve"),
                    review_note=review_note,
                )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:scheduled_shifts")

        try:
            _notify_stylist_about_leave_review(
                leave_request=reviewed,
                actor=request.user,
            )
        except Exception:
            logger.exception(
                "Failed to notify stylist about leave request review. leave_request_id=%s",
                reviewed.id,
            )

        if reviewed.status == StaffLeaveRequest.Status.APPROVED:
            messages.success(
                request,
                f"درخواست مرخصی {reviewed.stylist.get_fullName()} تأیید شد.",
            )
        else:
            messages.success(
                request,
                f"درخواست مرخصی {reviewed.stylist.get_fullName()} رد شد.",
            )

        return redirect("dashboards:scheduled_shifts")


# -------------------------------------------------------------------------------------------------------------------------------------------------------------
# ثابت‌های مورد نیاز برای نمایش تاریخ شمسی
MONTHS_FA = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]


def _find_cross_salon_shift_conflict(
    *, stylist, salon, schedule_date, start_time, end_time
):
    """Return an existing shift in another salon that overlaps the given range."""
    if not all([stylist, salon, schedule_date, start_time, end_time]):
        return None

    return (
        StylistSchedule.objects.filter(
            stylist=stylist,
            date=schedule_date,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        .exclude(salon=salon)
        .select_related("salon")
        .order_by("start_time")
        .first()
    )


def _schedule_conflict_message(conflict):
    salon_name = (
        getattr(getattr(conflict, "salon", None), "salon_name", None) or "مجموعه دیگر"
    )
    return (
        "این متخصص در "
        f"{format_jalali_with_weekday(conflict.date)} "
        f"از {format_time_fa(conflict.start_time)} تا {format_time_fa(conflict.end_time)} "
        f"در «{salon_name}» برنامه کاری دارد؛ ثبت شیفت هم‌پوشان در مجموعه دیگر مجاز نیست."
    )


DASHBOARD_SCHEDULE_ACTIONS = {"approve", "reject"}


def _dashboard_schedule_post_max_bytes():
    return max(
        int(getattr(settings, "DASHBOARD_SCHEDULE_POST_MAX_BYTES", 16 * 1024) or 1),
        1,
    )


def _dashboard_schedule_review_note_max_chars():
    return max(
        int(getattr(settings, "DASHBOARD_SCHEDULE_REVIEW_NOTE_MAX_CHARS", 500) or 1),
        1,
    )


def _dashboard_schedule_max_shift_rows():
    return max(
        int(getattr(settings, "DASHBOARD_SCHEDULE_MAX_SHIFT_ROWS", 24) or 1),
        1,
    )


def _dashboard_schedule_request_too_large(request):
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        content_length = 0

    return content_length > _dashboard_schedule_post_max_bytes()


def _validate_dashboard_schedule_post_size(request):
    if _dashboard_schedule_request_too_large(request):
        raise ValidationError("حجم اطلاعات ارسالی بیش از حد مجاز است.")


def _clean_dashboard_schedule_action(request):
    _validate_dashboard_schedule_post_size(request)

    action = (request.POST.get("action") or "").strip().lower()
    if action not in DASHBOARD_SCHEDULE_ACTIONS:
        raise ValidationError("عملیات انتخاب‌شده معتبر نیست.")

    return action


def _clean_dashboard_schedule_review_note(request):
    note = str(request.POST.get("review_note") or "").strip()
    note = note.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")

    if len(note) > _dashboard_schedule_review_note_max_chars():
        raise ValidationError("یادداشت بررسی بیش از حد مجاز است.")

    return note


def _get_managed_schedule_salon_and_stylist(request, salon_pk, stylist_pk):
    salon = get_object_or_404(
        Salon.objects.select_related("salon_manager__user"),
        pk=salon_pk,
        salon_manager__user=request.user,
    )

    stylist = get_object_or_404(
        Stylist.objects.select_related("user").prefetch_related(
            Prefetch(
                "services_of_stylist",
                queryset=Services.objects.filter(services_of_salon=salon),
                to_attr="available_services_in_salon",
            )
        ),
        pk=stylist_pk,
        stylists_of_salon=salon,
    )

    return salon, stylist


def _service_is_valid_for_schedule_row(*, salon, stylist, service_id):
    if service_id is None:
        return True

    return Services.objects.filter(
        pk=service_id,
        services_of_salon=salon,
        stylists=stylist,
        is_active=True,
    ).exists()


def _extract_shift_indices_from_post(request):
    indices = set()

    for key in request.POST:
        if not key.startswith("shifts[") or "][" not in key:
            continue

        try:
            index_text = key.split("[", 1)[1].split("]", 1)[0]
            index = int(index_text)
        except (TypeError, ValueError, IndexError):
            raise ValidationError("ساختار ردیف‌های شیفت معتبر نیست.")

        if index < 0:
            raise ValidationError("ساختار ردیف‌های شیفت معتبر نیست.")

        indices.add(index)

    if len(indices) > _dashboard_schedule_max_shift_rows():
        raise ValidationError("تعداد ردیف‌های شیفت بیش از حد مجاز است.")

    return sorted(indices)


class EditStylistDayScheduleView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/edit_day_schedule.html"

    def get_time_options(self, open_time, close_time):
        options = []
        if not open_time or not close_time:
            return options

        current_time = datetime.combine(date.today(), open_time)
        end_datetime = datetime.combine(date.today(), close_time)

        while current_time <= end_datetime:
            options.append(current_time.strftime("%H:%M"))
            current_time += timedelta(minutes=30)
        return options

    def _resolve_date(self, date_iso):
        try:
            return date.fromisoformat(date_iso)
        except ValueError:
            return None

    def _get_salon_hours_for_day(self, salon, date_obj):
        day_of_week_for_model = ((date_obj.weekday() + 2) % 7) + 1
        return SalonOpeningHours.objects.filter(
            salon=salon,
            day_of_week=day_of_week_for_model,
            is_closed=False,
            open_time__isnull=False,
            close_time__isnull=False,
        ).first()

    def _build_context(
        self, stylist, salon, date_obj, existing_schedules, open_time, close_time
    ):
        jalali_date_obj = jdatetime.date.fromgregorian(date=date_obj)
        day_name_fa = jalali_date_obj.strftime("%A")
        page_title_date = f"{day_name_fa}، {jalali_date_obj.day} {MONTHS_FA[jalali_date_obj.month - 1]}"

        available_services = getattr(stylist, "available_services_in_salon", [])
        # A member can have working hours before services are attached.
        # Service selection is optional and empty service means "all/future services".
        # But a work shift must never be created on a day when the salon is closed.
        can_schedule = bool(open_time and close_time)

        initial_shift_rows = []
        for index, shift in enumerate(existing_schedules):
            initial_shift_rows.append(
                {
                    "index": index,
                    "start_time": shift.start_time.strftime("%H:%M"),
                    "end_time": shift.end_time.strftime("%H:%M"),
                    "service_id": shift.service_id,
                }
            )

        if not initial_shift_rows and can_schedule:
            initial_shift_rows.append(
                {
                    "index": 0,
                    "start_time": "",
                    "end_time": "",
                    "service_id": "",
                }
            )

        salon_hours_label = "برای این روز ساعت کاری تعریف نشده است"
        if open_time and close_time:
            salon_hours_label = (
                f"{format_time_fa(open_time)} تا {format_time_fa(close_time)}"
            )

        focus_items = []
        if not can_schedule:
            focus_items.append(
                {
                    "title": "مجموعه در این روز فعال نیست",
                    "value": "تعطیل",
                    "description": "برای جلوگیری از رزرو و تداخل عملیاتی، امکان ثبت شیفت کاری در روز تعطیل یا بدون ساعت کاری وجود ندارد.",
                    "tone": "warning",
                }
            )
        if len(existing_schedules) == 0 and can_schedule:
            focus_items.append(
                {
                    "title": "برای این روز هنوز شیفتی ثبت نشده",
                    "value": "خالی",
                    "description": "می‌توانی همین‌جا اولین شیفت روزانه این عضو تیم را ایجاد کنی.",
                    "tone": "neutral",
                }
            )

        if not focus_items:
            focus_items = [
                {
                    "title": "برنامه این روز قابل مدیریت است",
                    "value": "آماده",
                    "description": "می‌توانی شیفت‌ها را بازبینی، حذف یا ردیف جدید اضافه کنی و برای این روز  برنامه ریزی دقیق‌تری بسازی.",
                    "tone": "success",
                }
            ]

        return {
            "stylist": stylist,
            "salon": salon,
            "date_iso": date_obj.isoformat(),
            "page_title_date": page_title_date,
            "available_services": available_services,
            "time_options": self.get_time_options(open_time, close_time),
            "initial_shift_rows": initial_shift_rows,
            "can_schedule": can_schedule,
            "back_url": reverse("dashboards:scheduled_shifts"),
            "edit_day_workspace": {
                "day_label": page_title_date,
                "salon_hours_label": salon_hours_label,
                "existing_shift_count_label": to_persian_digits(
                    len(existing_schedules)
                ),
                "available_services_count_label": to_persian_digits(
                    len(available_services)
                ),
                "focus_items": focus_items,
            },
        }

    def get(self, request, stylist_pk, salon_pk, date_iso):
        date_obj = self._resolve_date(date_iso)
        if not date_obj:
            messages.error(request, "فرمت تاریخ نامعتبر است.")
            return redirect("dashboards:scheduled_shifts")

        salon, stylist = _get_managed_schedule_salon_and_stylist(
            request,
            salon_pk,
            stylist_pk,
        )

        salon_hours_for_day = self._get_salon_hours_for_day(salon, date_obj)
        open_time, close_time = (None, None)
        if salon_hours_for_day:
            open_time = salon_hours_for_day.open_time
            close_time = salon_hours_for_day.close_time
        else:
            messages.warning(
                request, "ساعات کاری برای این روز در مجموعه تعریف نشده است."
            )

        existing_schedules = list(
            StylistSchedule.objects.filter(
                stylist=stylist,
                salon=salon,
                date=date_obj,
            ).order_by("start_time")
        )

        context = self._build_context(
            stylist=stylist,
            salon=salon,
            date_obj=date_obj,
            existing_schedules=existing_schedules,
            open_time=open_time,
            close_time=close_time,
        )
        return render(request, self.template_name, context)

    def post(self, request, stylist_pk, salon_pk, date_iso):
        try:
            _validate_dashboard_schedule_post_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:scheduled_shifts")

        salon, stylist = _get_managed_schedule_salon_and_stylist(
            request,
            salon_pk,
            stylist_pk,
        )

        date_obj = self._resolve_date(date_iso)
        if not date_obj:
            messages.error(request, "فرمت تاریخ نامعتبر برای ارسال اطلاعات.")
            return redirect("dashboards:scheduled_shifts")

        salon_hours_for_day = self._get_salon_hours_for_day(salon, date_obj)
        open_time, close_time = (None, None)
        if salon_hours_for_day:
            open_time = salon_hours_for_day.open_time
            close_time = salon_hours_for_day.close_time

        shifts_data = []
        try:
            shift_indices = _extract_shift_indices_from_post(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect(
                "dashboards:edit_day_schedule",
                stylist_pk=stylist.pk,
                salon_pk=salon.pk,
                date_iso=date_obj.isoformat(),
            )

        for index in sorted(list(shift_indices)):
            start_time_str = request.POST.get(f"shifts[{index}][start_time]")
            end_time_str = request.POST.get(f"shifts[{index}][end_time]")
            service_id_str = request.POST.get(f"shifts[{index}][service_id]")

            if not any([start_time_str, end_time_str, service_id_str]):
                continue

            if not all([start_time_str, end_time_str]):
                messages.error(
                    request,
                    f"ردیف {index + 1} ناقص است. لطفاً شروع و پایان را کامل کن. انتخاب خدمت اختیاری است.",
                )
                return redirect(
                    "dashboards:edit_day_schedule",
                    stylist_pk=stylist.pk,
                    salon_pk=salon.pk,
                    date_iso=date_obj.isoformat(),
                )

            try:
                start_time = dt_time.fromisoformat(start_time_str)
                end_time = dt_time.fromisoformat(end_time_str)
                service_id = int(service_id_str) if service_id_str else None
                if not _service_is_valid_for_schedule_row(
                    salon=salon,
                    stylist=stylist,
                    service_id=service_id,
                ):
                    messages.error(
                        request,
                        f"خدمت انتخاب‌شده در ردیف {index + 1} برای این متخصص در این مجموعه معتبر نیست.",
                    )
                    return redirect(
                        "dashboards:edit_day_schedule",
                        stylist_pk=stylist.pk,
                        salon_pk=salon.pk,
                        date_iso=date_obj.isoformat(),
                    )
            except (ValueError, TypeError):
                messages.error(request, f"فرمت داده‌های ردیف {index + 1} نامعتبر است.")
                return redirect(
                    "dashboards:edit_day_schedule",
                    stylist_pk=stylist.pk,
                    salon_pk=salon.pk,
                    date_iso=date_obj.isoformat(),
                )

            if end_time <= start_time:
                messages.error(
                    request,
                    f"در ردیف {index + 1} زمان پایان باید بعد از زمان شروع باشد.",
                )
                return redirect(
                    "dashboards:edit_day_schedule",
                    stylist_pk=stylist.pk,
                    salon_pk=salon.pk,
                    date_iso=date_obj.isoformat(),
                )

            if open_time and close_time:
                if start_time < open_time or end_time > close_time:
                    messages.error(
                        request,
                        f"ردیف {index + 1} خارج از ساعات کاری مجموعه برای این روز است.",
                    )
                    return redirect(
                        "dashboards:edit_day_schedule",
                        stylist_pk=stylist.pk,
                        salon_pk=salon.pk,
                        date_iso=date_obj.isoformat(),
                    )

            shifts_data.append(
                {
                    "service_id": service_id,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

        ordered_shifts = sorted(shifts_data, key=lambda x: x["start_time"])
        if ordered_shifts and (not open_time or not close_time):
            messages.error(
                request,
                "مجموعه در این روز تعطیل است یا ساعت کاری فعال ندارد؛ امکان ثبت شیفت کاری وجود ندارد.",
            )
            return redirect(
                "dashboards:edit_day_schedule",
                stylist_pk=stylist.pk,
                salon_pk=salon.pk,
                date_iso=date_obj.isoformat(),
            )

        for i in range(1, len(ordered_shifts)):
            prev_shift = ordered_shifts[i - 1]
            current_shift = ordered_shifts[i]
            if current_shift["start_time"] < prev_shift["end_time"]:
                messages.error(
                    request, "بین شیفت‌های ثبت‌شده هم‌پوشانی زمانی وجود دارد."
                )
                return redirect(
                    "dashboards:edit_day_schedule",
                    stylist_pk=stylist.pk,
                    salon_pk=salon.pk,
                    date_iso=date_obj.isoformat(),
                )

        for data in ordered_shifts:
            conflict = _find_cross_salon_shift_conflict(
                stylist=stylist,
                salon=salon,
                schedule_date=date_obj,
                start_time=data["start_time"],
                end_time=data["end_time"],
            )
            if conflict:
                messages.error(request, _schedule_conflict_message(conflict))
                return redirect(
                    "dashboards:edit_day_schedule",
                    stylist_pk=stylist.pk,
                    salon_pk=salon.pk,
                    date_iso=date_obj.isoformat(),
                )

        try:
            with transaction.atomic():
                StylistSchedule.objects.filter(
                    stylist=stylist,
                    salon=salon,
                    date=date_obj,
                ).delete()

                new_schedules = [
                    StylistSchedule(
                        stylist=stylist,
                        salon=salon,
                        date=date_obj,
                        service_id=data["service_id"],
                        start_time=data["start_time"],
                        end_time=data["end_time"],
                    )
                    for data in ordered_shifts
                ]

                if new_schedules:
                    StylistSchedule.objects.bulk_create(new_schedules)

            if not ordered_shifts:
                messages.info(request, "تمام شیفت‌های این روز حذف شدند.")
            else:
                messages.success(
                    request,
                    f"{len(ordered_shifts)} شیفت برای این روز با موفقیت ذخیره شد.",
                )

        except Exception:
            logger.exception(
                "Failed to save day schedule | stylist=%s | salon=%s | date=%s",
                stylist.pk,
                salon.pk,
                date_obj,
            )
            messages.error(
                request, "خطا در ذخیره‌سازی شیفت‌ها. لطفاً دوباره تلاش کنید."
            )

        return redirect(
            "dashboards:edit_day_schedule",
            stylist_pk=stylist.pk,
            salon_pk=salon.pk,
            date_iso=date_obj.isoformat(),
        )


# --------------------------------------------------------------------------------------------------------------------------------
class DeleteDayScheduleView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    def _resolve_date_or_400(self, date_iso):
        try:
            return datetime.strptime(date_iso, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _get_authorized_objects(self, request, stylist_id):
        """
        مدیر مجموعه فقط می‌تواند برنامه متخصصی را حذف کند که عضو مجموعه خودش باشد.
        چون URL فعلی salon_id ندارد، مجموعه مجاز از رابطه manager -> salon -> stylist تشخیص داده می‌شود.
        """
        stylist = get_object_or_404(
            Stylist.objects.select_related("user"),
            pk=stylist_id,
            stylists_of_salon__salon_manager__user=request.user,
        )

        managed_salons = (
            Salon.objects.filter(
                salon_manager__user=request.user,
                stylists=stylist,
            )
            .distinct()
            .order_by("id")
        )

        salon_id = request.POST.get("salon_id") or request.GET.get("salon_id")

        if salon_id:
            salon = get_object_or_404(
                managed_salons,
                pk=salon_id,
            )
        else:
            salon = managed_salons.first()

        if salon is None:
            raise Http404("Stylist is not managed by this salon manager.")

        return salon, stylist

    def post(self, request, stylist_id, date_iso):
        schedule_date = self._resolve_date_or_400(date_iso)

        try:
            _validate_dashboard_schedule_post_size(request)
        except ValidationError as exc:
            return JsonResponse(
                {
                    "status": "error",
                    "message": str(exc),
                },
                status=400,
            )

        if schedule_date is None:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "فرمت تاریخ نامعتبر است.",
                },
                status=400,
            )

        salon, stylist = self._get_authorized_objects(request, stylist_id)

        try:
            with transaction.atomic():
                deleted_schedules_count, _ = StylistSchedule.objects.filter(
                    stylist=stylist,
                    salon=salon,
                    date=schedule_date,
                ).delete()

                deleted_timeoffs_count = 0

            return JsonResponse(
                {
                    "status": "success",
                    "message": "برنامه روز با موفقیت حذف شد.",
                    "deleted_schedules_count": deleted_schedules_count,
                    "deleted_timeoffs_count": deleted_timeoffs_count,
                }
            )

        except Exception:
            logger.exception(
                "Failed to delete day schedule | stylist=%s | salon=%s | date=%s",
                stylist.pk,
                salon.pk,
                schedule_date,
            )
            return JsonResponse(
                {
                    "status": "error",
                    "message": "خطایی در هنگام حذف برنامه رخ داد. لطفاً دوباره تلاش کنید.",
                },
                status=500,
            )


# -------------------------------------------------------------------------------------------------------------------------------------------
def to_english_numerals(text):
    if text is None:
        return None
    persian_to_english = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    return str(text).translate(persian_to_english).replace("/", "-").strip()


PERSIAN_WEEKDAY_NAMES = [
    "شنبه",
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
]


class SetSalonHoursView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    def get(self, request, salon_id):
        # در اینجا می‌توانید فرم کامل تنظیم ساعت کاری را پیاده‌سازی کنید
        from django.http import HttpResponse

        salon = get_object_or_404(Salon, pk=salon_id)
        return HttpResponse(
            f"لطفاً در این صفحه فرم تنظیم ساعات کاری برای مجموعه '{salon.salon_name}' را پیاده‌سازی کنید."
        )


class SetRegularShiftsView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/set_regular_shifts.html"

    def _get_objects(self, request, stylist_id, salon_id):
        salon = get_object_or_404(
            Salon.objects.prefetch_related("opening_hours", "services", "stylists"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        stylist = get_object_or_404(
            Stylist.objects.select_related("user").prefetch_related(
                "services_of_stylist"
            ),
            pk=stylist_id,
            stylists_of_salon=salon,
        )
        return salon, stylist

    def _build_day_cards(self, salon):
        opening_hours_map = {
            item.day_of_week: item for item in salon.opening_hours.all()
        }
        day_cards = []
        open_days_count = 0

        for index, label in enumerate(PERSIAN_WEEKDAY_NAMES):
            model_day = index + 1
            opening_hour = opening_hours_map.get(model_day)

            is_open = False
            open_time = ""
            close_time = ""
            hours_label = "تعطیل یا بدون ساعت کاری"

            if (
                opening_hour
                and not opening_hour.is_closed
                and opening_hour.open_time
                and opening_hour.close_time
            ):
                is_open = True
                open_days_count += 1
                open_time = opening_hour.open_time.strftime("%H:%M")
                close_time = opening_hour.close_time.strftime("%H:%M")
                hours_label = f"{format_time_fa(opening_hour.open_time)} تا {format_time_fa(opening_hour.close_time)}"

            day_cards.append(
                {
                    "index": index,
                    "label": label,
                    "is_open": is_open,
                    "open_time": open_time,
                    "close_time": close_time,
                    "hours_label": hours_label,
                }
            )

        return day_cards, open_days_count

    def _build_context(self, stylist, salon):
        day_cards, open_days_count = self._build_day_cards(salon)

        today_jalali = jdatetime.date.today()
        default_end_jalali = today_jalali + timedelta(days=29)

        available_services_count = (
            Services.objects.filter(services_of_salon=salon, stylists=stylist)
            .distinct()
            .count()
        )

        focus_items = []
        if open_days_count == 0:
            focus_items.append(
                {
                    "title": "برای مجموعه هنوز ساعت کاری فعالی ثبت نشده",
                    "value": "نیازمند اقدام",
                    "description": "تا وقتی ساعت کاری روزهای مجموعه مشخص نشود، ساخت شیفت منظم معنی‌دار نخواهد بود.",
                    "tone": "warning",
                }
            )
        if available_services_count == 0:
            focus_items.append(
                {
                    "title": "این عضو هنوز خدمت متصل‌شده‌ای ندارد",
                    "value": "قابل بهبود",
                    "description": "شیفت منظم ثبت می‌شود، اما بهتر است خدمات قابل پوشش این عضو هم کامل باشند.",
                    "tone": "primary",
                }
            )

        if not focus_items:
            focus_items = [
                {
                    "title": "این صفحه برای  برنامه ریزی منظم آماده است",
                    "value": "آماده",
                    "description": "می‌توانی برای هر روز چند بازه تعریف کنی و آن‌ها را در یک بازه تاریخی به‌صورت batch اعمال کنی.",
                    "tone": "success",
                }
            ]

        return {
            "stylist": stylist,
            "salon": salon,
            "day_cards": day_cards,
            "back_url": reverse("dashboards:scheduled_shifts"),
            "team_member_url": reverse("dashboards:team_member"),
            "stylist_profile_url": reverse(
                "dashboards:stylist_overview",
                kwargs={"stylist_id": stylist.user.id},
            ),
            "edit_stylist_url": reverse(
                "dashboards:edit_stylist",
                kwargs={"stylist_id": stylist.user.id},
            ),
            "default_start_date": to_persian_digits(today_jalali.strftime("%Y/%m/%d")),
            "default_end_date": to_persian_digits(
                default_end_jalali.strftime("%Y/%m/%d")
            ),
            "regular_shift_workspace": {
                "open_days_count_label": to_persian_digits(open_days_count),
                "closed_days_count_label": to_persian_digits(7 - open_days_count),
                "services_count_label": to_persian_digits(available_services_count),
                "focus_items": focus_items,
            },
        }

    def get(self, request, stylist_id, salon_id):
        salon, stylist = self._get_objects(request, stylist_id, salon_id)

        if not salon.opening_hours.exists():
            messages.warning(request, "ابتدا باید ساعت کاری مجموعه را کامل کنی.")
            return redirect("dashboards:salon_profile_creator_step3")

        context = self._build_context(stylist=stylist, salon=salon)
        return render(request, self.template_name, context)

    def post(self, request, stylist_id, salon_id):
        salon, stylist = self._get_objects(request, stylist_id, salon_id)

        try:
            _validate_dashboard_schedule_post_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect(request.path_info)

        if not salon.opening_hours.exists():
            messages.warning(request, "ابتدا باید ساعت کاری مجموعه را کامل کنی.")
            return redirect("dashboards:salon_profile_creator_step3")

        start_date_str = to_english_numerals(request.POST.get("start_date"))
        end_date_str = to_english_numerals(request.POST.get("end_date"))

        try:
            start_jalali = jdatetime.datetime.strptime(
                start_date_str, "%Y-%m-%d"
            ).date()
            end_jalali = jdatetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
            start_date = start_jalali.togregorian()
            end_date = end_jalali.togregorian()
        except (ValueError, TypeError, AttributeError):
            messages.error(request, "لطفاً تاریخ شروع و پایان را به‌درستی وارد کن.")
            return redirect(request.path_info)

        if end_date < start_date:
            messages.error(request, "تاریخ پایان باید بعد از تاریخ شروع باشد.")
            return redirect(request.path_info)

        opening_hours_map = {
            item.day_of_week - 1: item
            for item in salon.opening_hours.all()
            if not item.is_closed and item.open_time and item.close_time
        }

        daily_shifts_data = {}

        for i in range(7):
            shifts_str = (request.POST.get(f"day-{i}-shifts") or "").strip()
            if not shifts_str:
                continue

            opening_hour = opening_hours_map.get(i)
            if not opening_hour:
                messages.error(
                    request,
                    f"برای روز {PERSIAN_WEEKDAY_NAMES[i]} ساعت کاری فعال تعریف نشده، اما شیفت وارد شده است.",
                )
                return redirect(request.path_info)

            parsed_rows = []
            for part in shifts_str.split(","):
                part = part.strip()
                if not part:
                    continue

                try:
                    start_str, end_str = part.split("-")
                    start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                    end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
                except ValueError:
                    messages.error(
                        request,
                        f"فرمت یکی از بازه‌های روز {PERSIAN_WEEKDAY_NAMES[i]} نامعتبر است.",
                    )
                    return redirect(request.path_info)

                if end_time <= start_time:
                    messages.error(
                        request,
                        f"در روز {PERSIAN_WEEKDAY_NAMES[i]}، زمان پایان باید بعد از شروع باشد.",
                    )
                    return redirect(request.path_info)

                if (
                    start_time < opening_hour.open_time
                    or end_time > opening_hour.close_time
                ):
                    messages.error(
                        request,
                        f"یکی از بازه‌های روز {PERSIAN_WEEKDAY_NAMES[i]} خارج از ساعت کاری مجموعه است.",
                    )
                    return redirect(request.path_info)

                parsed_rows.append({"start": start_time, "end": end_time})

            parsed_rows = sorted(parsed_rows, key=lambda x: x["start"])

            for idx in range(1, len(parsed_rows)):
                previous_row = parsed_rows[idx - 1]
                current_row = parsed_rows[idx]
                if current_row["start"] < previous_row["end"]:
                    messages.error(
                        request,
                        f"بین بازه‌های روز {PERSIAN_WEEKDAY_NAMES[i]} هم‌پوشانی زمانی وجود دارد.",
                    )
                    return redirect(request.path_info)

            if parsed_rows:
                daily_shifts_data[i] = parsed_rows

        try:
            with transaction.atomic():
                StylistSchedule.objects.filter(
                    stylist=stylist,
                    salon=salon,
                    date__range=[start_date, end_date],
                ).delete()

                schedules_to_create = []
                current_date = start_date

                while current_date <= end_date:
                    persian_weekday_index = (current_date.weekday() + 2) % 7
                    if persian_weekday_index in daily_shifts_data:
                        for shift in daily_shifts_data[persian_weekday_index]:
                            schedules_to_create.append(
                                StylistSchedule(
                                    stylist=stylist,
                                    salon=salon,
                                    date=current_date,
                                    start_time=shift["start"],
                                    end_time=shift["end"],
                                    service=None,
                                )
                            )
                    current_date += timedelta(days=1)

                for schedule in schedules_to_create:
                    conflict = _find_cross_salon_shift_conflict(
                        stylist=schedule.stylist,
                        salon=schedule.salon,
                        schedule_date=schedule.date,
                        start_time=schedule.start_time,
                        end_time=schedule.end_time,
                    )
                    if conflict:
                        raise ValidationError(_schedule_conflict_message(conflict))

                if schedules_to_create:
                    StylistSchedule.objects.bulk_create(schedules_to_create)
                    messages.success(
                        request,
                        f"{to_persian_digits(len(schedules_to_create))} شیفت منظم با موفقیت ثبت شد.",
                    )
                else:
                    messages.info(
                        request,
                        "در این بازه هیچ شیفتی ثبت نشد و برنامه قبلی این بازه پاک شد.",
                    )

        except ValidationError as e:
            messages.error(
                request,
                e.messages[0] if hasattr(e, "messages") and e.messages else str(e),
            )
            return redirect(request.path_info)
        except Exception:
            logger.exception(
                "Failed to save regular shifts | stylist=%s | salon=%s",
                stylist.pk,
                salon.pk,
            )
            messages.error(
                request, "خطایی در هنگام ذخیره‌سازی رخ داد. لطفاً دوباره تلاش کنید."
            )
            return redirect(request.path_info)

        return redirect("dashboards:scheduled_shifts")


# ----------------------------------------------------------------------------------------------------------------------------------
class AddTimeOffView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/add_time_off.html"
    form_class = StylistTimeOffForm

    def _get_objects(self, request, stylist_id, salon_id):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        stylist = get_object_or_404(
            Stylist.objects.select_related("user"),
            pk=stylist_id,
            stylists_of_salon=salon,
        )
        return salon, stylist

    def _get_time_options(self, date_obj, salon):
        time_options = []
        day_of_week_for_model = ((date_obj.weekday() + 2) % 7) + 1

        salon_hours = SalonOpeningHours.objects.filter(
            salon=salon,
            day_of_week=day_of_week_for_model,
            is_closed=False,
        ).first()

        if salon_hours and salon_hours.open_time and salon_hours.close_time:
            current = datetime.combine(date.today(), salon_hours.open_time)
            end = datetime.combine(date.today(), salon_hours.close_time)
            while current <= end:
                time_options.append(current.strftime("%H:%M"))
                current += timedelta(minutes=30)

        return time_options

    def _get_salon_hours_for_day(self, date_obj, salon):
        day_of_week_for_model = ((date_obj.weekday() + 2) % 7) + 1
        return SalonOpeningHours.objects.filter(
            salon=salon,
            day_of_week=day_of_week_for_model,
            is_closed=False,
        ).first()

    def _serialize_shift(self, shift):
        return {
            "service_name": (
                shift.service.service_name if shift.service_id else "تمام خدمات"
            ),
            "time_label": f"{format_time_fa(shift.start_time)} تا {format_time_fa(shift.end_time)}",
        }

    def _split_schedule_around_time_off(self, schedule, time_off):
        """
        Preserve the available parts of an existing work shift when an hourly
        time off is registered inside it.

        Example:
            shift 09:00-17:00 + time off 12:00-13:00
            => 09:00-12:00 and 13:00-17:00
        """
        if not time_off.start_time or not time_off.end_time:
            return []

        segments = []

        if schedule.start_time < time_off.start_time:
            before_end = min(schedule.end_time, time_off.start_time)
            if schedule.start_time < before_end:
                segments.append((schedule.start_time, before_end))

        if schedule.end_time > time_off.end_time:
            after_start = max(schedule.start_time, time_off.end_time)
            if after_start < schedule.end_time:
                segments.append((after_start, schedule.end_time))

        return segments

    def _build_context(
        self, *, salon, stylist, date_obj, form, time_options, existing_shifts
    ):
        jalali_date = jdatetime.date.fromgregorian(date=date_obj)
        day_name_fa = PERSIAN_WEEKDAY_NAMES[jalali_date.weekday()]
        jalali_date_display = (
            f"{day_name_fa}، {to_persian_digits(jalali_date.day)} "
            f"{MONTHS_FA[jalali_date.month - 1]} {to_persian_digits(jalali_date.year)}"
        )

        salon_hours = self._get_salon_hours_for_day(date_obj, salon)
        salon_hours_label = "برای این روز ساعت کاری فعالی ثبت نشده است"
        if salon_hours and salon_hours.open_time and salon_hours.close_time:
            salon_hours_label = f"{format_time_fa(salon_hours.open_time)} تا {format_time_fa(salon_hours.close_time)}"

        focus_items = []
        if not time_options:
            focus_items.append(
                {
                    "title": "ساعت کاری مجموعه برای این روز فعال نیست",
                    "value": "توجه",
                    "description": "برای مرخصی تمام‌روز مشکلی نیست، اما ثبت مرخصی ساعتی بدون ساعت کاری فعال معنی‌دار نیست.",
                    "tone": "warning",
                }
            )

        if len(existing_shifts) > 0:
            focus_items.append(
                {
                    "title": "برای این روز شیفت ثبت شده است",
                    "value": to_persian_digits(len(existing_shifts)),
                    "description": "اگر مرخصی تمام‌روز ثبت کنی، همه شیفت‌های این روز حذف می‌شوند. اگر مرخصی ساعتی باشد، فقط شیفت‌های متداخل حذف می‌شوند.",
                    "tone": "primary",
                }
            )
        else:
            focus_items.append(
                {
                    "title": "شیفت فعالی برای این روز وجود ندارد",
                    "value": "خالی",
                    "description": "ثبت مرخصی همچنان ممکن است، اما در حال حاضر شیفتی برای حذف یا جابه‌جایی وجود ندارد.",
                    "tone": "neutral",
                }
            )

        return {
            "form": form,
            "salon": salon,
            "stylist": stylist,
            "jalali_date_display": jalali_date_display,
            "back_url": reverse("dashboards:scheduled_shifts"),
            "existing_shifts": [
                self._serialize_shift(item) for item in existing_shifts
            ],
            "add_time_off_workspace": {
                "salon_hours_label": salon_hours_label,
                "existing_shift_count_label": to_persian_digits(len(existing_shifts)),
                "time_slot_count_label": to_persian_digits(len(time_options)),
                "focus_items": focus_items,
            },
        }

    def get(self, request, stylist_id, salon_id, date_iso):
        salon, stylist = self._get_objects(request, stylist_id, salon_id)

        try:
            date_obj = date.fromisoformat(date_iso)
        except ValueError:
            messages.error(request, "فرمت تاریخ نامعتبر است.")
            return redirect("dashboards:scheduled_shifts")

        time_options = self._get_time_options(date_obj, salon)
        existing_shifts = list(
            StylistSchedule.objects.filter(
                stylist=stylist,
                salon=salon,
                date=date_obj,
            )
            .select_related("service")
            .order_by("start_time")
        )

        form = self.form_class(
            initial={"stylist": stylist, "date": date_obj},
            time_options=time_options,
        )

        context = self._build_context(
            salon=salon,
            stylist=stylist,
            date_obj=date_obj,
            form=form,
            time_options=time_options,
            existing_shifts=existing_shifts,
        )
        return render(request, self.template_name, context)

    def post(self, request, stylist_id, salon_id, date_iso):
        salon, stylist = self._get_objects(request, stylist_id, salon_id)

        try:
            _validate_dashboard_schedule_post_size(request)
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:scheduled_shifts")

        try:
            date_obj = date.fromisoformat(date_iso)
        except ValueError:
            messages.error(request, "فرمت تاریخ نامعتبر است.")
            return redirect("dashboards:scheduled_shifts")

        time_options = self._get_time_options(date_obj, salon)
        existing_shifts = list(
            StylistSchedule.objects.filter(
                stylist=stylist,
                salon=salon,
                date=date_obj,
            )
            .select_related("service")
            .order_by("start_time")
        )

        form = self.form_class(request.POST, time_options=time_options)

        if form.is_valid():
            try:
                with transaction.atomic():
                    time_off = form.save(commit=False)
                    time_off.stylist = stylist
                    time_off.date = date_obj

                    if not time_off.start_time and not time_off.end_time:
                        StylistSchedule.objects.filter(
                            stylist=stylist,
                            date=time_off.date,
                            salon=salon,
                        ).delete()
                    else:
                        overlapping_schedules = list(
                            StylistSchedule.objects.filter(
                                stylist=stylist,
                                date=time_off.date,
                                salon=salon,
                                start_time__lt=time_off.end_time,
                                end_time__gt=time_off.start_time,
                            ).select_related("service")
                        )

                        replacement_schedules = []
                        for schedule in overlapping_schedules:
                            for (
                                start_time,
                                end_time,
                            ) in self._split_schedule_around_time_off(
                                schedule, time_off
                            ):
                                replacement_schedules.append(
                                    StylistSchedule(
                                        stylist=schedule.stylist,
                                        salon=schedule.salon,
                                        date=schedule.date,
                                        service=schedule.service,
                                        start_time=start_time,
                                        end_time=end_time,
                                    )
                                )

                        if overlapping_schedules:
                            StylistSchedule.objects.filter(
                                pk__in=[item.pk for item in overlapping_schedules]
                            ).delete()
                            StylistSchedule.objects.bulk_create(replacement_schedules)

                    time_off.save()

                messages.success(request, "مرخصی با موفقیت ثبت شد.")
                return redirect("dashboards:scheduled_shifts")

            except Exception:
                logger.exception(
                    "Failed to save time off | stylist=%s | salon=%s | date=%s",
                    stylist.pk,
                    salon.pk,
                    date_obj,
                )
                messages.error(
                    request, "خطایی در هنگام ذخیره‌سازی رخ داد. لطفاً دوباره تلاش کنید."
                )

        context = self._build_context(
            salon=salon,
            stylist=stylist,
            date_obj=date_obj,
            form=form,
            time_options=time_options,
            existing_shifts=existing_shifts,
        )
        return render(request, self.template_name, context)


# ------------------------------------------------------------------------------------------------------------------------------
import json
from datetime import datetime, timedelta
import jdatetime  # <<< ۱. اضافه کردن کتابخانه jdatetime
from django.shortcuts import render, get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse

# این دیکشنری همچنان برای محاسبه روز هفته لازم است
JALALI_WEEKDAY_MAP = {
    5: 1,  # Saturday
    6: 2,  # Sunday
    0: 3,  # Monday
    1: 4,  # Tuesday
    2: 5,  # Wednesday
    3: 6,  # Thursday
    4: 7,  # Friday
}


def _format_currency_fa(value):
    return f"{to_persian_digits(f'{int(value or 0):,}')} تومان"


class AppointmentDetailView(SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View):
    template_name = "dashboards/appointment_detail.html"

    def _get_object(self, request, appointment_id):
        return get_object_or_404(
            OrderDetail.objects.select_related(
                "order__customer__user",
                "stylist__user",
                "service",
                "salon",
            ),
            pk=appointment_id,
            salon__salon_manager__user=request.user,
        )

    def _build_timeline(self, appointment):
        events = [
            {
                "title": "ثبت رزرو",
                "meta": format_jalali_with_weekday(appointment.order.register_date),
                "description": "رزرو توسط مشتری یا مجموعه در سیستم ثبت شده است.",
                "tone": "primary",
            }
        ]
        if appointment.order.stylist_approved or appointment.order.status in [
            "confirmed",
            "paid",
            "completed",
        ]:
            events.append(
                {
                    "title": "تایید نوبت",
                    "meta": format_jalali_with_weekday(appointment.order.update_date),
                    "description": "نوبت برای اجرای خدمت در تقویم مجموعه تایید شده است.",
                    "tone": "success",
                }
            )
        if appointment.order.is_paid or appointment.order.status in [
            "paid",
            "completed",
        ]:
            events.append(
                {
                    "title": "ثبت پرداخت",
                    "meta": format_jalali_with_weekday(appointment.order.update_date),
                    "description": "پرداخت این رزرو در وضعیت سفارش ثبت شده است.",
                    "tone": "success",
                }
            )
        events.append(
            {
                "title": "وضعیت فعلی",
                "meta": appointment.get_status_display_fa(),
                "description": "وضعیت فعلی این رزرو بر اساس داده‌های سفارش نمایش داده می‌شود.",
                "tone": "neutral",
            }
        )
        return events

    def get(self, request, appointment_id):
        appointment = self._get_object(request, appointment_id)
        customer = appointment.order.customer
        salon = appointment.salon
        back_url = reverse(
            "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
        )
        focus_back_url = (
            f"{back_url}?start={format_jalali_numeric(appointment.date)}&end={format_jalali_numeric(appointment.date)}"
            if appointment.date
            else back_url
        )

        context = build_dashboard_context(
            request.user,
            sidebar_active="appointments",
            page_title="جزئیات نوبت",
            request_path=request.path,
        )
        context.update(
            {
                "hide_dashboard_header": True,
                "salon": salon,
                "appointment": appointment,
                "appointment_view": {
                    "title": f"نوبت {customer.get_fullName()}",
                    "status_label": appointment.get_status_display_fa(),
                    "status_badge_class": {
                        "pending": "bg-amber-100 text-amber-700",
                        "confirmed": "bg-loomera-primarySoft text-loomera-primaryText",
                        "paid": "bg-emerald-100 text-emerald-700",
                        "completed": "bg-sky-100 text-sky-700",
                        "cancelled": "bg-rose-100 text-rose-700",
                    }.get(appointment.order.status, "bg-slate-100 text-slate-700"),
                    "order_code": getattr(
                        appointment.order, "order_number", f"ORD-{appointment.order_id}"
                    ),
                    "date_label": (
                        format_jalali_with_weekday(appointment.date)
                        if appointment.date
                        else "بدون تاریخ"
                    ),
                    "time_label": (
                        format_time_fa(appointment.time)
                        if appointment.time
                        else "--:--"
                    ),
                    "end_time_label": (
                        format_time_fa(appointment.end_time)
                        if appointment.end_time
                        else None
                    ),
                    "price_label": _format_currency_fa(appointment.price),
                    "back_url": focus_back_url,
                    "customer_name": customer.get_fullName(),
                    "customer_phone": getattr(customer.user, "mobile_number", None)
                    or "بدون شماره ثبت‌شده",
                    "customer_email": getattr(customer.user, "email", None) or "—",
                    "service_name": (
                        appointment.service.service_name
                        if appointment.service_id
                        else "خدمت ثبت نشده"
                    ),
                    "stylist_name": (
                        appointment.stylist.get_fullName()
                        if appointment.stylist_id
                        else "بدون متخصص"
                    ),
                    "notes": appointment.order.description
                    or "یادداشتی برای این نوبت ثبت نشده است.",
                    "payment_status": (
                        "پرداخت شده"
                        if appointment.order.is_paid
                        or appointment.order.status in ["paid", "completed"]
                        else "در انتظار پرداخت"
                    ),
                    "payment_badge": (
                        "bg-emerald-100 text-emerald-700"
                        if appointment.order.is_paid
                        or appointment.order.status in ["paid", "completed"]
                        else "bg-amber-100 text-amber-700"
                    ),
                    "actions": [
                        {
                            "key": "approve",
                            "label": "تایید نوبت",
                            "visible": appointment.order.status == "pending",
                            "class": "bg-loomera-primary text-white",
                        },
                        {
                            "key": "mark_paid",
                            "label": "ثبت پرداخت",
                            "visible": appointment.order.status
                            in ["confirmed", "pending"],
                            "class": "border border-slate-200 bg-white text-slate-800",
                        },
                        {
                            "key": "complete",
                            "label": "بستن نوبت",
                            "visible": appointment.order.status
                            in ["confirmed", "paid"],
                            "class": "border border-slate-200 bg-white text-slate-800",
                        },
                        {
                            "key": "cancel",
                            "label": "لغو نوبت",
                            "visible": appointment.order.status != "cancelled",
                            "class": "border border-rose-200 bg-rose-50 text-rose-700",
                        },
                    ],
                    "timeline": self._build_timeline(appointment),
                },
                "detail_items": [
                    {
                        "label": "عضو تیم",
                        "value": (
                            appointment.stylist.get_fullName()
                            if appointment.stylist_id
                            else "—"
                        ),
                    },
                    {
                        "label": "خدمت",
                        "value": (
                            appointment.service.service_name
                            if appointment.service_id
                            else "—"
                        ),
                    },
                    {
                        "label": "وضعیت سفارش",
                        "value": appointment.get_status_display_fa(),
                    },
                    {
                        "label": "شماره تماس مشتری",
                        "value": getattr(customer.user, "mobile_number", None) or "—",
                    },
                    {
                        "label": "بازگشت به تقویم",
                        "value": "مشاهده در تقویم",
                        "url": focus_back_url,
                        "icon": "fa-solid fa-arrow-left",
                    },
                ],
            }
        )
        return render(request, self.template_name, context)

    def post(self, request, appointment_id):
        appointment = self._get_object(request, appointment_id)
        action = request.POST.get("action")
        order = appointment.order

        if action == "approve":
            order.status = "confirmed"
            order.is_finally = True
            order.stylist_approved = True
            messages.success(request, "نوبت تایید شد.")
        elif action == "mark_paid":
            order.status = "paid"
            order.is_finally = True
            order.is_paid = True
            order.stylist_approved = True
            messages.success(request, "وضعیت پرداخت رزرو به‌روزرسانی شد.")
        elif action == "cancel":
            from apps.payments.finance import cancel_order_with_financials
            from apps.accounts.notifications import notify_booking_cancelled
            from apps.orders.lifecycle import cancel_order_reminder

            cancellation = cancel_order_with_financials(
                order=order,
                reason="لغو توسط مجموعه",
                refund_reason="لغو توسط مجموعه",
                payment=order.payment_order.order_by("-id").first(),
            )

            cancel_order_reminder(order)

            refund_amount = int(getattr(cancellation, "refund_amount", 0) or 0)

            notify_booking_cancelled(
                customer=order.customer,
                order=order,
                refund_amount=refund_amount,
            )

            notify_operational_milestone(
                order,
                event_type="manager_cancelled_booking",
                title="نوبت توسط مجموعه لغو شد",
                body="این نوبت از سمت مجموعه لغو شد و وضعیت رزرو برای مشتری به‌روزرسانی شد.",
            )

            messages.success(request, "نوبت لغو شد و به مشتری اطلاع داده شد.")
        else:
            messages.error(request, "عملیات انتخاب‌شده معتبر نیست.")
            return redirect(
                "dashboards:appointment_detail", appointment_id=appointment.id
            )

        if action != "cancel":
            order.save()
            from apps.payments.finance import sync_settlement_for_order

            sync_settlement_for_order(
                order, payment=order.payment_order.order_by("-id").first()
            )
        return redirect(
            "dashboards:appointment_detail_legacy", appointment_id=appointment.id
        )


@login_required
@manager_required
def reports_view(request, salon_id):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return redirect_response

    salon = get_object_or_404(Salon, pk=salon_id, salon_manager__user=request.user)

    if request.GET.get("export") == "csv":
        return build_reports_csv_response(request, salon)

    context = build_dashboard_context(
        request.user,
        nav_active="home",
        sidebar_active="reports",
        page_title="گزارش‌ها",
    )
    context.update(build_reports_context(request, salon))
    return render(request, "dashboards/reports.html", context)


def _build_manual_booking_frontend_context(*, salon, form):
    customer_qs = form.fields["customer"].queryset
    service_qs = form.fields["service"].queryset.prefetch_related("stylists__user")
    stylist_qs = form.fields["stylist"].queryset.prefetch_related("services_of_stylist")

    customers = [
        {
            "id": customer.pk,
            "name": customer.user.name or "",
            "family": customer.user.family or "",
            "mobile": customer.user.mobile_number or "",
            "label": f"{customer.get_fullName()} • {customer.user.mobile_number}",
        }
        for customer in customer_qs
    ]

    services = [
        {
            "id": service.pk,
            "name": service.service_name,
            "duration": int(getattr(service, "duration_minutes", 0) or 0),
            "stylist_ids": [
                str(stylist.pk)
                for stylist in service.stylists.filter(
                    stylists_of_salon=salon, is_active=True
                ).distinct()
            ],
        }
        for service in service_qs
    ]

    stylists = [
        {
            "id": stylist.pk,
            "name": stylist.get_fullName(),
            "service_ids": [
                str(service.pk)
                for service in stylist.services_of_stylist.filter(
                    services_of_salon=salon, is_active=True
                ).distinct()
            ],
        }
        for stylist in stylist_qs
    ]

    return {
        "manual_booking_customers_json": customers,
        "manual_booking_services_json": services,
        "manual_booking_stylists_json": stylists,
    }


class DashboardManualBookingAvailabilityView(LoginRequiredMixin, View):
    """Return only canonical free dates/times for the selected manager booking pair.

    The response intentionally reuses the same availability engine used by
    booking validation, so the dashboard never advertises a slot that the
    submit path will reject because of schedules, leave, existing bookings,
    or service buffers.
    """

    horizon_days = QUICK_LINK_AVAILABILITY_HORIZON_DAYS

    def get(self, request, salon_id):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        service_id = (request.GET.get("service_id") or "").strip()
        stylist_id = (request.GET.get("stylist_id") or "").strip()

        if not service_id or not stylist_id:
            return JsonResponse(
                {"availability": []},
                json_dumps_params={"ensure_ascii": False},
            )

        service = (
            Services.objects.filter(
                pk=service_id,
                services_of_salon=salon,
                is_active=True,
            )
            .distinct()
            .first()
        )
        if service is None:
            return JsonResponse(
                {"error": "خدمت انتخاب‌شده معتبر نیست."},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        stylist = (
            Stylist.objects.filter(
                pk=stylist_id,
                stylists_of_salon=salon,
                services_of_stylist=service,
                is_active=True,
            )
            .select_related("user")
            .distinct()
            .first()
        )
        if stylist is None:
            return JsonResponse(
                {"error": "این متخصص خدمت انتخاب‌شده را در این مجموعه ارائه نمی‌دهد."},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        availability = _quick_link_availability_days(
            salon=salon,
            service=service,
            stylist=stylist,
            horizon_days=self.horizon_days,
        )
        return JsonResponse(
            {
                "availability": availability,
                "horizon_days": self.horizon_days,
            },
            json_dumps_params={"ensure_ascii": False},
        )


class DashboardManualBookingView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/manual_booking_form.html"

    def get(self, request, salon_id):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        form = DashboardManualBookingForm(salon=salon)
        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="appointments",
            page_title="افزودن رزرو",
            request_path=request.path,
        )
        context.update(
            {
                "hide_dashboardHeader": True,
                "manual_booking_form": form,
                "manual_booking_salon": salon,
                "back_url": reverse(
                    "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
                ),
                "add_customer_url": reverse(
                    "accounts:add_customer", kwargs={"salon_id": salon.id}
                ),
            }
        )
        context.update(_build_manual_booking_frontend_context(salon=salon, form=form))
        return render(request, self.template_name, context)

    @transaction.atomic
    def post(self, request, salon_id):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        form = DashboardManualBookingForm(request.POST, salon=salon)
        if not form.is_valid():
            context = build_dashboard_context(
                request.user,
                nav_active="home",
                sidebar_active="appointments",
                page_title="افزودن رزرو",
                request_path=request.path,
            )
            context.update(
                {
                    "hide_dashboardHeader": True,
                    "manual_booking_form": form,
                    "manual_booking_salon": salon,
                    "back_url": reverse(
                        "dashboards:appointment_calendar", kwargs={"salon_id": salon.id}
                    ),
                    "add_customer_url": reverse(
                        "accounts:add_customer", kwargs={"salon_id": salon.id}
                    ),
                }
            )
            context.update(
                _build_manual_booking_frontend_context(salon=salon, form=form)
            )
            return render(request, self.template_name, context)

        cd = form.cleaned_data
        price = int(cd["resolved_price"] or 0)

        order = Order.objects.create(
            customer=cd["customer"],
            salon=salon,
            status="confirmed",
            is_finally=True,
            is_paid=False,
            selected_payment_method="pay_in_salon",
            requires_online_payment=False,
            subtotal_amount=price,
            discount_amount=0,
            basket_discount_amount=0,
            coupon_discount_amount=0,
            basket_discount_percent=0,
            basket_discount_title="",
            tax_amount=0,
            total_amount=price,
            coupon_code="",
            discount=0,
            platform_commission_applies=False,
            platform_commission_percent=0,
            platform_commission_amount=0,
            salon_payout_amount=price,
            checkout_locked_at=timezone.now(),
            description=(cd.get("notes") or "").strip(),
            booking_source="dashboard_manual",
        )
        appointment = OrderDetail.objects.create(
            order=order,
            service=cd["service"],
            stylist=cd["stylist"],
            salon=salon,
            price=price,
            date=cd["appointment_date"],
            time=cd["start_time"],
            end_time=cd["resolved_end_time"],
        )

        from apps.payments.finance import sync_settlement_for_order

        sync_settlement_for_order(order)
        messages.success(
            request, "رزرو دستی با موفقیت ثبت شد و برای آن کارمزدی اعمال نشد."
        )
        return redirect(
            "dashboards:appointment_detail",
            salon_id=salon.id,
            appointment_id=appointment.id,
        )


@login_required
@manager_required
def calendar_view(request, salon_id):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return redirect_response
    salon = get_object_or_404(Salon, pk=salon_id, salon_manager__user=request.user)
    base_url = reverse("dashboards:appointment_calendar", kwargs={"salon_id": salon.id})
    query_string = request.GET.urlencode()
    redirect_url = f"{base_url}?{query_string}" if query_string else base_url

    if request.method == "POST":
        return apply_bulk_appointment_action(request, salon, redirect_url)

    context = build_dashboard_context(
        request.user,
        nav_active="home",
        sidebar_active="appointments",
        page_title="مدیریت نوبت‌ها",
    )
    context.update(build_appointment_management_context(request, salon))
    return render(request, "dashboards/appointment_calendar.html", context)


@login_required
@manager_required
def get_calendar_data(request, salon_id):
    redirect_response = _redirect_to_required_onboarding(request)
    if redirect_response:
        return JsonResponse({"error": "onboarding_required"}, status=403)
    date_str = request.GET.get("date", timezone.localdate().strftime("%Y-%m-%d"))
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse(
            {"error": "Invalid date format. Use YYYY-MM-DD."}, status=400
        )

    salon = get_object_or_404(
        Salon.objects.defer("location"),
        pk=salon_id,
        salon_manager__user=request.user,
    )

    day_of_week_model = JALALI_WEEKDAY_MAP.get(selected_date.weekday())
    opening_hours = SalonOpeningHours.objects.filter(
        salon=salon,
        day_of_week=day_of_week_model,
    ).first()

    if not opening_hours or opening_hours.is_closed:
        return JsonResponse(
            {
                "salonIsOpen": False,
                "message": "مجموعه در این روز تعطیل است.",
                "appointments": [],
            }
        )

    appointments_qs = (
        OrderDetail.objects.filter(salon=salon, date=selected_date)
        .select_related("order__customer__user", "service", "stylist__user", "order")
        .order_by("time", "id")
    )

    appointments_data = []
    for detail in appointments_qs:
        if detail.date is None or detail.time is None:
            continue

        end_time = detail.end_time
        if not end_time:
            duration = detail.service.duration_minutes if detail.service else 60
            end_dt = datetime.combine(selected_date, detail.time) + timedelta(
                minutes=int(duration)
            )
            end_time = end_dt.time()

        order_status = detail.order.status or "pending"
        if detail.order.status == "cancelled":
            visual_status = "cancelled"
            visual_label = "لغو شده"
        elif detail.order.status == "no_show":
            visual_status = "no_show"
            visual_label = "عدم حضور"
        elif detail.order.status == "completed":
            visual_status = "completed"
            visual_label = "انجام شده"
        elif detail.order.is_paid:
            visual_status = "paid"
            visual_label = "پرداخت شده"
        elif detail.order.status == "confirmed":
            visual_status = "confirmed"
            visual_label = "تایید شده"
        else:
            visual_status = "unpaid"
            visual_label = "پرداخت‌نشده"

        appointments_data.append(
            {
                "id": detail.id,
                "order_id": detail.order_id,
                "customer_name": (
                    detail.order.customer.get_fullName()
                    if getattr(detail.order, "customer", None)
                    else "مشتری"
                ),
                "service_name": (
                    detail.service.service_name if detail.service else "خدمت"
                ),
                "stylist_name": (
                    detail.stylist.get_fullName() if detail.stylist else "متخصص"
                ),
                "start_time": detail.time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "status": visual_status,
                "status_label": visual_label,
                "is_paid": bool(detail.order.is_paid),
                "detail_url": reverse(
                    "dashboards:appointment_detail",
                    kwargs={"salon_id": salon.id, "appointment_id": detail.id},
                ),
            }
        )

    return JsonResponse(
        {
            "salonIsOpen": True,
            "openingHours": {
                "open_time": (
                    opening_hours.open_time.strftime("%H:%M")
                    if opening_hours.open_time
                    else ""
                ),
                "close_time": (
                    opening_hours.close_time.strftime("%H:%M")
                    if opening_hours.close_time
                    else ""
                ),
            },
            "appointments": appointments_data,
        },
        json_dumps_params={"ensure_ascii": False},
    )


# -----------------------------------------------------------------------
class ManagerAppointmentDetailView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/appointment_detail.html"

    def get(self, request, salon_id, appointment_id):
        salon = get_object_or_404(
            Salon.objects.defer("location"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        appointment = get_object_or_404(
            OrderDetail.objects.select_related(
                "order",
                "order__customer__user",
                "service",
                "stylist__user",
                "salon",
            ),
            pk=appointment_id,
            salon=salon,
        )

        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="appointments",
            page_title="جزئیات نوبت",
        )
        context.update({"salon": salon})
        context.update(build_manager_appointment_detail_context(salon, appointment))
        return render(request, self.template_name, context)


class ManagerAppointmentActionView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    def post(self, request, salon_id, appointment_id):
        salon = get_object_or_404(
            Salon.objects.defer("location"),
            pk=salon_id,
            salon_manager__user=request.user,
        )
        appointment = get_object_or_404(
            OrderDetail.objects.select_related(
                "order",
                "order__customer__user",
                "service",
                "stylist__user",
                "salon",
            ),
            pk=appointment_id,
            salon=salon,
        )

        action = (request.POST.get("action") or "").strip()

        try:
            message = apply_partner_appointment_action(
                appointment.order,
                appointment,
                action,
                actor=request.user,
            )
            messages.success(request, message)
        except ValidationError as exc:
            messages.error(request, str(exc))

        return redirect(
            "dashboards:appointment_detail",
            salon_id=salon.id,
            appointment_id=appointment.id,
        )


class ManagerNotificationCenterView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    template_name = "dashboards/notifications_center.html"

    def get(self, request, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )
        active_category = (request.GET.get("category") or "all").strip()
        context = build_dashboard_context(
            request.user,
            nav_active="overview",
            sidebar_active="overview",
            request_path=request.path,
        )
        notifications = context.get("dashboard_notifications", {})
        tabs = notifications.get("tabs", [])
        valid_categories = {tab["key"] for tab in tabs}
        if active_category not in valid_categories:
            active_category = "all"
        items = notifications.get("items", [])
        if active_category != "all":
            items = [item for item in items if item.get("category") == active_category]
        context.update(
            {
                "salon": salon,
                "notification_center_title": "مرکز اعلان‌های مدیر مجموعه",
                "notification_center_description": "اعلان‌های رزرو، مالی، مشتری و تیم را یک‌جا ببین و مستقیم وارد صفحه مرتبط شو.",
                "notification_center_empty_label": "هنوز اعلانی برای این مجموعه ثبت نشده است.",
                "notification_center": {
                    "tabs": tabs,
                    "items": items,
                    "active_category": active_category,
                    "is_empty": len(items) == 0,
                },
            }
        )
        return render(request, self.template_name, context)


# ------------------------------------------------------------------------------


def _build_stylist_lifecycle_timeline(order, detail=None):
    """Show only real lifecycle events for this appointment item.

    Static checklist rows caused duplicate-looking timeline entries after the
    stylist performed actions. The timeline should grow only when an event is
    actually written for this OrderDetail.
    """
    if detail is None:
        return []

    return [
        {
            "title": event.get_event_type_display(),
            "meta": (
                format_jalali_with_weekday(event.created_at)
                if event.created_at
                else "—"
            ),
            "description": event.note
            or "این رویداد در تاریخچه همین آیتم نوبت ثبت شده است.",
        }
        for event in detail.events.select_related("actor").order_by("created_at", "id")[
            :20
        ]
    ]


def _get_allowed_stylist_lifecycle_actions(detail):
    order = detail.order
    if order.status == "cancelled":
        return []

    actions = []

    if detail.confirmation_status == OrderDetail.ConfirmationStatus.PENDING:
        actions.append(
            {
                "key": "confirm",
                "label": "تایید نوبت",
                "class": "bg-loomera-primary text-white",
            }
        )
        actions.append(
            {
                "key": "reject",
                "label": "رد نوبت",
                "class": "border border-rose-200 bg-rose-50 text-rose-700",
            }
        )
        return actions

    if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
        return []

    if (
        detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED
        and not detail.customer_arrived_at
        and not detail.no_show_pending_at
    ):
        if not detail.client_late_recorded_at:
            actions.append(
                {
                    "key": "client_late",
                    "label": "ثبت تأخیر مشتری",
                    "class": "border border-amber-200 bg-amber-50 text-amber-700",
                }
            )
        actions.append(
            {
                "key": "arrived",
                "label": "ثبت رسیدن مشتری",
                "class": "border border-slate-200 bg-white text-slate-800",
            }
        )
        actions.append(
            {
                "key": "no_show_pending",
                "label": "ثبت عدم حضور برای بررسی",
                "class": "border border-orange-200 bg-orange-50 text-orange-700",
            }
        )

    if detail.no_show_pending_at and not detail.no_show_confirmed_at:
        actions.append(
            {
                "key": "confirm_no_show",
                "label": "تأیید نهایی عدم حضور",
                "class": "border border-rose-200 bg-rose-50 text-rose-700",
            }
        )
        actions.append(
            {
                "key": "mark_disputed",
                "label": "ارسال برای بررسی اختلاف",
                "class": "border border-slate-200 bg-white text-slate-800",
            }
        )

    if detail.customer_arrived_at and not detail.service_started_at:
        actions.append(
            {
                "key": "start_service",
                "label": "شروع کار",
                "class": "border border-slate-200 bg-white text-slate-800",
            }
        )

    if detail.service_started_at and not detail.service_completed_at:
        # ثبت دستی «طولانی‌شدن خدمت» از جریان عملیاتی حذف شده است تا نوبت‌ها
        # به‌خاطر اختلاف زمان سیستم/مدت خدمت دچار وضعیت مبهم نشوند.
        # اگر خدمت دیرتر تمام شود، زمان واقعی پایان خدمت در complete_service ذخیره می‌شود
        # و گزارش‌ها می‌توانند overrun را از همان زمان واقعی محاسبه کنند.
        actions.append(
            {
                "key": "complete_service",
                "label": "پایان کار",
                "class": "border border-emerald-200 bg-emerald-50 text-emerald-700",
            }
        )

    return actions


def _apply_stylist_lifecycle_action(detail, action, *, actor=None):
    from apps.payments.finance import (
        finalize_order_financials,
        sync_settlement_for_order,
    )

    now = timezone.now()

    detail = (
        OrderDetail.objects.select_for_update(of=("self",))
        .select_related("order", "service", "stylist", "salon")
        .get(pk=detail.pk)
    )
    order = Order.objects.select_for_update().get(pk=detail.order_id)

    if order.status == "cancelled":
        raise ValidationError("این رزرو لغو شده است.")

    if action == "confirm_cash_payment":
        result = confirm_pay_in_salon_cash_payment(order, actor=actor, role="stylist")
        if result.get("already_paid"):
            return "پرداخت این رزرو قبلاً نهایی شده است."
        if result.get("finalized"):
            return "دریافت پرداخت نقدی تایید شد و چون مشتری هم تایید کرده بود، پرداخت رزرو نهایی شد."
        return (
            "تایید دریافت پرداخت نقدی ثبت شد. پرداخت بعد از تایید مشتری نهایی می‌شود."
        )

    was_fully_confirmed = not order.order_details1.exclude(
        confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
    ).exists()

    if action == "confirm":
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED:
            raise ValidationError("این خدمت قبلاً تایید شده است.")
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
            raise ValidationError("این خدمت قبلاً رد شده است.")

        confirm_order_detail(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()

        is_fully_confirmed = not order.order_details1.exclude(
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED
        ).exists()

        sync_settlement_for_order(
            order, payment=order.payment_order.order_by("-id").first()
        )

        # Customer confirmation notice is emitted exactly once inside
        # confirm_order_detail when the whole multi-service order flips
        # from partial to fully confirmed.

        return "این خدمت با موفقیت از سمت متخصص تایید شد."

    if action == "reject":
        if detail.confirmation_status == OrderDetail.ConfirmationStatus.CONFIRMED:
            raise ValidationError("خدمت تایید شده را از این بخش نمی‌توان رد کرد.")

        if detail.confirmation_status == OrderDetail.ConfirmationStatus.REJECTED:
            raise ValidationError("این خدمت قبلاً رد شده است.")

        reject_order_detail(
            detail=detail,
            actor=actor,
            reason="رد شده توسط متخصص",
        )

        order.refresh_from_db()

        return (
            "این نوبت رد و به‌صورت خودکار لغو شد. به مشتری و مدیر مجموعه اطلاع داده شد."
        )

    if action == "client_late":
        mark_client_late(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()
        notify_operational_milestone(
            order,
            event_type="client_late",
            title="تأخیر مشتری ثبت شد",
            body="متخصص تأخیر مشتری را ثبت کرد. این وضعیت فقط برای بررسی عملیاتی ثبت شده و نوبت‌های بعدی را جابه‌جا نمی‌کند.",
        )
        return "تأخیر مشتری ثبت شد."

    if action == "arrived":
        mark_order_detail_customer_arrived(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()
        notify_operational_milestone(
            order,
            event_type="customer_arrived",
            title="مشتری به مجموعه رسید",
            body="رسیدن مشتری برای این رزرو از سمت متخصص ثبت شد.",
        )
        return "رسیدن مشتری ثبت شد."

    if action == "no_show_pending":
        mark_no_show_pending(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()
        notify_operational_milestone(
            order,
            event_type="no_show_pending_review",
            title="عدم حضور مشتری در انتظار بررسی ثبت شد",
            body="برای این نوبت عدم حضور در وضعیت بررسی ثبت شد. مشتری/مدیر می‌توانند نتیجه را پیگیری کنند.",
        )
        return "عدم حضور مشتری در وضعیت بررسی ثبت شد."

    if action == "confirm_no_show":
        confirm_no_show(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()
        notify_operational_milestone(
            order,
            event_type="no_show_confirmed",
            title="عدم حضور مشتری تایید شد",
            body="عدم حضور این نوبت بعد از بررسی تایید شد.",
        )
        return "عدم حضور مشتری تایید شد."

    if action == "mark_disputed":
        mark_order_detail_disputed(
            detail=detail, actor=actor, note="ثبت اختلاف از داشبورد متخصص"
        )
        order.refresh_lifecycle_from_details()
        notify_operational_milestone(
            order,
            event_type="appointment_disputed",
            title="نوبت وارد وضعیت اختلاف شد",
            body="این نوبت برای بررسی بیشتر وارد وضعیت اختلاف شد.",
        )
        return "این نوبت برای بررسی اختلاف ثبت شد."

    if action == "start_service":
        if not detail.customer_arrived_at:
            raise ValidationError("ابتدا باید رسیدن مشتری ثبت شود.")
        if detail.service_started_at:
            raise ValidationError("شروع این خدمت قبلاً ثبت شده است.")

        start_order_detail_service(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()

        notify_operational_milestone(
            order,
            event_type="service_started",
            title="انجام کار شروع شد",
            body=f"اجرای خدمت {detail.service.service_name if detail.service_id else ''} شروع شد.",
        )

        return "شروع کار ثبت شد."

    if action == "service_overrun":
        raise ValidationError(
            "ثبت دستی طولانی‌شدن خدمت غیرفعال شده است. برای پایان کار از دکمه «پایان کار» استفاده کن؛ زمان واقعی پایان خدمت در گزارش‌ها ثبت می‌شود."
        )

    if action == "complete_service":
        complete_order_detail_service(detail=detail, actor=actor)
        order.refresh_lifecycle_from_details()

        all_completed = not order.order_details1.filter(
            service_completed_at__isnull=True
        ).exists()

        if all_completed:
            latest_payment = order.payment_order.order_by("-id").first()

            sync_settlement_for_order(order, payment=latest_payment)

            notify_operational_milestone(
                order,
                event_type="service_completed",
                title="خدمت به پایان رسید",
                body="همه خدمات این رزرو انجام شدند. اکنون مواد مصرفی باید ثبت و محاسبات مالی نهایی شود.",
            )

            if order.selected_payment_method == "pay_in_salon" and not order.is_paid:
                notify_operational_milestone(
                    order,
                    event_type="pay_in_salon_pending",
                    title="رزرو آماده تسویه در مجموعه است",
                    body="خدمت کامل شده و مشتری می‌تواند پرداخت نقدی را تایید کند یا آنلاین بپردازد.",
                )
            else:
                mark_review_requested(order)
        else:
            notify_operational_milestone(
                order,
                event_type="service_completed",
                title="یک خدمت به پایان رسید",
                body=f"خدمت {detail.service.service_name if detail.service_id else ''} انجام شد. هنوز همه خدمات این رزرو کامل نشده‌اند.",
            )

        return "پایان کار ثبت شد."

    raise ValidationError("این عملیات معتبر نیست.")


def _active_future_appointment_count_for_membership(membership):
    if not membership or not membership.stylist_id or not membership.salon_id:
        return 0

    return (
        OrderDetail.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
            date__gte=timezone.localdate(),
        )
        .exclude(order__status__in=["cancelled", "completed", "no_show"])
        .count()
    )


def _membership_future_appointment_block_message(membership):
    count = _active_future_appointment_count_for_membership(membership)
    count_label = to_persian_digits(count)

    return (
        f"برای این همکاری {count_label} نوبت فعال یا آینده وجود دارد. "
        "قبل از پایان همکاری باید نوبت‌ها انجام، جابه‌جا یا با ذکر علت لغو شوند."
    )


def _notify_stylist_about_membership_request_review(
    *, membership, actor=None, accepted=False
):
    stylist = membership.stylist
    salon = membership.salon
    stylist_user = getattr(stylist, "user", None)

    if not stylist_user:
        return None

    salon_name = getattr(salon, "salon_name", "مجموعه")

    if accepted:
        title = "درخواست همکاری تایید شد"
        body = f"درخواست همکاری شما با {salon_name} تایید شد."
        event_type = "stylist_membership_request_accepted"
        priority = NotificationPriority.HIGH
        icon = "fa-solid fa-user-check"
    else:
        title = "درخواست همکاری رد شد"
        body = f"درخواست همکاری شما با {salon_name} رد شد."
        event_type = "stylist_membership_request_rejected"
        priority = NotificationPriority.NORMAL
        icon = "fa-solid fa-user-xmark"

    return create_notification(
        event_type=event_type,
        category=NotificationCategory.STAFF,
        priority=priority,
        title=title,
        body=body,
        action_url=f"{reverse('dashboards:stylist_profile')}#stylist-collaboration-section",
        icon=icon,
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=membership,
        metadata={
            "membership_id": membership.id,
            "salon_id": salon.id if salon else None,
            "stylist_id": stylist.user_id if stylist else None,
            "accepted": accepted,
        },
        dedupe_key=f"stylist_membership_request_review:{membership.id}:{'accepted' if accepted else 'rejected'}",
    )


def _notify_stylist_about_collaboration_closed(
    *, membership, actor=None, ended_by_manager=False
):
    stylist = membership.stylist
    salon = membership.salon
    stylist_user = getattr(stylist, "user", None)

    if not stylist_user:
        return None

    salon_name = getattr(salon, "salon_name", "مجموعه")

    if ended_by_manager:
        title = "همکاری با مجموعه پایان یافت"
        body = f"مدیر {salon_name} همکاری شما با این مجموعه را پایان داد. دسترسی‌های مربوط به همین مجموعه بسته شد."
        event_type = "collaboration_ended_by_manager"
    else:
        title = "جدا شدن از مجموعه ثبت شد"
        body = f"همکاری شما با {salon_name} پایان یافت و دسترسی‌های مربوط به همین مجموعه بسته شد."
        event_type = "collaboration_left_by_stylist"

    return create_notification(
        event_type=event_type,
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title=title,
        body=body,
        action_url=f"{reverse('dashboards:stylist_profile')}#stylist-collaboration-section",
        icon="fa-solid fa-user-xmark",
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=membership,
        metadata={
            "membership_id": membership.id,
            "salon_id": salon.id if salon else None,
            "stylist_id": stylist.user_id if stylist else None,
            "ended_by_manager": ended_by_manager,
        },
        dedupe_key=f"collaboration_closed:{membership.id}:{'manager' if ended_by_manager else 'stylist'}",
    )


def _notify_manager_about_stylist_left_collaboration(*, membership, actor=None):
    salon = membership.salon
    stylist = membership.stylist
    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)

    if not manager_user or not stylist:
        return None

    return create_notification(
        event_type="collaboration_left_by_stylist",
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title="متخصص از مجموعه جدا شد",
        body=f"{stylist.get_fullName()} همکاری با {salon.salon_name} را پایان داد.",
        action_url=reverse("dashboards:team_member"),
        icon="fa-solid fa-right-from-bracket",
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=membership,
        metadata={
            "membership_id": membership.id,
            "salon_id": salon.id,
            "stylist_id": stylist.user_id,
        },
        dedupe_key=f"collaboration_left_manager_notice:{membership.id}",
    )


def _disable_membership_dashboard_permissions(membership):
    permissions = getattr(membership, "dashboard_permissions", None)
    if not permissions:
        return

    permission_fields = [
        "can_complete_appointments",
        "can_view_own_finance",
        "can_request_payout",
        "can_view_own_clients",
        "can_create_own_bookings",
        "can_view_client_phone",
        "can_manage_own_portfolio",
        "can_submit_posts",
        "can_submit_stories",
        "can_request_leave",
        "can_manage_own_schedule",
    ]

    for field_name in permission_fields:
        setattr(permissions, field_name, False)

    permissions.save(update_fields=[*permission_fields, "updated_at"])


def _close_membership_access(
    *,
    membership,
    actor,
    request=None,
    new_status,
    event_type,
    reason,
    metadata=None,
):
    if not membership or membership.status != SalonMembershipStatus.ACTIVE:
        return membership

    old_status = membership.status
    future_appointments_count = _active_future_appointment_count_for_membership(
        membership
    )

    with transaction.atomic():
        membership = change_membership_status(
            membership=membership,
            new_status=new_status,
            actor=actor,
            reason=reason,
            request=request,
        )

        membership_metadata = dict(membership.metadata or {})
        membership_metadata.update(metadata or {})
        membership_metadata.update(
            {
                "access_closed_at": timezone.now().isoformat(),
                "future_appointments_count_at_closure": future_appointments_count,
            }
        )

        membership.metadata = membership_metadata
        membership.show_on_salon_profile = False
        membership.save(
            update_fields=[
                "metadata",
                "show_on_salon_profile",
                "updated_at",
            ]
        )

        if membership.stylist_id:
            membership.salon.stylists.remove(membership.stylist)

        _disable_membership_dashboard_permissions(membership)

        closure_date = timezone.localdate()
        legacy_end_date = closure_date - timedelta(days=1)

        JobDetails.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=closure_date)).update(
            end_date=legacy_end_date
        )

        # چون قبل از پایان همکاری نوبت آینده را block کرده‌ایم، شیفت‌های آینده
        # این همکاری باید حذف شوند تا availability همان سالن دوباره متخصص را نشان ندهد.
        StylistSchedule.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
            date__gte=closure_date,
        ).delete()

        StaffScheduleRequest.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
            status=StaffScheduleRequest.Status.PENDING,
        ).update(
            status=StaffScheduleRequest.Status.CANCELLED,
            reviewed_by=actor if getattr(actor, "is_authenticated", False) else None,
            reviewed_at=timezone.now(),
            review_note="به دلیل پایان همکاری با مجموعه، درخواست برنامه کاری لغو شد.",
        )

        StaffLeaveRequest.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
            status=StaffLeaveRequest.Status.PENDING,
        ).update(
            status=StaffLeaveRequest.Status.CANCELLED,
            reviewed_by=actor if getattr(actor, "is_authenticated", False) else None,
            reviewed_at=timezone.now(),
            review_note="به دلیل پایان همکاری با مجموعه، درخواست مرخصی لغو شد.",
        )

        log_membership_event(
            membership,
            event_type=event_type,
            actor=actor,
            old_status=old_status,
            new_status=new_status,
            note=reason,
            metadata=membership_metadata,
        )

    return membership


def _stylist_status_meta(order):
    mapping = {
        "pending": {
            "label": "در انتظار تایید",
            "badge_class": "bg-amber-100 text-amber-700",
        },
        "confirmed": {
            "label": "تایید شده",
            "badge_class": "bg-loomera-primarySoft text-loomera-primaryText",
        },
        "paid": {
            "label": "پرداخت شده",
            "badge_class": "bg-emerald-100 text-emerald-700",
        },
        "completed": {"label": "انجام شده", "badge_class": "bg-sky-100 text-sky-700"},
        "cancelled": {"label": "لغو شده", "badge_class": "bg-rose-100 text-rose-700"},
        "no_show": {
            "label": "عدم حضور",
            "badge_class": "bg-orange-100 text-orange-700",
        },
        "disputed": {
            "label": "دارای اختلاف",
            "badge_class": "bg-slate-100 text-slate-700",
        },
    }
    return mapping.get(getattr(order, "status", "pending"), mapping["pending"])


def _serialize_stylist_appointment_card(detail, *, can_view_client_phone=True):
    customer = getattr(detail.order, "customer", None)
    customer_name = customer.get_fullName() if customer else "مشتری ثبت نشده"
    customer_phone = (
        getattr(getattr(customer, "user", None), "mobile_number", "")
        if customer and can_view_client_phone
        else ""
    )
    status_meta = _stylist_detail_status_meta(detail)
    pricing = _stylist_item_pricing_meta(detail)
    return {
        "id": detail.id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service_name": (
            detail.service.service_name if detail.service_id else "خدمت ثبت نشده"
        ),
        "date_label": (
            format_jalali_with_weekday(detail.date) if detail.date else "بدون تاریخ"
        ),
        "time_label": format_time_fa(detail.time) if detail.time else "بدون ساعت",
        "end_time_label": format_time_fa(detail.end_time) if detail.end_time else "—",
        "status_label": status_meta["label"],
        "status_badge_class": status_meta["badge_class"],
        "price_label": pricing["final_price_label"],
        "base_price_label": pricing["base_price_label"],
        "discount_label": pricing["discount_label"],
        "has_discount": pricing["has_discount"],
        "detail_url": reverse(
            "dashboards:stylist_appointment_detail",
            kwargs={"appointment_id": detail.id},
        ),
        "payment_method": (
            detail.order.get_selected_payment_method_display()
            if hasattr(detail.order, "get_selected_payment_method_display")
            else (detail.order.selected_payment_method or "—")
        ),
        "payment_state": "پرداخت شده" if detail.order.is_paid else "پرداخت‌نشده",
        "salon_name": detail.salon.salon_name if detail.salon_id else "",
    }


def _serialize_stylist_schedule_row(item):
    return {
        "date_label": format_jalali_with_weekday(item.date) if item.date else "—",
        "service_name": item.service.service_name if item.service_id else "همه خدمات",
        "start_label": format_time_fa(item.start_time) if item.start_time else "—",
        "end_label": format_time_fa(item.end_time) if item.end_time else "—",
        "salon_name": item.salon.salon_name if item.salon_id else "—",
    }


def _serialize_stylist_time_off_row(item):
    if item.start_time and item.end_time:
        time_label = (
            f"{format_time_fa(item.start_time)} تا {format_time_fa(item.end_time)}"
        )
    else:
        time_label = "تمام روز"

    is_leave_request = isinstance(item, StaffLeaveRequest)

    return {
        "date_label": format_jalali_with_weekday(item.date) if item.date else "—",
        "time_label": time_label,
        "reason": item.reason or "مرخصی",
        "source_label": (
            "درخواست تاییدشده مدیر" if is_leave_request else "مرخصی ثبت‌شده"
        ),
        "sort_key": f"{item.date.isoformat() if item.date else ''}-{item.start_time or ''}",
    }


def _serialize_stylist_service_coverage(service, stylist):
    return {
        "name": service.service_name,
        "duration_label": f"{to_persian_digits(getattr(service, 'duration_minutes', 0) or 0)} دقیقه",
        "price_label": _dashboard_currency(stylist.get_price_for_service(service) or 0),
    }


def _stylist_portfolio_queryset(stylist, salon=None):
    qs = WorkSamples.objects.filter(stylist=stylist).select_related(
        "service", "salon", "appointment"
    )
    if salon is not None:
        qs = qs.filter(Q(salon=salon) | Q(salon__isnull=True))
    return qs.order_by("-is_verified_work", "-id")


def _serialize_stylist_portfolio_item(sample):
    try:
        image_url = sample.sample_image.url if sample.sample_image else ""
    except Exception:
        image_url = ""

    return {
        "id": sample.pk,
        "image_url": image_url,
        "description": sample.description or "",
        "service_name": (
            sample.service.service_name if sample.service_id else "بدون خدمت مشخص"
        ),
        "salon_name": sample.salon.salon_name if sample.salon_id else "عمومی",
        "is_active": bool(sample.is_active),
        "is_public": bool(sample.is_public),
        "is_verified": bool(sample.is_verified_work),
        "status_label": "منتشر" if sample.is_active and sample.is_public else "مخفی",
    }


def _stylist_portfolio_payload(stylist, salon=None, *, form=None):
    samples = [
        _serialize_stylist_portfolio_item(sample)
        for sample in _stylist_portfolio_queryset(stylist, salon=salon)[:24]
    ]
    return {
        "work_sample_form": form or WorkSamplesForm(stylist=stylist, salon=salon),
        "portfolio_samples": samples,
        "portfolio_count_label": to_persian_digits(len(samples)),
    }


def _build_stylist_profile_summary(stylist, salon=None):
    active_services = Services.objects.filter(
        stylists=stylist,
        is_active=True,
    ).distinct()

    if salon is not None:
        active_services = active_services.filter(services_of_salon=salon)

    active_services = active_services.order_by("service_name")

    today = timezone.localdate()

    next_shift_qs = StylistSchedule.objects.filter(
        stylist=stylist,
        date__gte=today,
    )
    if salon is not None:
        next_shift_qs = next_shift_qs.filter(salon=salon)

    next_shift = next_shift_qs.order_by("date", "start_time").first()

    next_time_off_qs = StaffLeaveRequest.objects.filter(
        stylist=stylist,
        status=StaffLeaveRequest.Status.APPROVED,
        date__gte=today,
    )
    if salon is not None:
        next_time_off_qs = next_time_off_qs.filter(salon=salon)

    next_time_off = next_time_off_qs.order_by("date", "start_time").first()

    profile_completion = 0
    if stylist.expert:
        profile_completion += 1
    if stylist.description:
        profile_completion += 1
    if stylist.profile_image:
        profile_completion += 1
    if stylist.insta_link or stylist.linkedin_link or stylist.telegram_link:
        profile_completion += 1
    if active_services.exists():
        profile_completion += 1
    if (
        _stylist_portfolio_queryset(stylist, salon=salon)
        .filter(
            is_active=True,
            is_public=True,
            review_status__in=["published", "approved"],
        )
        .exists()
    ):
        profile_completion += 1

    return {
        "headline": (
            stylist.get_fullName() if hasattr(stylist, "get_fullName") else str(stylist)
        ),
        "expert": stylist.expert or "تخصص ثبت نشده",
        "salon_name": salon.salon_name if salon else "بدون مجموعه فعال",
        "profile_completion_label": f"{to_persian_digits(profile_completion)} از {to_persian_digits(6)} بخش",
        "next_shift_label": (
            format_jalali_with_weekday(next_shift.date) if next_shift else "ثبت نشده"
        ),
        "next_shift_meta": (
            f"{format_time_fa(next_shift.start_time)} تا {format_time_fa(next_shift.end_time)}"
            if next_shift and next_shift.start_time and next_shift.end_time
            else "هنوز شیفت آینده‌ای ثبت نشده است."
        ),
        "next_time_off_label": (
            format_jalali_with_weekday(next_time_off.date)
            if next_time_off
            else "بدون مرخصی"
        ),
        "next_time_off_meta": (
            (
                f"{format_time_fa(next_time_off.start_time)} تا {format_time_fa(next_time_off.end_time)}"
                if next_time_off.start_time and next_time_off.end_time
                else "تمام روز"
            )
            if next_time_off
            else "در آینده نزدیک مرخصی تاییدشده‌ای ثبت نشده است."
        ),
        "active_services": [
            _serialize_stylist_service_coverage(service, stylist)
            for service in active_services[:8]
        ],
    }


def _membership_status_ui(status):
    mapping = {
        SalonMembershipStatus.INVITED: {
            "label": "دعوت‌شده",
            "badge_class": "bg-sky-100 text-sky-700",
        },
        SalonMembershipStatus.PENDING_ACCEPTANCE: {
            "label": "در انتظار تایید مدیر",
            "badge_class": "bg-amber-100 text-amber-700",
        },
        SalonMembershipStatus.ACTIVE: {
            "label": "فعال",
            "badge_class": "bg-emerald-100 text-emerald-700",
        },
        SalonMembershipStatus.PAUSED: {
            "label": "موقتاً غیرفعال",
            "badge_class": "bg-slate-100 text-slate-700",
        },
        SalonMembershipStatus.ENDED: {
            "label": "قطع همکاری",
            "badge_class": "bg-slate-100 text-slate-600",
        },
        SalonMembershipStatus.REJECTED: {
            "label": "رد شده",
            "badge_class": "bg-rose-100 text-rose-700",
        },
        SalonMembershipStatus.EXPIRED: {
            "label": "منقضی شده",
            "badge_class": "bg-slate-100 text-slate-600",
        },
        SalonMembershipStatus.CANCELLED_BY_SALON: {
            "label": "لغو شده توسط سالن",
            "badge_class": "bg-slate-100 text-slate-600",
        },
    }
    return mapping.get(
        status,
        {
            "label": "نامشخص",
            "badge_class": "bg-slate-100 text-slate-600",
        },
    )


def _serialize_stylist_membership_row(membership):
    status_ui = _membership_status_ui(membership.status)
    salon = membership.salon
    metadata = membership.metadata or {}
    message = metadata.get("request_message") or metadata.get("invite_message") or ""
    if membership.status == SalonMembershipStatus.ENDED and metadata.get(
        "cancelled_by_stylist"
    ):
        status_ui = {
            "label": "حذف شده توسط شما",
            "badge_class": "bg-slate-100 text-slate-600",
        }

    return {
        "id": membership.id,
        "salon_name": salon.salon_name if salon else "سالن حذف‌شده",
        "status": membership.status,
        "status_label": status_ui["label"],
        "status_badge_class": status_ui["badge_class"],
        "role_title": membership.role_title or "بدون عنوان نقش",
        "created_label": (
            format_jalali_with_weekday(membership.created_at)
            if membership.created_at
            else "—"
        ),
        "message": message,
        "is_pending_request": membership.status
        == SalonMembershipStatus.PENDING_ACCEPTANCE,
        "can_manage_request": (
            membership.status == SalonMembershipStatus.PENDING_ACCEPTANCE
            and bool(metadata.get("requested_by_stylist"))
        ),
        "is_manager_invite": bool(metadata.get("invited_by_manager")),
        "can_accept_invite": (
            membership.status == SalonMembershipStatus.INVITED
            and bool(metadata.get("invited_by_manager"))
        ),
        "can_reject_invite": (
            membership.status == SalonMembershipStatus.INVITED
            and bool(metadata.get("invited_by_manager"))
        ),
        "can_leave_membership": membership.status == SalonMembershipStatus.ACTIVE,
        "leave_warning": "با جدا شدن از این مجموعه، دسترسی شما به نوبت‌ها، مشتریان، مالی و برنامه کاری این مجموعه بسته می‌شود.",
    }


def _get_stylist_emergency_info(stylist):
    return EmergencyInfo.objects.filter(stylist=stylist).order_by("id").first()


def _is_stylist_profile_ready_for_request(stylist):
    user = stylist.user
    emergency_info = _get_stylist_emergency_info(stylist)

    missing_items = []

    if not (user.name or "").strip():
        missing_items.append("نام")
    if not (user.family or "").strip():
        missing_items.append("نام خانوادگی")
    if not (stylist.expert or "").strip():
        missing_items.append("تخصص اصلی")
    if not (stylist.resume_headline or "").strip():
        missing_items.append("عنوان حرفه‌ای")
    if not (stylist.resume_summary or "").strip():
        missing_items.append("خلاصه رزومه")
    if not (stylist.description or "").strip():
        missing_items.append("توضیحات حرفه‌ای")

    if not emergency_info:
        missing_items.append("اطلاعات تماس اضطراری")
    else:
        if not (emergency_info.full_name or "").strip():
            missing_items.append("نام تماس اضطراری")
        if not (emergency_info.emergency_contact or "").strip():
            missing_items.append("شماره تماس اضطراری")
        if not (emergency_info.relationship or "").strip():
            missing_items.append("نسبت تماس اضطراری")

    return {
        "is_ready": not missing_items,
        "missing_items": missing_items,
        "missing_items_label": "، ".join(missing_items),
        "emergency_info": emergency_info,
    }


def _build_stylist_collaboration_workspace(stylist):
    readiness = _is_stylist_profile_ready_for_request(stylist)
    mobile = normalize_mobile(getattr(stylist.user, "mobile_number", "") or "")

    memberships = list(
        SalonMembership.objects.select_related("salon", "stylist__user")
        .filter(
            Q(stylist=stylist)
            | Q(
                stylist__isnull=True,
                invited_phone=mobile,
                status=SalonMembershipStatus.INVITED,
            )
        )
        .order_by("-created_at", "-id")
    )

    blocked_statuses = {
        SalonMembershipStatus.ACTIVE,
        SalonMembershipStatus.PENDING_ACCEPTANCE,
        SalonMembershipStatus.INVITED,
        SalonMembershipStatus.PAUSED,
    }
    blocked_salon_ids = [
        membership.salon_id
        for membership in memberships
        if membership.salon_id and membership.status in blocked_statuses
    ]

    available_salons = (
        Salon.objects.filter(is_active=True)
        .exclude(id__in=blocked_salon_ids)
        .select_related("neighborhood")
        .order_by("salon_name")[:80]
    )

    active_count = sum(
        1 for item in memberships if item.status == SalonMembershipStatus.ACTIVE
    )
    pending_count = sum(
        1
        for item in memberships
        if item.status == SalonMembershipStatus.PENDING_ACCEPTANCE
    )

    return {
        "available_salons": available_salons,
        "memberships": [
            _serialize_stylist_membership_row(item) for item in memberships[:20]
        ],
        "active_count_label": to_persian_digits(active_count),
        "pending_count_label": to_persian_digits(pending_count),
        "can_request": readiness["is_ready"],
        "readiness": readiness,
    }


def _notify_stylist_about_manager_invite(*, membership, actor=None):
    stylist = membership.stylist
    salon = membership.salon

    stylist_user = getattr(stylist, "user", None)
    if not stylist_user:
        return None

    salon_name = getattr(salon, "salon_name", "مجموعه")
    action_url = (
        f"{reverse('dashboards:stylist_profile')}#stylist-collaboration-section"
    )

    return create_notification(
        event_type="manager_invited_stylist",
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title="دعوت همکاری از طرف مجموعه",
        body=f"{salon_name} برای همکاری از شما دعوت کرده است.",
        action_url=action_url,
        icon="fa-solid fa-envelope-open-text",
        recipients=[
            {
                "user": stylist_user,
                "audience_role": NotificationAudienceRole.STYLIST,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=membership,
        metadata={
            "membership_id": membership.id,
            "salon_id": salon.id,
            "stylist_id": stylist.user_id,
        },
        dedupe_key=f"manager_invited_stylist:{membership.id}",
    )


def _notify_manager_about_invite_response(*, membership, actor=None, accepted=False):
    salon = membership.salon
    stylist = membership.stylist

    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)
    if not manager_user or not stylist:
        return None

    stylist_name = stylist.get_fullName()
    salon_name = getattr(salon, "salon_name", "مجموعه")

    if accepted:
        title = "دعوت همکاری پذیرفته شد"
        body = f"{stylist_name} دعوت همکاری با {salon_name} را پذیرفت."
        priority = NotificationPriority.HIGH
    else:
        title = "دعوت همکاری رد شد"
        body = f"{stylist_name} دعوت همکاری با {salon_name} را رد کرد."
        priority = NotificationPriority.NORMAL

    return create_notification(
        event_type="manager_invite_response",
        category=NotificationCategory.STAFF,
        priority=priority,
        title=title,
        body=body,
        action_url=f"{reverse('dashboards:team_member')}#team-member-section-invites",
        icon="fa-solid fa-user-check" if accepted else "fa-solid fa-user-xmark",
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=membership,
        metadata={
            "membership_id": membership.id,
            "stylist_id": stylist.user_id,
            "salon_id": salon.id,
            "accepted": accepted,
        },
        dedupe_key=f"manager_invite_response:{membership.id}:{'accepted' if accepted else 'rejected'}",
    )


def _serialize_manager_sent_invite(membership):
    stylist = membership.stylist
    user = stylist.user if stylist else None
    metadata = membership.metadata or {}
    status_ui = _membership_status_ui(membership.status)

    return {
        "id": membership.id,
        "full_name": (
            stylist.get_fullName()
            if stylist
            else metadata.get("invitee_name") or "متخصص ثبت‌نام‌نکرده"
        ),
        "expert": getattr(stylist, "expert", "")
        or membership.role_title
        or "تخصص ثبت نشده",
        "mobile": getattr(user, "mobile_number", "")
        or membership.invited_phone
        or "بدون شماره",
        "message": metadata.get("invite_message", ""),
        "created_label": (
            format_jalali_with_weekday(membership.created_at)
            if membership.created_at
            else "—"
        ),
        "status_label": status_ui["label"],
        "status_badge_class": status_ui["badge_class"],
        "cancel_url": reverse(
            "dashboards:cancel_stylist_invite",
            kwargs={"membership_id": membership.id},
        ),
        "is_registered": bool(stylist),
    }


def _build_manager_sent_invites(salon):
    qs = (
        SalonMembership.objects.select_related("stylist__user", "salon")
        .filter(
            salon=salon,
            status=SalonMembershipStatus.INVITED,
        )
        .order_by("-created_at", "-id")
    )

    return [_serialize_manager_sent_invite(item) for item in qs[:30]]


def _create_manager_stylist_invite(request):
    salon = get_object_or_404(
        Salon.objects.select_related("salon_manager__user"),
        salon_manager__user=request.user,
    )

    mobile = normalize_mobile(request.POST.get("mobile_number") or "")
    invitee_name = (request.POST.get("invitee_name") or "").strip()
    role_title = (request.POST.get("role_title") or "").strip()
    invite_message = (request.POST.get("invite_message") or "").strip()

    if not mobile or len(mobile) < 10:
        messages.error(request, "شماره موبایل متخصص برای ارسال دعوت معتبر نیست.")
        return redirect("dashboards:team_member")

    user = CustomUser.objects.filter(mobile_number=mobile).first()
    stylist = getattr(user, "stylist", None) if user else None

    if stylist:
        existing = (
            SalonMembership.objects.filter(salon=salon, stylist=stylist)
            .order_by("-id")
            .first()
        )
    else:
        existing = (
            SalonMembership.objects.filter(
                salon=salon,
                invited_phone=mobile,
                stylist__isnull=True,
            )
            .order_by("-id")
            .first()
        )

    if existing and existing.status == SalonMembershipStatus.ACTIVE:
        messages.info(request, "این متخصص همین حالا عضو فعال این مجموعه است.")
        return redirect("dashboards:team_member")

    if existing and existing.status == SalonMembershipStatus.PENDING_ACCEPTANCE:
        messages.warning(
            request,
            "این متخصص قبلاً درخواست همکاری داده است. از بخش درخواست‌ها آن را تایید یا رد کنید.",
        )
        return redirect("dashboards:team_member")

    metadata = dict(getattr(existing, "metadata", {}) or {}) if existing else {}
    metadata.update(
        {
            "invited_by_manager": True,
            "invitee_name": invitee_name,
            "invite_message": invite_message,
            "manager_invited_at": timezone.now().isoformat(),
        }
    )

    with transaction.atomic():
        if existing:
            old_status = existing.status

            existing.status = SalonMembershipStatus.INVITED
            existing.stylist = existing.stylist or stylist
            existing.invited_phone = mobile
            existing.invited_email = (
                getattr(user, "email", "") if user else existing.invited_email
            )
            existing.role_title = (
                role_title or existing.role_title or getattr(stylist, "expert", "")
                if stylist
                else role_title or existing.role_title
            )
            existing.invited_by = request.user
            existing.expires_at = default_invite_expiry()
            existing.ended_at = None
            existing.accepted_at = None
            existing.metadata = metadata
            existing.save(
                update_fields=[
                    "status",
                    "stylist",
                    "invited_phone",
                    "invited_email",
                    "role_title",
                    "invited_by",
                    "expires_at",
                    "ended_at",
                    "accepted_at",
                    "metadata",
                    "updated_at",
                ]
            )

            membership = existing

            log_membership_event(
                membership,
                event_type="manager_invite_updated",
                actor=request.user,
                old_status=old_status,
                new_status=SalonMembershipStatus.INVITED,
                note=invite_message,
                metadata={"source": "team_member"},
            )
        else:
            membership = SalonMembership.objects.create(
                salon=salon,
                stylist=stylist,
                invited_phone=mobile,
                invited_email=getattr(user, "email", "") if user else "",
                role_title=(
                    role_title or getattr(stylist, "expert", "")
                    if stylist
                    else role_title
                ),
                status=SalonMembershipStatus.INVITED,
                invited_by=request.user,
                expires_at=default_invite_expiry(),
                metadata=metadata,
            )

            log_membership_event(
                membership,
                event_type="manager_invited_stylist",
                actor=request.user,
                new_status=SalonMembershipStatus.INVITED,
                note=invite_message,
                metadata={"source": "team_member"},
            )

    if membership.stylist_id:
        try:
            _notify_stylist_about_manager_invite(
                membership=membership,
                actor=request.user,
            )
        except Exception:
            logger.exception(
                "Failed to create manager stylist invite notification. membership_id=%s",
                membership.pk,
            )

    if membership.stylist_id:
        messages.success(request, "دعوت همکاری برای متخصص ارسال شد.")
    else:
        messages.success(
            request,
            "دعوت همکاری ثبت شد. متخصص بعد از ثبت‌نام با همین شماره می‌تواند دعوت را در پروفایل خود ببیند.",
        )

    return redirect("dashboards:team_member")


def _cancel_manager_stylist_invite(request, membership_id):
    salon = get_object_or_404(
        Salon.objects.select_related("salon_manager__user"),
        salon_manager__user=request.user,
    )

    membership = get_object_or_404(
        SalonMembership.objects.select_related("salon", "stylist__user"),
        pk=membership_id,
        salon=salon,
        status=SalonMembershipStatus.INVITED,
    )

    old_status = membership.status

    change_membership_status(
        membership=membership,
        new_status=SalonMembershipStatus.CANCELLED_BY_SALON,
        actor=request.user,
        reason="لغو دعوت همکاری متخصص توسط مدیر سالن",
        request=request,
    )

    metadata = dict(membership.metadata or {})
    metadata["cancelled_invite_by_manager"] = True
    metadata["cancelled_invite_at"] = timezone.now().isoformat()
    membership.metadata = metadata
    membership.save(update_fields=["metadata", "updated_at"])

    log_membership_event(
        membership,
        event_type="manager_invite_cancelled",
        actor=request.user,
        old_status=old_status,
        new_status=SalonMembershipStatus.CANCELLED_BY_SALON,
        note="لغو دعوت همکاری توسط مدیر",
        metadata={"source": "team_member"},
    )

    if membership.stylist_id:
        try:
            create_notification(
                event_type="manager_invite_cancelled",
                category=NotificationCategory.STAFF,
                priority=NotificationPriority.NORMAL,
                title="دعوت همکاری لغو شد",
                body=f"دعوت همکاری {membership.salon.salon_name} لغو شد.",
                action_url=reverse("dashboards:stylist_profile"),
                icon="fa-solid fa-ban",
                recipients=[
                    {
                        "user": membership.stylist.user,
                        "audience_role": NotificationAudienceRole.STYLIST,
                        "channels": [NotificationChannel.DASHBOARD],
                    }
                ],
                actor=request.user,
                salon=membership.salon,
                related_object=membership,
                metadata={"membership_id": membership.id},
                dedupe_key=f"manager_invite_cancelled:{membership.id}",
            )
        except Exception:
            logger.exception(
                "Failed to notify stylist about cancelled invite. membership_id=%s",
                membership.pk,
            )

    messages.success(request, "دعوت همکاری لغو شد.")
    return redirect("dashboards:team_member")


def _respond_to_manager_invite(request, stylist, *, accepted):
    membership_id = (request.POST.get("membership_id") or "").strip()
    mobile = normalize_mobile(getattr(stylist.user, "mobile_number", "") or "")

    if not membership_id.isdigit():
        messages.error(request, "دعوت انتخاب‌شده معتبر نیست.")
        return redirect("dashboards:stylist_profile")

    membership = get_object_or_404(
        SalonMembership.objects.select_related(
            "salon", "stylist__user", "salon__salon_manager__user"
        ),
        Q(pk=int(membership_id)),
        Q(status=SalonMembershipStatus.INVITED),
        Q(stylist=stylist) | Q(stylist__isnull=True, invited_phone=mobile),
    )

    metadata = dict(membership.metadata or {})
    if not metadata.get("invited_by_manager"):
        messages.error(request, "این دعوت از مسیر مدیر سالن ثبت نشده است.")
        return redirect("dashboards:stylist_profile")

    if accepted:
        readiness = _is_stylist_profile_ready_for_request(stylist)
        if not readiness["is_ready"]:
            messages.error(
                request,
                f"قبل از پذیرش دعوت باید پروفایل متخصص را کامل کنی. موارد ناقص: {readiness['missing_items_label']}",
            )
            return redirect("dashboards:stylist_profile")

        conflict = (
            SalonMembership.objects.filter(
                salon=membership.salon,
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            .exclude(pk=membership.pk)
            .first()
        )
        if conflict:
            messages.info(request, "شما همین حالا عضو فعال این مجموعه هستید.")
            return redirect("dashboards:stylist_profile")

        with transaction.atomic():
            if not membership.stylist_id:
                membership.stylist = stylist

            membership.invited_phone = membership.invited_phone or mobile
            membership.invited_email = membership.invited_email or getattr(
                stylist.user, "email", ""
            )
            membership.role_title = (
                membership.role_title or getattr(stylist, "expert", "") or ""
            )
            metadata["accepted_manager_invite_at"] = timezone.now().isoformat()
            membership.metadata = metadata
            membership.save(
                update_fields=[
                    "stylist",
                    "invited_phone",
                    "invited_email",
                    "role_title",
                    "metadata",
                    "updated_at",
                ]
            )

            membership = change_membership_status(
                membership=membership,
                new_status=SalonMembershipStatus.ACTIVE,
                actor=request.user,
                reason="پذیرش دعوت همکاری مدیر توسط متخصص",
                request=request,
            )
            ensure_membership_permissions(membership)

            accepted_date = (
                timezone.localtime(membership.accepted_at).date()
                if membership.accepted_at
                else timezone.localdate()
            )
            JobDetails.objects.get_or_create(
                salon=membership.salon,
                stylist=stylist,
                defaults={
                    "start_date": accepted_date,
                    "employment_type": "",
                },
            )

        try:
            _notify_manager_about_invite_response(
                membership=membership,
                actor=request.user,
                accepted=True,
            )
        except Exception:
            logger.exception(
                "Failed to notify manager about accepted invite. membership_id=%s",
                membership.pk,
            )

        request.session["active_stylist_salon_id"] = str(membership.salon_id)
        request.session.modified = True

        messages.success(
            request,
            f"دعوت همکاری {membership.salon.salon_name} پذیرفته شد. حالا این مجموعه به داشبورد شما اضافه شد.",
        )
        return redirect("dashboards:stylist_profile")

    old_status = membership.status
    metadata["rejected_manager_invite_at"] = timezone.now().isoformat()

    if not membership.stylist_id:
        membership.stylist = stylist

    membership.metadata = metadata
    membership.save(update_fields=["stylist", "metadata", "updated_at"])

    membership = change_membership_status(
        membership=membership,
        new_status=SalonMembershipStatus.REJECTED,
        actor=request.user,
        reason="رد دعوت همکاری مدیر توسط متخصص",
        request=request,
    )

    log_membership_event(
        membership,
        event_type="manager_invite_rejected_by_stylist",
        actor=request.user,
        old_status=old_status,
        new_status=SalonMembershipStatus.REJECTED,
        note="رد دعوت همکاری توسط متخصص",
        metadata={"source": "stylist_profile"},
    )

    try:
        _notify_manager_about_invite_response(
            membership=membership,
            actor=request.user,
            accepted=False,
        )
    except Exception:
        logger.exception(
            "Failed to notify manager about rejected invite. membership_id=%s",
            membership.pk,
        )

    messages.success(request, "دعوت همکاری رد شد.")
    return redirect("dashboards:stylist_profile")


def _notify_manager_about_stylist_request(*, membership, actor=None):
    salon = membership.salon
    stylist = membership.stylist

    manager_user = getattr(getattr(salon, "salon_manager", None), "user", None)
    if not manager_user or not stylist:
        logger.warning(
            "Stylist membership request notification skipped: manager_user or stylist missing. membership_id=%s",
            membership.id,
        )
        return None

    stylist_name = stylist.get_fullName()
    salon_name = getattr(salon, "salon_name", "سالن")
    action_url = f"{reverse('dashboards:team_member')}#team-member-section-requests"

    return create_notification(
        event_type="stylist_membership_requested",
        category=NotificationCategory.STAFF,
        priority=NotificationPriority.HIGH,
        title="درخواست همکاری متخصص جدید",
        body=f"{stylist_name} برای همکاری با {salon_name} درخواست ارسال کرده است.",
        action_url=action_url,
        icon="fa-solid fa-user-plus",
        channels=[NotificationChannel.DASHBOARD],
        recipients=[
            {
                "user": manager_user,
                "audience_role": NotificationAudienceRole.MANAGER,
                "channels": [NotificationChannel.DASHBOARD],
            }
        ],
        actor=actor,
        salon=salon,
        related_object=membership,
        metadata={
            "membership_id": membership.id,
            "stylist_id": stylist.user_id,
            "salon_id": salon.id,
        },
        dedupe_key=f"stylist_membership_requested:{membership.id}",
    )


def _create_stylist_membership_request(request, stylist):
    readiness = _is_stylist_profile_ready_for_request(stylist)
    if not readiness["is_ready"]:
        messages.error(
            request,
            f"قبل از ارسال درخواست همکاری باید پروفایل متخصص را کامل کنی. موارد ناقص: {readiness['missing_items_label']}",
        )
        return redirect("dashboards:stylist_profile")

    membership_for_notification = None

    salon_id = (request.POST.get("salon_id") or "").strip()
    request_message = (request.POST.get("request_message") or "").strip()

    if not salon_id.isdigit():
        messages.error(request, "برای ارسال درخواست همکاری، یک سالن معتبر انتخاب کن.")
        return redirect("dashboards:stylist_profile")

    salon = Salon.objects.filter(pk=int(salon_id), is_active=True).first()
    if not salon:
        messages.error(
            request,
            "سالن انتخاب‌شده فعال نیست یا امکان دریافت درخواست همکاری ندارد.",
        )
        return redirect("dashboards:stylist_profile")

    existing = SalonMembership.objects.filter(salon=salon, stylist=stylist).first()

    if existing and existing.status == SalonMembershipStatus.ACTIVE:
        messages.info(request, "شما همین حالا عضو فعال این سالن هستید.")
        return redirect("dashboards:stylist_profile")

    if existing and existing.status == SalonMembershipStatus.PENDING_ACCEPTANCE:
        messages.warning(
            request,
            "درخواست همکاری شما برای این سالن قبلاً ثبت شده و در انتظار بررسی مدیر است.",
        )
        return redirect("dashboards:stylist_profile")

    if existing and existing.status == SalonMembershipStatus.INVITED:
        messages.info(
            request,
            "برای این سالن قبلاً دعوت همکاری ثبت شده است. مدیر سالن می‌تواند وضعیت همکاری را پیگیری کند.",
        )
        return redirect("dashboards:stylist_profile")

    metadata = dict(getattr(existing, "metadata", {}) or {}) if existing else {}
    metadata.update(
        {
            "requested_by_stylist": True,
            "request_message": request_message,
            "requested_at": timezone.now().isoformat(),
        }
    )

    with transaction.atomic():
        if existing:
            old_status = existing.status

            existing.status = SalonMembershipStatus.PENDING_ACCEPTANCE
            existing.invited_phone = existing.invited_phone or getattr(
                stylist.user,
                "mobile_number",
                "",
            )
            existing.invited_email = existing.invited_email or getattr(
                stylist.user,
                "email",
                "",
            )
            existing.role_title = existing.role_title or getattr(stylist, "expert", "")
            existing.metadata = metadata
            existing.ended_at = None
            existing.expires_at = timezone.now() + timedelta(days=14)
            existing.save(
                update_fields=[
                    "status",
                    "invited_phone",
                    "invited_email",
                    "role_title",
                    "metadata",
                    "ended_at",
                    "expires_at",
                    "updated_at",
                ]
            )

            membership_for_notification = existing

            log_membership_event(
                existing,
                event_type="requested_by_stylist",
                actor=request.user,
                old_status=old_status,
                new_status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                note=request_message,
                metadata={"source": "stylist_profile"},
            )

        else:
            membership = SalonMembership.objects.create(
                salon=salon,
                stylist=stylist,
                invited_phone=getattr(stylist.user, "mobile_number", "") or "",
                invited_email=getattr(stylist.user, "email", "") or "",
                role_title=getattr(stylist, "expert", "") or "",
                status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                invited_by=request.user,
                expires_at=timezone.now() + timedelta(days=14),
                metadata=metadata,
            )

            membership_for_notification = membership

            log_membership_event(
                membership,
                event_type="requested_by_stylist",
                actor=request.user,
                new_status=SalonMembershipStatus.PENDING_ACCEPTANCE,
                note=request_message,
                metadata={"source": "stylist_profile"},
            )

    if membership_for_notification:
        try:
            membership_for_notification = SalonMembership.objects.select_related(
                "salon__salon_manager__user", "stylist__user"
            ).get(pk=membership_for_notification.pk)
            _notify_manager_about_stylist_request(
                membership=membership_for_notification,
                actor=request.user,
            )
        except Exception:
            logger.exception(
                "Failed to create stylist membership request notification. membership_id=%s",
                getattr(membership_for_notification, "pk", None),
            )

    messages.success(request, "درخواست همکاری برای مدیر سالن ارسال شد.")
    return redirect("dashboards:stylist_profile")


def _get_pending_membership_request_for_stylist(stylist, membership_id):
    return get_object_or_404(
        SalonMembership.objects.select_related("salon", "stylist"),
        pk=membership_id,
        stylist=stylist,
        status=SalonMembershipStatus.PENDING_ACCEPTANCE,
    )


def _update_stylist_membership_request(request, stylist):
    membership_id = request.POST.get("membership_id")
    request_message = (request.POST.get("request_message") or "").strip()

    membership = _get_pending_membership_request_for_stylist(stylist, membership_id)
    metadata = dict(membership.metadata or {})

    if not metadata.get("requested_by_stylist"):
        messages.error(
            request, "این درخواست توسط متخصص ثبت نشده و از این بخش قابل ویرایش نیست."
        )
        return redirect("dashboards:stylist_profile")

    metadata["request_message"] = request_message
    metadata["updated_by_stylist_at"] = timezone.now().isoformat()

    membership.metadata = metadata
    membership.save(update_fields=["metadata", "updated_at"])

    messages.success(request, "متن درخواست همکاری به‌روزرسانی شد.")
    return redirect("dashboards:stylist_profile")


def _cancel_stylist_membership_request(request, stylist):
    membership_id = request.POST.get("membership_id")
    membership = _get_pending_membership_request_for_stylist(stylist, membership_id)
    metadata = dict(membership.metadata or {})

    if not metadata.get("requested_by_stylist"):
        messages.error(
            request, "این درخواست توسط متخصص ثبت نشده و از این بخش قابل حذف نیست."
        )
        return redirect("dashboards:stylist_profile")

    metadata["cancelled_by_stylist"] = True
    metadata["cancelled_by_stylist_at"] = timezone.now().isoformat()

    old_status = membership.status
    membership.status = SalonMembershipStatus.ENDED
    membership.ended_at = timezone.now()
    membership.metadata = metadata
    membership.save(update_fields=["status", "ended_at", "metadata", "updated_at"])

    log_membership_event(
        membership,
        event_type="cancelled_by_stylist",
        actor=request.user,
        old_status=old_status,
        new_status=SalonMembershipStatus.ENDED,
        note="لغو درخواست همکاری در انتظار بررسی توسط متخصص",
        metadata={"source": "stylist_profile"},
    )

    messages.success(request, "درخواست همکاری حذف شد.")
    return redirect("dashboards:stylist_profile")


def _build_manager_request_profile_payload(membership):
    stylist = membership.stylist
    salon = membership.salon
    user = stylist.user if stylist else None

    if not stylist or not user:
        return {
            "has_profile": False,
            "salon_name": salon.salon_name if salon else "مجموعه",
            "full_name": "متخصص حذف‌شده",
            "display_name": "متخصص حذف‌شده",
            "expert": "—",
            "headline": "—",
            "summary": "",
            "description": "",
            "mobile": "—",
            "email": "",
            "profile_image_url": "",
            "started_working_year_label": "ثبت نشده",
            "visibility_label": "—",
            "is_verified": False,
            "role_title": "",
            "rating_average_label": "۰.۰",
            "rating_count_label": "۰",
            "completed_count_label": "۰",
            "services_count_label": "۰",
            "service_cards": [],
            "portfolio_items": [],
            "instagram": "",
            "telegram": "",
            "linkedin": "",
        }

    profile_image_url = ""
    if getattr(stylist, "profile_image", None):
        try:
            profile_image_url = stylist.profile_image.url
        except Exception:
            profile_image_url = ""

    full_name = stylist.get_fullName()
    display_name = (
        getattr(stylist, "professional_display_name", "")
        or getattr(stylist, "display_name", "")
        or full_name
    )

    rating_in_salon = (
        get_stylist_rating_summary(stylist=stylist, salon=salon)
        if salon
        else {"average": 0, "count": 0}
    )
    completed_in_salon = (
        get_completed_appointment_count(stylist=stylist, salon=salon) if salon else 0
    )

    service_cards = []
    if salon:
        for service in get_stylist_services_for_salon(
            salon=salon,
            stylist=stylist,
        )[:6]:
            service_description = (
                getattr(service, "description", "")
                or getattr(service, "service_description", "")
                or getattr(service, "descriptions", "")
                or getattr(service, "details", "")
                or ""
            )

            service_cards.append(
                {
                    "name": service.service_name,
                    "description": service_description,
                }
            )

    portfolio_items = []
    if salon:
        for sample in get_public_work_samples(
            stylist=stylist,
            salon=salon,
            limit=6,
        ):
            image_url = ""
            try:
                image_url = sample.sample_image.url if sample.sample_image else ""
            except Exception:
                image_url = ""

            portfolio_items.append(
                {
                    "image_url": image_url,
                    "service_name": (
                        sample.service.service_name if sample.service else ""
                    ),
                    "is_verified": bool(
                        getattr(sample, "is_verified_work", False)
                        or getattr(sample, "appointment_id", None)
                    ),
                }
            )

    started_year = getattr(stylist, "started_working_year", None)

    return {
        "has_profile": True,
        "salon_name": salon.salon_name if salon else "مجموعه",
        "full_name": full_name,
        "display_name": display_name,
        "expert": getattr(stylist, "expert", "") or "تخصص ثبت نشده",
        "headline": (
            getattr(stylist, "resume_headline", "")
            or getattr(stylist, "expert", "")
            or "متخصص زیبایی"
        ),
        "summary": (
            getattr(stylist, "resume_summary", "")
            or getattr(stylist, "description", "")
            or ""
        ),
        "description": getattr(stylist, "description", "") or "",
        "mobile": getattr(user, "mobile_number", "") or "بدون شماره",
        "email": getattr(user, "email", "") or "",
        "profile_image_url": profile_image_url,
        "started_working_year_label": (
            to_persian_digits(started_year) if started_year else "ثبت نشده"
        ),
        "visibility_label": (
            stylist.get_public_visibility_display()
            if hasattr(stylist, "get_public_visibility_display")
            else "—"
        ),
        "is_verified": bool(getattr(stylist, "is_verified_professional", False)),
        "role_title": membership.role_title or "",
        "rating_average_label": to_persian_digits(
            f"{float(rating_in_salon.get('average') or 0):.1f}"
        ),
        "rating_count_label": to_persian_digits(rating_in_salon.get("count") or 0),
        "completed_count_label": to_persian_digits(completed_in_salon),
        "services_count_label": to_persian_digits(len(service_cards)),
        "service_cards": service_cards,
        "portfolio_items": portfolio_items,
        "instagram": getattr(stylist, "insta_link", "") or "",
        "telegram": getattr(stylist, "telegram_link", "") or "",
        "linkedin": getattr(stylist, "linkedin_link", "") or "",
    }


def _serialize_manager_membership_request(membership):
    stylist = membership.stylist
    user = stylist.user if stylist else None
    metadata = membership.metadata or {}
    status_ui = _membership_status_ui(membership.status)

    return {
        "id": membership.id,
        "full_name": stylist.get_fullName() if stylist else "متخصص حذف‌شده",
        "expert": getattr(stylist, "expert", "") or "تخصص ثبت نشده",
        "mobile": getattr(user, "mobile_number", "") or "بدون شماره",
        "message": metadata.get("request_message", ""),
        "created_label": (
            format_jalali_with_weekday(membership.created_at)
            if membership.created_at
            else "—"
        ),
        "status_label": status_ui["label"],
        "status_badge_class": status_ui["badge_class"],
        "profile": _build_manager_request_profile_payload(membership),
        "action_url": reverse(
            "dashboards:membership_request_action",
            kwargs={"membership_id": membership.id},
        ),
    }


def _build_manager_membership_requests(salon):
    qs = (
        SalonMembership.objects.select_related("stylist__user", "salon")
        .filter(
            salon=salon,
            status=SalonMembershipStatus.PENDING_ACCEPTANCE,
            stylist__isnull=False,
        )
        .order_by("-created_at", "-id")
    )

    return [_serialize_manager_membership_request(item) for item in qs[:20]]


def _active_future_appointment_count_for_membership(membership):
    if not membership or not membership.stylist_id or not membership.salon_id:
        return 0

    return (
        OrderDetail.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
            date__gte=timezone.localdate(),
        )
        .exclude(order__status__in=["cancelled", "completed", "no_show"])
        .count()
    )


def _disable_membership_dashboard_permissions(membership):
    permissions = getattr(membership, "dashboard_permissions", None)
    if not permissions:
        return

    permission_fields = [
        "can_complete_appointments",
        "can_view_own_finance",
        "can_request_payout",
        "can_view_own_clients",
        "can_create_own_bookings",
        "can_view_client_phone",
        "can_manage_own_portfolio",
        "can_submit_posts",
        "can_submit_stories",
        "can_request_leave",
        "can_manage_own_schedule",
    ]

    for field_name in permission_fields:
        setattr(permissions, field_name, False)

    permissions.save(update_fields=[*permission_fields, "updated_at"])


def _close_membership_access(
    *,
    membership,
    actor,
    request=None,
    new_status,
    event_type,
    reason,
    metadata=None,
):
    if not membership or membership.status != SalonMembershipStatus.ACTIVE:
        return membership

    future_appointments_count = _active_future_appointment_count_for_membership(
        membership
    )

    with transaction.atomic():
        membership = change_membership_status(
            membership=membership,
            new_status=new_status,
            actor=actor,
            reason=reason,
            request=request,
        )

        membership_metadata = dict(membership.metadata or {})
        membership_metadata.update(metadata or {})
        membership_metadata.update(
            {
                "access_closed_at": timezone.now().isoformat(),
                "future_appointments_count_at_closure": future_appointments_count,
            }
        )

        membership.metadata = membership_metadata
        membership.show_on_salon_profile = False
        membership.save(
            update_fields=[
                "metadata",
                "show_on_salon_profile",
                "updated_at",
            ]
        )

        if membership.stylist_id:
            membership.salon.stylists.remove(membership.stylist)

        _disable_membership_dashboard_permissions(membership)

        JobDetails.objects.filter(
            salon=membership.salon,
            stylist=membership.stylist,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gt=timezone.localdate())
        ).update(
            end_date=timezone.localdate()
        )

        log_membership_event(
            membership,
            event_type=event_type,
            actor=actor,
            old_status=SalonMembershipStatus.ACTIVE,
            new_status=new_status,
            note=reason,
            metadata=membership_metadata,
        )

    return membership


def _leave_stylist_membership(request, stylist):
    membership_id = (request.POST.get("membership_id") or "").strip()

    if not membership_id.isdigit():
        messages.error(request, "عضویت انتخاب‌شده معتبر نیست.")
        return redirect("dashboards:stylist_profile")

    membership = get_object_or_404(
        SalonMembership.objects.select_related("salon", "stylist"),
        pk=int(membership_id),
        stylist=stylist,
        status=SalonMembershipStatus.ACTIVE,
    )

    salon_name = membership.salon.salon_name

    future_appointments_count = _active_future_appointment_count_for_membership(
        membership
    )
    if future_appointments_count:
        messages.error(
            request,
            _membership_future_appointment_block_message(membership),
        )
        return redirect("dashboards:stylist_profile")

    closed_membership = _close_membership_access(
        membership=membership,
        actor=request.user,
        request=request,
        new_status=SalonMembershipStatus.ENDED,
        event_type="left_by_stylist",
        reason="جدا شدن متخصص از مجموعه توسط خودش",
        metadata={
            "ended_by_stylist": True,
            "ended_by_manager": False,
        },
    )

    try:
        _notify_manager_about_stylist_left_collaboration(
            membership=closed_membership,
            actor=request.user,
        )
    except Exception:
        logger.exception(
            "Failed to notify manager about stylist leaving collaboration. membership_id=%s",
            closed_membership.pk,
        )

    try:
        _notify_stylist_about_collaboration_closed(
            membership=closed_membership,
            actor=request.user,
            ended_by_manager=False,
        )
    except Exception:
        logger.exception(
            "Failed to notify stylist about leaving collaboration. membership_id=%s",
            closed_membership.pk,
        )

    active_session_salon_id = str(request.session.get("active_stylist_salon_id") or "")
    if active_session_salon_id == str(membership.salon_id):
        next_membership = (
            SalonMembership.objects.filter(
                stylist=stylist,
                status=SalonMembershipStatus.ACTIVE,
            )
            .exclude(pk=membership.pk)
            .select_related("salon")
            .order_by("salon__salon_name", "id")
            .first()
        )

        if next_membership:
            request.session["active_stylist_salon_id"] = str(next_membership.salon_id)
        else:
            request.session.pop("active_stylist_salon_id", None)

        request.session.modified = True

    messages.success(
        request,
        f"همکاری شما با {salon_name} پایان یافت و دسترسی‌های این مجموعه بسته شد.",
    )
    return redirect("dashboards:stylist_profile")


def _build_stylist_home_payload(*, stylist, salon, can_view_client_phone=False):
    today = timezone.localdate()

    empty_payload = {
        "today_count_label": "۰",
        "upcoming_count_label": "۰",
        "service_count_label": "۰",
        "time_off_count_label": "۰",
        "today_items": [],
        "schedule_rows": [],
        "services": [],
        "time_off_rows": [],
    }

    if not stylist or not salon:
        return empty_payload

    base_qs = _stylist_base_appointments_qs(stylist, salon=salon).exclude(
        order__status="cancelled"
    )

    today_qs = base_qs.filter(date=today).order_by("time", "id")
    upcoming_qs = base_qs.filter(
        date__gt=today,
        date__lte=today + timedelta(days=7),
    ).order_by("date", "time", "id")

    today_items = [
        _serialize_stylist_appointment_card(
            item,
            can_view_client_phone=can_view_client_phone,
        )
        for item in today_qs[:6]
    ]

    schedule_rows = []
    schedule_qs = (
        StylistSchedule.objects.filter(
            stylist=stylist,
            salon=salon,
            date__gte=today,
        )
        .select_related("salon", "service")
        .order_by("date", "start_time")[:6]
    )

    for item in schedule_qs:
        row = _serialize_stylist_schedule_row(item)
        row["time_label"] = f"{row['start_label']} تا {row['end_label']}"
        schedule_rows.append(row)

    service_count = Services.objects.filter(
        stylists=stylist,
        services_of_salon=salon,
        is_active=True,
    ).distinct().count()

    approved_leave_qs = StaffLeaveRequest.objects.filter(
        stylist=stylist,
        salon=salon,
        status=StaffLeaveRequest.Status.APPROVED,
        date__gte=today,
    ).order_by("date", "start_time")[:6]

    time_off_rows = [
        _serialize_stylist_time_off_row(item) for item in approved_leave_qs
    ]
    time_off_count = StaffLeaveRequest.objects.filter(
        stylist=stylist,
        salon=salon,
        status=StaffLeaveRequest.Status.APPROVED,
        date__gte=today,
    ).count()

    return {
        "today_count_label": to_persian_digits(today_qs.count()),
        "upcoming_count_label": to_persian_digits(upcoming_qs.count()),
        "service_count_label": to_persian_digits(service_count),
        "time_off_count_label": to_persian_digits(time_off_count),
        "today_items": today_items,
        "schedule_rows": schedule_rows,
        "services": [],
        "time_off_rows": [],
    }


class StylistDashboardView(StylistDashboardGuardMixin, View):
    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon

        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="overview",
            page_title="خانه کاری من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )

        context.update(
            build_dashboard_home_context(
                request.user,
                role="stylist",
                salon_override=salon,
                stylist_override=stylist,
            )
        )

        context.update(
            {
                "stylist_dashboard_mode": True,
                "stylist_home": _build_stylist_home_payload(
                    stylist=stylist,
                    salon=salon,
                    can_view_client_phone=ctx.can("can_view_client_phone", False),
                ),
            }
        )

        context.update(_stylist_context_payload(ctx))

        return render(request, "dashboards/stylist_dashboard.html", context)




STYLIST_QUICK_LINK_PERIOD_OPTIONS = (
    ("7", "۷ روز اخیر"),
    ("30", "۳۰ روز اخیر"),
    ("90", "۹۰ روز اخیر"),
    ("all", "همه زمان‌ها"),
)

STYLIST_QUICK_LINK_SORT_OPTIONS = (
    ("newest", "جدیدترین"),
    ("unique_visitors", "بیشترین بازدیدکننده یکتا"),
    ("conversions", "بیشترین رزرو"),
    ("conversion_rate", "بالاترین نرخ تبدیل"),
    ("last_activity", "آخرین فعالیت"),
)


def _serialize_stylist_quick_link_stats_row(request, stats_row):
    quick_link = stats_row["quick_link"]
    payload = quick_link.payload if isinstance(quick_link.payload, dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    return {
        **stats_row,
        "id": quick_link.pk,
        "title": quick_link.title or quick_link.get_mode_display(),
        "mode_label": quick_link.get_mode_display(),
        "status_label": quick_link.status_label,
        "status_tone": quick_link.status_tone,
        "is_active": quick_link.is_active,
        "is_permanent": quick_link.is_permanent,
        "placement_label": quick_link.get_placement_display(),
        "campaign_name": quick_link.campaign_name or "بدون کمپین",
        "internal_note": quick_link.internal_note or "",
        "service_name": (
            summary.get("service")
            or getattr(quick_link.service, "service_name", "")
            or "همه خدمات فعال من"
        ),
        "date_label": summary.get("date") or "—",
        "time_label": summary.get("time") or "—",
        "url": build_quick_link_url(request, quick_link),
        "qr_preview_url": reverse(
            "dashboards:stylist_quick_link_qr_preview",
            kwargs={"link_id": quick_link.pk},
        ),
        "qr_download_url": reverse(
            "dashboards:stylist_quick_link_qr_download",
            kwargs={"link_id": quick_link.pk},
        ),
    }


def _build_stylist_quick_link_workspace(
    request,
    salon,
    stylist,
    *,
    generated_link=None,
    generated_payload=None,
    generator_errors=None,
):
    services = list(
        Services.objects.filter(
            services_of_salon=salon,
            stylists=stylist,
            is_active=True,
        )
        .distinct()
        .order_by("service_name")[:40]
    )

    payload = generated_payload or {}
    payload_services = payload.get("service_ids") or []

    raw_selected_date = (
        request.POST.get("appointment_date")
        or request.GET.get("appointment_date")
        or payload.get("date")
        or timezone.localdate()
    )
    if isinstance(raw_selected_date, date):
        selected_date_obj = raw_selected_date
    else:
        try:
            selected_date_obj = date.fromisoformat(str(raw_selected_date))
        except (TypeError, ValueError):
            selected_date_obj = (
                parse_jalali_input(raw_selected_date, fallback=timezone.localdate())
                or timezone.localdate()
            )

    current_mode = (
        request.POST.get("quick_link_mode")
        or request.GET.get("quick_link_mode")
        or payload.get("mode")
        or "stylist"
    ).strip()

    selected_service = str(
        request.POST.get("service_id")
        or (payload_services[0] if payload_services else "")
        or ""
    ).strip()

    selected_time = str(
        request.POST.get("appointment_time")
        or payload.get("time")
        or ""
    ).strip()

    selected_placement = str(
        request.POST.get("placement")
        or BookingQuickLink.Placement.DIRECT
    ).strip()

    scoped_links = BookingQuickLink.objects.filter(
        salon=salon,
        creator=request.user,
        stylist=stylist,
    )

    stats = build_booking_quick_link_stats(
        links_queryset=scoped_links,
        period=request.GET.get("period") or request.POST.get("period"),
        sort=request.GET.get("sort") or request.POST.get("sort"),
    )

    rows = [
        _serialize_stylist_quick_link_stats_row(
            request,
            stats_row,
        )
        for stats_row in stats["links"]
    ]

    best_link = stats["summary"]["best_link"]
    best_link_summary = None
    if best_link:
        best_link_summary = {
            "id": best_link["id"],
            "title": (
                best_link["quick_link"].title
                or best_link["quick_link"].get_mode_display()
            ),
            "converted_count": best_link["converted_count"],
            "conversion_rate": best_link["conversion_rate"],
        }

    title_field = BookingQuickLink._meta.get_field("title")
    campaign_field = BookingQuickLink._meta.get_field("campaign_name")
    note_field = BookingQuickLink._meta.get_field("internal_note")

    return {
        "mode_options": [
            {"value": "stylist", "label": "فقط خودم"},
            {"value": "service_stylist", "label": "خدمت + خودم"},
            {
                "value": "service_stylist_time",
                "label": "خدمت + خودم + زمان",
            },
        ],
        "services": services,
        "generated_link": generated_link,
        "generated_payload": payload,
        "errors": generator_errors or [],
        "default_date": format_jalali_numeric(timezone.localdate()),
        "current_mode": current_mode,
        "selected_service": selected_service,
        "selected_date": selected_date_obj.isoformat(),
        "selected_date_label": format_jalali_numeric(selected_date_obj),
        "selected_time": selected_time,
        "selected_title": str(
            request.POST.get("quick_link_title") or ""
        ).strip(),
        "selected_placement": selected_placement,
        "campaign_name": str(
            request.POST.get("campaign_name") or ""
        ).strip(),
        "internal_note": str(
            request.POST.get("internal_note") or ""
        ).strip(),
        "is_permanent": request.POST.get("is_permanent") == "on",
        "placement_options": BookingQuickLink.Placement.choices,
        "title_max_length": title_field.max_length,
        "campaign_name_max_length": campaign_field.max_length,
        "internal_note_max_length": note_field.max_length,
        "options_url": reverse("dashboards:stylist_quick_link_options"),
        "stylist_name": stylist.get_fullName(),
        "salon_name": getattr(salon, "salon_name", ""),
        "expires_in_days": max(1, MAX_AGE_SECONDS // 86400),
        "has_services": bool(services),
        "period": stats["period"],
        "sort": stats["sort"],
        "period_options": STYLIST_QUICK_LINK_PERIOD_OPTIONS,
        "sort_options": STYLIST_QUICK_LINK_SORT_OPTIONS,
        "summary": {
            **stats["summary"],
            "best_link": best_link_summary,
        },
        "links": rows,
    }



def _generate_stylist_quick_link(request, salon, stylist):
    mode = (request.POST.get("quick_link_mode") or "stylist").strip()
    service_id = str(request.POST.get("service_id") or "").strip()
    appointment_date = str(
        request.POST.get("appointment_date") or ""
    ).strip()
    appointment_time = str(
        request.POST.get("appointment_time") or ""
    ).strip()
    placement = str(
        request.POST.get("placement")
        or BookingQuickLink.Placement.DIRECT
    ).strip()
    campaign_name = str(
        request.POST.get("campaign_name") or ""
    ).strip()
    internal_note = str(
        request.POST.get("internal_note") or ""
    ).strip()

    errors = []
    payload = {
        "mode": mode,
        "salon_id": salon.id,
        "stylist_user_id": stylist.pk,
    }
    service_obj = None

    if mode not in {
        "stylist",
        "service_stylist",
        "service_stylist_time",
    }:
        errors.append("نوع لینک برای workspace متخصص معتبر نیست.")

    if mode in {"service_stylist", "service_stylist_time"}:
        if not service_id:
            errors.append(
                "برای این نوع لینک باید یکی از خدمات فعال خودت را انتخاب کنی."
            )
        else:
            service_obj = (
                Services.objects.filter(
                    pk=service_id,
                    services_of_salon=salon,
                    stylists=stylist,
                    is_active=True,
                )
                .distinct()
                .first()
            )
            if not service_obj:
                errors.append(
                    "خدمت انتخاب‌شده برای این سالن و این متخصص فعال نیست."
                )
            else:
                payload["service_ids"] = [service_obj.pk]

    parsed_date = None
    if mode == "service_stylist_time":
        if not appointment_date or not appointment_time:
            errors.append(
                "برای لینک مستقیم preview باید تاریخ و ساعت هم مشخص شود."
            )
        else:
            try:
                parsed_date = date.fromisoformat(appointment_date)
            except (TypeError, ValueError):
                parsed_date = parse_jalali_input(appointment_date)

            if not parsed_date:
                errors.append("تاریخ انتخاب‌شده معتبر نیست.")

            available_times = []
            if parsed_date and service_obj is not None:
                available_times = [
                    start.strftime("%H:%M")
                    for start, _ in get_available_slots_for_service(
                        salon=salon,
                        stylist=stylist,
                        service=service_obj,
                        date_value=parsed_date,
                    )
                ]

            if parsed_date and appointment_time not in available_times:
                errors.append("این زمان دیگر برای رزرو در دسترس نیست. یک زمان آزاد دیگر انتخاب کن.")
            elif parsed_date:
                payload["date"] = parsed_date.isoformat()
                payload["time"] = appointment_time

    if errors:
        return None, payload, errors

    try:
        payload = normalize_booking_payload(payload)
    except Exception as exc:
        return None, payload, [str(exc)]

    payload["summary"] = {
        "salon": salon.salon_name,
        "stylist": stylist.get_fullName(),
        "service": service_obj.service_name if service_obj else "—",
        "date": format_jalali_numeric(parsed_date) if parsed_date else "—",
        "time": format_time_fa(appointment_time) if appointment_time else "—",
    }

    is_permanent = request.POST.get("is_permanent") == "on"
    title = (
        request.POST.get("quick_link_title")
        or payload["summary"]["service"]
        or "لینک رزرو متخصص"
    )

    try:
        _quick_link, link = create_booking_quick_link(
            request=request,
            creator=request.user,
            salon=salon,
            payload=payload,
            service_obj=service_obj,
            stylist_obj=stylist,
            title=title,
            is_permanent=is_permanent,
            placement=placement,
            campaign_name=campaign_name,
            internal_note=internal_note,
        )
    except ValidationError as exc:
        return (
            None,
            payload,
            list(getattr(exc, "messages", [str(exc)])),
        )

    return link, payload, []



def _build_salon_hours_map_for_schedule_form(salon):
    result = {}

    opening_hours = SalonOpeningHours.objects.filter(salon=salon).order_by(
        "day_of_week"
    )
    for item in opening_hours:
        if item.is_closed or not item.open_time or not item.close_time:
            result[str(item.day_of_week)] = {
                "closed": True,
                "open": "",
                "close": "",
                "label": "تعطیل",
            }
            continue

        result[str(item.day_of_week)] = {
            "closed": False,
            "open": item.open_time.strftime("%H:%M"),
            "close": item.close_time.strftime("%H:%M"),
            "label": f"{format_time_fa(item.open_time)} تا {format_time_fa(item.close_time)}",
        }

    return result


class StylistAddScheduleView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/stylist_add_schedule.html"

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if salon is None:
            messages.error(
                request,
                "برای ثبت درخواست برنامه کاری ابتدا باید مجموعه فعال داشته باشید.",
            )
            return redirect("dashboards:stylist_schedule")
        form = StylistSelfScheduleForm(salon=salon, stylist=stylist)
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_schedule",
            page_title="درخواست برنامه کاری",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "form": form,
                "salon_hours_map": _build_salon_hours_map_for_schedule_form(salon),
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if salon is None:
            messages.error(
                request,
                "برای ثبت درخواست برنامه کاری ابتدا باید مجموعه فعال داشته باشید.",
            )
            return redirect("dashboards:stylist_schedule")
        form = StylistSelfScheduleForm(request.POST, salon=salon, stylist=stylist)
        if form.is_valid():
            try:
                create_schedule_request(
                    stylist=stylist,
                    salon=salon,
                    service=form.cleaned_data.get("service"),
                    date_value=form.cleaned_data["date"],
                    start_time=form.cleaned_data["start_time"],
                    end_time=form.cleaned_data["end_time"],
                    note=(form.cleaned_data.get("note") or "").strip(),
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(
                    request,
                    "درخواست برنامه کاری شما برای بررسی مدیر مجموعه ثبت شد.",
                )
                return redirect("dashboards:stylist_schedule")
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_schedule",
            page_title="درخواست برنامه کاری",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "form": form,
                "salon_hours_map": _build_salon_hours_map_for_schedule_form(salon),
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)


class StylistAddCustomerView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/stylist_add_customer.html"

    def _clean_next_url(self, request):
        next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
        if next_url and not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return ""
        return next_url

    def _build_context(self, request, form, stylist, salon, next_url):
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_appointments",
            page_title="افزودن مشتری",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "form": form,
                "stylist_obj": stylist,
                "stylist_salon": salon,
                "next_url": next_url,
                "back_url": next_url or reverse("dashboards:stylist_dashboard"),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if not ctx.can("can_view_own_clients", True):
            messages.error(request, "دسترسی ثبت یا مشاهده مشتری برای شما فعال نیست.")
            return redirect("dashboards:stylist_dashboard")
        form = AddCustomerForm()
        next_url = self._clean_next_url(request)
        return render(
            request,
            self.template_name,
            self._build_context(request, form, stylist, salon, next_url),
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if not ctx.can("can_view_own_clients", True):
            messages.error(request, "دسترسی ثبت یا مشاهده مشتری برای شما فعال نیست.")
            return redirect("dashboards:stylist_dashboard")
        form = AddCustomerForm(request.POST or None)
        next_url = self._clean_next_url(request)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                user = CustomUser.objects.create(
                    mobile_number=cd["mobile_number"],
                    name=cd["name"],
                    family=cd["family"],
                    email=cd.get("email", ""),
                    is_active=True,
                )
                customer = Customer.objects.create(
                    user=user,
                    address=cd.get("address", ""),
                    added_by_salon=salon,
                )
            except IntegrityError:
                form.add_error("mobile_number", "این شماره موبایل قبلاً ثبت شده است.")
            else:
                redirect_url = next_url or reverse("dashboards:stylist_add_booking")
                if redirect_url:
                    separator = "&" if "?" in redirect_url else "?"
                    redirect_url = f"{redirect_url}{separator}customer={customer.pk}"
                messages.success(request, "مشتری جدید برای workflow شخصی شما ثبت شد.")
                return redirect(redirect_url)
        return render(
            request,
            self.template_name,
            self._build_context(request, form, stylist, salon, next_url),
        )


class StylistAddBookingView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/stylist_add_booking.html"

    def _build_context(self, request, form, stylist, salon):
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_appointments",
            page_title="ثبت نوبت برای خودم",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "form": form,
                "stylist_obj": stylist,
                "stylist_salon": salon,
                "add_customer_url": f"{reverse('dashboards:stylist_add_customer')}?next={reverse('dashboards:stylist_add_booking')}",
                "customer_count": form.fields["customer"].queryset.count(),
                "service_count": form.fields["service"].queryset.count(),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if not ctx.can("can_create_own_bookings", True):
            messages.error(request, "دسترسی ثبت نوبت برای شما فعال نیست.")
            return redirect("dashboards:stylist_dashboard")
        initial = {}
        requested_customer = str(request.GET.get("customer") or "").strip()
        if (
            requested_customer
            and Customer.objects.filter(
                Q(added_by_salon=salon) | Q(orders__salon=salon),
                pk=requested_customer,
            )
            .distinct()
            .exists()
        ):
            initial["customer"] = requested_customer
        form = StylistSelfBookingForm(initial=initial, salon=salon, stylist=stylist)
        return render(
            request,
            self.template_name,
            self._build_context(request, form, stylist, salon),
        )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if not ctx.can("can_create_own_bookings", True):
            messages.error(request, "دسترسی ثبت نوبت برای شما فعال نیست.")
            return redirect("dashboards:stylist_dashboard")
        form = StylistSelfBookingForm(request.POST, salon=salon, stylist=stylist)
        if form.is_valid():
            cd = form.cleaned_data
            price = int(cd["resolved_price"] or 0)
            order = Order.objects.create(
                customer=cd["customer"],
                salon=salon,
                status="confirmed",
                is_finally=True,
                is_paid=False,
                selected_payment_method="pay_in_salon",
                requires_online_payment=False,
                subtotal_amount=price,
                discount_amount=0,
                basket_discount_amount=0,
                coupon_discount_amount=0,
                basket_discount_percent=0,
                basket_discount_title="",
                tax_amount=0,
                total_amount=price,
                coupon_code="",
                discount=0,
                platform_commission_applies=False,
                platform_commission_percent=0,
                platform_commission_amount=0,
                salon_payout_amount=price,
                checkout_locked_at=timezone.now(),
                description=(cd.get("notes") or "").strip(),
                booking_source="dashboard_manual",
                stylist_approved=True,
                stylist_confirmed_at=timezone.now(),
            )
            appointment = OrderDetail.objects.create(
                order=order,
                service=cd["service"],
                stylist=stylist,
                salon=salon,
                price=price,
                date=cd["appointment_date"],
                time=cd["start_time"],
                end_time=cd["resolved_end_time"],
            )
            from apps.payments.finance import sync_settlement_for_order

            sync_settlement_for_order(order)
            messages.success(
                request,
                "نوبت برای خودت با موفقیت ثبت شد. این رزرو به‌صورت پرداخت در مجموعه و بدون کارمزد جدید ثبت شد.",
            )
            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=appointment.id
            )
        return render(
            request,
            self.template_name,
            self._build_context(request, form, stylist, salon),
        )


def _render_booking_quick_link_qr_response(
    request,
    *,
    quick_link,
    as_attachment,
):
    warnings = get_booking_quick_link_qr_warnings(
        quick_link
    )

    confirmation_received = (
        request.GET.get("confirm") == "1"
    )

    if (
        as_attachment
        and warnings
        and not confirmation_received
    ):
        return JsonResponse(
            {
                "ok": False,
                "code": (
                    "quick_link_qr_confirmation_required"
                ),
                "message": (
                    "این لینک دارای هشدار است. "
                    "پیش از دانلود، هشدارها را بررسی و "
                    "دانلود را تأیید کنید."
                ),
                "link_id": quick_link.pk,
                "warnings": list(warnings),
                "confirmation_parameter": "confirm=1",
            },
            status=409,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    generated = generate_booking_quick_link_qr(
        request=request,
        quick_link=quick_link,
    )

    disposition = (
        "attachment"
        if as_attachment
        else "inline"
    )

    ascii_filename = (
        f"loomera-quick-link-{quick_link.pk}.png"
    )

    encoded_filename = quote(
        generated.filename,
        safe="",
    )

    response = HttpResponse(
        generated.content,
        content_type=generated.content_type,
    )

    response["Content-Disposition"] = (
        f'{disposition}; '
        f'filename="{ascii_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )

    response["Cache-Control"] = (
        "private, no-store, max-age=0"
    )

    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"

    response["X-Loomera-QR-Warning-Count"] = str(
        len(generated.warnings)
    )

    return response


class ManagerBookingQuickLinkQRView(
    LoginRequiredMixin,
    View,
):
    as_attachment = False

    def dispatch(self, request, *args, **kwargs):
        redirect_response = (
            _redirect_if_non_manager_user(request)
        )

        if redirect_response:
            return redirect_response

        return super().dispatch(
            request,
            *args,
            **kwargs,
        )

    def get(self, request, link_id, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.only("pk"),
            salon_manager__user=request.user,
        )

        quick_link = get_object_or_404(
            BookingQuickLink.objects.select_related(
                "salon",
                "service",
                "stylist__user",
                "creator",
            ),
            pk=link_id,
            salon=salon,
        )

        return _render_booking_quick_link_qr_response(
            request,
            quick_link=quick_link,
            as_attachment=self.as_attachment,
        )


class StylistBookingQuickLinkQRView(
    StylistDashboardGuardMixin,
    View,
):
    as_attachment = False

    def get(self, request, link_id, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(
            request
        )

        if ctx.stylist is None or ctx.salon is None:
            raise Http404(
                "لینک رزرو در سالن فعال پیدا نشد."
            )

        quick_link = get_object_or_404(
            BookingQuickLink.objects.select_related(
                "salon",
                "service",
                "stylist__user",
                "creator",
            ),
            pk=link_id,
            salon=ctx.salon,
            stylist=ctx.stylist,
            creator=request.user,
        )

        return _render_booking_quick_link_qr_response(
            request,
            quick_link=quick_link,
            as_attachment=self.as_attachment,
        )


class StylistQuickLinksView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/stylist_quick_links.html"

    def _build_context(
        self,
        request,
        stylist,
        salon,
        *,
        generated_link=None,
        generated_payload=None,
        generator_errors=None,
    ):
        workspace = _build_stylist_quick_link_workspace(
            request,
            salon,
            stylist,
            generated_link=generated_link,
            generated_payload=generated_payload,
            generator_errors=generator_errors,
        )
        context = build_dashboard_context(
            request.user,
            sidebar_active="quick_links",
            page_title="لینک رزرو من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "stylist_obj": stylist,
                "stylist_salon": salon,
                "quick_link_workspace": workspace,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        context = self._build_context(request, stylist, salon)
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        quick_link_action = str(
            request.POST.get("quick_link_action") or ""
        ).strip()

        if quick_link_action:
            scoped_links = BookingQuickLink.objects.filter(
                salon=salon,
                creator=request.user,
                stylist=stylist,
            )

            try:
                if quick_link_action == "edit":
                    _link, message = update_booking_quick_link_metadata(
                        links_queryset=scoped_links,
                        link_id=request.POST.get("quick_link_id"),
                        title=request.POST.get("quick_link_title"),
                        placement=request.POST.get("placement"),
                        campaign_name=request.POST.get("campaign_name"),
                        internal_note=request.POST.get("internal_note"),
                        is_permanent=(
                            request.POST.get("is_permanent") == "on"
                        ),
                    )
                elif quick_link_action == "clone":
                    _link, message = clone_booking_quick_link(
                        links_queryset=scoped_links,
                        link_id=request.POST.get("quick_link_id"),
                        creator=request.user,
                    )
                else:
                    _link, message = change_booking_quick_link_status(
                        links_queryset=scoped_links,
                        link_id=request.POST.get("quick_link_id"),
                        action=quick_link_action,
                    )

                messages.success(request, message)
            except ValidationError as exc:
                messages.error(
                    request,
                    " ".join(
                        getattr(exc, "messages", [str(exc)])
                    ),
                )

            return redirect("dashboards:stylist_quick_links")

        generated_link, generated_payload, generator_errors = (
            _generate_stylist_quick_link(
                request,
                salon,
                stylist,
            )
        )

        if generated_link:
            messages.success(request, "لینک رزرو با موفقیت ساخته شد.")
        else:
            messages.error(
                request,
                "برای ساخت لینک، خطاهای فرم را بررسی کن.",
            )

        context = self._build_context(
            request,
            stylist,
            salon,
            generated_link=generated_link,
            generated_payload=generated_payload,
            generator_errors=generator_errors,
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)



class StylistAppointmentsView(StylistDashboardGuardMixin, View):
    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        today = timezone.localdate()

        base_qs = _stylist_base_appointments_qs(stylist, salon=salon)

        today_qs = base_qs.filter(date=today)
        upcoming_qs = base_qs.filter(date__gt=today)
        past_qs = base_qs.filter(date__lt=today).order_by("-date", "-time", "-id")
        # Keep the complete scoped list in the response context for runtime
        # contracts/operational acceptance. The simplified UX intentionally
        # does not render a separate "all" tab.
        all_qs = base_qs.order_by("-date", "-time", "-id")

        can_view_phone = ctx.can("can_view_client_phone", False)

        today_cards = [
            _serialize_stylist_appointment_card(
                detail,
                can_view_client_phone=can_view_phone,
            )
            for detail in today_qs[:30]
        ]
        upcoming_cards = [
            _serialize_stylist_appointment_card(
                detail,
                can_view_client_phone=can_view_phone,
            )
            for detail in upcoming_qs[:40]
        ]
        past_cards = [
            _serialize_stylist_appointment_card(
                detail,
                can_view_client_phone=can_view_phone,
            )
            for detail in past_qs[:40]
        ]
        all_cards = [
            _serialize_stylist_appointment_card(
                detail,
                can_view_client_phone=can_view_phone,
            )
            for detail in all_qs[:60]
        ]

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_appointments",
            page_title="نوبت‌های من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "today_appointment_cards": today_cards,
                "upcoming_appointment_cards": upcoming_cards,
                "past_appointment_cards": past_cards,
                # Compatibility/runtime scope contract; not rendered as a
                # duplicate task in the specialist appointments UI.
                "all_appointment_cards": all_cards,
                "today_count_label": to_persian_digits(len(today_cards)),
                "upcoming_count_label": to_persian_digits(len(upcoming_cards)),
                "past_count_label": to_persian_digits(len(past_cards)),
                "all_count_label": to_persian_digits(len(all_cards)),
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, "dashboards/stylist_appointments.html", context)


class StylistAppointmentDetailView(StylistDashboardGuardMixin, View):
    def _get_detail(self, stylist, appointment_id, salon=None):
        qs = OrderDetail.objects.select_related(
            "order__customer__user",
            "service",
            "salon",
            "stylist__user",
        ).filter(pk=appointment_id, stylist=stylist)
        if salon is not None:
            qs = qs.filter(salon=salon)
        return get_object_or_404(qs)

    def _build_material_context(self, request, detail):
        usages = (
            AppointmentMaterialUsage.objects.filter(order_detail=detail)
            .select_related("material", "recorded_by")
            .order_by("id")
        )

        templates = (
            ServiceMaterialTemplate.objects.filter(
                salon=detail.salon,
                service=detail.service,
                is_active=True,
            )
            .select_related("material")
            .order_by("material__name")
        )

        snapshot = getattr(detail, "financial_snapshot", None)

        return {
            "material_usages": usages,
            "material_templates": templates,
            "material_usage_form": AppointmentMaterialUsageForm(
                salon=detail.salon,
                order_detail=detail,
            ),
            "material_total_label": _dashboard_currency(
                detail.get_material_cost_total()
            ),
            "financial_snapshot": snapshot,
            "is_financial_finalized": bool(
                getattr(detail, "financial_finalized_at", None)
            ),
            "can_finalize_finance": bool(detail.service_completed_at)
            and not bool(getattr(detail, "financial_finalized_at", None)),
        }

    def _build_dispute_context(self, detail):
        cases = list(
            DisputeCase.objects.filter(
                order=detail.order,
                order_detail=detail,
                salon=detail.salon,
                stylist=detail.stylist,
            ).order_by("-updated_at", "-created_at")
        )

        return {
            "stylist_dispute_cases": [
                {
                    "id": case.id,
                    "type_label": case.get_dispute_type_display(),
                    "status_label": case.get_status_display(),
                    "priority_label": case.get_priority_display(),
                    "subject": case.subject or "پرونده اختلاف",
                    "description": case.description or "",
                    "resolution": case.resolution or "",
                    "resolution_note": case.resolution_note or "",
                    "created_label": (
                        format_jalali_numeric(
                            timezone.localtime(case.created_at).date()
                        )
                        if case.created_at
                        else "—"
                    ),
                    "updated_label": (
                        format_jalali_numeric(
                            timezone.localtime(case.updated_at).date()
                        )
                        if case.updated_at
                        else "—"
                    ),
                }
                for case in cases
            ],
            "stylist_dispute_count_label": to_persian_digits(len(cases)),
            "has_stylist_dispute_cases": bool(cases),
        }

    def _create_material_template_for_current_service(self, request, detail):
        name = (request.POST.get("template_material_name") or "").strip()
        unit = request.POST.get("template_material_unit") or MaterialItem.Unit.PIECE
        quantity = request.POST.get("template_quantity") or "1"
        unit_cost = int(request.POST.get("template_unit_cost") or 0)
        paid_by = (
            request.POST.get("template_paid_by") or ServiceMaterialTemplate.PaidBy.SALON
        )

        if not name:
            raise ValidationError("نام ماده مصرفی را وارد کنید.")

        if unit not in dict(MaterialItem.Unit.choices):
            unit = MaterialItem.Unit.PIECE

        if paid_by not in dict(ServiceMaterialTemplate.PaidBy.choices):
            paid_by = ServiceMaterialTemplate.PaidBy.SALON

        material, _ = MaterialItem.objects.get_or_create(
            salon=detail.salon,
            name=name,
            defaults={
                "unit": unit,
                "default_unit_cost": unit_cost,
                "is_active": True,
                "description": "ثبت‌شده توسط متخصص از صفحه جزئیات نوبت",
            },
        )

        if not material.is_active:
            material.is_active = True
            material.save(update_fields=["is_active", "updated_at"])

        template, created = ServiceMaterialTemplate.objects.update_or_create(
            salon=detail.salon,
            service=detail.service,
            material=material,
            defaults={
                "default_quantity": Decimal(str(quantity or "1")),
                "unit_cost": unit_cost or int(material.default_unit_cost or 0),
                "paid_by": paid_by,
                "is_active": True,
            },
        )

        return template, created

    def get(self, request, appointment_id, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        detail = self._get_detail(stylist, appointment_id, salon=salon)

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_appointments",
            page_title="جزئیات نوبت من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "appointment": _serialize_stylist_appointment_card(
                    detail,
                    can_view_client_phone=ctx.can("can_view_client_phone", False),
                ),
                "appointment_obj": detail,
                "stylist_lifecycle_actions": _get_allowed_stylist_lifecycle_actions(
                    detail
                ),
                "stylist_lifecycle_timeline": _build_stylist_lifecycle_timeline(
                    detail.order, detail
                ),
                "cash_payment_state": get_pay_in_salon_cash_confirmation_state(
                    detail.order
                ),
            }
        )
        context.update(_stylist_context_payload(ctx))
        context.update(self._build_material_context(request, detail))
        context.update(self._build_dispute_context(detail))
        return render(request, "dashboards/stylist_appointment_detail.html", context)

    def _handle_material_action(self, request, detail, action):
        if action != "finalize_detail_finance" and getattr(
            detail, "financial_finalized_at", None
        ):
            messages.error(
                request,
                "محاسبات مالی این خدمت نهایی شده و مواد مصرفی دیگر قابل تغییر نیست.",
            )
            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        if action == "create_material_template":
            try:
                template, created = self._create_material_template_for_current_service(
                    request,
                    detail,
                )
                if created:
                    messages.success(request, "قالب مواد مصرفی برای این خدمت ثبت شد.")
                else:
                    messages.success(request, "قالب مواد مصرفی این خدمت بروزرسانی شد.")
            except ValidationError as exc:
                messages.error(request, str(exc))
            except Exception:
                logger.exception(
                    "Failed to create stylist material template for detail_id=%s",
                    detail.pk,
                )
                messages.error(request, "ثبت قالب مواد مصرفی با خطا مواجه شد.")

            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        if action == "generate_materials":
            created = detail.ensure_material_usage_from_template(
                recorded_by=request.user
            )
            messages.success(
                request, f"{len(created)} مورد از قالب مواد مصرفی خدمت اضافه شد."
            )
            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        if action == "create_material_usage":
            form = AppointmentMaterialUsageForm(
                request.POST,
                salon=detail.salon,
                order_detail=detail,
            )

            if form.is_valid():
                usage = form.save(commit=False)
                usage.recorded_by = request.user
                usage.save()
                messages.success(request, "ماده مصرفی برای این نوبت ثبت شد.")
            else:
                messages.error(request, "اطلاعات ماده مصرفی معتبر نیست.")

            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        if action == "update_material_usage":
            usage = get_object_or_404(
                AppointmentMaterialUsage,
                pk=request.POST.get("usage_id"),
                order_detail=detail,
            )

            usage.quantity = request.POST.get("quantity") or "0"
            usage.unit_cost = int(request.POST.get("unit_cost") or 0)
            usage.paid_by = request.POST.get("paid_by") or usage.paid_by
            usage.note = request.POST.get("note") or ""
            usage.recorded_by = request.user
            usage.save()

            messages.success(request, "مواد مصرفی بروزرسانی شد.")
            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        if action == "delete_material_usage":
            usage = get_object_or_404(
                AppointmentMaterialUsage,
                pk=request.POST.get("usage_id"),
                order_detail=detail,
            )
            usage.delete()

            messages.warning(request, "ماده مصرفی حذف شد.")
            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        if action == "finalize_detail_finance":
            try:
                snapshot = finalize_order_detail_financials(
                    detail,
                    recorded_by=request.user,
                    require_completed=True,
                )
                messages.success(
                    request,
                    f"محاسبات مالی نهایی شد. سهم شما: {_dashboard_currency(snapshot.stylist_net_share)}",
                )
            except ValidationError as exc:
                messages.error(request, str(exc))

            return redirect(
                "dashboards:stylist_appointment_detail", appointment_id=detail.id
            )

        messages.error(request, "عملیات انتخاب‌شده معتبر نیست.")
        return redirect(
            "dashboards:stylist_appointment_detail", appointment_id=detail.id
        )

    def post(self, request, appointment_id, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if not ctx.can("can_complete_appointments", True):
            messages.error(request, "دسترسی اجرای مراحل نوبت برای شما فعال نیست.")
            return redirect("dashboards:stylist_appointments")
        detail = self._get_detail(stylist, appointment_id, salon=salon)
        action = (request.POST.get("action") or "").strip()

        material_actions = {
            "generate_materials",
            "create_material_usage",
            "update_material_usage",
            "delete_material_usage",
            "finalize_detail_finance",
            "create_material_template",
        }

        if action in material_actions:
            return self._handle_material_action(request, detail, action)

        try:
            with transaction.atomic():
                message = _apply_stylist_lifecycle_action(
                    detail, action, actor=request.user
                )
            messages.success(request, message)
        except ValidationError as exc:
            messages.error(request, str(exc))

        return redirect(
            "dashboards:stylist_appointment_detail", appointment_id=detail.id
        )


class StylistFinanceView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/stylist_finance.html"

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon

        if not ctx.can("can_view_own_finance", True):
            messages.error(request, "دسترسی مشاهده مالی برای شما فعال نیست.")
            return redirect("dashboards:stylist_dashboard")

        wallet, _ = StylistWallet.objects.get_or_create(stylist=stylist)
        if salon:
            release_eligible_stylist_wallet_funds_for_salon(salon)
            snapshots = (
                OrderDetailFinancialSnapshot.objects.filter(
                    stylist=stylist,
                    salon=salon,
                    status=OrderDetailFinancialSnapshot.Status.FINALIZED,
                )
                .select_related("order", "service", "salon", "order_detail")
                .order_by("-finalized_at", "-created_at", "-id")
            )
            transactions_qs = (
                wallet.transactions.select_related(
                    "order", "order_detail", "financial_snapshot"
                )
                .filter(salon=salon)
                .exclude(transaction_type__in=["withdraw_request", "withdraw_restore"])
                .order_by("-created_at", "-id")
            )
        else:
            snapshots = OrderDetailFinancialSnapshot.objects.none()
            transactions_qs = wallet.transactions.none()
            messages.warning(request, "برای مشاهده درآمد، ابتدا یک مجموعه فعال انتخاب کنید.")

        finalized_summary = snapshots.aggregate(
            count=Count("id"),
            stylist_share=Sum("stylist_net_share"),
        )

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_finance",
            page_title="مالی من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "wallet": wallet,
                "snapshots": snapshots[:100],
                "transactions": transactions_qs[:50],
                "active_finance_salon": salon,
                "finance_scope_label": f"مجموعه {salon.salon_name}" if salon else "بدون مجموعه فعال",
                "summary_cards": [
                    {
                        "label": "قابل دریافت",
                        "value": _dashboard_currency(wallet.available_balance_for_salon(salon)),
                        "icon": "fa-solid fa-building-columns",
                    },
                    {
                        "label": "در انتظار آزادشدن",
                        "value": _dashboard_currency(wallet.pending_balance_for_salon(salon)),
                        "icon": "fa-regular fa-clock",
                    },
                    {
                        "label": "درآمد قطعی",
                        "value": _dashboard_currency(finalized_summary.get("stylist_share") or 0),
                        "icon": "fa-solid fa-chart-line",
                    },
                    {
                        "label": "خدمات نهایی‌شده",
                        "value": to_persian_digits(finalized_summary.get("count") or 0),
                        "icon": "fa-solid fa-receipt",
                    },
                ],
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)


class StylistRequestPayoutView(StylistDashboardGuardMixin, View):
    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        if not ctx.can("can_request_payout", True):
            messages.error(request, "دسترسی ثبت درخواست پرداخت برای شما فعال نیست.")
            return redirect("dashboards:stylist_finance")

        raw_amount = (request.POST.get("amount") or "").strip().replace(",", "")
        amount = None
        if raw_amount:
            try:
                amount = int(raw_amount)
            except ValueError:
                messages.error(request, "مبلغ درخواست معتبر نیست.")
                return redirect("dashboards:stylist_finance")

        try:
            payout = create_staff_payout_request(
                stylist=stylist,
                salon=salon,
                requested_by=request.user,
                amount=amount,
                note=request.POST.get("note") or "",
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"درخواست پرداخت به مبلغ {_dashboard_currency(payout.requested_amount)} ثبت شد.",
            )
        return redirect("dashboards:stylist_finance")


class StylistScheduleView(StylistDashboardGuardMixin, View):
    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        today = timezone.localdate()
        schedules = [
            _serialize_stylist_schedule_row(item)
            for item in StylistSchedule.objects.filter(
                stylist=stylist, salon=salon, date__gte=today
            )
            .select_related("salon", "service")
            .order_by("date", "start_time")[:30]
        ]
        legacy_time_off_rows = [
            _serialize_stylist_time_off_row(item)
            for item in StylistTimeOff.objects.filter(
                stylist=stylist,
                date__gte=today,
            ).order_by("date", "start_time")[:20]
        ]

        approved_leave_rows = [
            _serialize_stylist_time_off_row(item)
            for item in StaffLeaveRequest.objects.filter(
                stylist=stylist,
                salon=salon,
                status=StaffLeaveRequest.Status.APPROVED,
                date__gte=today,
            ).order_by("date", "start_time")[:20]
        ]

        time_offs = sorted(
            legacy_time_off_rows + approved_leave_rows,
            key=lambda item: item.get("sort_key") or "",
        )[:20]
        leave_requests = (
            StaffLeaveRequest.objects.filter(
                stylist=stylist,
                salon=salon,
            )
            .select_related("salon")
            .order_by("-created_at", "-id")[:20]
        )
        schedule_requests = (
            StaffScheduleRequest.objects.filter(
                stylist=stylist,
                salon=salon,
            )
            .select_related("salon", "service")
            .order_by("-created_at", "-id")[:20]
        )
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_schedule",
            page_title="برنامه و مرخصی من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "schedule_rows": schedules,
                "time_off_rows": time_offs,
                "leave_requests": leave_requests,
                "schedule_requests": schedule_requests,
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, "dashboards/stylist_schedule.html", context)


class StylistAddTimeOffView(StylistDashboardGuardMixin, View):
    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon

        if not salon:
            messages.error(
                request,
                "برای ثبت درخواست مرخصی، ابتدا باید یک مجموعه فعال داشته باشید.",
            )
            return redirect("dashboards:stylist_profile")

        form = StylistSelfTimeOffForm()
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_schedule",
            page_title="درخواست مرخصی",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update({"form": form})
        context.update(_stylist_context_payload(ctx))
        return render(request, "dashboards/stylist_add_time_off.html", context)

    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon

        if not salon:
            messages.error(
                request,
                "برای ثبت درخواست مرخصی، ابتدا باید یک مجموعه فعال داشته باشید.",
            )
            return redirect("dashboards:stylist_profile")

        form = StylistSelfTimeOffForm(request.POST)
        if form.is_valid():
            try:
                leave_request = create_leave_request(
                    stylist=stylist,
                    salon=salon,
                    date_value=form.cleaned_data["date"],
                    start_time=form.cleaned_data.get("start_time"),
                    end_time=form.cleaned_data.get("end_time"),
                    reason=(form.cleaned_data.get("reason") or "").strip(),
                    actor=request.user,
                    auto_approve=False,
                )
            except ValidationError as exc:
                messages.error(request, str(exc))
            else:
                try:
                    _notify_manager_about_leave_request(
                        leave_request=leave_request,
                        actor=request.user,
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify manager about staff leave request. leave_request_id=%s",
                        leave_request.id,
                    )
                messages.success(
                    request,
                    "درخواست مرخصی شما برای بررسی مدیر مجموعه ثبت شد.",
                    "success",
                )
                return redirect("dashboards:stylist_schedule")

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_schedule",
            page_title="درخواست مرخصی",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update({"form": form})
        context.update(_stylist_context_payload(ctx))
        return render(request, "dashboards/stylist_add_time_off.html", context)


class StylistProfileView(StylistDashboardGuardMixin, View):
    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        user_form = StylistUserForm(instance=request.user, allow_mobile_edit=False)
        profile_form = StylistProfileForm(instance=stylist)
        emergency_info = _get_stylist_emergency_info(stylist)
        emergency_form = EmergencyInfoForm(instance=emergency_info)
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_profile",
            page_title="پروفایل من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "user_form": user_form,
                "profile_form": profile_form,
                "emergency_form": emergency_form,
                "stylist_profile_summary": _build_stylist_profile_summary(
                    stylist, salon=salon
                ),
                "stylist_collaboration_workspace": _build_stylist_collaboration_workspace(
                    stylist
                ),
            }
        )
        context.update(_stylist_portfolio_payload(stylist, salon=salon))
        context.update(_stylist_context_payload(ctx))
        return render(request, "dashboards/stylist_profile.html", context)

    def post(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon

        profile_action = (request.POST.get("profile_action") or "save_profile").strip()

        if profile_action == "request_salon_membership":
            return _create_stylist_membership_request(request, stylist)

        if profile_action == "update_salon_membership_request":
            return _update_stylist_membership_request(request, stylist)

        if profile_action == "cancel_salon_membership_request":
            return _cancel_stylist_membership_request(request, stylist)

        if profile_action == "leave_salon_membership":
            return _leave_stylist_membership(request, stylist)

        if profile_action == "accept_manager_invite":
            return _respond_to_manager_invite(request, stylist, accepted=True)

        if profile_action == "reject_manager_invite":
            return _respond_to_manager_invite(request, stylist, accepted=False)

        if profile_action == "add_work_sample":
            if not ctx.can("can_manage_own_portfolio", True):
                messages.error(request, "دسترسی مدیریت نمونه‌کار برای شما فعال نیست.")
                return redirect("dashboards:stylist_profile")

            work_sample_form = WorkSamplesForm(
                request.POST,
                request.FILES,
                stylist=stylist,
                salon=salon,
            )
            if work_sample_form.is_valid():
                work_sample_form.save(stylist=stylist, salon=salon)
                messages.success(request, "نمونه‌کار جدید با موفقیت منتشر شد.")
                return redirect("dashboards:stylist_profile")

            emergency_info = _get_stylist_emergency_info(stylist)
            context = build_dashboard_context(
                request.user,
                sidebar_active="my_profile",
                page_title="پروفایل من",
                request_path=request.path,
                role="stylist",
                salon_override=salon,
                stylist_override=stylist,
            )
            context.update(
                {
                    "user_form": StylistUserForm(instance=request.user, allow_mobile_edit=False),
                    "profile_form": StylistProfileForm(instance=stylist),
                    "emergency_form": EmergencyInfoForm(instance=emergency_info),
                    "stylist_profile_summary": _build_stylist_profile_summary(
                        stylist, salon=salon
                    ),
                    "stylist_collaboration_workspace": _build_stylist_collaboration_workspace(
                        stylist
                    ),
                }
            )
            context.update(
                _stylist_portfolio_payload(
                    stylist,
                    salon=salon,
                    form=work_sample_form,
                )
            )
            context.update(_stylist_context_payload(ctx))
            messages.error(
                request, "نمونه‌کار قابل ذخیره نیست. خطاهای فرم را بررسی کن."
            )
            return render(request, "dashboards/stylist_profile.html", context)

        if profile_action == "delete_work_sample":
            if not ctx.can("can_manage_own_portfolio", True):
                messages.error(request, "دسترسی مدیریت نمونه‌کار برای شما فعال نیست.")
                return redirect("dashboards:stylist_profile")

            sample_id = (request.POST.get("sample_id") or "").strip()
            deleted_count = (
                WorkSamples.objects.filter(
                    pk=sample_id,
                    stylist=stylist,
                ).delete()[0]
                if sample_id.isdigit()
                else 0
            )
            if deleted_count:
                messages.success(request, "نمونه‌کار حذف شد.")
            else:
                messages.error(request, "نمونه‌کار انتخاب‌شده پیدا نشد.")
            return redirect("dashboards:stylist_profile")

        if profile_action != "save_profile":
            messages.error(request, "عملیات انتخاب‌شده برای پروفایل متخصص معتبر نیست.")
            return redirect("dashboards:stylist_profile")

        emergency_info = _get_stylist_emergency_info(stylist)

        user_form = StylistUserForm(request.POST, instance=request.user, allow_mobile_edit=False)
        profile_form = StylistProfileForm(request.POST, request.FILES, instance=stylist)
        emergency_form = EmergencyInfoForm(request.POST, instance=emergency_info)

        if (
            user_form.is_valid()
            and profile_form.is_valid()
            and emergency_form.is_valid()
        ):
            user_form.save()
            profile_form.save()

            emergency = emergency_form.save(commit=False)
            emergency.stylist = stylist

            emergency_name = (
                emergency_form.cleaned_data.get("emergency_contact_name") or ""
            ).strip()
            emergency_family = (
                emergency_form.cleaned_data.get("emergency_contact_family") or ""
            ).strip()
            emergency_phone = (
                emergency_form.cleaned_data.get("emergency_phone") or ""
            ).strip()

            emergency.full_name = f"{emergency_name} {emergency_family}".strip()
            emergency.emergency_contact = emergency_phone
            emergency.save()

            messages.success(request, "پروفایل متخصص با موفقیت به‌روزرسانی شد.")
            return redirect("dashboards:stylist_profile")

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_profile",
            page_title="پروفایل من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "user_form": user_form,
                "profile_form": profile_form,
                "emergency_form": emergency_form,
                "stylist_profile_summary": _build_stylist_profile_summary(
                    stylist,
                    salon=salon,
                ),
                "stylist_collaboration_workspace": _build_stylist_collaboration_workspace(
                    stylist
                ),
            }
        )
        messages.error(
            request, "اطلاعات پروفایل کامل یا معتبر نیست. لطفاً فیلدها را بررسی کن."
        )
        context.update(_stylist_portfolio_payload(stylist, salon=salon))
        context.update(_stylist_context_payload(ctx))
        return render(request, "dashboards/stylist_profile.html", context)


class ManagerProfileView(LoginRequiredMixin, View):
    template_name = "dashboards/manager_profile.html"

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "salon_manager_profile"):
            return redirect("dashboards:salon_manager_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def _build_context(self, request, form, manager_profile):
        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title="پروفایل مدیر",
            request_path=request.path,
        )
        context.update(
            {
                "hide_dashboard_header": True,
                "hide_dashboard_top_nav": True,
                "page_meta": {
                    "title": "پروفایل مدیر",
                    "description": "نام، ایمیل و تصویر حساب مدیر را مدیریت کن؛ اطلاعات مجموعه در پروفایل مجموعه نگهداری می‌شود.",
                    "icon": "fa-regular fa-user",
                    "badges": [],
                    "primary_action": {
                        "label": "بازگشت به تنظیمات",
                        "url": reverse("dashboards:workspace_settings"),
                    },
                },
                "form": form,
                "manager_profile": manager_profile,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        manager_profile = request.user.salon_manager_profile
        form = SalonManagerUpdateProfileForm(
            manager_instance=manager_profile,
            instance=request.user,
        )
        context = self._build_context(request, form, manager_profile)
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        manager_profile = request.user.salon_manager_profile
        form = SalonManagerUpdateProfileForm(
            request.POST,
            request.FILES,
            manager_instance=manager_profile,
            instance=request.user,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "پروفایل مدیر با موفقیت ذخیره شد.")
            return redirect("dashboards:manager_profile")

        messages.error(request, "لطفاً خطاهای فرم را بررسی کنید.", "danger")
        context = self._build_context(request, form, manager_profile)
        return render(request, self.template_name, context)


# -------------------------------------------------------------------------------
class WorkspaceSettingsHubView(LoginRequiredMixin, View):
    template_name = "dashboards/workspace_settings.html"

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "salon_manager_profile"):
            return redirect("dashboards:salon_manager_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def _settings_groups(self):
        return [
            {
                "key": "business",
                "eyebrow": "مجموعه و رزرو",
                "title": "چیزی که مشتری می‌بیند",
                "description": "اطلاعات عمومی مجموعه و مسیر رزرو آنلاین را از همین دو بخش تنظیم کن.",
                "icon": "fa-solid fa-shop",
                "items": [
                    {
                        "title": "پروفایل مجموعه",
                        "description": "نام و تماس، موقعیت، ساعات کاری، تصاویر، امکانات و معرفی مجموعه",
                        "url": reverse("dashboards:salon_profile"),
                        "icon": "fa-solid fa-store",
                    },
                    {
                        "title": "رزرو آنلاین و لینک‌ها",
                        "description": "صفحه رزرو، Quick Linkها، QR و قالب‌های چاپی",
                        "url": reverse("dashboards:online_booking"),
                        "icon": "fa-solid fa-link",
                    },
                ],
            },
            {
                "key": "account",
                "eyebrow": "حساب و امنیت",
                "title": "حساب مدیر مجموعه",
                "description": "اطلاعات شخصی مدیر و امنیت ورود را مستقل از اطلاعات عمومی مجموعه مدیریت کن.",
                "icon": "fa-solid fa-shield-halved",
                "items": [
                    {
                        "title": "پروفایل مدیر",
                        "description": "نام، تصویر، ایمیل و اطلاعات تماس حساب مدیر",
                        "url": reverse("dashboards:manager_profile"),
                        "icon": "fa-regular fa-user",
                    },
                    {
                        "title": "تغییر رمز عبور",
                        "description": "رمز ورود حساب را تغییر بده و امنیت ورود را حفظ کن",
                        "url": reverse("accounts:change_password"),
                        "icon": "fa-solid fa-key",
                    },
                ],
            },
            {
                "key": "notifications",
                "eyebrow": "اعلان‌ها و ارتباطات",
                "title": "پیام‌هایی که دریافت می‌کنی",
                "description": "اعلان‌های عملیاتی و تبلیغاتی مدیر را جدا کنترل کن و اتصال پیام‌رسان را ببین.",
                "icon": "fa-regular fa-bell",
                "items": [
                    {
                        "title": "اعلان‌ها و ارتباطات",
                        "description": "اعلان‌های مدیر و اتصال بله را از یک صفحه مدیریت کن",
                        "url": reverse("dashboards:manager_communication_settings"),
                        "icon": "fa-regular fa-bell",
                    },
                ],
            },
        ]

    def get(self, request, *args, **kwargs):
        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title="تنظیمات",
            request_path=request.path,
        )

        context.update(
            {
                "hide_dashboard_header": True,
                "hide_dashboard_top_nav": True,
                "page_meta": {
                    "title": "تنظیمات",
                    "description": "پروفایل و رزرو آنلاین مجموعه، حساب مدیر، امنیت و اعلان‌ها را از یک مسیر ساده مدیریت کن.",
                    "icon": "fa-solid fa-gear",
                    "badges": [],
                    "primary_action": {
                        "label": "بازگشت به داشبورد",
                        "url": reverse("dashboards:home"),
                    },
                },
                "workspace_settings_groups": self._settings_groups(),
                "workspace_settings_legal_links": [
                    {
                        "label": "حریم خصوصی",
                        "url": reverse("accounts:privacy_policy"),
                    },
                    {
                        "label": "شرایط استفاده",
                        "url": reverse("accounts:terms_of_use"),
                    },
                    {
                        "label": "حریم خصوصی پیام‌رسان‌ها",
                        "url": reverse("messaging:privacy"),
                    },
                ],
            }
        )
        return render(request, self.template_name, context)

class StylistSettingsHubView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/stylist_settings.html"

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_settings",
            page_title="تنظیمات من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "stylist_settings_groups": [
                    {
                        "key": "account",
                        "eyebrow": "حساب",
                        "title": "حساب و امنیت",
                        "description": "اطلاعات حرفه‌ای و امنیت حساب خودت را مدیریت کن.",
                        "icon": "fa-regular fa-user",
                        "items": [
                            {
                                "title": "پروفایل من",
                                "description": "نام، رزومه، تصویر، نمونه‌کار و اطلاعات حرفه‌ای",
                                "icon": "fa-regular fa-id-card",
                                "url": reverse("dashboards:stylist_profile"),
                            },
                            {
                                "title": "تغییر رمز عبور",
                                "description": "رمز ورود حساب لومرا را تغییر بده",
                                "icon": "fa-solid fa-key",
                                "url": reverse("accounts:change_password"),
                            },
                        ],
                    },
                    {
                        "key": "communications",
                        "eyebrow": "ارتباطات",
                        "title": "اعلان‌ها و پیام‌رسان",
                        "description": "وضعیت اتصال بله و ترجیح دریافت اعلان‌ها را مدیریت کن.",
                        "icon": "fa-regular fa-bell",
                        "items": [
                            {
                                "title": "اعلان‌ها و ارتباطات",
                                "description": "تنظیم پیام‌های کاری/تبلیغاتی و اتصال حساب بله",
                                "icon": "fa-regular fa-bell",
                                "url": reverse("dashboards:stylist_communication_settings"),
                            },
                            {
                                "title": "مرکز اعلان‌های من",
                                "description": "همه اعلان‌های کاری خودت را یک‌جا مرور کن",
                                "icon": "fa-regular fa-bell",
                                "url": reverse("dashboards:stylist_notifications"),
                            },
                        ],
                    },
                ]
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)


class StylistQuickLinkOptionsView(StylistDashboardGuardMixin, View):
    """Availability options for the signed-in stylist using canonical booking slots."""

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        service_id = (request.GET.get("service_id") or "").strip()
        if not service_id:
            return JsonResponse({"availability": []})
        service = (
            Services.objects.filter(
                pk=service_id,
                services_of_salon=salon,
                stylists=stylist,
                is_active=True,
            )
            .distinct()
            .first()
        )
        if service is None:
            return JsonResponse({"error": "این خدمت برای شما در مجموعه فعال نیست."}, status=400)
        return JsonResponse(
            {"availability": _quick_link_availability_days(salon=salon, service=service, stylist=stylist)},
            json_dumps_params={"ensure_ascii": False},
        )


class StylistNotificationCenterView(StylistDashboardGuardMixin, View):
    template_name = "dashboards/notifications_center.html"

    def get(self, request, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon
        context = build_dashboard_context(
            request.user,
            sidebar_active="overview",
            page_title="اعلان‌های من",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        notifications = context.get("dashboard_notifications", {})
        context.update(
            {
                "salon": salon,
                "notification_center_title": "مرکز اعلان‌های من",
                "notification_center_description": "نوبت‌ها، مالی و تغییرات کاری مرتبط با خودت را یک‌جا ببین و از همان اعلان وارد صفحه مرتبط شو.",
                "notification_center_empty_label": "هنوز اعلان کاری برای شما ثبت نشده است.",
                "notification_center": {
                    "tabs": notifications.get("tabs", []),
                    "items": notifications.get("items", []),
                    "active_category": "all",
                    "is_empty": not notifications.get("items"),
                },
            }
        )
        context.update(_stylist_context_payload(ctx))
        return render(request, self.template_name, context)


def _activate_salon_public_page(request, salon):
    """Activate the public page using the canonical booking-readiness checks."""
    if salon.is_active:
        messages.info(request, "صفحه عمومی مجموعه قبلاً فعال شده است.")
        return None

    readiness = build_salon_readiness_checklist(salon)
    next_prerequisite = next(
        (
            item
            for item in readiness["booking_items"]
            if item["key"] != "public_active" and not item["is_done"]
        ),
        None,
    )
    if next_prerequisite:
        messages.warning(
            request,
            f"قبل از فعال‌سازی صفحه عمومی، این مورد را کامل کن: {next_prerequisite['title']}",
        )
        return next_prerequisite.get("action_url") or reverse("dashboards:salon_profile")

    salon.is_active = True
    salon.save(update_fields=["is_active"])
    messages.success(
        request,
        "صفحه عمومی مجموعه فعال شد. حالا مسیر رزرو را یک‌بار از نگاه مشتری بررسی کن.",
    )
    return None


@login_required
@manager_required
def legacy_quick_links_redirect(request):
    """Keep the old manager quick-links reverse name pointed at Online Booking."""
    return redirect(f'{reverse("dashboards:online_booking")}?tab=list')


def _is_manager_profile_edit_mode(user):
    """Return True after the required three-step onboarding is complete."""
    return _get_required_onboarding_view_name(user) is None



class CustomerAppointmentsPopupView(
    SalonManagerOnboardingGuardMixin, LoginRequiredMixin, View
):
    """Read-only appointment history used by the customer-list modal."""

    def get(self, request, customer_id):
        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            salon_manager__user=request.user,
        )

        customer = get_object_or_404(
            Customer.objects.select_related("user")
            .filter(pk=customer_id)
            .filter(
                Q(added_by_salon=salon)
                | Q(orders__order_details1__salon=salon)
            )
            .distinct()
        )

        appointments = (
            OrderDetail.objects.filter(salon=salon, order__customer=customer)
            .select_related("order", "service", "stylist__user")
            .order_by("-date", "-time", "-pk")
        )

        status_classes = {
            "pending": "bg-amber-100 text-amber-700",
            "confirmed": "bg-loomera-primarySoft text-loomera-primaryText",
            "paid": "bg-emerald-100 text-emerald-700",
            "completed": "bg-sky-100 text-sky-700",
            "cancelled": "bg-rose-100 text-rose-700",
        }

        items = []
        for appointment in appointments:
            items.append(
                {
                    "id": appointment.pk,
                    "detail_url": reverse(
                        "dashboards:appointment_detail",
                        kwargs={
                            "salon_id": salon.pk,
                            "appointment_id": appointment.pk,
                        },
                    ),
                    "date_label": (
                        format_jalali_with_weekday(appointment.date)
                        if appointment.date
                        else "بدون تاریخ"
                    ),
                    "time_label": (
                        format_time_fa(appointment.time)
                        if appointment.time
                        else "--:--"
                    ),
                    "service_name": (
                        appointment.service.service_name
                        if appointment.service_id
                        else "خدمت ثبت نشده"
                    ),
                    "stylist_name": (
                        appointment.stylist.get_fullName()
                        if appointment.stylist_id
                        else "بدون متخصص"
                    ),
                    "status_label": appointment.get_status_display_fa(),
                    "status_badge_class": status_classes.get(
                        appointment.order.status,
                        "bg-slate-100 text-slate-700",
                    ),
                    "price_label": _dashboard_currency(appointment.price or 0),
                }
            )

        return JsonResponse(
            {
                "customer_name": customer.get_fullName()
                or customer.user.get_fullName()
                or "مشتری",
                "count": len(items),
                "appointments": items,
            }
        )
