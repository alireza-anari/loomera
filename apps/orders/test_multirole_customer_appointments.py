"""Regression coverage for multirole customer appointment access."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Customer, SalonManager, Stylist
from apps.orders.models import Order
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class MultiroleCustomerAppointmentsTests(Stage1DomainFactoryMixin, TestCase):
    def _open_appointments(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("orders:appointments"))

    def test_two_salon_manager_can_open_personal_appointments(self):
        user = self.make_user()
        Customer.objects.create(user=user)
        manager = SalonManager.objects.create(user=user, is_active=True)
        self.make_salon(manager=manager)
        self.make_salon(manager=manager)

        response = self._open_appointments(user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("orders:appointments"))

    def test_stylist_can_open_personal_appointments(self):
        user = self.make_user()
        Customer.objects.create(user=user)
        Stylist.objects.create(user=user, expert="زیبایی", is_active=True)

        response = self._open_appointments(user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("orders:appointments"))

    def test_manager_and_stylist_can_open_personal_appointments(self):
        user = self.make_user()
        Customer.objects.create(user=user)
        SalonManager.objects.create(user=user, is_active=True)
        Stylist.objects.create(user=user, expert="زیبایی", is_active=True)

        response = self._open_appointments(user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("orders:appointments"))

    def test_professional_without_customer_gets_safe_lazy_customer(self):
        user = self.make_user()
        SalonManager.objects.create(user=user, is_active=True)
        self.assertFalse(Customer.objects.filter(user=user).exists())

        response = self._open_appointments(user)

        self.assertEqual(response.status_code, 200)
        customer = Customer.objects.get(user=user)
        self.assertFalse(customer.notify_marketing_email)
        self.assertFalse(customer.notify_marketing_sms)
        self.assertFalse(customer.notify_marketing_whatsapp)

    @override_settings(ONLINE_PAYMENT_ENABLED=False, PAYMENT_MODE="mock")
    @patch("apps.orders.views.notify_manager_and_stylists_for_booking")
    @patch("apps.orders.views.schedule_order_reminder")
    @patch("apps.payments.finance.sync_settlement_for_order")
    def test_multisalon_manager_checkout_lands_on_customer_appointments(
        self, mock_sync_settlement, _mock_schedule_reminder, _mock_notify
    ):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user, is_active=True)
        salon = self.make_salon(manager=manager)
        self.make_salon(manager=manager)
        stylist = self.make_stylist()
        service = self.make_service(name="خدمت رزرو چندنقشی", duration_minutes=30)
        self.connect_service(
            salon=salon, stylist=stylist, service=service, price=120_000
        )
        target_date = timezone.localdate() + timedelta(days=3)
        self.add_schedule(
            stylist=stylist,
            salon=salon,
            service=service,
            date_value=target_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        self.client.force_login(user)
        session = self.client.session
        session["salon_id"] = salon.pk
        session["stylist_selections"] = [
            {
                "serviceId": service.pk,
                "stylistId": str(stylist.user_id),
                "requestedStylistId": str(stylist.user_id),
                "serviceName": service.service_name,
            }
        ]
        session["datetime_selections"] = {
            f"{stylist.user_id}_{service.pk}": {
                "date": target_date.isoformat(),
                "time": "10:00",
            }
        }
        session.save()

        preview = self.client.get(reverse("orders:reservation_preview"))
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(Customer.objects.filter(user=user).exists())

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "form_action": "confirm_checkout",
                "coupon_code": "",
                "payment_method": "pay_in_salon",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], reverse("orders:appointments"))
        self.assertEqual(response.request["PATH_INFO"], reverse("orders:appointments"))
        self.assertEqual(Order.objects.filter(customer__user=user).count(), 1)
        mock_sync_settlement.assert_called_once()
