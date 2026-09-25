"""Phase 5B-1: explicit salon targets never inherit mutable workspace state."""

from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SalonManager
from apps.orders.models import OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerOperationsTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user)
        self.a = self.make_salon(manager=self.manager)
        self.b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.own_a = self.make_service(name="اختصاصی الف", is_platform_catalog=False)
        self.own_b = self.make_service(name="اختصاصی ب", is_platform_catalog=False)
        self.a.services.add(self.own_a)
        self.b.services.add(self.own_b)
        self.client.force_login(self.user)

    def url(self, name, salon, **kwargs):
        return reverse(f"dashboards:{name}", kwargs={"salon_id": salon.pk, **kwargs})

    def test_service_team_and_booking_views_only_show_selected_salon(self):
        for name in (
            "multirole_manager_salon_services",
            "multirole_manager_salon_team",
            "multirole_manager_salon_bookings",
        ):
            with self.subTest(name=name):
                response = self.client.get(self.url(name, self.b))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.b.salon_name)
                # The shared workspace switcher intentionally exposes the names of
                # the manager's other owned salons.  Cross-salon isolation is
                # asserted below using operational service/team/booking data.
                self.assertContains(response, self.a.salon_name)
                self.assertContains(
                    response,
                    f'name="salon_id" value="{self.a.pk}"',
                )
                self.assertIn(
                    self.client.get(self.url(name, self.foreign)).status_code,
                    (403, 404),
                )

        service_response = self.client.get(
            self.url("multirole_manager_salon_services", self.b)
        )
        self.assertContains(service_response, self.own_b.service_name)
        self.assertNotContains(service_response, self.own_a.service_name)

    def test_team_and_booking_rows_never_leak_between_owned_salons(self):
        member_a = self.make_stylist()
        member_b = self.make_stylist()
        self.a.stylists.add(member_a)
        self.b.stylists.add(member_b)
        response = self.client.get(self.url("multirole_manager_salon_team", self.b))
        self.assertContains(response, member_b.get_fullName())
        self.assertNotContains(response, member_a.get_fullName())

        customer = self.make_customer()
        order_a = self.make_order(customer=customer, salon=self.a, status="confirmed")
        order_b = self.make_order(customer=customer, salon=self.b, status="confirmed")
        for salon, service, member, order in (
            (self.a, self.own_a, member_a, order_a),
            (self.b, self.own_b, member_b, order_b),
        ):
            OrderDetail.objects.create(
                order=order,
                salon=salon,
                service=service,
                stylist=member,
                date=timezone.localdate() + timedelta(days=1),
                time=time(10, 0),
                end_time=time(10, 30),
                price=120000,
            )
        response = self.client.get(self.url("multirole_manager_salon_bookings", self.b))
        self.assertContains(response, self.own_b.service_name)
        self.assertNotContains(response, self.own_a.service_name)

    def test_scoped_service_toggle_changes_only_exact_owned_service(self):
        url_b = self.url(
            "multirole_manager_service_toggle", self.b, service_id=self.own_b.pk
        )
        response = self.client.post(url_b, {"salon_id": str(self.b.pk)})
        self.assertRedirects(
            response,
            self.url("multirole_manager_salon_services", self.b),
            fetch_redirect_response=False,
        )
        self.own_b.refresh_from_db()
        self.own_a.refresh_from_db()
        self.assertFalse(self.own_b.is_active)
        self.assertTrue(self.own_a.is_active)

    def test_wrong_salon_service_and_form_target_are_rejected_without_mutation(self):
        wrong_pair = self.url(
            "multirole_manager_service_toggle", self.a, service_id=self.own_b.pk
        )
        url_a = self.url(
            "multirole_manager_service_toggle", self.a, service_id=self.own_a.pk
        )
        foreign = self.url(
            "multirole_manager_service_toggle", self.foreign, service_id=self.own_a.pk
        )
        for url, data in (
            (wrong_pair, {"salon_id": str(self.a.pk)}),
            (url_a, {"salon_id": str(self.b.pk)}),
            (url_a, {}),
            (foreign, {"salon_id": str(self.foreign.pk)}),
        ):
            with self.subTest(url=url, data=data):
                self.assertIn(self.client.post(url, data).status_code, (403, 404))
        self.own_a.refresh_from_db()
        self.own_b.refresh_from_db()
        self.assertTrue(self.own_a.is_active)
        self.assertTrue(self.own_b.is_active)

    def test_two_tabs_keep_immutable_target_even_when_workspace_changes(self):
        url_a = self.url(
            "multirole_manager_service_toggle", self.a, service_id=self.own_a.pk
        )
        self.client.post(
            reverse("accounts:workspace_choose"),
            {"kind": "manager", "salon_id": str(self.b.pk)},
        )
        response = self.client.post(url_a, {"salon_id": str(self.a.pk)})
        self.assertEqual(response.status_code, 302)
        self.own_a.refresh_from_db()
        self.own_b.refresh_from_db()
        self.assertFalse(self.own_a.is_active)
        self.assertTrue(self.own_b.is_active)

    def test_global_and_shared_services_cannot_be_modified_across_salons(self):
        catalog = self.make_service(name="کاتالوگ مشترک", is_platform_catalog=True)
        self.a.services.add(catalog)
        shared_private = self.make_service(
            name="خصوصی مشترک", is_platform_catalog=False
        )
        self.a.services.add(shared_private)
        self.b.services.add(shared_private)
        for service in (catalog, shared_private):
            with self.subTest(service=service.pk):
                url = self.url(
                    "multirole_manager_service_toggle", self.a, service_id=service.pk
                )
                self.assertEqual(
                    self.client.post(url, {"salon_id": str(self.a.pk)}).status_code, 403
                )
                service.refresh_from_db()
                self.assertTrue(service.is_active)

    def test_cannot_deactivate_service_with_future_active_booking(self):
        customer = self.make_customer()
        stylist = self.make_stylist()
        order = self.make_order(customer=customer, salon=self.a, status="confirmed")
        OrderDetail.objects.create(
            order=order,
            salon=self.a,
            service=self.own_a,
            stylist=stylist,
            date=timezone.localdate() + timedelta(days=1),
            time=time(10, 0),
            end_time=time(10, 30),
            price=120000,
        )
        response = self.client.post(
            self.url(
                "multirole_manager_service_toggle", self.a, service_id=self.own_a.pk
            ),
            {"salon_id": str(self.a.pk)},
        )
        self.assertEqual(response.status_code, 403)
        self.own_a.refresh_from_db()
        self.assertTrue(self.own_a.is_active)

    def test_read_only_and_stale_ownership_never_mutate(self):
        url = self.url(
            "multirole_manager_service_toggle", self.a, service_id=self.own_a.pk
        )
        self.assertEqual(self.client.get(url).status_code, 405)
        self.a.salon_manager = self.make_salon_manager()
        self.a.save(update_fields=["salon_manager"])
        self.assertIn(
            self.client.post(url, {"salon_id": str(self.a.pk)}).status_code, (403, 404)
        )
        self.own_a.refresh_from_db()
        self.assertTrue(self.own_a.is_active)

    def test_legacy_manager_mutation_still_blocked_for_multisalon_manager(self):
        url = reverse(
            "dashboards:toggle_service_status", kwargs={"service_id": self.own_b.pk}
        )
        self.assertEqual(
            self.client.post(url, {"salon_id": str(self.b.pk)}).status_code, 403
        )

    def test_customer_without_manager_role_cannot_view_any_salon(self):
        self.client.force_login(self.make_user())
        response = self.client.get(self.url("multirole_manager_salon_services", self.a))
        self.assertIn(response.status_code, (403, 404))
