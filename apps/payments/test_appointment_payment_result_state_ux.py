from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.payments.models import Payment
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    ONLINE_PAYMENT_ENABLED=True,
    PAYMENT_MODE="mock",
)
class AppointmentPaymentResultStateUXTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_customer(password="StrongPass123!")
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

    def _make_payment(self, *, state, order_status="pending", meta=None):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            selected_payment_method="online",
            status=order_status,
            is_paid=False,
            is_finally=False,
        )
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=120_000,
            description="Appointment result state UX test",
            provider=Payment.Provider.ZIBAL,
            purpose=Payment.Purpose.APPOINTMENT,
            state=state,
            is_finally=state
            in {Payment.State.SUCCESS, Payment.State.FAILED, Payment.State.CANCELLED},
            gateway_track_id=f"track-{uuid.uuid4().hex}",
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
            meta=meta or {"source": "appointment_checkout"},
        )
        return order, payment

    def _get_result(self, payment):
        return self.client.get(
            reverse(
                "payments:appointment_result",
                kwargs={
                    "payment_id": payment.id,
                    "token": payment.callback_token,
                },
            )
        )

    def test_expired_checkout_result_has_dedicated_copy(self):
        order, payment = self._make_payment(
            state=Payment.State.CANCELLED,
            order_status="cancelled",
            meta={
                "source": "appointment_checkout",
                "abandoned_checkout": {
                    "expired": True,
                    "reason": "مهلت پرداخت آنلاین به پایان رسید و رزرو آزاد شد.",
                },
            },
        )

        response = self._get_result(payment)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مهلت پرداخت به پایان رسید")
        self.assertContains(response, "رزرو زمان جدید")
        self.assertContains(response, "زمان انتخاب‌شده آزاد شده است")
        self.assertNotContains(response, "پرداخت توسط شما لغو شد")

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.state, Payment.State.CANCELLED)
        self.assertEqual(order.status, "cancelled")

    def test_cancelled_payment_result_is_not_rendered_as_expired(self):
        order, payment = self._make_payment(
            state=Payment.State.CANCELLED,
            order_status="cancelled",
            meta={"source": "appointment_checkout"},
        )

        response = self._get_result(payment)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پرداخت توسط شما لغو شد")
        self.assertContains(response, "تلاش دوباره برای رزرو")
        self.assertNotContains(response, "مهلت پرداخت به پایان رسید")

    def test_failed_payment_result_has_failed_copy_and_support_cta(self):
        order, payment = self._make_payment(
            state=Payment.State.FAILED,
            order_status="cancelled",
            meta={"source": "appointment_checkout"},
        )

        response = self._get_result(payment)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پرداخت ناموفق بود")
        self.assertContains(response, "پیگیری با پشتیبانی")
        self.assertNotContains(response, "دوباره پرداخت نکنید")
        self.assertNotContains(response, "مهلت پرداخت به پایان رسید")

    def test_success_result_keeps_success_copy(self):
        order, payment = self._make_payment(
            state=Payment.State.SUCCESS,
            order_status="confirmed",
            meta={"source": "appointment_checkout"},
        )
        order.is_paid = True
        order.is_finally = True
        order.save(update_fields=["is_paid", "is_finally"])

        response = self._get_result(payment)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "رزروت ثبت شد")
        self.assertContains(response, "مشاهده نوبت‌ها")
        self.assertNotContains(response, "پرداخت ناموفق بود")
        self.assertNotContains(response, "مهلت پرداخت به پایان رسید")
