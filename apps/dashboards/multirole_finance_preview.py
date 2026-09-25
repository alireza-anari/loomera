"""Non-mutating, salon-scoped finance preview for managers of several salons.

Keep the existing finance hub and all payout/withdrawal mutations behind the
legacy multi-salon guard until their scope and business rules are audited.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.shortcuts import render
from django.views import View

from apps.accounts.services.access import resolve_manager_salon
from apps.payments.models import SalonSettlement, SalonWallet


class ScopedManagerFinancePreviewView(LoginRequiredMixin, View):
    http_method_names = ["get"]
    template_name = "dashboards/multirole_manager_finance_preview.html"

    def get(self, request, salon_id):
        # Validate ownership from the URL on every request. A session-stored
        # workspace is neither a target nor permission to access financial data.
        salon = resolve_manager_salon(request.user, salon_id)
        wallet = SalonWallet.objects.filter(salon_id=salon.pk).first()
        summary = SalonSettlement.objects.filter(salon_id=salon.pk).aggregate(
            settlement_count=Count("pk"),
            recorded_gross=Sum("gross_services_amount"),
        )
        # Intentionally avoid get_or_create and finance-hub helper calls:
        # even a GET must not release funds or change historic financial state.
        return render(request, self.template_name, {
            "salon": salon,
            "wallet": wallet,
            "settlement_count": summary["settlement_count"],
            "recorded_gross": summary["recorded_gross"] or 0,
        })
