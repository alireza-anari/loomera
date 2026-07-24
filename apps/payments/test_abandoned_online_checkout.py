from __future__ import annotations

from datetime import timedelta
from io import StringIO
import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.payments.gateways import GatewayVerifyResult
from apps.payments.models import Payment
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
    PAYMENT_MODE="mock",
    PAYMENT_PROVIDER="zibal",
    ONLINE_PAYMENT_ENABLED=True,
    STORAGES={
        "default": {
            "BACKEND": (
                "django.core.files.storage."
                "FileSystemStorage"
            ),
        },
        "staticfiles": {
            "BACKEND": (
                "django.contrib.staticfiles.storage."
                "StaticFilesStorage"
            ),
        },
    },
)
class AbandonedOnlineCheckoutTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        super().setUp()

        self.customer = self.make_customer(
            password="StrongPass123!"
        )
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager
        )

    def make_online_order_and_payment(self):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            selected_payment_method="online",
            status="pending",
            is_paid=False,
            is_finally=False,
            total_amount=650_000,
            subtotal_amount=650_000,
            salon_payout_amount=650_000,
        )

        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=650_000,
            description="abandoned online checkout test",
            provider=Payment.Provider.MOCK,
            purpose=Payment.Purpose.APPOINTMENT,
            state=Payment.State.PENDING,
            is_finally=False,
            gateway_track_id=f"mock-{uuid.uuid4().hex}",
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
            meta={
                "request": {
                    "mode": "mock",
                },
            },
        )

        Payment.objects.filter(pk=payment.pk).update(
            update_date=(
                timezone.now() - timedelta(minutes=45)
            )
        )

        payment.refresh_from_db()
        return order, payment

    def test_dry_run_does_not_expire_order_or_payment(self):
        order, payment = self.make_online_order_and_payment()

        out = StringIO()

        call_command(
            "expire_abandoned_online_checkouts",
            "--max-age-minutes=30",
            stdout=out,
        )

        order.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "pending")
        self.assertEqual(payment.state, Payment.State.PENDING)
        self.assertIn("expire_candidate", out.getvalue())

    def test_apply_expires_abandoned_online_checkout(self):
        order, payment = self.make_online_order_and_payment()

        out = StringIO()

        call_command(
            "expire_abandoned_online_checkouts",
            "--apply",
            "--max-age-minutes=30",
            stdout=out,
        )

        order.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)
        self.assertIn(
            "مهلت پرداخت آنلاین",
            order.cancellation_reason,
        )

        self.assertEqual(
            payment.state,
            Payment.State.CANCELLED,
        )
        self.assertFalse(payment.is_finally)
        self.assertTrue(
            payment.meta["abandoned_checkout"]["expired"]
        )
        self.assertIn("expired", out.getvalue())

    def test_verify_pending_payment_is_not_expired(self):
        order, payment = self.make_online_order_and_payment()

        payment.meta = {
            **(payment.meta or {}),
            "verify_pending": {
                "retryable": True,
                "message": "gateway timeout",
            },
        }
        payment.save(update_fields=["meta"])

        Payment.objects.filter(pk=payment.pk).update(
            update_date=(
                timezone.now() - timedelta(minutes=45)
            )
        )

        out = StringIO()

        call_command(
            "expire_abandoned_online_checkouts",
            "--apply",
            "--max-age-minutes=30",
            stdout=out,
        )

        order.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "pending")
        self.assertEqual(
            payment.state,
            Payment.State.PENDING,
        )
        self.assertIn("candidates=0", out.getvalue())

    @patch("apps.payments.views.verify_payment")
    def test_late_success_after_expiration_requires_review_without_reactivating_order(
        self,
        mock_verify,
    ):
        order, payment = self.make_online_order_and_payment()

        call_command(
            "expire_abandoned_online_checkouts",
            "--apply",
            "--max-age-minutes=30",
            stdout=StringIO(),
        )

        order.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(
            payment.state,
            Payment.State.CANCELLED,
        )

        mock_verify.return_value = GatewayVerifyResult(
            success=True,
            retryable=False,
            requires_review=False,
            ref_id=f"ref-{payment.id}",
            track_id=payment.gateway_track_id,
            code=100,
            raw={
                "result": 100,
                "status": 1,
                "amount": 6_500_000,
                "orderId": str(order.id),
                "refNumber": f"ref-{payment.id}",
            },
        )

        response = self.client.get(
            reverse(
                "payments:appointment_verify",
                kwargs={
                    "payment_id": payment.id,
                    "token": payment.callback_token,
                },
            ),
            {
                "trackId": payment.gateway_track_id,
                "status": "2",
            },
        )

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertRedirects(
            response,
            reverse(
                "payments:appointment_result",
                kwargs={
                    "payment_id": payment.id,
                    "token": payment.callback_token,
                },
            ),
            fetch_redirect_response=False,
        )

        self.assertEqual(order.status, "cancelled")
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)

        self.assertEqual(
            payment.state,
            Payment.State.PENDING,
        )
        self.assertFalse(payment.is_finally)

        verify_pending = payment.meta["verify_pending"]

        self.assertTrue(
            verify_pending["requires_review"]
        )
        self.assertIn(
            "late_success_after_abandoned_checkout",
            verify_pending["integrity_errors"],
        )