"""Fail-closed cancellation of one future, unpaid, manual salon appointment.

Other booking kinds, paid orders, and multi-item orders retain their existing
cancellation/financial flows. A workspace preference never authorizes a write.
"""
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from apps.accounts.services.access import resolve_manager_salon
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.dashboards.appointment_management import (
    apply_partner_appointment_action,
    get_allowed_partner_actions,
)


def can_cancel_scoped_manual_booking(order, appointment, *, item_count=None):
    """Extra restrictions for this narrow action, plus existing lifecycle rules."""
    if (
        order.salon_id != appointment.salon_id
        or order.booking_source != "dashboard_manual"
        or order.status != "confirmed"
        or not order.is_finally
        or order.is_paid
        or order.selected_payment_method != "pay_in_salon"
        or appointment.confirmation_status != OrderDetail.ConfirmationStatus.CONFIRMED
        or appointment.lifecycle_status != OrderDetail.ServiceLifecycleStatus.CONFIRMED
        or not appointment.date
        or not appointment.time
    ):
        return False
    if item_count is None:
        item_count = order.order_details1.count()
    if item_count != 1:
        return False
    starts_at = timezone.make_aware(
        datetime.combine(appointment.date, appointment.time),
        timezone.get_current_timezone(),
    )
    if starts_at <= timezone.now():
        return False
    return "cancel" in get_allowed_partner_actions(order, appointment)


class ScopedManagerManualBookingCancelView(LoginRequiredMixin, View):
    """URL salon + appointment + POST targets must agree on every mutation."""

    http_method_names = ["get", "post"]
    template_name = "dashboards/multirole_manager_manual_booking_cancel.html"

    @staticmethod
    def owned_detail(request, salon_id, appointment_id):
        salon = resolve_manager_salon(request.user, salon_id)
        detail = get_object_or_404(
            OrderDetail.objects.select_related("order", "service"),
            pk=appointment_id, salon_id=salon.pk, order__salon_id=salon.pk,
        )
        return salon, detail

    def get(self, request, salon_id, appointment_id):
        salon, detail = self.owned_detail(request, salon_id, appointment_id)
        if not can_cancel_scoped_manual_booking(detail.order, detail):
            raise PermissionDenied("این رزرو از این مسیر قابل لغو نیست.")
        return render(request, self.template_name, {
            "salon": salon, "booking": detail,
        })

    def post(self, request, salon_id, appointment_id):
        salon, detail = self.owned_detail(request, salon_id, appointment_id)
        if (
            request.POST.get("salon_id") != str(salon.pk)
            or request.POST.get("appointment_id") != str(detail.pk)
        ):
            raise PermissionDenied("شناسه رزرو و سالن با درخواست مطابقت ندارند.")

        with transaction.atomic():
            # The same lock order as scoped booking creation: salon, then order.
            salon = get_object_or_404(
                Salon.objects.select_for_update(),
                pk=salon.pk, salon_manager__user_id=request.user.pk,
            )
            order = get_object_or_404(
                Order.objects.select_for_update(),
                pk=detail.order_id, salon_id=salon.pk,
            )
            detail = get_object_or_404(
                OrderDetail.objects.select_for_update(),
                pk=detail.pk, salon_id=salon.pk, order_id=order.pk,
            )
            if not can_cancel_scoped_manual_booking(order, detail):
                raise PermissionDenied("این رزرو دیگر قابل لغو نیست.")
            # Reuse existing cancellation + settlement + notification semantics;
            # never implement financial reversals directly in a manager view.
            message = apply_partner_appointment_action(
                order, detail, "cancel", actor=request.user,
            )

        messages.success(request, message)
        return redirect(
            "dashboards:multirole_manager_salon_bookings", salon_id=salon.pk,
        )
