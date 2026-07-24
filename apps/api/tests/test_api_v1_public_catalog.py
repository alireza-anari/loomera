from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ApiV1PublicCatalogTests(Stage1DomainFactoryMixin, TestCase):
    def test_public_salon_list_hides_inactive_salons_and_private_values(self):
        manager = self.make_salon_manager(
            user_kwargs={
                "mobile_number": "09121110001",
                "email": "manager-private@example.com",
            }
        )
        active_salon = self.make_salon(
            manager=manager,
            salon_name="سالن فعال API",
            payout_iban="IR000000000000000000000000",
            payout_contact_mobile="09129999999",
        )
        self.make_salon(
            manager=manager,
            salon_name="سالن غیرفعال API",
            is_active=False,
        )

        response = self.client.get(reverse("api:v1:public_salon_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        salon_ids = {item["id"] for item in payload["data"]}
        self.assertIn(active_salon.pk, salon_ids)

        body = response.content.decode("utf-8")
        self.assertIn("سالن فعال API", body)
        self.assertNotIn("سالن غیرفعال API", body)
        self.assertNotIn("09121110001", body)
        self.assertNotIn("manager-private@example.com", body)
        self.assertNotIn("IR000000000000000000000000", body)
        self.assertNotIn("09129999999", body)
        self.assertNotIn("payout_iban", body)
        self.assertNotIn("payout_contact_mobile", body)

    def test_public_salon_detail_returns_404_for_inactive_salon(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(
            manager=manager,
            salon_name="سالن مخفی API",
            is_active=False,
        )

        response = self.client.get(
            reverse("api:v1:public_salon_detail", kwargs={"salon_slug": salon.slug})
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "salon_not_found")

    def test_public_salon_services_return_only_active_attached_services(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        public_service = self.make_service(name="پاکسازی پوست", is_active=True)
        inactive_service = self.make_service(name="خدمت غیرفعال", is_active=False)
        foreign_service = self.make_service(name="خدمت سالن دیگر", is_active=True)

        salon.services.add(public_service, inactive_service)

        response = self.client.get(
            reverse("api:v1:public_salon_services", kwargs={"salon_slug": salon.slug})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        service_ids = {item["id"] for item in payload["data"]}

        self.assertIn(public_service.pk, service_ids)
        self.assertNotIn(inactive_service.pk, service_ids)
        self.assertNotIn(foreign_service.pk, service_ids)

    def test_public_service_catalog_hides_inactive_and_non_catalog_services(self):
        public_service = self.make_service(
            name="اصلاح صورت",
            is_active=True,
            is_platform_catalog=True,
        )
        inactive_service = self.make_service(
            name="خدمت غیرفعال",
            is_active=False,
            is_platform_catalog=True,
        )
        private_service = self.make_service(
            name="خدمت اختصاصی سالن",
            is_active=True,
            is_platform_catalog=False,
        )

        response = self.client.get(reverse("api:v1:public_service_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        service_ids = {item["id"] for item in payload["data"]}

        self.assertIn(public_service.pk, service_ids)
        self.assertNotIn(inactive_service.pk, service_ids)
        self.assertNotIn(private_service.pk, service_ids)

    def test_public_salon_stylists_hide_private_inactive_and_foreign_stylists(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        visible_stylist = self.make_stylist(
            user_kwargs={
                "mobile_number": "09125550001",
                "email": "stylist-private@example.com",
                "name": "متخصص",
                "family": "نمایان",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        hidden_stylist = self.make_stylist(
            user_kwargs={
                "mobile_number": "09125550002",
                "email": "hidden-stylist@example.com",
                "name": "متخصص",
                "family": "مخفی",
            },
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        inactive_stylist = self.make_stylist(
            user_kwargs={
                "mobile_number": "09125550003",
                "email": "inactive-stylist@example.com",
                "name": "متخصص",
                "family": "غیرفعال",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        inactive_stylist.is_active = False
        inactive_stylist.save(update_fields=["is_active"])
        foreign_stylist = self.make_stylist(
            user_kwargs={
                "mobile_number": "09125550004",
                "email": "foreign-stylist@example.com",
                "name": "متخصص",
                "family": "دیگر",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )

        salon.stylists.add(visible_stylist, hidden_stylist, inactive_stylist)

        response = self.client.get(
            reverse("api:v1:public_salon_stylists", kwargs={"salon_slug": salon.slug})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        stylist_ids = {item["id"] for item in payload["data"]}

        self.assertIn(visible_stylist.pk, stylist_ids)
        self.assertNotIn(hidden_stylist.pk, stylist_ids)
        self.assertNotIn(inactive_stylist.pk, stylist_ids)
        self.assertNotIn(foreign_stylist.pk, stylist_ids)

        body = response.content.decode("utf-8")
        self.assertNotIn("09125550001", body)
        self.assertNotIn("stylist-private@example.com", body)
        self.assertNotIn("09125550002", body)
        self.assertNotIn("hidden-stylist@example.com", body)
        self.assertNotIn("09125550003", body)
        self.assertNotIn("inactive-stylist@example.com", body)

    @override_settings(LOOMERA_API_PUBLIC_QUERY_MAX_CHARS=12)
    def test_public_catalog_rejects_large_query_string(self):
        response = self.client.get(
            reverse("api:v1:public_salon_list"),
            data={"q": "x" * 50},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "query_too_large")

    def test_public_salon_list_pagination_is_bounded(self):
        manager = self.make_salon_manager()
        for index in range(3):
            self.make_salon(manager=manager, salon_name=f"سالن صفحه {index}")

        response = self.client.get(
            reverse("api:v1:public_salon_list"),
            data={"limit": "2", "offset": "0"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(len(payload["data"]), 2)
        self.assertEqual(payload["meta"]["pagination"]["limit"], 2)
        self.assertEqual(payload["meta"]["pagination"]["offset"], 0)
        self.assertEqual(payload["meta"]["pagination"]["total"], 3)
        self.assertTrue(payload["meta"]["pagination"]["has_next"])
