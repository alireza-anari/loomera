"""An unpaid manual booking may only be cancelled by its own salon manager."""
from datetime import time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SalonManager
from apps.orders.models import OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerManualBookingCancelTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        manager = SalonManager.objects.create(user=self.user)
        self.a = self.make_salon(manager=manager)
        self.b = self.make_salon(manager=manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.client.force_login(self.user)
        self.a_detail = self.booking(self.a)
        self.b_detail = self.booking(self.b)
        self.foreign_detail = self.booking(self.foreign)

    def booking(self, salon, *, booking_source="dashboard_manual", date=None):
        customer = self.make_customer(added_by_salon=salon)
        service = self.make_service()
        stylist = self.make_stylist()
        order = self.make_order(
            salon=salon, customer=customer, booking_source=booking_source,
        )
        return self.make_order_detail(
            order=order, salon=salon, service=service, stylist=stylist,
            date_value=date or timezone.localdate() + timedelta(days=1),
            start=time(10), end=time(10, 30),
            confirmation_status=OrderDetail.ConfirmationStatus.CONFIRMED,
            lifecycle_status=OrderDetail.ServiceLifecycleStatus.CONFIRMED,
        )

    def url(self, salon, detail):
        return reverse(
            "dashboards:multirole_manager_manual_booking_cancel",
            kwargs={"salon_id": salon.pk, "appointment_id": detail.pk},
        )

    def cancel(self, salon, detail, **overrides):
        data = {"salon_id": str(salon.pk), "appointment_id": str(detail.pk)}
        data.update(overrides)
        return self.client.post(self.url(salon, detail), data)

    def test_confirmation_is_scoped_and_get_cannot_cancel(self):
        response = self.client.get(self.url(self.a, self.a_detail))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.a.salon_name)
        self.assertEqual(response.context["salon"], self.a)
        # The other owned salon is navigation, not cancellation scope.
        self.assertContains(response, self.b.salon_name, count=1)
        self.assertNotContains(response, self.foreign.salon_name)
        self.assertContains(response, f'name="salon_id" value="{self.a.pk}"')
        self.a_detail.order.refresh_from_db()
        self.assertEqual(self.a_detail.order.status, "confirmed")

    def test_booking_list_exposes_only_eligible_cancel_link_for_this_salon(self):
        url_a = reverse(
            "dashboards:multirole_manager_salon_bookings",
            kwargs={"salon_id": self.a.pk},
        )
        response = self.client.get(url_a)
        self.assertContains(response, self.url(self.a, self.a_detail))
        self.assertNotContains(response, self.url(self.b, self.b_detail))
        self.a_detail.order.is_paid = True
        self.a_detail.order.save(update_fields=["is_paid"])
        self.assertNotContains(self.client.get(url_a), self.url(self.a, self.a_detail))

    def test_cancel_only_requested_salon_booking(self):
        response = self.cancel(self.b, self.b_detail)
        self.assertRedirects(
            response,
            reverse("dashboards:multirole_manager_salon_bookings", kwargs={"salon_id": self.b.pk}),
            fetch_redirect_response=False,
        )
        self.b_detail.order.refresh_from_db()
        self.a_detail.order.refresh_from_db()
        self.assertEqual(self.b_detail.order.status, "cancelled")
        self.assertFalse(self.b_detail.order.is_finally)
        self.assertFalse(self.b_detail.order.is_paid)
        self.assertEqual(self.a_detail.order.status, "confirmed")

    def test_foreign_salon_and_wrong_salon_detail_are_denied(self):
        for salon, detail in (
            (self.foreign, self.foreign_detail),
            (self.a, self.b_detail),
            (self.b, self.a_detail),
        ):
            with self.subTest(salon=salon.pk, detail=detail.pk):
                self.assertIn(self.client.get(self.url(salon, detail)).status_code, (403, 404))
                self.assertIn(self.cancel(salon, detail).status_code, (403, 404))
        for detail in (self.a_detail, self.b_detail, self.foreign_detail):
            detail.order.refresh_from_db()
            self.assertEqual(detail.order.status, "confirmed")

    def test_mismatched_or_absent_form_target_is_denied(self):
        for fields in (
            {"salon_id": str(self.b.pk)},
            {"salon_id": ""},
            {"appointment_id": str(self.b_detail.pk)},
            {"appointment_id": ""},
        ):
            with self.subTest(fields=fields):
                self.assertIn(self.cancel(self.a, self.a_detail, **fields).status_code, (403, 404))
        self.a_detail.order.refresh_from_db()
        self.assertEqual(self.a_detail.order.status, "confirmed")

    def test_switching_workspace_in_other_tab_cannot_retarget_existing_form(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.b.pk),
        })
        self.assertEqual(self.cancel(self.a, self.a_detail).status_code, 302)
        self.a_detail.order.refresh_from_db()
        self.b_detail.order.refresh_from_db()
        self.assertEqual(self.a_detail.order.status, "cancelled")
        self.assertEqual(self.b_detail.order.status, "confirmed")

    def test_revoked_ownership_after_get_denies_post(self):
        self.assertEqual(self.client.get(self.url(self.a, self.a_detail)).status_code, 200)
        self.a.salon_manager = self.make_salon_manager()
        self.a.save(update_fields=["salon_manager"])
        self.assertIn(self.cancel(self.a, self.a_detail).status_code, (403, 404))
        self.a_detail.order.refresh_from_db()
        self.assertEqual(self.a_detail.order.status, "confirmed")

    def test_already_cancelled_request_is_rejected_without_repeat_action(self):
        self.assertEqual(self.cancel(self.a, self.a_detail).status_code, 302)
        self.assertEqual(self.cancel(self.a, self.a_detail).status_code, 403)
        self.a_detail.order.refresh_from_db()
        self.assertEqual(self.a_detail.order.status, "cancelled")

    def test_online_or_paid_booking_is_not_cancellable_here(self):
        online = self.booking(self.a, booking_source="customer")
        self.a_detail.order.is_paid = True
        self.a_detail.order.save(update_fields=["is_paid"])
        for detail in (online, self.a_detail):
            with self.subTest(detail=detail.pk):
                self.assertEqual(self.client.get(self.url(self.a, detail)).status_code, 403)
                self.assertEqual(self.cancel(self.a, detail).status_code, 403)
                detail.order.refresh_from_db()
                self.assertEqual(detail.order.status, "confirmed")

    def test_past_and_started_bookings_are_not_cancellable(self):
        past = self.booking(self.a, date=timezone.localdate() - timedelta(days=1))
        self.a_detail.order.service_started_at = timezone.now()
        self.a_detail.order.save(update_fields=["service_started_at"])
        for detail in (past, self.a_detail):
            with self.subTest(detail=detail.pk):
                self.assertEqual(self.cancel(self.a, detail).status_code, 403)
                detail.order.refresh_from_db()
                self.assertEqual(detail.order.status, "confirmed")

    def test_multi_item_order_is_not_cancelled_by_single_item_link(self):
        second = self.make_order_detail(
            order=self.a_detail.order, salon=self.a,
            service=self.make_service(), stylist=self.make_stylist(),
            date_value=timezone.localdate() + timedelta(days=1),
            start=time(11), end=time(11, 30),
        )
        self.assertEqual(self.cancel(self.a, self.a_detail).status_code, 403)
        second.order.refresh_from_db()
        self.assertEqual(second.order.status, "confirmed")

    def test_anonymous_get_and_post_do_not_change_order(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url(self.a, self.a_detail)).status_code, 302)
        self.assertEqual(self.cancel(self.a, self.a_detail).status_code, 302)
        self.a_detail.order.refresh_from_db()
        self.assertEqual(self.a_detail.order.status, "confirmed")
