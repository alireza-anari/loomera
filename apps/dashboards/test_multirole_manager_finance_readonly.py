"""Finance preview must never read another salon or mutate money on GET."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.payments.models import SalonSettlement, SalonWallet, SalonWalletTransaction
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerFinanceReadOnlyTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        manager = SalonManager.objects.create(user=self.user)
        self.a = self.make_salon(manager=manager)
        self.b = self.make_salon(manager=manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.wa = SalonWallet.objects.create(
            salon=self.a, available_balance=412345, pending_balance=412346,
        )
        self.wb = SalonWallet.objects.create(
            salon=self.b, available_balance=523456, pending_balance=523457,
        )
        SalonWallet.objects.create(
            salon=self.foreign, available_balance=634567, pending_balance=634568,
        )
        for salon, gross in ((self.a, 11111), (self.b, 22222), (self.foreign, 33333)):
            customer = self.make_customer()
            order = self.make_order(customer=customer, salon=salon)
            SalonSettlement.objects.create(
                salon=salon, customer=customer, order=order,
                gross_services_amount=gross, net_amount_due_to_salon=gross,
            )
        self.client.force_login(self.user)

    def url(self, salon):
        return reverse(
            "dashboards:multirole_manager_salon_finance_preview",
            kwargs={"salon_id": salon.pk},
        )

    def test_each_owned_salon_shows_only_its_wallet_and_settlement(self):
        response = self.client.get(self.url(self.b))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.b.salon_name)
        self.assertContains(response, "523456")
        self.assertContains(response, "523457")
        self.assertContains(response, "22222")
        self.assertEqual(response.context["salon"], self.b)
        # The other owned salon is deliberately listed by the workspace switcher.
        # Its financial values must still never enter this salon-scoped preview.
        self.assertContains(response, self.a.salon_name, count=1)
        for forbidden in (
            self.foreign.salon_name,
            "412345", "412346", "11111", "634567", "634568", "33333",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotContains(response, forbidden)

    def test_missing_wallet_is_displayed_without_creating_a_new_one(self):
        empty_salon = self.make_salon(manager=self.a.salon_manager)
        before = SalonWallet.objects.count()
        response = self.client.get(self.url(empty_salon))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, empty_salon.salon_name)
        self.assertContains(response, "کیف پولی ثبت نشده است")
        self.assertEqual(SalonWallet.objects.count(), before)

    def test_preview_does_not_release_pending_funds_or_create_transactions(self):
        before = (self.wb.available_balance, self.wb.pending_balance)
        tx_before = SalonWalletTransaction.objects.count()
        response = self.client.get(self.url(self.b))
        self.assertEqual(response.status_code, 200)
        self.wb.refresh_from_db()
        self.assertEqual((self.wb.available_balance, self.wb.pending_balance), before)
        self.assertEqual(SalonWalletTransaction.objects.count(), tx_before)

    def test_foreign_salon_and_revoked_ownership_are_denied(self):
        self.assertIn(self.client.get(self.url(self.foreign)).status_code, (403, 404))
        self.assertEqual(self.client.get(self.url(self.a)).status_code, 200)
        self.a.salon_manager = self.make_salon_manager()
        self.a.save(update_fields=["salon_manager"])
        self.assertIn(self.client.get(self.url(self.a)).status_code, (403, 404))

    def test_workspace_switch_does_not_retarget_explicit_salon_url(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.a.pk),
        })
        response = self.client.get(self.url(self.b))
        self.assertContains(response, "523456")
        self.assertNotContains(response, "412345")

    def test_finance_preview_is_get_only_and_does_not_modify_wallet(self):
        before = (self.wb.available_balance, self.wb.pending_balance)
        self.assertEqual(self.client.post(self.url(self.b), {"amount": "99999"}).status_code, 405)
        self.wb.refresh_from_db()
        self.assertEqual((self.wb.available_balance, self.wb.pending_balance), before)

    def test_anonymous_and_customer_without_manager_cannot_read_finance(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url(self.a)).status_code, 302)
        self.client.force_login(self.make_user())
        self.assertIn(self.client.get(self.url(self.a)).status_code, (403, 404))

    def test_legacy_finance_hub_remains_closed_for_multi_salon_manager(self):
        url = reverse("dashboards:finance_hub")
        self.assertEqual(self.client.get(url).status_code, 403)
