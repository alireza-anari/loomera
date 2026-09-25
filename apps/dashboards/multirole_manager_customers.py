"""Read-only customer index, explicitly scoped to a currently owned salon.

Legacy customer profile/note/add views lack an immutable salon target and are
blocked for multi-salon managers until they are separately migrated. No profile,
marketing preference, order or wallet is created by this GET endpoint.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.views import View

from apps.accounts.models import Customer
from apps.accounts.services.access import resolve_manager_salon
from apps.orders.models import OrderDetail


class ScopedManagerCustomersView(LoginRequiredMixin, View):
    http_method_names = ["get"]
    template_name = "dashboards/multirole_manager_customers.html"
    page_size = 20

    def get(self, request, salon_id):
        salon = resolve_manager_salon(request.user, salon_id)
        # Keep the existing manager-customer visibility contract: the customer
        # is either added by this salon or booked an OrderDetail in this salon.
        # A matching order in a different salon never makes them visible here.
        booked_customer_ids = OrderDetail.objects.filter(
            salon_id=salon.pk,
        ).values_list("order__customer_id", flat=True)
        customers = (
            Customer.objects.filter(
                Q(added_by_salon_id=salon.pk) | Q(pk__in=booked_customer_ids)
            )
            .select_related("user")
            .distinct()
            .order_by("user__name", "user__family", "pk")
        )
        page_obj = Paginator(customers, self.page_size).get_page(
            request.GET.get("page", "1")
        )
        return render(request, self.template_name, {
            "salon": salon,
            "page_obj": page_obj,
        })
