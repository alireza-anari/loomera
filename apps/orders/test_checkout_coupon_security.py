from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, Customer
from apps.orders.models import Order


class CheckoutCouponSecurityTests(TestCase):
    def _user(self, *, mobile="09127000001"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name="مشتری",
            family="تست",
            is_active=True,
        )

    def _customer(self, *, mobile="09127000001"):
        user = self._user(mobile=mobile)
        return Customer.objects.create(user=user)

    @override_settings(APPOINTMENT_CHECKOUT_POST_MAX_BYTES=20)
    def test_checkout_rejects_large_payload_before_building_payload(self):
        customer = self._customer(mobile="09127000101")
        self.client.force_login(customer.user)

        with patch("apps.orders.views._build_checkout_payload") as mocked:
            response = self.client.post(
                reverse("orders:checkout"),
                data={
                    "form_action": "confirm_checkout",
                    "coupon_code": "الف" * 100,
                    "payment_method": "pay_in_salon",
                },
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_rejects_unknown_form_action_before_building_payload(self):
        customer = self._customer(mobile="09127000102")
        self.client.force_login(customer.user)

        with patch("apps.orders.views._build_checkout_payload") as mocked:
            response = self.client.post(
                reverse("orders:checkout"),
                data={
                    "form_action": "delete_everything",
                    "coupon_code": "",
                    "payment_method": "pay_in_salon",
                },
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(APPOINTMENT_CHECKOUT_COUPON_CODE_MAX_CHARS=8)
    def test_checkout_rejects_long_coupon_before_building_payload(self):
        customer = self._customer(mobile="09127000103")
        self.client.force_login(customer.user)

        with patch("apps.orders.views._build_checkout_payload") as mocked:
            response = self.client.post(
                reverse("orders:checkout"),
                data={
                    "form_action": "apply_coupon",
                    "coupon_code": "LONG-CODE-123",
                    "payment_method": "pay_in_salon",
                },
            )

        self.assertEqual(response.status_code, 302)
        mocked.assert_not_called()
        self.assertEqual(Order.objects.count(), 0)

    @override_settings(APPOINTMENT_CHECKOUT_COUPON_CODE_MAX_CHARS=8)
    def test_checkout_get_rejects_long_coupon_query(self):
        customer = self._customer(mobile="09127000104")
        self.client.force_login(customer.user)

        response = self.client.get(
            reverse("orders:checkout"),
            data={"coupon": "LONG-CODE-123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].endswith(reverse("orders:reservation_preview"))
        )
        self.assertNotIn("LONG-CODE-123", response["Location"])
