from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid

import requests
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.payments.gateways import (
    GatewayVerifyResult,
    verify_payment,
)
from apps.payments.models import (
    Payment,
    Wallet,
    WalletTransaction,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

@override_settings(
    PAYMENT_MODE="sandbox",
    PAYMENT_PROVIDER="zibal",
    ZIBAL_SANDBOX_MERCHANT="zibal",
)
class GatewayVerifyClassificationTests(SimpleTestCase):
    def make_gateway_payment(
        self,
        *,
        payment_id=1,
        order_id=None,
        amount=120_000,
        track_id="track-1",
    ):
        return SimpleNamespace(
            id=payment_id,
            pk=payment_id,
            order_id=order_id,
            amount=amount,
            gateway_track_id=track_id,
        )

    @patch("apps.payments.gateways.requests.post")
    def test_network_error_is_retryable(self, mock_post):
        mock_post.side_effect = requests.Timeout(
            "gateway timeout"
        )

        payment = self.make_gateway_payment(
            payment_id=1,
            track_id="track-1",
        )

        result = verify_payment(
            payment=payment,
            track_id="track-1",
        )

        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertFalse(result.requires_review)
        self.assertEqual(result.track_id, "track-1")

    @patch("apps.payments.gateways.requests.post")
    def test_invalid_json_is_retryable(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError(
            "invalid json"
        )
        mock_post.return_value = response

        payment = self.make_gateway_payment(
            payment_id=2,
            track_id="track-2",
        )

        result = verify_payment(
            payment=payment,
            track_id="track-2",
        )

        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertFalse(result.requires_review)

    @patch("apps.payments.gateways.requests.post")
    def test_gateway_decline_is_not_retryable(
        self,
        mock_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": 202,
            "message": "transaction not found",
            "trackId": "track-3",
        }
        mock_post.return_value = response

        payment = self.make_gateway_payment(
            payment_id=3,
            track_id="track-3",
        )

        result = verify_payment(
            payment=payment,
            track_id="track-3",
        )

        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertFalse(result.requires_review)
        self.assertEqual(result.code, 202)

    @patch("apps.payments.gateways.requests.post")
    def test_track_id_mismatch_requires_review_without_request(
        self,
        mock_post,
    ):
        payment = self.make_gateway_payment(
            payment_id=10,
            amount=120_000,
            track_id="stored-track",
        )

        result = verify_payment(
            payment=payment,
            track_id="different-track",
        )

        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertTrue(result.requires_review)
        self.assertIn(
            "track_id_mismatch",
            result.integrity_errors,
        )
        mock_post.assert_not_called()

    @patch("apps.payments.gateways.requests.post")
    def test_amount_mismatch_requires_review(
        self,
        mock_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 999_000,
            "orderId": "11",
            "refNumber": "ref-11",
        }
        mock_post.return_value = response

        payment = self.make_gateway_payment(
            payment_id=11,
            order_id=None,
            amount=120_000,
            track_id="track-11",
        )

        result = verify_payment(
            payment=payment,
            track_id="track-11",
        )

        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertTrue(result.requires_review)
        self.assertIn(
            "amount_mismatch",
            result.integrity_errors,
        )

    @patch("apps.payments.gateways.requests.post")
    def test_order_id_mismatch_requires_review(
        self,
        mock_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1_200_000,
            "orderId": "999",
            "refNumber": "ref-12",
        }
        mock_post.return_value = response

        payment = self.make_gateway_payment(
            payment_id=12,
            order_id=500,
            amount=120_000,
            track_id="track-12",
        )

        result = verify_payment(
            payment=payment,
            track_id="track-12",
        )

        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertTrue(result.requires_review)
        self.assertIn(
            "order_id_mismatch",
            result.integrity_errors,
        )

    @patch("apps.payments.gateways.requests.post")
    def test_matching_verified_payment_succeeds(
        self,
        mock_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": 100,
            "status": 1,
            "amount": 1_200_000,
            "orderId": "700",
            "refNumber": "ref-13",
            "cardNumber": "6037-****-****-1234",
        }
        mock_post.return_value = response

        payment = self.make_gateway_payment(
            payment_id=13,
            order_id=700,
            amount=120_000,
            track_id="track-13",
        )

        result = verify_payment(
            payment=payment,
            track_id="track-13",
        )

        self.assertTrue(result.success)
        self.assertFalse(result.retryable)
        self.assertFalse(result.requires_review)
        self.assertEqual(result.ref_id, "ref-13")

@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
    PAYMENT_MODE="sandbox",
    PAYMENT_PROVIDER="zibal",
    ZIBAL_SANDBOX_MERCHANT="zibal",
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
class RetryableVerifyCallbackTests(
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

    def make_payment(
        self,
        *,
        purpose,
        order=None,
        amount=120_000,
    ):
        return Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=amount,
            description=(
                "Gateway verify resilience test"
            ),
            provider=Payment.Provider.ZIBAL,
            purpose=purpose,
            state=Payment.State.PENDING,
            is_finally=False,
            gateway_track_id=(
                f"track-{uuid.uuid4().hex}"
            ),
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
        )

    @patch(
        "apps.payments.views."
        "notify_wallet_charge_failed"
    )
    @patch("apps.payments.views.verify_payment")
    def test_wallet_retryable_verify_stays_pending_without_deposit(
        self,
        mock_verify,
        mock_notify_failed,
    ):
        payment = self.make_payment(
            purpose=Payment.Purpose.WALLET
        )

        wallet, _ = Wallet.objects.get_or_create(
            user=self.customer.user
        )
        initial_balance = int(wallet.balance)

        mock_verify.return_value = GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=payment.gateway_track_id,
            message=(
                "نتیجه قطعی پرداخت از درگاه "
                "دریافت نشد."
            ),
        )

        response = self.client.get(
            reverse(
                "payments:charge_verify",
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
        wallet.refresh_from_db()

        self.assertRedirects(
            response,
            reverse("payments:detail"),
            fetch_redirect_response=False,
        )

        self.assertEqual(
            payment.state,
            Payment.State.PENDING,
        )
        self.assertFalse(payment.is_finally)
        self.assertIsNone(payment.status_code)
        self.assertTrue(
            payment.meta["verify_pending"]["retryable"]
        )
        self.assertEqual(
            int(wallet.balance),
            initial_balance,
        )
        self.assertFalse(
            WalletTransaction.objects.filter(
                wallet=wallet
            ).exists()
        )

        mock_notify_failed.assert_not_called()

    @patch(
        "apps.payments.views."
        "cancel_order_with_financials"
    )
    @patch(
        "apps.payments.views.notify_payment_failed"
    )
    @patch("apps.payments.views.verify_payment")
    def test_appointment_retryable_verify_keeps_order_and_payment_pending(
        self,
        mock_verify,
        mock_notify_failed,
        mock_cancel_order,
    ):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            selected_payment_method="online",
            status="pending",
            is_paid=False,
            is_finally=False,
        )

        payment = self.make_payment(
            purpose=Payment.Purpose.APPOINTMENT,
            order=order,
        )

        mock_verify.return_value = GatewayVerifyResult(
            success=False,
            retryable=True,
            track_id=payment.gateway_track_id,
            message=(
                "نتیجه قطعی پرداخت از درگاه "
                "دریافت نشد."
            ),
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

        self.assertEqual(
            payment.state,
            Payment.State.PENDING,
        )
        self.assertFalse(payment.is_finally)
        self.assertTrue(
            payment.meta["verify_pending"]["retryable"]
        )

        self.assertEqual(order.status, "pending")
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)

        mock_cancel_order.assert_not_called()
        mock_notify_failed.assert_not_called()

@patch("apps.payments.views.verify_payment")
def test_retryable_verify_does_not_reopen_cancelled_payment(
    self,
    mock_verify,
):
    order = self.make_order(
        customer=self.customer,
        salon=self.salon,
        selected_payment_method="online",
        status="cancelled",
        is_paid=False,
        is_finally=False,
    )

    payment = self.make_payment(
        purpose=Payment.Purpose.APPOINTMENT,
        order=order,
    )
    payment.state = Payment.State.CANCELLED
    payment.is_finally = False
    payment.save(update_fields=["state", "is_finally"])

    mock_verify.return_value = GatewayVerifyResult(
        success=False,
        retryable=True,
        track_id=payment.gateway_track_id,
        message="gateway timeout",
    )

    self.client.get(
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

    self.assertEqual(
        payment.state,
        Payment.State.CANCELLED,
    )

@patch("apps.payments.gateways.requests.post")
def test_track_id_mismatch_requires_review_without_request(
    self,
    mock_post,
):
    payment = SimpleNamespace(
        id=10,
        pk=10,
        order_id=None,
        amount=120_000,
        gateway_track_id="stored-track",
    )

    result = verify_payment(
        payment=payment,
        track_id="different-track",
    )

    self.assertFalse(result.success)
    self.assertFalse(result.retryable)
    self.assertTrue(result.requires_review)
    self.assertIn(
        "track_id_mismatch",
        result.integrity_errors,
    )
    mock_post.assert_not_called()


@patch("apps.payments.gateways.requests.post")
def test_amount_mismatch_requires_review(
    self,
    mock_post,
):
    payment = SimpleNamespace(
        id=11,
        pk=11,
        order_id=None,
        amount=120_000,
        gateway_track_id="track-11",
    )

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "result": 100,
        "status": 1,
        "amount": 999_000,
        "orderId": "11",
        "refNumber": "ref-11",
    }
    mock_post.return_value = response

    result = verify_payment(
        payment=payment,
        track_id="track-11",
    )

    self.assertFalse(result.success)
    self.assertTrue(result.requires_review)
    self.assertIn(
        "amount_mismatch",
        result.integrity_errors,
    )


@patch("apps.payments.gateways.requests.post")
def test_order_id_mismatch_requires_review(
    self,
    mock_post,
):
    payment = SimpleNamespace(
        id=12,
        pk=12,
        order_id=500,
        amount=120_000,
        gateway_track_id="track-12",
    )

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "result": 100,
        "status": 1,
        "amount": 1_200_000,
        "orderId": "999",
        "refNumber": "ref-12",
    }
    mock_post.return_value = response

    result = verify_payment(
        payment=payment,
        track_id="track-12",
    )

    self.assertFalse(result.success)
    self.assertTrue(result.requires_review)
    self.assertIn(
        "order_id_mismatch",
        result.integrity_errors,
    )


@patch("apps.payments.gateways.requests.post")
def test_matching_verified_payment_succeeds(
    self,
    mock_post,
):
    payment = SimpleNamespace(
        id=13,
        pk=13,
        order_id=700,
        amount=120_000,
        gateway_track_id="track-13",
    )

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "result": 100,
        "status": 1,
        "amount": 1_200_000,
        "orderId": "700",
        "refNumber": "ref-13",
        "cardNumber": "6037-****-****-1234",
    }
    mock_post.return_value = response

    result = verify_payment(
        payment=payment,
        track_id="track-13",
    )

    self.assertTrue(result.success)
    self.assertFalse(result.retryable)
    self.assertFalse(result.requires_review)
    self.assertEqual(result.ref_id, "ref-13")


@override_settings(
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher"
    ],
    PAYMENT_MODE="sandbox",
    PAYMENT_PROVIDER="zibal",
    ZIBAL_SANDBOX_MERCHANT="zibal",
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
class PendingGatewayPaymentReconcileCommandTests(
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

    def make_gateway_payment(
        self,
        *,
        purpose,
        order=None,
        amount=120_000,
    ):
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=amount,
            description=(
                "Pending gateway reconciliation test"
            ),
            provider=Payment.Provider.ZIBAL,
            purpose=purpose,
            state=Payment.State.PENDING,
            is_finally=False,
            gateway_track_id=(
                f"track-{uuid.uuid4().hex}"
            ),
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
            meta={
                "verify_pending": {
                    "retryable": True,
                    "message": "previous timeout",
                },
            },
        )

        Payment.objects.filter(pk=payment.pk).update(
            update_date=(
                timezone.now() - timedelta(minutes=30)
            )
        )

        payment.refresh_from_db()
        return payment

    @patch(
        "apps.payments.management.commands."
        "reconcile_pending_gateway_payments.verify_payment"
    )
    def test_dry_run_does_not_change_wallet_payment(
        self,
        mock_verify,
    ):
        payment = self.make_gateway_payment(
            purpose=Payment.Purpose.WALLET
        )

        wallet, _ = Wallet.objects.get_or_create(
            user=self.customer.user
        )
        initial_balance = int(wallet.balance)

        mock_verify.return_value = GatewayVerifyResult(
            success=True,
            retryable=False,
            requires_review=False,
            track_id=payment.gateway_track_id,
            ref_id=f"ref-{payment.id}",
            code=100,
            raw={
                "result": 100,
                "status": 1,
            },
        )

        out = StringIO()

        call_command(
            "reconcile_pending_gateway_payments",
            "--min-age-minutes=0",
            stdout=out,
        )

        payment.refresh_from_db()
        wallet.refresh_from_db()

        self.assertEqual(
            payment.state,
            Payment.State.PENDING,
        )
        self.assertFalse(payment.is_finally)
        self.assertEqual(
            int(wallet.balance),
            initial_balance,
        )
        self.assertIn(
            "success_candidate",
            out.getvalue(),
        )

    @patch(
        "apps.payments.management.commands."
        "reconcile_pending_gateway_payments.verify_payment"
    )
    def test_apply_wallet_success_deposits_once(
        self,
        mock_verify,
    ):
        payment = self.make_gateway_payment(
            purpose=Payment.Purpose.WALLET,
            amount=120_000,
        )

        wallet, _ = Wallet.objects.get_or_create(
            user=self.customer.user
        )
        initial_balance = int(wallet.balance)

        mock_verify.return_value = GatewayVerifyResult(
            success=True,
            retryable=False,
            requires_review=False,
            track_id=payment.gateway_track_id,
            ref_id=f"ref-{payment.id}",
            code=100,
            raw={
                "result": 100,
                "status": 1,
            },
        )

        call_command(
            "reconcile_pending_gateway_payments",
            "--apply",
            "--min-age-minutes=0",
            "--limit=10",
            stdout=StringIO(),
        )

        payment.refresh_from_db()
        wallet.refresh_from_db()

        self.assertEqual(
            payment.state,
            Payment.State.SUCCESS,
        )
        self.assertTrue(payment.is_finally)
        self.assertEqual(
            int(wallet.balance),
            initial_balance + 120_000,
        )

        call_command(
            "reconcile_pending_gateway_payments",
            "--apply",
            "--min-age-minutes=0",
            "--limit=10",
            stdout=StringIO(),
        )

        wallet.refresh_from_db()

        self.assertEqual(
            int(wallet.balance),
            initial_balance + 120_000,
        )

    @patch(
        "apps.payments.management.commands."
        "reconcile_pending_gateway_payments.verify_payment"
    )
    def test_requires_review_stays_pending_and_records_meta(
        self,
        mock_verify,
    ):
        payment = self.make_gateway_payment(
            purpose=Payment.Purpose.WALLET,
            amount=120_000,
        )

        mock_verify.return_value = GatewayVerifyResult(
            success=False,
            retryable=False,
            requires_review=True,
            track_id=payment.gateway_track_id,
            code=100,
            message="integrity mismatch",
            integrity_errors=("amount_mismatch",),
            raw={
                "result": 100,
                "status": 1,
                "amount": 1,
            },
        )

        call_command(
            "reconcile_pending_gateway_payments",
            "--apply",
            "--min-age-minutes=0",
            stdout=StringIO(),
        )

        payment.refresh_from_db()

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
            "amount_mismatch",
            verify_pending["integrity_errors"],
        )

    @patch(
        "apps.payments.management.commands."
        "reconcile_pending_gateway_payments.verify_payment"
    )
    def test_appointment_requires_review_does_not_cancel_order(
        self,
        mock_verify,
    ):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            selected_payment_method="online",
            status="pending",
            is_paid=False,
            is_finally=False,
        )

        payment = self.make_gateway_payment(
            purpose=Payment.Purpose.APPOINTMENT,
            order=order,
            amount=120_000,
        )

        mock_verify.return_value = GatewayVerifyResult(
            success=False,
            retryable=False,
            requires_review=True,
            track_id=payment.gateway_track_id,
            code=100,
            message="integrity mismatch",
            integrity_errors=("order_id_mismatch",),
            raw={
                "result": 100,
                "status": 1,
                "amount": 1_200_000,
            },
        )

        call_command(
            "reconcile_pending_gateway_payments",
            "--apply",
            "--min-age-minutes=0",
            stdout=StringIO(),
        )

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(
            payment.state,
            Payment.State.PENDING,
        )
        self.assertFalse(payment.is_finally)
        self.assertEqual(order.status, "pending")
        self.assertFalse(order.is_paid)
        self.assertFalse(order.is_finally)