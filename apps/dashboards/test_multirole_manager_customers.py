"""Salon-scoped customer list and fail-closed legacy account manager pages."""
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SalonManager, Customer
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedMultiSalonCustomerTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        manager = SalonManager.objects.create(user=self.user)
        self.salon_a = self.make_salon(manager=manager)
        self.salon_b = self.make_salon(manager=manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.customer_a = self.make_customer(added_by_salon=self.salon_a)
        self.customer_b = self.make_customer(added_by_salon=self.salon_b)
        self.customer_foreign = self.make_customer(added_by_salon=self.foreign)
        self.client.force_login(self.user)

    def url(self, salon):
        return reverse(
            "dashboards:multirole_manager_salon_customers",
            kwargs={"salon_id": salon.pk},
        )

    def test_salon_lists_only_customers_of_that_salon(self):
        for salon, expected in (
            (self.salon_a, self.customer_a),
            (self.salon_b, self.customer_b),
        ):
            with self.subTest(salon=salon.pk):
                response = self.client.get(self.url(salon))
                self.assertEqual(response.status_code, 200)
                ids = [customer.pk for customer in response.context["page_obj"].object_list]
                self.assertEqual(ids, [expected.pk])
                self.assertContains(response, salon.salon_name)
                self.assertNotContains(response, self.foreign.salon_name)

    def test_booking_customer_is_included_without_salon_added_by_relation(self):
        booking_customer = self.make_customer()
        service = self.make_service()
        stylist = self.make_stylist()
        self.connect_service(salon=self.salon_b, stylist=stylist, service=service)
        order = self.make_order(customer=booking_customer, salon=self.salon_b)
        self.make_order_detail(
            order=order, service=service, stylist=stylist, salon=self.salon_b,
            date_value=timezone.localdate() + timedelta(days=2),
            start=time(10, 0), end=time(10, 30),
        )
        response_b = self.client.get(self.url(self.salon_b))
        self.assertEqual(response_b.status_code, 200)
        ids_b = {item.pk for item in response_b.context["page_obj"].object_list}
        self.assertIn(booking_customer.pk, ids_b)
        response_a = self.client.get(self.url(self.salon_a))
        self.assertEqual(response_a.status_code, 200)
        ids_a = {item.pk for item in response_a.context["page_obj"].object_list}
        self.assertNotIn(booking_customer.pk, ids_a)

    def test_foreign_or_revoked_salon_denied_without_customer_leak(self):
        self.assertIn(self.client.get(self.url(self.foreign)).status_code, (403, 404))
        self.salon_a.salon_manager = self.make_salon_manager()
        self.salon_a.save(update_fields=["salon_manager"])
        self.assertIn(self.client.get(self.url(self.salon_a)).status_code, (403, 404))

    def test_get_only_and_anonymous_must_not_access_customer_list(self):
        self.assertEqual(self.client.post(self.url(self.salon_a)).status_code, 405)
        self.client.logout()
        self.assertNotEqual(self.client.get(self.url(self.salon_a)).status_code, 200)

    def test_workspace_switch_does_not_change_target_salon(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.salon_a.pk),
        })
        response = self.client.get(self.url(self.salon_b))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [c.pk for c in response.context["page_obj"].object_list],
            [self.customer_b.pk],
        )

    def test_legacy_customer_manager_routes_are_blocked_for_two_salons(self):
        requests = (
            ("accounts:add_customer", {"salon_id": self.salon_a.pk}),
            ("accounts:detail_customer", {"customer_id": self.customer_a.pk}),
            ("accounts:delete_customer_note", {"customer_id": self.customer_a.pk, "note_id": 1}),
        )
        count_before = Customer.objects.count()
        for name, kwargs in requests:
            with self.subTest(name=name):
                url = reverse(name, kwargs=kwargs)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {"note": "must not save"}).status_code, 403)
        self.assertEqual(Customer.objects.count(), count_before)

    def test_one_salon_manager_not_blocked_by_new_guard(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        own_salon = self.make_salon(manager=manager)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:add_customer", kwargs={"salon_id": own_salon.pk}))
        self.assertNotEqual(response.status_code, 403)
