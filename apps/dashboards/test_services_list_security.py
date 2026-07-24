from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from tests_stage1_helpers import Stage1DomainFactoryMixin


class DashboardServicesListSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def test_services_list_requires_login(self):
        response = self.client.get(reverse("dashboards:services_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

    def test_services_list_rejects_post_method(self):
        manager = self.make_salon_manager()
        self.make_salon(manager=manager)

        self.client.force_login(manager.user)
        response = self.client.post(reverse("dashboards:services_list"))

        self.assertEqual(response.status_code, 405)

    def test_services_list_forbids_non_manager_user(self):
        customer = self.make_customer()
        self.client.force_login(customer.user)

        response = self.client.get(reverse("dashboards:services_list"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_services_list_returns_only_manager_owned_salon_services(self):
        manager = self.make_salon_manager()
        other_manager = self.make_salon_manager()

        salon = self.make_salon(manager=manager)
        other_salon = self.make_salon(manager=other_manager)

        own_service = self.make_service(name="خدمت سالن خودی")
        other_service = self.make_service(name="خدمت سالن دیگر")

        salon.services.add(own_service)
        other_salon.services.add(other_service)

        self.client.force_login(manager.user)
        response = self.client.get(
            reverse("dashboards:services_list"),
            {"salon_id": str(salon.pk)},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        service_ids = {item["id"] for item in payload["services"]}

        self.assertIn(own_service.pk, service_ids)
        self.assertNotIn(other_service.pk, service_ids)

    def test_services_list_forbids_foreign_salon_id(self):
        manager = self.make_salon_manager()
        other_manager = self.make_salon_manager()

        self.make_salon(manager=manager)
        other_salon = self.make_salon(manager=other_manager)

        self.client.force_login(manager.user)
        response = self.client.get(
            reverse("dashboards:services_list"),
            {"salon_id": str(other_salon.pk)},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_services_list_rejects_invalid_salon_id(self):
        manager = self.make_salon_manager()
        self.make_salon(manager=manager)

        self.client.force_login(manager.user)
        response = self.client.get(
            reverse("dashboards:services_list"),
            {"salon_id": "abc"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_salon_id")