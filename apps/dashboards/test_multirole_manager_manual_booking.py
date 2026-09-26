"""Phase 5B-5: manager booking must stay bound to one owned salon."""
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SalonManager
from apps.orders.models import Order, OrderDetail
from apps.salons.models import SalonMembership, SalonMembershipStatus
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerManualBookingTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.owner = self.make_user()
        self.manager = SalonManager.objects.create(user=self.owner)
        self.a = self.make_salon(manager=self.manager)
        self.b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.customer_a = self.make_customer(added_by_salon=self.a)
        self.customer_b = self.make_customer(added_by_salon=self.b)
        self.service_a = self.make_service(name="خدمت الف")
        self.service_b = self.make_service(name="خدمت ب")
        self.stylist_a = self.make_stylist()
        self.stylist_b = self.make_stylist()
        self.connect_service(salon=self.a, stylist=self.stylist_a, service=self.service_a)
        self.connect_service(salon=self.b, stylist=self.stylist_b, service=self.service_b)
        self.date = timezone.localdate() + timedelta(days=1)
        for salon, stylist, service in (
            (self.a, self.stylist_a, self.service_a),
            (self.b, self.stylist_b, self.service_b),
        ):
            self.add_schedule(
                salon=salon, stylist=stylist, service=service,
                date_value=self.date, start=time(10, 0), end=time(13, 0),
            )
        self.client.force_login(self.owner)

    def url(self, salon):
        return reverse("dashboards:multirole_manager_manual_booking", kwargs={"salon_id": salon.pk})

    def payload(self, salon, *, at="10:00", **overrides):
        customer, service, stylist = (
            (self.customer_a, self.service_a, self.stylist_a)
            if salon == self.a else
            (self.customer_b, self.service_b, self.stylist_b)
        )
        data = {
            "salon_id": str(salon.pk), "customer": str(customer.pk),
            "service": str(service.pk), "stylist": str(stylist.pk),
            "appointment_date": self.date.isoformat(),
            "start_time": at, "notes": "نوبت دستی",
        }
        data.update(overrides)
        return data

    def test_get_shows_only_selected_salons_customers_services_and_stylists(self):
        response = self.client.get(self.url(self.a))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertQuerySetEqual(form.fields["customer"].queryset, [self.customer_a])
        self.assertQuerySetEqual(form.fields["service"].queryset, [self.service_a])
        self.assertQuerySetEqual(form.fields["stylist"].queryset, [self.stylist_a])
        self.assertContains(response, f'name="salon_id" value="{self.a.pk}"')
        self.assertContains(response, self.a.salon_name)
        self.assertEqual(response.context["salon"], self.a)
        # The second owned salon is expected in the shared workspace switcher only.
        self.assertContains(response, self.b.salon_name, count=1)
        self.assertNotContains(response, self.foreign.salon_name)
        self.assertIn(self.client.get(self.url(self.foreign)).status_code, (403, 404))

    def test_create_booking_for_b_preserves_a_and_payment_semantics(self):
        response = self.client.post(self.url(self.b), self.payload(self.b))
        self.assertRedirects(
            response,
            reverse("dashboards:multirole_manager_salon_bookings", kwargs={"salon_id": self.b.pk}),
            fetch_redirect_response=False,
        )
        detail = OrderDetail.objects.get(order__booking_source="dashboard_manual")
        order = detail.order
        self.assertEqual((detail.salon_id, order.salon_id), (self.b.pk, self.b.pk))
        self.assertEqual(detail.stylist_id, self.stylist_b.pk)
        self.assertEqual(detail.service_id, self.service_b.pk)
        self.assertEqual(order.customer_id, self.customer_b.pk)
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(order.selected_payment_method, "pay_in_salon")
        self.assertFalse(order.is_paid)
        self.assertFalse(order.platform_commission_applies)
        self.assertFalse(OrderDetail.objects.filter(salon=self.a).exists())

    def test_mismatched_or_missing_form_salon_is_rejected_before_write(self):
        for wrong in ("", str(self.b.pk), "not-a-number"):
            with self.subTest(wrong=wrong):
                response = self.client.post(self.url(self.a), self.payload(self.a, salon_id=wrong))
                self.assertIn(response.status_code, (403, 404))
        self.assertFalse(Order.objects.filter(booking_source="dashboard_manual").exists())

    def test_cross_salon_customer_service_stylist_and_foreign_route_are_denied(self):
        for field, other in (
            ("customer", self.customer_b),
            ("service", self.service_b),
            ("stylist", self.stylist_b),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    self.url(self.a), self.payload(self.a, **{field: str(other.pk)}),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        response = self.client.post(self.url(self.foreign), self.payload(self.foreign))
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(Order.objects.filter(booking_source="dashboard_manual").exists())

    def test_workspace_switch_in_other_tab_does_not_retarget_booking(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.b.pk),
        })
        response = self.client.post(self.url(self.a), self.payload(self.a))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get(booking_source="dashboard_manual").salon_id, self.a.pk)
        self.assertFalse(OrderDetail.objects.filter(salon=self.b).exists())

    def test_revoked_manager_access_prevents_booking(self):
        self.a.salon_manager = self.make_salon_manager()
        self.a.save(update_fields=["salon_manager"])
        response = self.client.post(self.url(self.a), self.payload(self.a))
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(Order.objects.filter(booking_source="dashboard_manual").exists())

    def test_paused_membership_cannot_book_despite_old_m2m_link(self):
        SalonMembership.objects.create(
            salon=self.a, stylist=self.stylist_a, status=SalonMembershipStatus.PAUSED,
        )
        response = self.client.post(self.url(self.a), self.payload(self.a))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Order.objects.filter(booking_source="dashboard_manual").exists())

    def test_existing_booking_is_rejected_by_canonical_availability(self):
        first = self.client.post(self.url(self.a), self.payload(self.a))
        self.assertEqual(first.status_code, 302)
        second = self.client.post(self.url(self.a), self.payload(self.a))
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.context["form"].errors)
        self.assertEqual(Order.objects.filter(booking_source="dashboard_manual").count(), 1)

    def test_non_owner_cannot_access_and_unauthenticated_user_is_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url(self.a)).status_code, 302)
        self.client.force_login(self.make_user())
        self.assertIn(self.client.get(self.url(self.a)).status_code, (403, 404))
        self.assertIn(self.client.post(self.url(self.a), self.payload(self.a)).status_code, (403, 404))
        self.assertFalse(Order.objects.filter(booking_source="dashboard_manual").exists())
