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
class AppointmentPaymentPendingResultUXTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.make_customer(password="StrongPass123!")
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

    def _make_pending_payment(self, *, verify_pending=None):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            selected_payment_method="online",
            status="pending",
            is_paid=False,
            is_finally=False,
        )
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=120_000,
            description="Pending payment result UX test",
            provider=Payment.Provider.ZIBAL,
            purpose=Payment.Purpose.APPOINTMENT,
            state=Payment.State.PENDING,
            is_finally=False,
            gateway_track_id=f"track-{uuid.uuid4().hex}",
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
            meta={
                "source": "appointment_checkout",
                "verify_pending": verify_pending
                or {
                    "retryable": True,
                    "requires_review": False,
                    "integrity_errors": [],
                    "message": "نتیجه قطعی پرداخت از درگاه دریافت نشد.",
                },
            },
        )
        return order, payment

    def test_pending_payment_result_is_not_rendered_as_failed(self):
        order, payment = self._make_pending_payment()

        response = self.client.get(
            reverse(
                "payments:appointment_result",
                kwargs={
                    "payment_id": payment.id,
                    "token": payment.callback_token,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نتیجه پرداخت هنوز قطعی نیست")
        self.assertContains(response, "دوباره پرداخت نکنید")
        self.assertContains(response, "در حال بررسی پرداخت")
        self.assertContains(response, "پیگیری نوبت")
        self.assertNotContains(response, "پرداخت ناموفق")
        self.assertNotContains(response, "پرداخت تأیید نشد")

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.state, Payment.State.PENDING)
        self.assertFalse(payment.is_finally)
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)

    def test_requires_review_payment_result_uses_manual_review_copy(self):
        order, payment = self._make_pending_payment(
            verify_pending={
                "retryable": False,
                "requires_review": True,
                "integrity_errors": ["amount_mismatch"],
                "message": "نیازمند بررسی دستی",
            }
        )

        response = self.client.get(
            reverse(
                "payments:appointment_result",
                kwargs={
                    "payment_id": payment.id,
                    "token": payment.callback_token,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پرداخت نیاز به بررسی دارد")
        self.assertContains(response, "برای امنیت مالی، وضعیت تراکنش در حال بررسی است")
        self.assertContains(response, "دوباره پرداخت نکنید")
        self.assertNotContains(response, "بازگشت به جزئیات رزرو")

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.state, Payment.State.PENDING)
        self.assertFalse(payment.is_finally)
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)

    def test_plain_pending_payment_without_verify_pending_is_not_rendered_as_failed(
        self,
    ):
        order, payment = self._make_pending_payment(verify_pending={})
        payment.meta = {"source": "appointment_checkout"}
        payment.save(update_fields=["meta"])

        response = self.client.get(
            reverse(
                "payments:appointment_result",
                kwargs={
                    "payment_id": payment.id,
                    "token": payment.callback_token,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نتیجه پرداخت هنوز قطعی نیست")
        self.assertContains(response, "دوباره پرداخت نکنید")
        self.assertContains(response, "در حال بررسی پرداخت")
        self.assertNotContains(response, "پرداخت ناموفق")
        self.assertNotContains(response, "پرداخت تأیید نشد")

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.state, Payment.State.PENDING)
        self.assertFalse(payment.is_finally)
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)
