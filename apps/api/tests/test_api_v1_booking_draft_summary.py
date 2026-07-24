from datetime import time, timedelta
from unittest.mock import patch
from django.apps import apps
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-booking-draft-summary-tests",
        }
    },
    LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=4 * 1024,
    ONLINE_PAYMENT_ENABLED=False,
)
class ApiV1BookingDraftSummaryTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.url = reverse("api:v1:booking_draft_summary")

    def _setup_available_slot(self, *, date_value=None):
        customer = self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "خلاصه",
                "mobile_number": "09126660001",
                "email": "booking-summary-customer@example.com",
            }
        )
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        service = self.make_service(
            name="خدمت خلاصه رزرو",
            duration_minutes=45,
            buffer_minutes=15,
            is_active=True,
        )
        stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "خلاصه",
                "mobile_number": "09126660002",
                "email": "booking-summary-stylist@example.com",
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

        return customer, salon, service, stylist, target_date

    def _payload(self, *, salon, service, stylist, target_date, start_time="10:00"):
        return {
            "salon_slug": salon.slug,
            "service_id": service.pk,
            "stylist_id": stylist.pk,
            "date": target_date.isoformat(),
            "start_time": start_time,
        }

    def test_booking_draft_summary_requires_authentication(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()

        response = self.client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_booking_draft_summary_returns_price_and_payment_without_creating_order(
        self,
    ):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        Order = apps.get_model("orders", "Order")
        before_order_count = Order.objects.count()

        with patch(
            "apps.api.v1.booking_views.get_price_for_stylist_service",
            return_value=250000,
        ):
            response = self.client.post(
                self.url,
                data=self._payload(
                    salon=salon,
                    service=service,
                    stylist=stylist,
                    target_date=target_date,
                    start_time="10:00",
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["valid"])
        self.assertEqual(payload["data"]["reason"], None)

        self.assertEqual(payload["data"]["salon"]["id"], salon.pk)
        self.assertEqual(payload["data"]["service"]["id"], service.pk)
        self.assertEqual(payload["data"]["stylist"]["id"], stylist.pk)

        self.assertEqual(payload["data"]["service"]["duration_minutes"], 45)
        self.assertEqual(payload["data"]["service"]["buffer_minutes"], 15)

        self.assertEqual(payload["data"]["slot"]["date"], target_date.isoformat())
        self.assertEqual(payload["data"]["slot"]["start_time"], "10:00")
        self.assertEqual(payload["data"]["slot"]["end_time"], "10:45")

        self.assertEqual(payload["data"]["booking_mode"], "pay_in_salon")
        self.assertEqual(payload["data"]["price"]["service_price"], 250000)
        self.assertEqual(payload["data"]["price"]["discount_amount"], 0)
        self.assertEqual(payload["data"]["price"]["total_price"], 250000)
        self.assertEqual(payload["data"]["price"]["currency"], "IRR")

        self.assertEqual(payload["data"]["payment"]["mode"], "pay_in_salon")
        self.assertFalse(payload["data"]["payment"]["online_payment_enabled"])
        self.assertEqual(payload["data"]["payment"]["amount_due_now"], 0)
        self.assertEqual(payload["data"]["payment"]["amount_payable_at_salon"], 250000)

        self.assertFalse(payload["data"]["creates_order"])
        self.assertFalse(payload["data"]["locks_slot"])

        self.assertEqual(Order.objects.count(), before_order_count)

        body = response.content.decode("utf-8")
        self.assertNotIn("09126660001", body)
        self.assertNotIn("booking-summary-customer@example.com", body)
        self.assertNotIn("09126660002", body)
        self.assertNotIn("booking-summary-stylist@example.com", body)

    def test_booking_draft_summary_returns_invalid_for_unavailable_slot(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        response = self.client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
                start_time="09:00",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["data"]["valid"])
        self.assertEqual(payload["data"]["reason"], "slot_unavailable")

    def test_booking_draft_summary_blocks_existing_booking_with_buffer(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        existing_customer = self.make_customer()
        order = self.make_order(customer=existing_customer, salon=salon)
        self.make_order_detail(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            date_value=target_date,
            start=time(10, 0),
            end=time(10, 45),
            occupied_until=time(11, 0),
        )

        response = self.client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
                start_time="10:00",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["valid"])
        self.assertEqual(response.json()["data"]["reason"], "slot_unavailable")

    def test_booking_draft_summary_blocks_approved_leave(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        self.add_time_off(
            stylist=stylist,
            salon=salon,
            date_value=target_date,
            start=time(10, 0),
            end=time(11, 0),
        )

        response = self.client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
                start_time="10:00",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["valid"])
        self.assertEqual(response.json()["data"]["reason"], "slot_unavailable")

    def test_booking_draft_summary_rejects_foreign_service(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        foreign_service = self.make_service(
            name="خدمت نامرتبط خلاصه",
            duration_minutes=30,
            is_active=True,
        )

        response = self.client.post(
            self.url,
            data={
                "salon_slug": salon.slug,
                "service_id": foreign_service.pk,
                "stylist_id": stylist.pk,
                "date": target_date.isoformat(),
                "start_time": "10:00",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "service_not_found")

    def test_booking_draft_summary_rejects_hidden_stylist(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        hidden_stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self.connect_service(salon=salon, stylist=hidden_stylist, service=service)

        response = self.client.post(
            self.url,
            data={
                "salon_slug": salon.slug,
                "service_id": service.pk,
                "stylist_id": hidden_stylist.pk,
                "date": target_date.isoformat(),
                "start_time": "10:00",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "stylist_not_found")

    def test_booking_draft_summary_rejects_invalid_date_and_time(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        invalid_date_response = self.client.post(
            self.url,
            data={
                "salon_slug": salon.slug,
                "service_id": service.pk,
                "stylist_id": stylist.pk,
                "date": "1403/01/01",
                "start_time": "10:00",
            },
            content_type="application/json",
        )

        self.assertEqual(invalid_date_response.status_code, 400)
        self.assertEqual(
            invalid_date_response.json()["error"]["code"],
            "invalid_date",
        )

        invalid_time_response = self.client.post(
            self.url,
            data={
                "salon_slug": salon.slug,
                "service_id": service.pk,
                "stylist_id": stylist.pk,
                "date": target_date.isoformat(),
                "start_time": "10-00",
            },
            content_type="application/json",
        )

        self.assertEqual(invalid_time_response.status_code, 400)
        self.assertEqual(
            invalid_time_response.json()["error"]["code"],
            "invalid_start_time",
        )

    @override_settings(LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=16)
    def test_booking_draft_summary_rejects_large_payload(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        response = self.client.post(
            self.url,
            data={
                "salon_slug": salon.slug,
                "service_id": service.pk,
                "stylist_id": stylist.pk,
                "date": target_date.isoformat(),
                "start_time": "10:00",
                "extra": "x" * 100,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "payload_too_large")

    def test_booking_draft_summary_requires_customer_profile(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        manager = self.make_salon_manager()
        self.client.force_login(manager.user)

        response = self.client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "customer_profile_required")
