from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin


class CustomerSearchSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def test_customers_search_requires_login(self):
        response = self.client.get(reverse("search:customers_search"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_customers_search_forbids_non_manager_user(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.get(reverse("search:customers_search"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_customers_search_returns_only_manager_salon_customers(self):
        manager = self.make_salon_manager()
        other_manager = self.make_salon_manager()

        salon = self.make_salon(manager=manager)
        other_salon = self.make_salon(manager=other_manager)

        own_customer = self.make_customer(
            user_kwargs={
                "name": "Own",
                "family": "Customer",
                "mobile_number": "09120000001",
                "email": "own@example.com",
            },
            added_by_salon=salon,
        )
        other_customer = self.make_customer(
            user_kwargs={
                "name": "Other",
                "family": "Customer",
                "mobile_number": "09120000002",
                "email": "other@example.com",
            },
            added_by_salon=other_salon,
        )

        self.client.force_login(manager.user)
        response = self.client.get(reverse("search:customers_search"), {"q": "Customer"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        customer_ids = {item["id"] for item in payload["customers"]}

        self.assertIn(own_customer.user_id, customer_ids)
        self.assertNotIn(other_customer.user_id, customer_ids)

    def test_customers_search_forbids_foreign_salon_id(self):
        manager = self.make_salon_manager()
        other_manager = self.make_salon_manager()

        self.make_salon(manager=manager)
        other_salon = self.make_salon(manager=other_manager)

        self.client.force_login(manager.user)
        response = self.client.get(
            reverse("search:customers_search"),
            {"salon_id": str(other_salon.pk)},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_filter_customers_requires_manager_before_mutating_session(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.post(
            reverse("search:filter_customers"),
            {
                "sort_by": "oldest",
                "client_group": "all",
                "gender": "all",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("customer_filters", self.client.session)

    def test_filter_customers_ajax_returns_only_manager_salon_customers(self):
        manager = self.make_salon_manager()
        other_manager = self.make_salon_manager()

        salon = self.make_salon(manager=manager)
        other_salon = self.make_salon(manager=other_manager)

        own_customer = self.make_customer(
            user_kwargs={
                "name": "Own",
                "family": "Client",
                "mobile_number": "09120000003",
                "email": "own-client@example.com",
            },
            added_by_salon=salon,
        )
        other_customer = self.make_customer(
            user_kwargs={
                "name": "Other",
                "family": "Client",
                "mobile_number": "09120000004",
                "email": "other-client@example.com",
            },
            added_by_salon=other_salon,
        )

        self.client.force_login(manager.user)
        response = self.client.post(
            reverse("search:filter_customers"),
            {
                "sort_by": "newest",
                "client_group": "all",
                "gender": "all",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        customer_ids = {item["id"] for item in payload["customers"]}

        self.assertIn(own_customer.user_id, customer_ids)
        self.assertNotIn(other_customer.user_id, customer_ids)