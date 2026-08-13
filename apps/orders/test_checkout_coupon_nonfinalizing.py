from django.conf import settings
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.orders.models import Order
from apps.orders.views import _clean_appointment_checkout_form_action


class CheckoutActionContractTests(SimpleTestCase):
    def test_missing_form_action_is_rejected_instead_of_defaulting_to_confirm(self):
        request = RequestFactory().post("/orders/checkout/", data={"coupon_code": "TEST"})

        with self.assertRaises(ValidationError):
            _clean_appointment_checkout_form_action(request)


class CheckoutCouponNonFinalizingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(
            mobile_number="09127770001",
            name="مشتری",
            family="تست",
            is_active=True,
        )
        self.client.force_login(self.user)

    def _payload(self, *, coupon=None):
        return {
            "requires_online_payment": False,
            "coupon": coupon,
        }

    @patch("apps.orders.views.AppointmentCheckoutView._render", return_value=HttpResponse("preview"))
    @patch("apps.orders.views._build_checkout_payload")
    def test_apply_coupon_never_creates_order(self, build_payload, mocked_render):
        build_payload.return_value = self._payload(coupon=None)

        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "form_action": "apply_coupon",
                "coupon_code": "",
                "payment_method": "pay_in_salon",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        mocked_render.assert_called_once()

    @patch("apps.orders.views._build_checkout_payload")
    def test_implicit_submit_cannot_create_order(self, build_payload):
        response = self.client.post(
            reverse("orders:checkout"),
            data={
                "coupon_code": "TEST",
                "payment_method": "pay_in_salon",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)
        build_payload.assert_not_called()


class CheckoutCouponActionTransportStaticGuardTests(SimpleTestCase):
    def test_coupon_action_is_proxied_before_native_submit(self):
        script = Path(settings.BASE_DIR, "static/js/pages/booking_checkout_submit_guard.js").read_text(encoding="utf-8")
        self.assertIn("ensureActionProxy(form, action);", script)
        self.assertIn("form.dataset.checkoutRequestedAction = action;", script)

    def test_enter_on_coupon_explicitly_requests_apply_action(self):
        script = Path(settings.BASE_DIR, "static/js/pages/booking_checkout_submit_guard.js").read_text(encoding="utf-8")
        self.assertIn('event.key !== "Enter"', script)
        self.assertIn("ensureActionProxy(form, APPLY_COUPON_ACTION);", script)

    def test_backend_reads_all_form_action_values_fail_closed(self):
        source = Path(settings.BASE_DIR, "apps/orders/views.py").read_text(encoding="utf-8")
        self.assertIn('request.POST.getlist("form_action")', source)
        self.assertIn("valid_actions[-1] if valid_actions else", source)
