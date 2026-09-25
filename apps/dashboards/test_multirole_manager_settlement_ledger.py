"""Read-only settlement ledger is always scoped to the explicitly owned salon."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.payments.models import SalonSettlement, SalonWallet, SalonWalletTransaction
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerSettlementLedgerTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user)
        self.a = self.make_salon(manager=self.manager)
        self.b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.customer = self.make_customer()
        self.a_settlement = self.settlement(self.a, 731001)
        self.b_settlement = self.settlement(self.b, 842002)
        self.foreign_settlement = self.settlement(self.foreign, 953003)
        self.client.force_login(self.user)

    def settlement(self, salon, gross):
        return SalonSettlement.objects.create(
            salon=salon,
            order=self.make_order(customer=self.customer, salon=salon),
            customer=self.customer,
            gross_services_amount=gross,
            net_amount_due_to_salon=gross,
            payout_state=SalonSettlement.PayoutState.READY,
        )

    def url(self, salon):
        return reverse(
            "dashboards:multirole_manager_salon_settlements",
            kwargs={"salon_id": salon.pk},
        )

    def test_only_target_salon_settlements_are_rendered(self):
        response = self.client.get(self.url(self.b))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.b.salon_name)
        self.assertContains(response, "842002")
        self.assertContains(response, "آماده تسویه")
        self.assertEqual(
            [item.pk for item in response.context["page_obj"].object_list],
            [self.b_settlement.pk],
        )
        self.assertEqual(response.context["salon"], self.b)
        # Owned salon A is navigation-only in the workspace switcher. Its ledger data stays out.
        self.assertContains(response, self.a.salon_name, count=1)
        for secret in (self.foreign.salon_name, "731001", "953003"):
            with self.subTest(secret=secret):
                self.assertNotContains(response, secret)

    def test_foreign_salon_and_revoked_ownership_are_denied(self):
        self.assertIn(self.client.get(self.url(self.foreign)).status_code, (403, 404))
        self.b.salon_manager = self.make_salon_manager()
        self.b.save(update_fields=["salon_manager"])
        self.assertIn(self.client.get(self.url(self.b)).status_code, (403, 404))

    def test_anonymous_and_customer_only_accounts_cannot_access(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url(self.a)).status_code, 302)
        self.client.force_login(self.make_user())
        self.assertIn(self.client.get(self.url(self.a)).status_code, (403, 404))

    def test_workspace_preference_cannot_retarget_salon(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.a.pk),
        })
        response = self.client.get(self.url(self.b))
        self.assertContains(response, "842002")
        self.assertNotContains(response, "731001")

    def test_get_is_non_mutating_and_post_is_disallowed(self):
        wa = SalonWallet.objects.create(
            salon=self.a, available_balance=100, pending_balance=200,
        )
        before_settlements = list(SalonSettlement.objects.values_list("pk", "payout_state"))
        self.assertEqual(self.client.get(self.url(self.a)).status_code, 200)
        self.assertEqual(
            self.client.post(self.url(self.a), {"payout_state": "paid", "salon_id": self.a.pk}).status_code,
            405,
        )
        wa.refresh_from_db()
        self.assertEqual((wa.available_balance, wa.pending_balance), (100, 200))
        self.assertEqual(SalonWalletTransaction.objects.count(), 0)
        self.assertEqual(
            list(SalonSettlement.objects.values_list("pk", "payout_state")),
            before_settlements,
        )

    def test_pagination_keeps_results_within_salon_and_order_stable(self):
        more = [self.settlement(self.b, 842100 + i) for i in range(20)]
        page1 = self.client.get(self.url(self.b))
        page2 = self.client.get(self.url(self.b), {"page": "2"})
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(page1.context["page_obj"].paginator.per_page, 20)
        self.assertEqual(len(page1.context["page_obj"].object_list), 20)
        self.assertEqual(len(page2.context["page_obj"].object_list), 1)
        self.assertEqual(page2.context["page_obj"].object_list[0].pk, self.b_settlement.pk)
        self.assertEqual(
            [s.pk for s in page1.context["page_obj"].object_list],
            [s.pk for s in reversed(more)],
        )
        self.assertNotContains(page1, "731001")
        self.assertNotContains(page2, "953003")

    def test_invalid_page_does_not_expand_scope_or_crash(self):
        for page in ("abc", "-1", "999999999999999999999999", "9" * 5000):
            with self.subTest(page=page):
                response = self.client.get(self.url(self.b), {"page": page})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [item.pk for item in response.context["page_obj"].object_list],
                    [self.b_settlement.pk],
                )
                self.assertNotContains(response, "953003")

    def test_legacy_finance_reports_stay_closed_for_multiple_salons(self):
        for name in ("dashboards:finance_reports", "dashboards:finance_reports_export"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
