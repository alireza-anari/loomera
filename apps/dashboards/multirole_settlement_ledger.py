"""GET-only settlement ledger for one explicitly authorized manager salon.

Do not call the legacy finance hub, payout routines or wallet helpers from here:
GET requests must neither create money records nor release pending balances.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views import View

from apps.accounts.services.access import resolve_manager_salon
from apps.payments.models import SalonSettlement


class ScopedManagerSettlementLedgerView(LoginRequiredMixin, View):
    http_method_names = ["get"]
    template_name = "dashboards/multirole_manager_settlement_ledger.html"
    page_size = 20

    def get(self, request, salon_id):
        # The URL identifies the resource; saved workspace and request query
        # parameters are never authorization or an alternative salon target.
        salon = resolve_manager_salon(request.user, salon_id)
        settlements = (
            SalonSettlement.objects.filter(salon_id=salon.pk)
            .only(
                "id", "created_at", "gross_services_amount",
                "net_amount_due_to_salon", "payout_state",
            )
            .order_by("-created_at", "-pk")
        )
        page_obj = Paginator(settlements, self.page_size).get_page(
            request.GET.get("page", "1")
        )
        return render(request, self.template_name, {
            "salon": salon,
            "page_obj": page_obj,
        })
