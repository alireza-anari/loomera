from datetime import time, timedelta

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
            "LOCATION": "api-my-appointments-tests",
        }
    },
    LOOMERA_API_PUBLIC_LIST_MAX_LIMIT=50,
)
class ApiV1MyAppointmentsTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.list_url = reverse("api:v1:my_appointments")
        self._appointment_setup_index = 0

    def _setup_appointment(self, *, customer=None, date_value=None, start=time(10, 0)):
        self._appointment_setup_index += 1
        unique_index = self._appointment_setup_index

        customer = customer or self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "رزروها",
                "mobile_number": f"0912887{unique_index:04d}",
                "email": f"my-appointments-customer-{unique_index}@example.com",
            }
        )
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        service = self.make_service(
            name="خدمت رزروهای من",
            duration_minutes=30,
            buffer_minutes=10,
            is_active=True,
        )
        stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "رزروها",
                "mobile_number": f"0912888{unique_index:04d}",
                "email": f"my-appointments-stylist-{unique_index}@example.com",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        self.connect_service(salon=salon, stylist=stylist, service=service)

        target_date = date_value or timezone.localdate() + timedelta(days=2)
        order = self.make_order(customer=customer, salon=salon)
        appointment = self.make_order_detail(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            date_value=target_date,
            start=start,
            end=(
                time(start.hour, start.minute + 30)
                if start.minute <= 29
                else time(start.hour + 1, start.minute - 30)
            ),
            occupied_until=(
                time(start.hour, start.minute + 40)
                if start.minute <= 19
                else time(start.hour + 1, start.minute - 20)
            ),
        )

        return customer, salon, service, stylist, order, appointment

    def _detail_url(self, appointment):
        return reverse(
            "api:v1:my_appointment_detail",
            kwargs={"appointment_id": appointment.pk},
        )

    def test_my_appointments_requires_authentication(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_my_appointments_requires_customer_profile(self):
        manager = self.make_salon_manager()
        self.client.force_login(manager.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "customer_profile_required")

    def test_my_appointments_lists_only_current_customer_appointments(self):
        customer, salon, service, stylist, order, appointment = (
            self._setup_appointment()
        )
        (
            other_customer,
            other_salon,
            other_service,
            other_stylist,
            other_order,
            other_appointment,
        ) = self._setup_appointment(
            customer=self.make_customer(
                user_kwargs={
                    "name": "مشتری",
                    "family": "دیگر",
                    "mobile_number": "09128880003",
                    "email": "other-my-appointments@example.com",
                }
            ),
            date_value=timezone.localdate() + timedelta(days=3),
            start=time(11, 0),
        )

        self.client.force_login(customer.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["pagination"]["total_count"], 1)
        self.assertEqual(len(payload["data"]["results"]), 1)

        item = payload["data"]["results"][0]
        self.assertEqual(item["id"], appointment.pk)
        self.assertEqual(item["order"]["id"], order.pk)
        self.assertEqual(item["salon"]["id"], salon.pk)
        self.assertEqual(item["service"]["id"], service.pk)
        self.assertEqual(item["stylist"]["id"], stylist.pk)

        body = response.content.decode("utf-8")
        self.assertNotIn(str(other_appointment.pk), body)
        self.assertNotIn("09128880001", body)
        self.assertNotIn("my-appointments-customer@example.com", body)
        self.assertNotIn("09128880002", body)
        self.assertNotIn("my-appointments-stylist@example.com", body)
        self.assertNotIn("09128880003", body)
        self.assertNotIn("other-my-appointments@example.com", body)

    def test_my_appointments_detail_returns_only_owned_appointment(self):
        customer, salon, service, stylist, order, appointment = (
            self._setup_appointment()
        )
        self.client.force_login(customer.user)

        response = self.client.get(self._detail_url(appointment))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertTrue(payload["ok"])
        data = payload["data"]["appointment"]

        self.assertEqual(data["id"], appointment.pk)
        self.assertEqual(data["order"]["id"], order.pk)
        self.assertEqual(data["salon"]["id"], salon.pk)
        self.assertEqual(data["service"]["id"], service.pk)
        self.assertEqual(data["stylist"]["id"], stylist.pk)
        self.assertEqual(data["slot"]["date"], appointment.date.isoformat())
        self.assertEqual(data["slot"]["start_time"], appointment.time.strftime("%H:%M"))
        self.assertEqual(
            data["slot"]["end_time"], appointment.end_time.strftime("%H:%M")
        )
        self.assertFalse(data["meta"]["can_cancel"])
        self.assertFalse(data["meta"]["can_reschedule"])

        body = response.content.decode("utf-8")
        self.assertNotIn("09128880001", body)
        self.assertNotIn("my-appointments-customer@example.com", body)
        self.assertNotIn("09128880002", body)
        self.assertNotIn("my-appointments-stylist@example.com", body)

    def test_my_appointments_detail_rejects_other_customer_appointment(self):
        customer = self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "خودم",
                "mobile_number": "09128880004",
                "email": "owner-my-appointments@example.com",
            }
        )
        other_customer, salon, service, stylist, order, other_appointment = (
            self._setup_appointment(
                customer=self.make_customer(
                    user_kwargs={
                        "name": "مشتری",
                        "family": "غیر",
                        "mobile_number": "09128880005",
                        "email": "not-owner-my-appointments@example.com",
                    }
                )
            )
        )

        self.client.force_login(customer.user)

        response = self.client.get(self._detail_url(other_appointment))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "appointment_not_found")

        body = response.content.decode("utf-8")
        self.assertNotIn("not-owner-my-appointments@example.com", body)
        self.assertNotIn("09128880005", body)

    def test_my_appointments_pagination_limits_results(self):
        customer = self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "صفحه",
                "mobile_number": "09128880006",
                "email": "pagination-my-appointments@example.com",
            }
        )
        self._setup_appointment(
            customer=customer,
            date_value=timezone.localdate() + timedelta(days=1),
            start=time(10, 0),
        )
        self._setup_appointment(
            customer=customer,
            date_value=timezone.localdate() + timedelta(days=2),
            start=time(11, 0),
        )
        self._setup_appointment(
            customer=customer,
            date_value=timezone.localdate() + timedelta(days=3),
            start=time(12, 0),
        )

        self.client.force_login(customer.user)

        response = self.client.get(self.list_url, {"limit": 2, "offset": 0})

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["data"]["pagination"]["limit"], 2)
        self.assertEqual(payload["data"]["pagination"]["offset"], 0)
        self.assertEqual(payload["data"]["pagination"]["count"], 2)
        self.assertEqual(payload["data"]["pagination"]["total_count"], 3)
        self.assertTrue(payload["data"]["pagination"]["has_next"])

    @override_settings(LOOMERA_API_PUBLIC_QUERY_MAX_CHARS=20)
    def test_my_appointments_rejects_large_query_string(self):
        customer, salon, service, stylist, order, appointment = (
            self._setup_appointment()
        )
        self.client.force_login(customer.user)

        response = self.client.get(self.list_url, {"q": "x" * 100})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "query_too_large")

    def test_my_appointments_are_read_only(self):
        customer, salon, service, stylist, order, appointment = (
            self._setup_appointment()
        )
        self.client.force_login(customer.user)

        Order = apps.get_model("orders", "Order")
        OrderDetail = apps.get_model("orders", "OrderDetail")
        before_order_count = Order.objects.count()
        before_detail_count = OrderDetail.objects.count()

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), before_order_count)
        self.assertEqual(OrderDetail.objects.count(), before_detail_count)

        detail_response = self.client.get(self._detail_url(appointment))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(Order.objects.count(), before_order_count)
        self.assertEqual(OrderDetail.objects.count(), before_detail_count)
