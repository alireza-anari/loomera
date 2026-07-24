from datetime import datetime, time, timedelta
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
            "LOCATION": "api-booking-security-tests",
        }
    },
    LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=4 * 1024,
    LOOMERA_API_PUBLIC_LIST_MAX_LIMIT=50,
    ONLINE_PAYMENT_ENABLED=False,
)
class ApiV1BookingSecurityRegressionTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.confirm_url = reverse("api:v1:booking_confirm")
        self.my_appointments_url = reverse("api:v1:my_appointments")
        self._setup_index = 0

    def _add_minutes(self, date_value, start_time, minutes):
        return (
            (datetime.combine(date_value, start_time) + timedelta(minutes=minutes))
            .time()
            .replace(second=0, microsecond=0)
        )

    def _setup_available_slot(
        self, *, customer=None, date_value=None, start=time(10, 0)
    ):
        self._setup_index += 1
        unique_index = self._setup_index

        customer = customer or self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "امنیت",
                "mobile_number": f"0912997{unique_index:04d}",
                "email": f"booking-security-customer-{unique_index}@example.com",
            }
        )

        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)
        service = self.make_service(
            name=f"خدمت امنیت رزرو {unique_index}",
            duration_minutes=30,
            buffer_minutes=10,
            is_active=True,
        )
        stylist = self.make_stylist(
            user_kwargs={
                "name": "متخصص",
                "family": "امنیت",
                "mobile_number": f"0912998{unique_index:04d}",
                "email": f"booking-security-stylist-{unique_index}@example.com",
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
            start=start,
            end=self._add_minutes(target_date, start, 120),
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

    def _detail_url(self, appointment):
        return reverse(
            "api:v1:my_appointment_detail",
            kwargs={"appointment_id": appointment.pk},
        )

    def _model_counts(self):
        Order = apps.get_model("orders", "Order")
        OrderDetail = apps.get_model("orders", "OrderDetail")
        Payment = apps.get_model("payments", "Payment")
        Wallet = apps.get_model("payments", "Wallet")
        AppointmentNotification = apps.get_model("orders", "AppointmentNotification")

        return {
            "orders": Order.objects.count(),
            "details": OrderDetail.objects.count(),
            "payments": Payment.objects.count(),
            "wallets": Wallet.objects.count(),
            "notifications": AppointmentNotification.objects.count(),
        }

    def test_confirm_requires_authentication_and_creates_nothing(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        before = self._model_counts()

        response = self.client.post(
            self.confirm_url,
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
        self.assertEqual(self._model_counts(), before)

    def test_confirm_rejects_online_payment_and_creates_nothing(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        before = self._model_counts()

        response = self.client.post(
            self.confirm_url,
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
        self.assertEqual(self._model_counts(), before)

    def test_confirm_rejects_foreign_service_and_creates_nothing(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        foreign_service = self.make_service(
            name="خدمت نامرتبط امنیتی",
            duration_minutes=30,
            is_active=True,
        )

        before = self._model_counts()

        response = self.client.post(
            self.confirm_url,
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
        self.assertEqual(self._model_counts(), before)

    def test_confirm_rejects_hidden_stylist_and_creates_nothing(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        hidden_stylist = self.make_stylist(
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        self.connect_service(salon=salon, stylist=hidden_stylist, service=service)

        before = self._model_counts()

        response = self.client.post(
            self.confirm_url,
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
        self.assertEqual(self._model_counts(), before)

    def test_confirm_double_submit_creates_only_one_booking(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        Order = apps.get_model("orders", "Order")
        OrderDetail = apps.get_model("orders", "OrderDetail")

        payload = self._payload(
            salon=salon,
            service=service,
            stylist=stylist,
            target_date=target_date,
            start_time="10:00",
        )

        first_response = self.client.post(
            self.confirm_url,
            data=payload,
            content_type="application/json",
        )
        second_response = self.client.post(
            self.confirm_url,
            data=payload,
            content_type="application/json",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(second_response.json()["error"]["code"], "slot_unavailable")

        self.assertEqual(
            Order.objects.filter(
                customer=customer,
                salon=salon,
                selected_payment_method="pay_in_salon",
            ).count(),
            1,
        )
        self.assertEqual(
            OrderDetail.objects.filter(
                order__customer=customer,
                salon=salon,
                service=service,
                stylist=stylist,
                date=target_date,
                time=time(10, 0),
            ).count(),
            1,
        )

    def test_confirm_pay_in_salon_creates_no_payment_wallet_or_notification(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        Payment = apps.get_model("payments", "Payment")
        Wallet = apps.get_model("payments", "Wallet")
        AppointmentNotification = apps.get_model("orders", "AppointmentNotification")

        before_payment_count = Payment.objects.count()
        before_wallet_count = Wallet.objects.count()
        before_notification_count = AppointmentNotification.objects.count()

        with patch(
            "apps.api.v1.booking_views.get_price_for_stylist_service",
            return_value=300000,
        ):
            response = self.client.post(
                self.confirm_url,
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

        self.assertEqual(payload["data"]["payment"]["mode"], "pay_in_salon")
        self.assertEqual(payload["data"]["payment"]["amount_due_now"], 0)
        self.assertEqual(payload["data"]["payment"]["amount_payable_at_salon"], 300000)
        self.assertFalse(payload["data"]["payment"]["payment_created"])
        self.assertFalse(payload["data"]["side_effects"]["payment_created"])
        self.assertFalse(payload["data"]["side_effects"]["wallet_changed"])
        self.assertFalse(payload["data"]["side_effects"]["notification_sent"])

        self.assertEqual(Payment.objects.count(), before_payment_count)
        self.assertEqual(Wallet.objects.count(), before_wallet_count)
        self.assertEqual(
            AppointmentNotification.objects.count(), before_notification_count
        )

    def test_confirm_response_does_not_leak_private_data(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        response = self.client.post(
            self.confirm_url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        body = response.content.decode("utf-8")
        self.assertNotIn(customer.user.mobile_number, body)
        self.assertNotIn(customer.user.email, body)
        self.assertNotIn(stylist.user.mobile_number, body)
        self.assertNotIn(stylist.user.email, body)

    def test_my_appointment_detail_idor_returns_404_without_leak(self):
        owner_customer, salon, service, stylist, target_date = (
            self._setup_available_slot()
        )
        attacker_customer = self.make_customer(
            user_kwargs={
                "name": "مشتری",
                "family": "مهاجم",
                "mobile_number": "09129990001",
                "email": "booking-security-attacker@example.com",
            }
        )

        owner_client = Client()
        owner_client.force_login(owner_customer.user)

        confirm_response = owner_client.post(
            self.confirm_url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )
        self.assertEqual(confirm_response.status_code, 201)
        appointment_id = confirm_response.json()["data"]["appointment"]["id"]

        attacker_client = Client()
        attacker_client.force_login(attacker_customer.user)

        response = attacker_client.get(
            reverse(
                "api:v1:my_appointment_detail",
                kwargs={"appointment_id": appointment_id},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "appointment_not_found")

        body = response.content.decode("utf-8")
        self.assertNotIn(owner_customer.user.mobile_number, body)
        self.assertNotIn(owner_customer.user.email, body)
        self.assertNotIn(stylist.user.mobile_number, body)
        self.assertNotIn(stylist.user.email, body)
        self.assertNotIn(str(appointment_id), body)

    def test_my_appointments_get_is_read_only(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        confirm_response = self.client.post(
            self.confirm_url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )
        self.assertEqual(confirm_response.status_code, 201)

        Order = apps.get_model("orders", "Order")
        OrderDetail = apps.get_model("orders", "OrderDetail")
        order = Order.objects.latest("id")
        appointment = OrderDetail.objects.latest("id")

        before_order_count = Order.objects.count()
        before_detail_count = OrderDetail.objects.count()
        before_order_status = order.status
        before_confirmation_status = appointment.confirmation_status
        before_lifecycle_status = appointment.lifecycle_status

        list_response = self.client.get(self.my_appointments_url)
        detail_response = self.client.get(self._detail_url(appointment))

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)

        order.refresh_from_db()
        appointment.refresh_from_db()

        self.assertEqual(Order.objects.count(), before_order_count)
        self.assertEqual(OrderDetail.objects.count(), before_detail_count)
        self.assertEqual(order.status, before_order_status)
        self.assertEqual(appointment.confirmation_status, before_confirmation_status)
        self.assertEqual(appointment.lifecycle_status, before_lifecycle_status)

    def test_booking_api_posts_do_not_require_csrf_for_api_session(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(customer.user)

        response = csrf_client.post(
            self.confirm_url,
            data=self._payload(
                salon=salon,
                service=service,
                stylist=stylist,
                target_date=target_date,
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

    def test_confirm_rejects_large_payload_without_creating_anything(self):
        customer, salon, service, stylist, target_date = self._setup_available_slot()
        self.client.force_login(customer.user)

        before = self._model_counts()

        with override_settings(LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=16):
            response = self.client.post(
                self.confirm_url,
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
        self.assertEqual(self._model_counts(), before)
