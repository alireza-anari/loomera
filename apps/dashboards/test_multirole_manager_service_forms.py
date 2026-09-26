"""Multi-salon service changes are authorized by immutable route and form targets."""
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SalonManager
from apps.orders.models import OrderDetail
from apps.services.models import Services
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerServiceFormTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user)
        self.a = self.make_salon(manager=self.manager)
        self.b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.catalog = self.make_service(name="خدمت پایه", is_platform_catalog=True)
        self.client.force_login(self.user)

    def url(self, name, salon, **kwargs):
        return reverse(f"dashboards:{name}", kwargs={"salon_id": salon.pk, **kwargs})

    def payload(self, salon, **kwargs):
        data = {
            "salon_id": str(salon.pk),
            "catalog_service": str(self.catalog.pk),
            "duration_minutes": "40",
            "buffer_minutes": "10",
            "base_price": "250000",
            "description": "خدمت اختصاصی همین سالن",
        }
        data.update(kwargs)
        return data

    def create(self, salon):
        return self.client.post(
            self.url("multirole_manager_service_add", salon), self.payload(salon)
        )

    def private_service(self, salon):
        service = self.make_service(
            name="نسخه خصوصی", is_platform_catalog=False, catalog_source=self.catalog
        )
        salon.services.add(service)
        return service

    def test_add_form_renders_populated_visible_catalog_selector(self):
        response = self.client.get(
            self.url("multirole_manager_service_add", self.a)
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        field = form.fields["catalog_service"]
        self.assertTrue(field.queryset.filter(pk=self.catalog.pk).exists())
        self.assertNotIn("hidden", (field.widget.attrs.get("class") or "").split())
        self.assertNotEqual(field.widget.attrs.get("aria-hidden"), "true")
        self.assertNotEqual(field.widget.attrs.get("tabindex"), "-1")
        self.assertContains(
            response, f'<option value="{self.catalog.pk}">', html=False
        )
        self.assertContains(response, self.catalog.service_name)

    def test_creation_for_b_does_not_attach_or_change_a_or_catalog(self):
        response = self.create(self.b)
        self.assertRedirects(
            response, self.url("multirole_manager_salon_services", self.b),
            fetch_redirect_response=False,
        )
        new = Services.objects.get(catalog_source=self.catalog, services_of_salon=self.b)
        self.assertFalse(new.is_platform_catalog)
        self.assertEqual(new.base_price, 250000)
        self.assertEqual(new.duration_minutes, 40)
        self.assertFalse(new.services_of_salon.filter(pk=self.a.pk).exists())
        self.catalog.refresh_from_db()
        self.assertTrue(self.catalog.is_platform_catalog)
        self.assertEqual(self.catalog.base_price, 120000)

    def test_create_requires_owned_route_and_matching_form_salon(self):
        url = self.url("multirole_manager_service_add", self.a)
        for endpoint, data in (
            (url, self.payload(self.b)),
            (url, self.payload(self.a, salon_id="")),
            (self.url("multirole_manager_service_add", self.foreign), self.payload(self.foreign)),
        ):
            with self.subTest(endpoint=endpoint, data=data):
                self.assertIn(self.client.post(endpoint, data).status_code, (403, 404))
        self.assertFalse(Services.objects.filter(catalog_source=self.catalog).exists())

    def test_invalid_catalog_and_repeated_submission_do_not_create_duplicates(self):
        private = self.private_service(self.a)
        response = self.client.post(
            self.url("multirole_manager_service_add", self.b),
            self.payload(self.b, catalog_service=str(private.pk)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Services.objects.filter(catalog_source=private).exists())
        self.assertEqual(self.create(self.b).status_code, 302)
        repeat = self.create(self.b)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(Services.objects.filter(catalog_source=self.catalog, services_of_salon=self.b).count(), 1)

    def test_create_rejects_member_of_other_salon_and_does_not_assign_them(self):
        other_member = self.make_stylist()
        self.b.stylists.add(other_member)
        response = self.client.post(
            self.url("multirole_manager_service_add", self.a),
            self.payload(self.a, stylists=[str(other_member.pk)]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Services.objects.filter(catalog_source=self.catalog).exists())

    def test_edit_b_is_independent_of_a_and_does_not_mutate_catalog(self):
        service_a = self.private_service(self.a)
        service_b = self.private_service(self.b)
        url = self.url("multirole_manager_service_edit", self.b, service_id=service_b.pk)
        response = self.client.post(url, self.payload(self.b, base_price="390000"))
        self.assertRedirects(
            response, self.url("multirole_manager_salon_services", self.b),
            fetch_redirect_response=False,
        )
        service_a.refresh_from_db()
        service_b.refresh_from_db()
        self.catalog.refresh_from_db()
        self.assertEqual(service_b.base_price, 390000)
        self.assertEqual(service_a.base_price, 120000)
        self.assertEqual(self.catalog.base_price, 120000)

    def test_edit_rejects_foreign_service_salon_mismatch_and_form_mismatch(self):
        service = self.private_service(self.b)
        for salon, data in (
            (self.a, self.payload(self.a)),
            (self.b, self.payload(self.a)),
            (self.foreign, self.payload(self.foreign)),
        ):
            url = self.url("multirole_manager_service_edit", salon, service_id=service.pk)
            with self.subTest(salon=salon.pk):
                self.assertIn(self.client.post(url, data).status_code, (403, 404))
        service.refresh_from_db()
        self.assertEqual(service.base_price, 120000)

    def test_catalog_and_shared_private_rows_are_not_edited_in_place(self):
        self.a.services.add(self.catalog)
        shared = self.private_service(self.a)
        self.b.services.add(shared)
        for service in (self.catalog, shared):
            url = self.url("multirole_manager_service_edit", self.a, service_id=service.pk)
            with self.subTest(service=service.pk):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, self.payload(self.a)).status_code, 403)

    def test_two_browser_tabs_cannot_retarget_service_edit(self):
        service_a = self.private_service(self.a)
        service_b = self.private_service(self.b)
        self.client.post(
            reverse("accounts:workspace_choose"),
            {"kind": "manager", "salon_id": str(self.b.pk)},
        )
        response = self.client.post(
            self.url("multirole_manager_service_edit", self.a, service_id=service_a.pk),
            self.payload(self.a, base_price="410000"),
        )
        self.assertEqual(response.status_code, 302)
        service_a.refresh_from_db()
        service_b.refresh_from_db()
        self.assertEqual(service_a.base_price, 410000)
        self.assertEqual(service_b.base_price, 120000)

    def test_future_booking_prevents_edit_of_booked_service(self):
        service = self.private_service(self.a)
        stylist = self.make_stylist()
        order = self.make_order(customer=self.make_customer(), salon=self.a, status="confirmed")
        OrderDetail.objects.create(
            order=order, salon=self.a, service=service, stylist=stylist,
            date=timezone.localdate() + timedelta(days=1),
            time=time(10, 0), end_time=time(10, 30), price=120000,
        )
        response = self.client.post(
            self.url("multirole_manager_service_edit", self.a, service_id=service.pk),
            self.payload(self.a, duration_minutes="60", base_price="999000"),
        )
        self.assertEqual(response.status_code, 403)
        service.refresh_from_db()
        self.assertEqual(service.duration_minutes, 30)
        self.assertEqual(service.base_price, 120000)

    def test_customer_cannot_create_or_edit_even_with_valid_salon_id(self):
        service = self.private_service(self.a)
        self.client.force_login(self.make_user())
        self.assertIn(self.create(self.a).status_code, (403, 404))
        self.assertIn(self.client.post(
            self.url("multirole_manager_service_edit", self.a, service_id=service.pk),
            self.payload(self.a),
        ).status_code, (403, 404))
