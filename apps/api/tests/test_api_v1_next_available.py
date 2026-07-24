from datetime import time, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ApiV1NextAvailableTests(Stage1DomainFactoryMixin, TestCase):
    def _setup_base(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        service = self.make_service(
            name="خدمت نزدیک‌ترین زمان",
            duration_minutes=30,
            buffer_minutes=10,
            is_active=True,
        )
        stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "نزدیک",
                "mobile_number": "09127770001",
                "email": "next-private@example.com",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        self.connect_service(salon=salon, stylist=stylist, service=service)
        return salon, service, stylist

    def _url(self, salon):
        return reverse(
            "api:v1:public_salon_next_available",
            kwargs={"salon_slug": salon.slug},
        )

    def test_next_available_returns_first_slot_across_search_window(self):
        salon, service, stylist = self._setup_base()
        start_date = timezone.localdate() + timedelta(days=1)
        available_date = start_date + timedelta(days=2)

        self.add_schedule(
            stylist=stylist,
            salon=salon,
            service=service,
            date_value=available_date,
            start=time(11, 0),
            end=time(12, 0),
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": start_date.isoformat(),
                "days": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        next_available = payload["data"]["next_available"]
        self.assertIsNotNone(next_available)
        self.assertEqual(next_available["date"], available_date.isoformat())
        self.assertEqual(next_available["start_time"], "11:00")
        self.assertEqual(next_available["end_time"], "11:30")
        self.assertEqual(next_available["stylist"]["id"], stylist.pk)
        self.assertTrue(payload["data"]["summary"]["has_available_slot"])

        body = response.content.decode("utf-8")
        self.assertNotIn("09127770001", body)
        self.assertNotIn("next-private@example.com", body)

    def test_next_available_returns_null_when_no_slot_exists(self):
        salon, service, stylist = self._setup_base()
        start_date = timezone.localdate() + timedelta(days=1)

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": start_date.isoformat(),
                "days": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIsNone(payload["data"]["next_available"])
        self.assertFalse(payload["data"]["summary"]["has_available_slot"])
        self.assertEqual(payload["data"]["summary"]["total_stylists"], 1)

    def test_next_available_respects_explicit_stylist_filter(self):
        salon, service, first_stylist = self._setup_base()
        second_stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "دوم",
                "mobile_number": "09127770002",
                "email": "second-next@example.com",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        self.connect_service(salon=salon, stylist=second_stylist, service=service)

        target_date = timezone.localdate() + timedelta(days=1)
        self.add_schedule(
            stylist=first_stylist,
            salon=salon,
            service=service,
            date_value=target_date,
            start=time(9, 0),
            end=time(10, 0),
        )
        self.add_schedule(
            stylist=second_stylist,
            salon=salon,
            service=service,
            date_value=target_date,
            start=time(11, 0),
            end=time(12, 0),
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "stylist_id": second_stylist.pk,
                "date": target_date.isoformat(),
                "days": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            payload["data"]["next_available"]["stylist"]["id"], second_stylist.pk
        )
        self.assertEqual(payload["data"]["next_available"]["start_time"], "11:00")
        self.assertEqual(len(payload["data"]["stylists"]), 1)

        body = response.content.decode("utf-8")
        self.assertNotIn("09127770002", body)
        self.assertNotIn("second-next@example.com", body)

    def test_next_available_hides_hidden_stylist(self):
        salon, service, visible_stylist = self._setup_base()
        hidden_stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self.connect_service(salon=salon, stylist=hidden_stylist, service=service)

        target_date = timezone.localdate() + timedelta(days=1)
        self.add_schedule(
            stylist=hidden_stylist,
            salon=salon,
            service=service,
            date_value=target_date,
            start=time(9, 0),
            end=time(10, 0),
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": target_date.isoformat(),
                "days": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        stylist_ids = {item["id"] for item in payload["data"]["stylists"]}
        self.assertNotIn(hidden_stylist.pk, stylist_ids)
        self.assertIsNone(payload["data"]["next_available"])

    def test_next_available_returns_404_for_explicit_hidden_stylist(self):
        salon, service, visible_stylist = self._setup_base()
        hidden_stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self.connect_service(salon=salon, stylist=hidden_stylist, service=service)

        target_date = timezone.localdate() + timedelta(days=1)

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "stylist_id": hidden_stylist.pk,
                "date": target_date.isoformat(),
                "days": 1,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "stylist_not_found")

    def test_next_available_ignores_blocked_slot_and_finds_later_slot(self):
        salon, service, stylist = self._setup_base()
        target_date = timezone.localdate() + timedelta(days=1)

        self.add_schedule(
            stylist=stylist,
            salon=salon,
            service=service,
            date_value=target_date,
            start=time(10, 0),
            end=time(12, 0),
        )

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
                "days": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        next_available = response.json()["data"]["next_available"]

        self.assertIsNotNone(next_available)
        self.assertEqual(next_available["start_time"], "10:45")
        self.assertEqual(next_available["end_time"], "11:15")

    def test_next_available_rejects_foreign_service(self):
        salon, service, stylist = self._setup_base()
        foreign_service = self.make_service(
            name="خدمت نامرتبط",
            duration_minutes=30,
            is_active=True,
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": foreign_service.pk,
                "date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "service_not_found")

    def test_next_available_rejects_date_out_of_range(self):
        salon, service, stylist = self._setup_base()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": (timezone.localdate() - timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "date_out_of_range")

    @override_settings(LOOMERA_API_NEXT_AVAILABLE_MAX_DAYS=2)
    def test_next_available_days_is_bounded_by_setting(self):
        salon, service, stylist = self._setup_base()
        start_date = timezone.localdate() + timedelta(days=1)
        available_date = start_date + timedelta(days=3)

        self.add_schedule(
            stylist=stylist,
            salon=salon,
            service=service,
            date_value=available_date,
            start=time(10, 0),
            end=time(11, 0),
        )

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": start_date.isoformat(),
                "days": 20,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"]["next_available"])

    @override_settings(LOOMERA_API_PUBLIC_QUERY_MAX_CHARS=20)
    def test_next_available_rejects_large_query_string(self):
        salon, service, stylist = self._setup_base()

        response = self.client.get(
            self._url(salon),
            {
                "service_id": service.pk,
                "date": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "q": "x" * 100,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "query_too_large")
