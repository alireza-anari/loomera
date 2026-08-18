from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.orders.forms import AppointmentCheckoutForm
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services


class PayInSalonSettlementSecurityTests(TestCase):
    def _user(self, *, mobile, name="کاربر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _customer(self, *, mobile="09126000001"):
        user = self._user(mobile=mobile, name="مشتری", family="تست")
        return Customer.objects.create(user=user)

    def _manager(self, *, mobile="09126000002"):
        user = self._user(mobile=mobile, name="مدیر", family="سالن")
        return SalonManager.objects.create(user=user, is_active=True)

    def _salon(self, *, verification_status="pending"):
        return Salon.objects.create(
            salon_name="سالن تست",
            salon_manager=self._manager(),
            is_active=True,
            verification_status=verification_status,
            address="تهران",
        )

    def _group(self):
        return GroupServices.objects.create(
            group_title="گروه تست",
            slug="test-group",
            group_image="test/group.jpg",
            is_active=True,
        )

    def _service(self, group):
        service = Services.objects.create(
            service_name="خدمت تست",
            slug="test-service",
            is_active=True,
            is_platform_catalog=True,
            duration_minutes=30,
            base_price=100000,
        )
        service.service_group.add(group)
        return service

    def _stylist(self, salon, service, *, mobile="09126000003"):
        stylist = Stylist.objects.create(
            user=self._user(mobile=mobile, name="متخصص", family="تست"),
            is_active=True,
            expert="تست",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        salon.stylists.add(stylist)
        service.stylists.add(stylist)
        return stylist

    def _appointment(
        self,
        *,
        customer=None,
        completed=True,
        is_paid=False,
        verification_status="pending",
        selected_payment_method=AppointmentCheckoutForm.PAYMENT_METHOD_SALON,
    ):
        customer = customer or self._customer()
        salon = self._salon(verification_status=verification_status)
        group = self._group()
        service = self._service(group)
        salon.services.add(service)
        stylist = self._stylist(salon, service)

        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="completed" if completed else "pending",
            is_finally=True,
            is_paid=is_paid,
            service_completed_at=timezone.now() if completed else None,
            selected_payment_method=selected_payment_method,
            total_amount=100000,
        )

        return OrderDetail.objects.create(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            price=100000,
            date=timezone.localdate(),
            time=time(10, 0),
            end_time=time(10, 30),
            service_completed_at=timezone.now() if completed else None,
        )

    def test_settlement_requires_post(self):
        customer = self._customer(mobile="09126000101")
        appointment = self._appointment(customer=customer)

        self.client.force_login(customer.user)

        response = self.client.get(
            reverse("orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk})
        )

        self.assertEqual(response.status_code, 405)

    def test_settlement_requires_owner(self):
        owner = self._customer(mobile="09126000102")
        other = self._customer(mobile="09126000103")
        appointment = self._appointment(customer=owner)

        self.client.force_login(other.user)

        response = self.client.post(
            reverse("orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}),
            data={"payment_action": "cash"},
        )

        self.assertEqual(response.status_code, 404)

    @override_settings(PAY_IN_SALON_SETTLEMENT_POST_MAX_BYTES=20)
    def test_settlement_rejects_large_payload(self):
        customer = self._customer(mobile="09126000104")
        appointment = self._appointment(customer=customer)

        self.client.force_login(customer.user)

        with patch("apps.payments.finance.confirm_pay_in_salon_cash_payment") as mocked:
            response = self.client.post(
                reverse(
                    "orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}
                ),
                data={"payment_action": "cash", "extra": "الف" * 100},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    def test_settlement_rejects_invalid_action(self):
        customer = self._customer(mobile="09126000105")
        appointment = self._appointment(customer=customer)

        self.client.force_login(customer.user)

        with patch("apps.payments.finance.confirm_pay_in_salon_cash_payment") as mocked:
            response = self.client.post(
                reverse(
                    "orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}
                ),
                data={"payment_action": "wire"},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    def test_cash_settlement_requires_completed_service(self):
        customer = self._customer(mobile="09126000106")
        appointment = self._appointment(customer=customer, completed=False)

        self.client.force_login(customer.user)

        with patch("apps.payments.finance.confirm_pay_in_salon_cash_payment") as mocked:
            response = self.client.post(
                reverse(
                    "orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}
                ),
                data={"payment_action": "cash"},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    def test_cash_settlement_calls_finance_service_for_valid_order(self):
        customer = self._customer(mobile="09126000107")
        appointment = self._appointment(customer=customer, completed=True)

        self.client.force_login(customer.user)

        with patch(
            "apps.payments.finance.confirm_pay_in_salon_cash_payment",
            return_value={
                "finalized": False,
                "order": appointment.order,
                "payment": None,
            },
        ) as mocked:
            response = self.client.post(
                reverse(
                    "orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}
                ),
                data={"payment_action": "cash"},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_called_once()

    def test_online_settlement_requires_verified_salon(self):
        customer = self._customer(mobile="09126000108")
        appointment = self._appointment(
            customer=customer,
            completed=True,
            verification_status="pending",
        )

        self.client.force_login(customer.user)

        with patch("apps.payments.gateways.initiate_payment") as mocked:
            response = self.client.post(
                reverse(
                    "orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}
                ),
                data={"payment_action": "online"},
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()

    def test_online_settlement_restores_method_on_gateway_failure(self):
        customer = self._customer(mobile="09126000109")
        appointment = self._appointment(
            customer=customer,
            completed=True,
            verification_status="verified",
        )

        self.client.force_login(customer.user)

        failed_gateway = SimpleNamespace(
            success=False,
            payment_url="",
            code=-2,
            message="gateway failed",
            raw={},
            track_id="",
        )

        with patch(
            "apps.payments.gateways.initiate_payment",
            return_value=failed_gateway,
        ):
            response = self.client.post(
                reverse(
                    "orders:pay_in_salon_settlement", kwargs={"pk": appointment.pk}
                ),
                data={"payment_action": "online"},
            )

        self.assertEqual(response.status_code, 302)

        appointment.order.refresh_from_db()
        self.assertEqual(
            appointment.order.selected_payment_method,
            AppointmentCheckoutForm.PAYMENT_METHOD_SALON,
        )
