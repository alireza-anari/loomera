from datetime import time, timedelta
from unittest.mock import patch

from django.apps import apps
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-booking-confirm-tests",
        }
    },
    LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=4 * 1024,
    ONLINE_PAYMENT_ENABLED=False,
)
class ApiV1BookingConfirmTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.url = reverse("api:v1:booking_confirm")

    def _setup_available_slot(self, *, date_value=None):
        customer = self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "ثبت",
                "mobile_number": "09127770001",
                "email": "booking-confirm-customer@example.com",
            }
        )
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        service = self.make_service(
            name="خدمت ثبت رزرو",
            duration_minutes=30,
            buffer_minutes=10,
            is_active=True,
        )
        stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "ثبت",
                "mobile_number": "09127770002",
                "email": "booking-confirm-stylist@example.com",
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

    def _payload(
        self,
        *,
        salon,
        service,
        stylist,
        target_date,
        start_time="10:00",
        payment_method="pay_in_salon",
    ):
        return {
            "salon_slug": salon.slug,
            "service_id": service.pk,
            "stylist_id": stylist.pk,
            "date": target_date.isoformat(),
            "start_time": start_time,
            "payment_method": payment_method,
        }

    def test_booking_confirm_requires_authentication(self):
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

    def test_booking_confirm_creates_pay_in_salon_order_and_detail_only(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        Order = apps.get_model("orders", "Order")
        OrderDetail = apps.get_model("orders", "OrderDetail")
        Payment = apps.get_model("payments", "Payment")
        Wallet = apps.get_model("payments", "Wallet")
        AppointmentNotification = apps.get_model("orders", "AppointmentNotification")

        before_order_count = Order.objects.count()
        before_detail_count = OrderDetail.objects.count()
        before_payment_count = Payment.objects.count()
        before_wallet_count = Wallet.objects.count()
        before_notification_count = AppointmentNotification.objects.count()

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

        self.assertEqual(response.status_code, 201)
        payload = response.json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["confirmed"])
        self.assertEqual(payload["data"]["booking_mode"], "pay_in_salon")

        self.assertEqual(Order.objects.count(), before_order_count + 1)
        self.assertEqual(OrderDetail.objects.count(), before_detail_count + 1)
        self.assertEqual(Payment.objects.count(), before_payment_count)
        self.assertEqual(Wallet.objects.count(), before_wallet_count)
        self.assertEqual(
            AppointmentNotification.objects.count(), before_notification_count
        )

        order = Order.objects.latest("id")
        appointment = OrderDetail.objects.latest("id")

        self.assertEqual(order.customer, customer)
        self.assertEqual(order.salon, salon)
        self.assertEqual(order.status, "pending")
        self.assertTrue(order.is_finally)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.selected_payment_method, "pay_in_salon")
        self.assertFalse(order.requires_online_payment)
        self.assertEqual(order.subtotal_amount, 250000)
        self.assertEqual(order.total_amount, 250000)
        self.assertEqual(order.salon_payout_amount, 250000)
        self.assertEqual(order.booking_source, "customer")

        self.assertEqual(appointment.order, order)
        self.assertEqual(appointment.service, service)
        self.assertEqual(appointment.stylist, stylist)
        self.assertEqual(appointment.salon, salon)
        self.assertEqual(appointment.price, 250000)
        self.assertEqual(appointment.date, target_date)
        self.assertEqual(appointment.time.strftime("%H:%M"), "10:00")
        self.assertEqual(appointment.end_time.strftime("%H:%M"), "10:30")
        self.assertEqual(appointment.scheduled_duration_minutes, 30)
        self.assertEqual(appointment.buffer_minutes, 10)
        self.assertEqual(appointment.occupied_until.strftime("%H:%M"), "10:40")

        self.assertEqual(payload["data"]["order"]["id"], order.pk)
        self.assertEqual(payload["data"]["order"]["status"], "pending")
        self.assertEqual(payload["data"]["order"]["is_paid"], False)
        self.assertEqual(payload["data"]["appointment"]["id"], appointment.pk)
        self.assertEqual(payload["data"]["slot"]["status"], "booked")
        self.assertEqual(payload["data"]["slot"]["occupied_until"], "10:40")
        self.assertEqual(payload["data"]["payment"]["amount_due_now"], 0)
        self.assertEqual(payload["data"]["payment"]["amount_payable_at_salon"], 250000)
        self.assertFalse(payload["data"]["payment"]["payment_created"])
        self.assertFalse(payload["data"]["side_effects"]["wallet_changed"])
        self.assertFalse(payload["data"]["side_effects"]["notification_sent"])

        body = response.content.decode("utf-8")
        self.assertNotIn("09127770001", body)
        self.assertNotIn("booking-confirm-customer@example.com", body)
        self.assertNotIn("09127770002", body)
        self.assertNotIn("booking-confirm-stylist@example.com", body)

    def test_booking_confirm_rechecks_availability_and_blocks_double_submit(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        Order = apps.get_model("orders", "Order")

        payload = self._payload(
            salon=salon,
            service=service,
            stylist=stylist,
            target_date=target_date,
            start_time="10:00",
        )

        first_response = self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )
        second_response = self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(second_response.json()["error"]["code"], "slot_unavailable")
        self.assertEqual(
            Order.objects.filter(customer=customer, salon=salon).count(), 1
        )

    def test_booking_confirm_blocks_existing_booking_with_buffer(self):
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
            end=time(10, 30),
            occupied_until=time(10, 40),
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

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "slot_unavailable")

    def test_booking_confirm_rejects_unsupported_payment_method(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        response = self.client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
                payment_method="online",
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unsupported_payment_method")

    def test_booking_confirm_rejects_foreign_service(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        foreign_service = self.make_service(
            name="خدمت نامرتبط ثبت",
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
                "payment_method": "pay_in_salon",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "service_not_found")

    def test_booking_confirm_rejects_hidden_stylist(self):
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
                "payment_method": "pay_in_salon",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "stylist_not_found")

    def test_booking_confirm_rejects_invalid_date_and_time(self):
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
        self.assertEqual(invalid_date_response.json()["error"]["code"], "invalid_date")

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

    def test_booking_confirm_requires_customer_profile(self):
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

    @override_settings(LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=16)
    def test_booking_confirm_rejects_large_payload(self):
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

    def test_booking_confirm_does_not_require_csrf_for_api_session(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(customer.user)

        response = csrf_client.post(
            self.url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
