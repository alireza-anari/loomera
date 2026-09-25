"""A narrowly scoped entry point while legacy manager routes are being audited.

Never render the legacy manager shell here: it currently chooses the first salon
for some widgets and actions, regardless of the selected workspace.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views import View

from apps.accounts.services.access import resolve_manager_salon
from apps.orders.models import OrderDetail


class MultiroleManagerSalonOverviewView(LoginRequiredMixin, View):
    http_method_names = ["get"]
    template_name = "dashboards/multirole_manager_salon_overview.html"

    def get(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        if salon is None:
            raise PermissionDenied("ابتدا سالن موردنظر را انتخاب کنید.")
        # Every metric here is scoped by the *authorized* target, never the
        # stored workspace preference or the first salon of this manager.
        context = {
            "salon": salon,
            "services_count": salon.services.count(),
            "team_count": salon.stylists.count(),
            "booking_count": OrderDetail.objects.filter(salon_id=salon.pk).count(),
        }
        return render(request, self.template_name, context)


class ScopedManagerServicesView(LoginRequiredMixin, View):
    """Only list services joined to the explicitly owned salon."""

    http_method_names = ["get"]

    def get(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        services = salon.services.order_by("service_name", "pk")
        return render(
            request,
            "dashboards/multirole_manager_services.html",
            {"salon": salon, "services": services},
        )


class ScopedManagerTeamView(LoginRequiredMixin, View):
    """Salon-owned team and invite listing; unrelated legacy edits stay blocked."""

    http_method_names = ["get"]

    def get(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        from apps.salons.models import SalonMembership, SalonMembershipStatus

        members = salon.stylists.select_related("user").order_by("pk")
        invites = (
            SalonMembership.objects.filter(
                salon_id=salon.pk, status=SalonMembershipStatus.INVITED,
            )
            .select_related("stylist__user")
            .order_by("-created_at", "-pk")[:30]
        )
        # Only an accepted, currently active salon-specific relationship may
        # expose the scoped edit link; do not derive access from a global
        # Stylist profile or a stale salon.stylists legacy M2M row.
        active_memberships = (
            SalonMembership.objects.filter(
                salon_id=salon.pk,
                status=SalonMembershipStatus.ACTIVE,
                stylist__isnull=False,
            )
            .select_related("stylist__user")
            .order_by("stylist_id", "pk")
        )
        return render(
            request,
            "dashboards/multirole_manager_team.html",
            {
                "salon": salon, "members": members,
                "active_memberships": active_memberships,
                "pending_invites": invites,
            },
        )


class ScopedManagerBookingsView(LoginRequiredMixin, View):
    """Read-only upcoming bookings for an owned salon; no implicit workspace."""

    http_method_names = ["get"]

    def get(self, request, salon_id):
        from django.utils import timezone

        salon = resolve_manager_salon(request.user, salon_id)
        bookings = (
            OrderDetail.objects.filter(salon_id=salon.pk, date__gte=timezone.localdate())
            .select_related("service", "stylist__user", "order")
            .order_by("date", "time", "pk")[:50]
        )
        # Precompute order item counts in one query; never show an actionable
        # cancellation link for an order spanning several appointments.
        from django.db.models import Count
        from django.utils import timezone
        from .multirole_manual_booking_cancel import can_cancel_scoped_manual_booking

        booking_rows = list(bookings)
        counts = dict(
            OrderDetail.objects.filter(
                order_id__in={item.order_id for item in booking_rows}
            ).values("order_id").annotate(total=Count("pk")).values_list("order_id", "total")
        )
        for item in booking_rows:
            item.can_cancel_scoped = can_cancel_scoped_manual_booking(
                item.order, item, item_count=counts.get(item.order_id, 0),
            )
        return render(
            request,
            "dashboards/multirole_manager_bookings.html",
            {"salon": salon, "bookings": booking_rows},
        )


class ScopedManagerServiceStatusView(LoginRequiredMixin, View):
    """POST only. Change a salon-exclusive service, never a shared/catalog row.

    Both URL and form include the salon target, so a different browser tab
    changing the active workspace cannot retarget an already-open form.
    """

    http_method_names = ["post"]

    def post(self, request, salon_id, service_id):
        from django.db import transaction
        from django.shortcuts import get_object_or_404, redirect
        from apps.services.models import Services
        from .views import _service_has_future_active_bookings

        salon = resolve_manager_salon(request.user, salon_id)
        if request.POST.get("salon_id") != str(salon.pk):
            raise PermissionDenied("سالن فرم با سالن انتخاب‌شده مطابقت ندارد.")

        with transaction.atomic():
            service = get_object_or_404(
                Services.objects.select_for_update(),
                pk=service_id,
                services_of_salon=salon,
            )
            # Modifying a catalog or multi-salon row would mutate the other
            # salons' service menu or the platform catalog. Block, don't guess.
            if service.is_platform_catalog or service.services_of_salon.count() != 1:
                raise PermissionDenied("خدمت مشترک از این مسیر قابل ویرایش نیست.")
            if service.is_active and _service_has_future_active_bookings(
                salon=salon, service=service
            ):
                raise PermissionDenied("برای این خدمت نوبت فعال آینده ثبت شده است.")
            service.is_active = not bool(service.is_active)
            service.save(update_fields=["is_active", "updated_date"])

        return redirect(
            "dashboards:multirole_manager_salon_services", salon_id=salon.pk
        )


class _ScopedManagerServiceFormMixin:
    """Use immutable URL/form salon target, never the mutable active workspace."""

    template_name = "dashboards/multirole_manager_service_form.html"

    def owned_salon(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        if salon is None:
            raise PermissionDenied("ابتدا سالن موردنظر را انتخاب کنید.")
        return salon

    def require_form_target(self, request, salon):
        if request.POST.get("salon_id") != str(salon.pk):
            raise PermissionDenied("سالن فرم با سالن انتخاب‌شده مطابقت ندارد.")

    def build_form(self, salon, *args, instance=None, **kwargs):
        from apps.services.forms import StylistServiceForm

        form = StylistServiceForm(*args, salon=salon, instance=instance, **kwargs)
        # Existing dashboard hides this field to power its custom JS picker.
        # Do not replace the widget here: ModelChoiceField binds its queryset
        # choices to the existing widget, so assigning a fresh Select after
        # form initialization produces an empty <select> even though the field
        # queryset is populated. Make the existing widget visible instead and
        # preserve the already-bound choices.
        catalog_widget = form.fields["catalog_service"].widget
        widget_attrs = catalog_widget.attrs
        class_tokens = [
            token for token in (widget_attrs.get("class") or "").split()
            if token != "hidden"
        ]
        visible_classes = [
            "w-full", "rounded-2xl", "border", "border-loomera-borderSoft",
            "bg-white", "px-4", "py-3", "text-sm", "font-bold",
            "text-loomera-textPrimary", "outline-none", "transition",
            "focus:border-loomera-primary/40", "focus:ring-4",
            "focus:ring-loomera-primary/10",
        ]
        widget_attrs["class"] = " ".join(dict.fromkeys(class_tokens + visible_classes))
        widget_attrs.pop("aria-hidden", None)
        widget_attrs.pop("tabindex", None)
        widget_attrs.pop("data-catalog-service-select", None)
        return form

    def render_form(self, request, salon, form, *, service=None):
        return render(request, self.template_name, {
            "salon": salon, "form": form, "service": service,
        })

    def locked_salon(self, request, salon):
        from django.shortcuts import get_object_or_404
        from apps.salons.models import Salon

        # Revalidate ownership inside the write transaction; a stale
        # preference, concurrent transfer, or user-supplied id grants nothing.
        return get_object_or_404(
            Salon.objects.select_for_update(),
            pk=salon.pk, salon_manager__user_id=request.user.pk,
        )


class ScopedManagerServiceAddView(_ScopedManagerServiceFormMixin, LoginRequiredMixin, View):
    """Create only a salon-owned copy of a currently active catalog service."""

    http_method_names = ["get", "post"]

    def get(self, request, salon_id):
        salon = self.owned_salon(request, salon_id)
        return self.render_form(request, salon, self.build_form(salon))

    def post(self, request, salon_id):
        from django.db import transaction
        from django.db.models import Q
        from django.shortcuts import redirect

        salon = self.owned_salon(request, salon_id)
        self.require_form_target(request, salon)
        with transaction.atomic():
            salon = self.locked_salon(request, salon)
            form = self.build_form(salon, request.POST)
            if form.is_valid():
                source = form.cleaned_data["catalog_service"]
                # Check again *under the salon row lock*: another tab may
                # have added the same catalog service after the form was sent.
                if salon.services.filter(
                    Q(pk=source.pk) | Q(catalog_source=source)
                    | Q(service_name=source.service_name)
                ).exists():
                    form.add_error("catalog_service", "این خدمت قبلاً برای این سالن ثبت شده است.")
                else:
                    form.save(commit=True, salon=salon)
                    return redirect(
                        "dashboards:multirole_manager_salon_services", salon_id=salon.pk
                    )
        return self.render_form(request, salon, form)


class ScopedManagerServiceEditView(_ScopedManagerServiceFormMixin, LoginRequiredMixin, View):
    """Edit only an exclusive salon copy; never mutate catalog/shared services."""

    http_method_names = ["get", "post"]

    def owned_service(self, salon, service_id, *, for_update=False):
        from django.shortcuts import get_object_or_404
        from apps.services.models import Services

        qs = Services.objects
        if for_update:
            qs = qs.select_for_update()
        service = get_object_or_404(qs, pk=service_id, services_of_salon=salon)
        if (
            service.is_platform_catalog
            or service.services_of_salon.count() != 1
            or not service.catalog_source_id
            or not service.catalog_source.is_platform_catalog
            or not service.catalog_source.is_active
        ):
            # Legacy private rows without catalog_source and shared rows need
            # a separate audited migration/clone flow. Fail closed here.
            raise PermissionDenied("فقط خدمت اختصاصی متصل به کاتالوگ قابل ویرایش است.")
        return service

    def get(self, request, salon_id, service_id):
        salon = self.owned_salon(request, salon_id)
        service = self.owned_service(salon, service_id)
        form = self.build_form(salon, instance=service)
        return self.render_form(request, salon, form, service=service)

    def post(self, request, salon_id, service_id):
        from django.db import transaction
        from django.shortcuts import redirect
        from .views import _service_has_future_active_bookings

        salon = self.owned_salon(request, salon_id)
        self.require_form_target(request, salon)
        with transaction.atomic():
            salon = self.locked_salon(request, salon)
            service = self.owned_service(salon, service_id, for_update=True)
            # A service with upcoming confirmed bookings must not have its
            # duration, provider assignment or listed terms changed in place.
            if _service_has_future_active_bookings(salon=salon, service=service):
                raise PermissionDenied("برای این خدمت نوبت فعال آینده ثبت شده است.")
            form = self.build_form(salon, request.POST, instance=service)
            if form.is_valid():
                form.save(commit=True, salon=salon)
                return redirect(
                    "dashboards:multirole_manager_salon_services", salon_id=salon.pk
                )
        return self.render_form(request, salon, form, service=service)


class _ScopedManagerTeamFormMixin:
    """Bind every team mutation to the owned URL salon and the form's target."""

    @staticmethod
    def owned_salon(request, salon_id):
        # This lookup never selects a salon from the workspace/session.
        salon = resolve_manager_salon(request.user, salon_id)
        if salon is None:
            raise PermissionDenied("ابتدا سالن موردنظر را انتخاب کنید.")
        return salon

    @staticmethod
    def require_form_target(request, salon):
        if request.POST.get("salon_id") != str(salon.pk):
            raise PermissionDenied("سالن فرم با سالن انتخاب‌شده مطابقت ندارد.")

    @staticmethod
    def locked_owned_salon(request, salon):
        from apps.salons.models import Salon
        from django.shortcuts import get_object_or_404

        return get_object_or_404(
            Salon.objects.select_for_update(),
            pk=salon.pk,
            salon_manager__user_id=request.user.pk,
        )

    @staticmethod
    def team_url(salon):
        from django.urls import reverse

        return reverse(
            "dashboards:multirole_manager_salon_team",
            kwargs={"salon_id": salon.pk},
        )


class ScopedManagerTeamInviteView(_ScopedManagerTeamFormMixin, LoginRequiredMixin, View):
    """Issue an invitation, without creating identities or activating membership.

    Existing PAUSED/ENDED/rejected membership is never revived automatically.
    Rows are serialized under a salon lock so two identical submissions cannot
    create multiple pending invitations on databases with row-level locking.
    """

    http_method_names = ["post"]

    def post(self, request, salon_id):
        import re
        import logging

        from django.contrib import messages
        from django.db import transaction
        from django.db.models import Q
        from django.shortcuts import redirect
        from django.utils import timezone

        from apps.accounts.models import CustomUser, Stylist
        from apps.salons.membership import (
            PERSIAN_DIGITS, default_invite_expiry, log_membership_event,
        )
        from apps.salons.models import SalonMembership, SalonMembershipStatus

        salon = self.owned_salon(request, salon_id)
        self.require_form_target(request, salon)
        phone = (request.POST.get("mobile_number") or "").strip().translate(PERSIAN_DIGITS)
        if re.fullmatch(r"09[0-9]{9}", phone) is None:
            messages.error(request, "شماره موبایل متخصص معتبر نیست.")
            return redirect(self.team_url(salon))

        with transaction.atomic():
            salon = self.locked_owned_salon(request, salon)
            account = CustomUser.objects.filter(mobile_number=phone).first()
            stylist = Stylist.objects.filter(user_id=account.pk).first() if account else None
            exists = SalonMembership.objects.filter(salon_id=salon.pk).filter(
                Q(invited_phone=phone) | Q(stylist_id=stylist.pk)
            ) if stylist else SalonMembership.objects.filter(salon_id=salon.pk, invited_phone=phone)
            if exists.exists() or (stylist and salon.stylists.filter(pk=stylist.pk).exists()):
                # Do not silently reset ACTIVE, PENDING, PAUSED or ENDED records.
                messages.warning(request, "برای این شماره در این سالن سابقه همکاری یا دعوت وجود دارد؛ وضعیت آن را بررسی کنید.")
                return redirect(self.team_url(salon))

            membership = SalonMembership.objects.create(
                salon=salon,
                stylist=stylist,
                invited_phone=phone,
                invited_email=(account.email or "")[:254] if account else "",
                role_title=(request.POST.get("role_title") or "").strip()[:128],
                status=SalonMembershipStatus.INVITED,
                invited_by=request.user,
                expires_at=default_invite_expiry(),
                metadata={
                    "invited_by_manager": True,
                    "invitee_name": (request.POST.get("invitee_name") or "").strip()[:160],
                    "invite_message": (request.POST.get("invite_message") or "").strip()[:500],
                    "manager_invited_at": timezone.now().isoformat(),
                },
            )
            log_membership_event(
                membership,
                event_type="manager_invited_stylist",
                actor=request.user,
                new_status=SalonMembershipStatus.INVITED,
                metadata={"source": "multirole_manager_team"},
            )
            if stylist is not None:
                member_id = membership.pk
                actor_id = request.user.pk

                def notify_after_commit():
                    try:
                        from .views import _notify_stylist_about_manager_invite
                        from apps.accounts.models import CustomUser
                        from apps.salons.models import SalonMembership

                        row = SalonMembership.objects.select_related("salon", "stylist__user").get(pk=member_id)
                        _notify_stylist_about_manager_invite(
                            membership=row, actor=CustomUser.objects.get(pk=actor_id)
                        )
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify stylist of scoped invitation id=%s", member_id
                        )

                transaction.on_commit(notify_after_commit)

        messages.success(request, "دعوت همکاری برای این سالن ثبت شد؛ فعال‌سازی عضویت نیازمند پذیرش متخصص است.")
        return redirect(self.team_url(salon))


class ScopedManagerTeamInviteCancelView(_ScopedManagerTeamFormMixin, LoginRequiredMixin, View):
    """Cancel only an invitation in the explicitly authorized URL salon."""

    http_method_names = ["post"]

    def post(self, request, salon_id, membership_id):
        import logging

        from django.contrib import messages
        from django.db import transaction
        from django.shortcuts import get_object_or_404, redirect

        from apps.salons.membership import change_membership_status, log_membership_event
        from apps.salons.models import SalonMembership, SalonMembershipStatus

        salon = self.owned_salon(request, salon_id)
        self.require_form_target(request, salon)
        with transaction.atomic():
            salon = self.locked_owned_salon(request, salon)
            membership = get_object_or_404(
                SalonMembership.objects.select_for_update().select_related("salon", "stylist__user"),
                pk=membership_id,
                salon_id=salon.pk,
                status=SalonMembershipStatus.INVITED,
            )
            change_membership_status(
                membership=membership,
                new_status=SalonMembershipStatus.CANCELLED_BY_SALON,
                actor=request.user,
                reason="لغو دعوت همکاری توسط مدیر سالن",
                request=request,
            )
            log_membership_event(
                membership,
                event_type="manager_invite_cancelled",
                actor=request.user,
                old_status=SalonMembershipStatus.INVITED,
                new_status=SalonMembershipStatus.CANCELLED_BY_SALON,
                metadata={"source": "multirole_manager_team"},
            )
            if membership.stylist_id:
                member_id = membership.pk
                actor_id = request.user.pk

                def notify_after_commit():
                    try:
                        from django.urls import reverse
                        from apps.accounts.models import CustomUser
                        from apps.notifications.models import (
                            NotificationAudienceRole, NotificationCategory,
                            NotificationChannel, NotificationPriority,
                        )
                        from apps.notifications.services import create_notification
                        from apps.salons.models import SalonMembership

                        row = SalonMembership.objects.select_related("salon", "stylist__user").get(pk=member_id)
                        create_notification(
                            event_type="manager_invite_cancelled",
                            category=NotificationCategory.STAFF,
                            priority=NotificationPriority.NORMAL,
                            title="دعوت همکاری لغو شد",
                            body=f"دعوت همکاری {row.salon.salon_name} لغو شد.",
                            action_url=reverse("dashboards:stylist_profile"),
                            icon="fa-solid fa-ban",
                            recipients=[{
                                "user": row.stylist.user,
                                "audience_role": NotificationAudienceRole.STYLIST,
                                "channels": [NotificationChannel.DASHBOARD],
                            }],
                            actor=CustomUser.objects.get(pk=actor_id),
                            salon=row.salon,
                            related_object=row,
                            metadata={"membership_id": row.pk},
                            dedupe_key=f"manager_invite_cancelled:{row.pk}",
                        )
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "Failed to notify stylist of scoped cancelled invite id=%s", member_id
                        )

                transaction.on_commit(notify_after_commit)

        messages.success(request, "دعوت همکاری این سالن لغو شد.")
        return redirect(self.team_url(salon))


class ScopedManagerTeamMemberEditView(_ScopedManagerTeamFormMixin, LoginRequiredMixin, View):
    """Edit only the *salon-local* job title of an accepted team member.

    Global Stylist/User fields, membership status, visibility, services,
    schedules, and staff permissions are deliberately not editable here.
    Each write verifies both immutable form salon and live ownership under
    a transaction; a workspace switch in another tab cannot retarget it.
    """

    http_method_names = ["get", "post"]
    template_name = "dashboards/multirole_manager_team_member_form.html"

    @staticmethod
    def role_form(*args, **kwargs):
        from django import forms

        class RoleTitleForm(forms.Form):
            role_title = forms.CharField(
                max_length=128, strip=True,
                label="عنوان همکاری در همین سالن",
            )

        return RoleTitleForm(*args, **kwargs)

    @staticmethod
    def owned_active_membership(salon, membership_id, *, for_update=False):
        from django.shortcuts import get_object_or_404
        from apps.salons.models import SalonMembership, SalonMembershipStatus

        # Do not join the nullable stylist FK in a SELECT FOR UPDATE query:
        # PostgreSQL rejects locking the nullable side of an outer join.
        queryset = (SalonMembership.objects.select_for_update() if for_update
                    else SalonMembership.objects.select_related("stylist__user"))
        return get_object_or_404(
            queryset,
            pk=membership_id,
            salon_id=salon.pk,
            status=SalonMembershipStatus.ACTIVE,
            stylist__isnull=False,
        )

    def render_editor(self, request, salon, membership, form):
        return render(request, self.template_name, {
            "salon": salon, "membership": membership, "form": form,
        })

    def get(self, request, salon_id, membership_id):
        salon = self.owned_salon(request, salon_id)
        membership = self.owned_active_membership(salon, membership_id)
        form = self.role_form(initial={"role_title": membership.role_title})
        return self.render_editor(request, salon, membership, form)

    def post(self, request, salon_id, membership_id):
        from django.contrib import messages
        from django.db import transaction
        from django.shortcuts import redirect
        from apps.salons.membership import log_membership_event

        salon = self.owned_salon(request, salon_id)
        self.require_form_target(request, salon)
        form = self.role_form(request.POST)
        with transaction.atomic():
            salon = self.locked_owned_salon(request, salon)
            membership = self.owned_active_membership(
                salon, membership_id, for_update=True,
            )
            if form.is_valid():
                title = form.cleaned_data["role_title"]
                if title != membership.role_title:
                    previous = membership.role_title
                    membership.role_title = title
                    membership.save(update_fields=["role_title", "updated_at"])
                    log_membership_event(
                        membership,
                        event_type="manager_member_role_title_updated",
                        actor=request.user,
                        metadata={"previous_role_title": previous, "new_role_title": title},
                    )
                messages.success(request, "عنوان همکاری این متخصص در همین سالن ذخیره شد.")
                return redirect(self.team_url(salon))
        return self.render_editor(request, salon, membership, form)
