"""An authenticated multi-salon manager must name an authorized customer scope.

These legacy search endpoints live outside the dashboards guard and can return
customer phone/email data; they must never silently fall back to salon #1.
"""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiSalonCustomerSearchScopeTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        manager = SalonManager.objects.create(user=self.user)
        self.a = self.make_salon(manager=manager)
        self.b = self.make_salon(manager=manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.customer_a = self.make_customer(added_by_salon=self.a)
        self.customer_b = self.make_customer(added_by_salon=self.b)
        self.customer_foreign = self.make_customer(added_by_salon=self.foreign)
        self.search_url = reverse("search:customers_search")
        self.filter_url = reverse("search:filter_customers")
        self.client.force_login(self.user)

    def test_multi_salon_search_without_explicit_target_fails_closed(self):
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_explicit_search_targets_only_selected_owned_salon(self):
        response = self.client.get(self.search_url, {"salon_id": str(self.b.pk)})
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["customers"]}
        self.assertIn(self.customer_b.user_id, ids)
        self.assertNotIn(self.customer_a.user_id, ids)
        self.assertNotIn(self.customer_foreign.user_id, ids)

    def test_unscoped_filter_does_not_change_session(self):
        response = self.client.post(self.filter_url, {"sort_by": "oldest"},
                                    HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("customer_filters", self.client.session)

    def test_explicit_filter_scopes_results_and_only_writes_own_filter_state(self):
        response = self.client.post(
            self.filter_url,
            {"salon_id": str(self.b.pk), "sort_by": "newest"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["customers"]}
        self.assertIn(self.customer_b.user_id, ids)
        self.assertNotIn(self.customer_a.user_id, ids)
        self.assertNotIn(self.customer_foreign.user_id, ids)

    def test_mismatched_query_and_form_target_is_rejected_without_session_change(self):
        response = self.client.post(
            f"{self.filter_url}?salon_id={self.a.pk}",
            {"salon_id": str(self.b.pk), "sort_by": "oldest"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("customer_filters", self.client.session)

    def test_invalid_and_foreign_targets_fail_closed(self):
        for target in ("invalid", "0", "01", str(self.foreign.pk)):
            with self.subTest(target=target):
                self.assertEqual(
                    self.client.get(self.search_url, {"salon_id": target}).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.post(self.filter_url, {"salon_id": target}).status_code,
                    403,
                )

    def test_revoked_ownership_is_not_restored_by_explicit_target(self):
        self.b.salon_manager = self.make_salon_manager()
        self.b.save(update_fields=["salon_manager"])
        self.assertEqual(
            self.client.get(self.search_url, {"salon_id": str(self.b.pk)}).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(self.filter_url, {"salon_id": str(self.b.pk)}).status_code,
            403,
        )

    def test_single_salon_legacy_search_still_works_without_target(self):
        self.b.salon_manager = self.make_salon_manager()
        self.b.save(update_fields=["salon_manager"])
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["customers"]}
        self.assertIn(self.customer_a.user_id, ids)
        self.assertNotIn(self.customer_b.user_id, ids)
