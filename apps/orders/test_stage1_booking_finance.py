from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.booking_utils import resolve_booking_sequence, slot_is_available
from apps.orders.forms import AppointmentCheckoutForm
from apps.payments.finance import cancel_order_with_financials
from apps.payments.models import Payment, Wallet, WalletTransaction
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    PLATFORM_FIRST_VISIT_COMMISSION_PERCENT=0,
    PAYMENT_MODE="mock",
    ONLINE_PAYMENT_ENABLED=True,
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class Stage1BookingFinanceTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_customer(password="StrongPass123!")
        self.manager = self.make_salon_manager()
        self.stylist = self.make_stylist()
        self.service = self.make_service(duration_minutes=30)
        self.salon = self.make_salon(manager=self.manager, cancellation_window_hours=24, cancellation_refund_percent=80)
        self.connect_service(salon=self.salon, stylist=self.stylist, service=self.service, price=120_000)
        self.target_date = timezone.localdate() + timedelta(days=3)
        self.add_schedule(
            stylist=self.stylist,
            salon=self.salon,
            service=self.service,
            date_value=self.target_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("14:00", "%H:%M").time(),
        )

    def test_resolve_booking_sequence_allows_next_service_at_previous_service_end_ignoring_buffer(self):
        self.service.duration_minutes = 60
        self.service.buffer_minutes = 15
        self.service.save(update_fields=["duration_minutes", "buffer_minutes"])

        second_service = self.make_service(name="Color", duration_minutes=30)
        second_service.buffer_minutes = 10
        second_service.save(update_fields=["buffer_minutes"])

        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=second_service,
            price=140_000,
        )

        self.add_schedule(
            stylist=self.stylist,
            salon=self.salon,
            service=second_service,
            date_value=self.target_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("14:00", "%H:%M").time(),
        )

        stylist_selections = [
            {
                "serviceId": self.service.id,
                "stylistId": str(self.stylist.user_id),
                "requestedStylistId": str(self.stylist.user_id),
            },
            {
                "serviceId": second_service.id,
                "stylistId": str(self.stylist.user_id),
                "requestedStylistId": str(self.stylist.user_id),
            },
        ]

        datetime_selections = {
            f"{self.stylist.user_id}_{self.service.id}": {
                "date": self.target_date.isoformat(),
                "time": "10:00",
            },
            f"{self.stylist.user_id}_{second_service.id}": {
                "date": self.target_date.isoformat(),
                "time": "11:00",
            },
        }

        resolved = resolve_booking_sequence(
            salon=self.salon,
            stylist_selections=stylist_selections,
            datetime_selections=datetime_selections,
        )

        self.assertEqual(len(resolved), 2)
        self.assertEqual(resolved[0].start_time.strftime("%H:%M"), "10:00")
        self.assertEqual(resolved[0].end_time.strftime("%H:%M"), "11:00")
        self.assertEqual(resolved[1].start_time.strftime("%H:%M"), "11:00")

    def test_slot_is_available_rejects_overlap_with_existing_booking(self):
        order = self.make_order(customer=self.customer, salon=self.salon, selected_payment_method="wallet")
        self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.target_date,
            start=timezone.datetime.strptime("11:00", "%H:%M").time(),
            end=timezone.datetime.strptime("11:30", "%H:%M").time(),
            price=120_000,
        )

        available = slot_is_available(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
            date_value=self.target_date,
            start_time=timezone.datetime.strptime("11:15", "%H:%M").time(),
            duration_minutes=30,
        )

        self.assertFalse(available)

    def test_slot_is_available_rejects_time_off_overlap(self):
        self.add_time_off(
            stylist=self.stylist,
            date_value=self.target_date,
            start=timezone.datetime.strptime("12:00", "%H:%M").time(),
            end=timezone.datetime.strptime("13:00", "%H:%M").time(),
        )

        available = slot_is_available(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
            date_value=self.target_date,
            start_time=timezone.datetime.strptime("12:15", "%H:%M").time(),
            duration_minutes=30,
        )

        self.assertFalse(available)

    def test_resolve_booking_sequence_rejects_non_sequential_same_day_times(self):
        second_service = self.make_service(name="Color", duration_minutes=30)
        self.connect_service(salon=self.salon, stylist=self.stylist, service=second_service, price=140_000)
        self.add_schedule(
            stylist=self.stylist,
            salon=self.salon,
            service=second_service,
            date_value=self.target_date,
            start=timezone.datetime.strptime("10:30", "%H:%M").time(),
            end=timezone.datetime.strptime("14:00", "%H:%M").time(),
        )

        stylist_selections = [
            {"serviceId": self.service.id, "stylistId": str(self.stylist.user_id), "requestedStylistId": str(self.stylist.user_id)},
            {"serviceId": second_service.id, "stylistId": str(self.stylist.user_id), "requestedStylistId": str(self.stylist.user_id)},
        ]
        datetime_selections = {
            f"{self.stylist.user_id}_{self.service.id}": {"date": self.target_date.isoformat(), "time": "11:00"},
            f"{self.stylist.user_id}_{second_service.id}": {"date": self.target_date.isoformat(), "time": "10:30"},
        }

        with self.assertRaises(ValidationError):
            resolve_booking_sequence(
                salon=self.salon,
                stylist_selections=stylist_selections,
                datetime_selections=datetime_selections,
            )

    def test_checkout_form_blocks_pay_in_salon_for_first_visit(self):
        form = AppointmentCheckoutForm(
            data={"payment_method": AppointmentCheckoutForm.PAYMENT_METHOD_SALON},
            requires_online_payment=True,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("payment_method", form.errors)

    @override_settings(ONLINE_PAYMENT_ENABLED=False)
    def test_checkout_form_beta_mode_allows_only_pay_in_salon(self):
        form = AppointmentCheckoutForm(
            data={"payment_method": AppointmentCheckoutForm.PAYMENT_METHOD_SALON},
            requires_online_payment=True,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.fields["payment_method"].choices,
            [(AppointmentCheckoutForm.PAYMENT_METHOD_SALON, "پرداخت در مجموعه")],
        )

        tampered = AppointmentCheckoutForm(
            data={"payment_method": AppointmentCheckoutForm.PAYMENT_METHOD_WALLET},
            requires_online_payment=False,
        )

        self.assertFalse(tampered.is_valid())
        self.assertIn("payment_method", tampered.errors)

    @patch("apps.orders.views.notify_manager_and_stylists_for_booking")
    @patch("apps.orders.views.schedule_order_reminder")
    @patch("apps.payments.finance.sync_settlement_for_order")
    def test_checkout_wallet_payment_creates_paid_order_and_wallet_payment(
        self,
        mock_sync_settlement,
        _mock_schedule_reminder,
        _mock_notify,
    ):
        wallet, _ = Wallet.objects.get_or_create(user=self.customer.user)
        wallet.balance = 200_000
        wallet.save(update_fields=["balance"])
        self.client.force_login(self.customer.user)
        session = self.client.session
        session["salon_id"] = self.salon.id
        session["stylist_selections"] = [
            {
                "serviceId": self.service.id,
                "stylistId": str(self.stylist.user_id),
                "requestedStylistId": str(self.stylist.user_id),
                "serviceName": self.service.service_name,
            }
        ]
        session["datetime_selections"] = {
            f"{self.stylist.user_id}_{self.service.id}": {
                "date": self.target_date.isoformat(),
                "time": "10:00",
            }
        }
        session.save()

        response = self.client.post(
            reverse("orders:checkout"),
            {
                "payment_method": AppointmentCheckoutForm.PAYMENT_METHOD_WALLET,
                "coupon_code": "",
                "form_action": "confirm_checkout",
            },
        )

        order = self.customer.orders.latest("id")
        payment = Payment.objects.get(order=order)
        self.customer.user.wallet.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("payments:appointment_result", kwargs={"payment_id": payment.id, "token": payment.callback_token}),
            fetch_redirect_response=False,
        )
        self.assertEqual(order.status, "paid")
        self.assertTrue(order.is_paid)
        self.assertTrue(order.is_finally)
        self.assertEqual(order.selected_payment_method, "wallet")
        self.assertEqual(int(self.customer.user.wallet.balance), 80_000)
        self.assertEqual(payment.provider, Payment.Provider.WALLET)
        self.assertEqual(payment.state, Payment.State.SUCCESS)
        self.assertTrue(
            WalletTransaction.objects.filter(
                wallet=self.customer.user.wallet,
                transaction_type=WalletTransaction.TransactionType.PURCHASE,
                order=order,
            ).exists()
        )
        mock_sync_settlement.assert_called_once()

    def test_cancel_order_with_financials_refunds_wallet_once(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.customer.user)
        wallet.balance = 0
        wallet.save(update_fields=["balance"])
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            selected_payment_method="wallet",
            status="paid",
            is_paid=True,
            is_finally=True,
            total_amount=100_000,
            salon_payout_amount=100_000,
        )
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=100_000,
            description="Wallet appointment",
            provider=Payment.Provider.WALLET,
            purpose=Payment.Purpose.APPOINTMENT,
            state=Payment.State.SUCCESS,
            is_finally=True,
            callback_token="token-1",
            idempotency_key="idem-1",
        )

        first = cancel_order_with_financials(order=order, payment=payment)
        second = cancel_order_with_financials(order=order, payment=payment)

        order.refresh_from_db()
        self.customer.user.wallet.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(first.refund_amount, 80_000)
        self.assertEqual(second.refund_amount, 80_000)
        self.assertEqual(int(order.refunded_to_wallet_amount), 80_000)
        self.assertEqual(int(self.customer.user.wallet.balance), 80_000)
        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=self.customer.user.wallet,
                transaction_type=WalletTransaction.TransactionType.REFUND,
                order=order,
            ).count(),
            1,
        )

    def test_cancel_appointment_endpoint_denies_other_customer(self):
        other_customer = self.make_customer(password="StrongPass123!")
        order = self.make_order(customer=self.customer, salon=self.salon, selected_payment_method="pay_in_salon", status="pending", is_paid=False)
        appointment = self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.target_date,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("10:30", "%H:%M").time(),
            price=120_000,
        )
        self.client.force_login(other_customer.user)

        response = self.client.post(reverse("orders:cancel_appointment", kwargs={"pk": appointment.pk}))

        self.assertEqual(response.status_code, 404)
