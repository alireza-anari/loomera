from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager
from apps.orders.models import Order
from apps.payments.models import SalonSettlement
from apps.salons.models import Salon


class FinanceReportExportSecurityTests(TestCase):
    def _user(
    self,
    *,
    mobile,
    name="کاربر",
    family="تست",
    is_staff=False,
    is_superuser=False,
    ):
        user = CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

        if is_staff or is_superuser:
            if hasattr(user, "is_admin"):
                user.is_admin = True

            if is_superuser:
                try:
                    user.is_superuser = True
                except AttributeError:
                    pass

            user.save()

        return user

    def _customer(self, *, mobile="09130000001"):
        return Customer.objects.create(
            user=self._user(mobile=mobile, name="مشتری", family="تست")
        )

    def _manager(self, *, mobile):
        return SalonManager.objects.create(
            user=self._user(mobile=mobile, name="مدیر", family="سالن"),
            is_active=True,
        )

    def _salon(self, *, mobile, name):
        return Salon.objects.create(
            salon_name=name,
            salon_manager=self._manager(mobile=mobile),
            is_active=True,
            address="تهران",
        )

    def _settlement(
        self,
        *,
        salon,
        customer=None,
        payment_method="online",
        payout_state=SalonSettlement.PayoutState.READY,
        total_amount=100000,
    ):
        customer = customer or self._customer()
        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="paid",
            is_finally=True,
            is_paid=True,
            selected_payment_method=payment_method,
            total_amount=total_amount,
            register_date=timezone.localdate(),
        )
        settlement = SalonSettlement.objects.create(
            order=order,
            salon=salon,
            customer=customer,
            payment_method=payment_method,
            payout_state=payout_state,
            gross_services_amount=total_amount,
            paid_amount=total_amount,
            net_amount_due_to_salon=total_amount,
        )
        return settlement

    def test_salon_finance_export_is_scoped_to_manager_salon(self):
        own_salon = self._salon(mobile="09130000101", name="سالن خودی")
        foreign_salon = self._salon(mobile="09130000102", name="سالن دیگر")

        own_settlement = self._settlement(salon=own_salon)
        foreign_settlement = self._settlement(
            salon=foreign_salon,
            customer=self._customer(mobile="09130000103"),
        )

        self.client.force_login(own_salon.salon_manager.user)

        response = self.client.get(reverse("dashboards:finance_reports_export"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="ignore")

        self.assertIn(own_settlement.order.order_number, body)
        self.assertNotIn(foreign_settlement.order.order_number, body)

    def test_salon_finance_export_ignores_invalid_filter_values(self):
        salon = self._salon(mobile="09130000104", name="سالن تست")
        settlement = self._settlement(salon=salon)

        self.client.force_login(salon.salon_manager.user)

        response = self.client.get(
            reverse("dashboards:finance_reports_export"),
            data={
                "payment_method": "bad-method",
                "payout_state": "bad-state",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="ignore")
        self.assertIn(settlement.order.order_number, body)

    @override_settings(FINANCE_REPORT_QUERY_MAX_CHARS=20)
    def test_salon_finance_export_rejects_large_query_string(self):
        salon = self._salon(mobile="09130000105", name="سالن تست")
        self.client.force_login(salon.salon_manager.user)

        response = self.client.get(
            reverse("dashboards:finance_reports_export"),
            data={"x": "a" * 100},
        )

        self.assertEqual(response.status_code, 400)

    def test_platform_finance_export_requires_staff(self):
        salon = self._salon(mobile="09130000106", name="سالن تست")
        self.client.force_login(salon.salon_manager.user)

        response = self.client.get(reverse("dashboards:platform_finance_export"))

        self.assertEqual(response.status_code, 302)

    def test_platform_finance_export_escapes_formula_like_cells(self):
        staff_user = self._user(
            mobile="09130000107",
            name="ادمین",
            family="تست",
            is_staff=True,
        )
        salon = self._salon(mobile="09130000108", name="=HYPERLINK")
        settlement = self._settlement(salon=salon)

        self.client.force_login(staff_user)

        response = self.client.get(reverse("dashboards:platform_finance_export"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8-sig", errors="ignore")

        self.assertIn("'=HYPERLINK", body)
        self.assertIn(settlement.order.order_number, body)