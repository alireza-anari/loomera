"""An explicitly salon-scoped manual booking path for multi-salon managers.

Do not route multi-salon users through the legacy manager dashboard shell: it
may select their first salon rather than the salon that owns this form.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.services.access import resolve_manager_salon
from apps.dashboards.forms import DashboardManualBookingForm
from apps.orders.booking_utils import bookable_stylists_for_salon
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus


class ScopedManagerManualBookingForm(DashboardManualBookingForm):
    """Reuse canonical schedule/price/slot validation, minus stale members."""

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, salon=salon, **kwargs)
        self.fields["stylist"].queryset = bookable_stylists_for_salon(
            salon=salon,
        ).order_by("user__name", "user__family", "pk")


class ScopedManagerManualBookingView(LoginRequiredMixin, View):
    """A submitted form always targets its own URL salon, never session state."""

    http_method_names = ["get", "post"]
    template_name = "dashboards/multirole_manager_manual_booking.html"

    def render_form(self, request, salon, form):
        return render(request, self.template_name, {"salon": salon, "form": form})

    def get(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        return self.render_form(request, salon, ScopedManagerManualBookingForm(salon=salon))

    def post(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        if request.POST.get("salon_id") != str(salon.pk):
            raise PermissionDenied("سالن رزرو با سالن انتخاب‌شده مطابقت ندارد.")

        # Serialize scoped dashboard bookings for this salon, and recheck live
        # ownership, membership, and availability before writing an Order.
        with transaction.atomic():
            salon = get_object_or_404(
                Salon.objects.select_for_update(),
                pk=salon.pk, salon_manager__user_id=request.user.pk,
            )
            form = ScopedManagerManualBookingForm(request.POST, salon=salon)
            if not form.is_valid():
                return self.render_form(request, salon, form)

            cd = form.cleaned_data
            # An ACTIVE membership is required when a membership exists; a
            # legacy salon/stylist pair with no membership retains PR119's
            # compatibility behavior. Lock the existing relationship so a
            # concurrent status update cannot turn a paused member bookable.
            membership = SalonMembership.objects.select_for_update().filter(
                salon_id=salon.pk, stylist_id=cd["stylist"].pk,
            ).first()
            if membership is not None and membership.status != SalonMembershipStatus.ACTIVE:
                form.add_error("stylist", "این متخصص در حال حاضر عضو فعال این سالن نیست.")
                return self.render_form(request, salon, form)

            # The existing manager manual-booking path uses the same confirmed
            # pay-at-salon order/appointment fields and settlement sync.
            price = int(cd["resolved_price"] or 0)
            order = Order.objects.create(
                customer=cd["customer"], salon=salon,
                status="confirmed", is_finally=True, is_paid=False,
                selected_payment_method="pay_in_salon",
                requires_online_payment=False,
                subtotal_amount=price, discount_amount=0,
                basket_discount_amount=0, coupon_discount_amount=0,
                basket_discount_percent=0, basket_discount_title="",
                tax_amount=0, total_amount=price, coupon_code="", discount=0,
                platform_commission_applies=False,
                platform_commission_percent=0, platform_commission_amount=0,
                salon_payout_amount=price, checkout_locked_at=timezone.now(),
                description=(cd.get("notes") or "").strip(),
                booking_source="dashboard_manual",
            )
            OrderDetail.objects.create(
                order=order, service=cd["service"], stylist=cd["stylist"],
                salon=salon, price=price, date=cd["appointment_date"],
                time=cd["start_time"], end_time=cd["resolved_end_time"],
                confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
                lifecycle_status=OrderDetail.ServiceLifecycleStatus.CONFIRMED,
                stylist_confirmed_at=timezone.now(),
            )
            order.refresh_lifecycle_from_details()
            from apps.payments.finance import sync_settlement_for_order

            sync_settlement_for_order(order)

        messages.success(request, "رزرو دستی همین سالن ثبت شد؛ پرداخت در سالن انجام می‌شود.")
        return redirect(
            "dashboards:multirole_manager_salon_bookings", salon_id=salon.pk,
        )
