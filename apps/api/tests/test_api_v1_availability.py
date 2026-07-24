from datetime import time, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ApiV1AvailabilityTests(Stage1DomainFactoryMixin, TestCase):
    def _setup_available_stylist(self, *, date_value=None):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        service = self.make_service(
            name="خدمت زمان آزاد",
            duration_minutes=30,
            buffer_minutes=10,
            is_active=True,
        )
        stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "زمان",
                "mobile_number": "09124440001",
                "email": "availability-private@example.com",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        self.connect_service(salon=salon, stylist=stylist, service=service)
        target_date = date_value or timezone.localdate() + timedelta(days=2)
        self.add_schedule(
            stylist=stylist,
            salon=salon,
            service=service,
            date_value=target_date,
            start=time(10, 0),
            end=time(12, 0),
        )
        return salon, service, stylist, target_date

    def _url(self, salon):
        return reverse(
            "api:v1:public_salon_availability",
            kwargs={"salon_slug": salon.slug},
        )

    def test_availability_returns_slots_for_public_active_salon_service_and_stylist(
        self,
    ):
        salon, service, stylist, target_date = self._setup_available_stylist()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["salon"]["id"], salon.pk)
        self.assertEqual(payload["data"]["service"]["id"], service.pk)
        self.assertEqual(payload["data"]["date"], target_date.isoformat())
        self.assertEqual(payload["data"]["service"]["duration_minutes"], 30)
        self.assertEqual(payload["data"]["service"]["buffer_minutes"], 10)

        stylists = payload["data"]["stylists"]
        self.assertEqual(len(stylists), 1)
        self.assertEqual(stylists[0]["id"], stylist.pk)
        self.assertTrue(stylists[0]["has_available_slots"])
        self.assertIn(
            {"start_time": "10:00", "end_time": "10:30"},
            stylists[0]["slots"],
        )

        body = response.content.decode("utf-8")
        self.assertNotIn("09124440001", body)
        self.assertNotIn("availability-private@example.com", body)

    def test_availability_requires_valid_date(self):
        salon, service, stylist, target_date = self._setup_available_stylist()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": "1403/01/01",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_date")

    def test_availability_rejects_past_date(self):
        salon, service, stylist, target_date = self._setup_available_stylist()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": (timezone.localdate() - timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "date_out_of_range")

    @override_settings(LOOMERA_API_AVAILABILITY_MAX_DAYS_AHEAD=3)
    def test_availability_rejects_date_too_far_ahead(self):
        salon, service, stylist, target_date = self._setup_available_stylist()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "date_out_of_range")

    def test_availability_hides_inactive_or_foreign_service(self):
        salon, service, stylist, target_date = self._setup_available_stylist()
        foreign_service = self.make_service(
            name="خدمت سالن دیگر",
            duration_minutes=30,
            is_active=True,
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": foreign_service.pk,
                "date": target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "service_not_found")

    def test_availability_hides_hidden_inactive_and_foreign_stylists(self):
        salon, service, visible_stylist, target_date = self._setup_available_stylist()

        hidden_stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "مخفی",
                "mobile_number": "09124440002",
                "email": "hidden-availability@example.com",
            },
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        inactive_stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "غیرفعال",
                "mobile_number": "09124440003",
                "email": "inactive-availability@example.com",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        inactive_stylist.is_active = False
        inactive_stylist.save(update_fields=["is_active"])

        foreign_stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )

        self.connect_service(salon=salon, stylist=hidden_stylist, service=service)
        self.connect_service(salon=salon, stylist=inactive_stylist, service=service)

        for stylist in [hidden_stylist, inactive_stylist, foreign_stylist]:
            self.add_schedule(
                stylist=stylist,
                salon=salon,
                service=service,
                date_value=target_date,
                start=time(10, 0),
                end=time(12, 0),
            )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        stylist_ids = {item["id"] for item in payload["data"]["stylists"]}

        self.assertIn(visible_stylist.pk, stylist_ids)
        self.assertNotIn(hidden_stylist.pk, stylist_ids)
        self.assertNotIn(inactive_stylist.pk, stylist_ids)
        self.assertNotIn(foreign_stylist.pk, stylist_ids)

        body = response.content.decode("utf-8")
        self.assertNotIn("09124440002", body)
        self.assertNotIn("hidden-availability@example.com", body)
        self.assertNotIn("09124440003", body)
        self.assertNotIn("inactive-availability@example.com", body)

    def test_availability_for_explicit_hidden_stylist_returns_404(self):
        salon, service, visible_stylist, target_date = self._setup_available_stylist()
        hidden_stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self.connect_service(salon=salon, stylist=hidden_stylist, service=service)

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "stylist_id": hidden_stylist.pk,
                "date": target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "stylist_not_found")

    def test_availability_blocks_existing_booking_with_buffer(self):
        salon, service, stylist, target_date = self._setup_available_stylist()
        customer = self.make_customer()
        order = self.make_order(customer=customer, salon=salon)
        self.make_order_detail(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            date_value=target_date,
            start=time(10, 0),
            end=time(10, 30),
            occupied_until=time(10, 40),
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        slots = response.json()["data"]["stylists"][0]["slots"]

        self.assertNotIn({"start_time": "10:00", "end_time": "10:30"}, slots)
        self.assertNotIn({"start_time": "10:15", "end_time": "10:45"}, slots)
        self.assertNotIn({"start_time": "10:30", "end_time": "11:00"}, slots)
        self.assertIn({"start_time": "10:45", "end_time": "11:15"}, slots)

    def test_availability_blocks_approved_leave(self):
        salon, service, stylist, target_date = self._setup_available_stylist()
        self.add_time_off(
            stylist=stylist,
            salon=salon,
            date_value=target_date,
            start=time(10, 0),
            end=time(11, 0),
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": target_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        slots = response.json()["data"]["stylists"][0]["slots"]

        self.assertNotIn({"start_time": "10:00", "end_time": "10:30"}, slots)
        self.assertIn({"start_time": "11:00", "end_time": "11:30"}, slots)

    @override_settings(LOOMERA_API_PUBLIC_QUERY_MAX_CHARS=20)
    def test_availability_rejects_large_query_string(self):
        salon, service, stylist, target_date = self._setup_available_stylist()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": target_date.isoformat(),
                "q": "x" * 100,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "query_too_large")
