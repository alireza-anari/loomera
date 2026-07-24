from __future__ import annotations

import ast
from datetime import timedelta
from io import StringIO
from pathlib import Path
import uuid
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
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
)
class PaymentCommandExceptionBoundaryTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    sensitive_error = (
        "secret-token-should-not-appear-in-command-output"
    )

    def setUp(self):
        super().setUp()

        self.customer = self.make_customer(
            password="StrongPass123!"
        )
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager
        )

    def make_pending_gateway_payment(
        self,
        *,
        age_minutes,
        provider=Payment.Provider.ZIBAL,
    ):
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
            description="payment command boundary test",
            provider=provider,
            purpose=Payment.Purpose.APPOINTMENT,
            state=Payment.State.PENDING,
            is_finally=False,
            gateway_track_id=(
                f"track-{uuid.uuid4().hex}"
            ),
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
            meta={},
        )

        Payment.objects.filter(
            pk=payment.pk
        ).update(
            update_date=(
                timezone.now()
                - timedelta(minutes=age_minutes)
            )
        )

        payment.refresh_from_db()
        return payment

    @patch(
        "apps.payments.management.commands."
        "reconcile_pending_gateway_payments.verify_payment"
    )
    def test_reconcile_isolates_one_payment_failure(
        self,
        mocked_verify,
    ):
        failing_payment = (
            self.make_pending_gateway_payment(
                age_minutes=60,
            )
        )
        succeeding_payment = (
            self.make_pending_gateway_payment(
                age_minutes=45,
            )
        )

        def verify_side_effect(
            *,
            payment,
            track_id,
        ):
            if payment.pk == failing_payment.pk:
                raise RuntimeError(
                    self.sensitive_error
                )

            self.assertEqual(
                payment.pk,
                succeeding_payment.pk,
            )
            self.assertEqual(
                track_id,
                succeeding_payment.gateway_track_id,
            )

            return GatewayVerifyResult(
                success=False,
                retryable=True,
                requires_review=False,
                track_id=track_id,
                code=None,
                message="temporary failure",
                raw={},
            )

        mocked_verify.side_effect = (
            verify_side_effect
        )

        stdout = StringIO()
        stderr = StringIO()

        with self.assertRaises(SystemExit) as context:
            call_command(
                "reconcile_pending_gateway_payments",
                "--min-age-minutes=0",
                "--limit=10",
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(context.exception.code, 1)
        self.assertEqual(
            mocked_verify.call_count,
            2,
        )

        output = stdout.getvalue()
        error_output = stderr.getvalue()

        self.assertIn("checked=2", output)
        self.assertIn("pending=1", output)
        self.assertIn("errors=1", output)
        self.assertIn(
            "pending_candidate",
            output,
        )

        self.assertIn(
            (
                f"payment={failing_payment.pk} "
                "error=processing_failed"
            ),
            error_output,
        )
        self.assertNotIn(
            self.sensitive_error,
            error_output,
        )
        self.assertNotIn(
            "RuntimeError",
            error_output,
        )

    @patch(
        "apps.payments.management.commands."
        "expire_abandoned_online_checkouts."
        "_expire_payment"
    )
    def test_expire_isolates_one_payment_failure(
        self,
        mocked_expire,
    ):
        failing_payment = (
            self.make_pending_gateway_payment(
                age_minutes=60,
                provider=Payment.Provider.MOCK,
            )
        )
        succeeding_payment = (
            self.make_pending_gateway_payment(
                age_minutes=45,
                provider=Payment.Provider.MOCK,
            )
        )

        def expire_side_effect(
            payment,
            *,
            reason,
        ):
            self.assertTrue(reason)

            if payment.pk == failing_payment.pk:
                raise RuntimeError(
                    self.sensitive_error
                )

            self.assertEqual(
                payment.pk,
                succeeding_payment.pk,
            )
            return "expired"

        mocked_expire.side_effect = (
            expire_side_effect
        )

        stdout = StringIO()
        stderr = StringIO()

        with self.assertRaises(SystemExit) as context:
            call_command(
                "expire_abandoned_online_checkouts",
                "--apply",
                "--max-age-minutes=30",
                "--limit=10",
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(context.exception.code, 1)
        self.assertEqual(
            mocked_expire.call_count,
            2,
        )

        output = stdout.getvalue()
        error_output = stderr.getvalue()

        self.assertIn("checked=2", output)
        self.assertIn("expired=1", output)
        self.assertIn("errors=1", output)

        self.assertIn(
            (
                f"payment={failing_payment.pk} "
                "error=processing_failed"
            ),
            error_output,
        )
        self.assertNotIn(
            self.sensitive_error,
            error_output,
        )
        self.assertNotIn(
            "RuntimeError",
            error_output,
        )

    def test_broad_handlers_exist_only_at_payment_boundary(
        self,
    ):
        command_paths = (
            Path(settings.BASE_DIR)
            / "apps"
            / "payments"
            / "management"
            / "commands"
        )

        files = (
            command_paths
            / "reconcile_pending_gateway_payments.py",
            command_paths
            / "expire_abandoned_online_checkouts.py",
        )

        for path in files:
            with self.subTest(command=path.name):
                source = path.read_text(
                    encoding="utf-8"
                )
                tree = ast.parse(
                    source,
                    filename=str(path),
                )

                broad_handlers = []

                for node in ast.walk(tree):
                    if not isinstance(
                        node,
                        ast.ExceptHandler,
                    ):
                        continue

                    if (
                        isinstance(node.type, ast.Name)
                        and node.type.id == "Exception"
                    ):
                        broad_handlers.append(node)

                    self.assertFalse(
                        node.type is None,
                        msg=(
                            f"{path.name} contains "
                            "a bare except."
                        ),
                    )

                    if (
                        isinstance(node.type, ast.Name)
                        and node.type.id
                        == "BaseException"
                    ):
                        self.fail(
                            f"{path.name} catches BaseException."
                        )

                self.assertEqual(
                    len(broad_handlers),
                    1,
                    msg=(
                        f"{path.name} must keep exactly one "
                        "broad handler at the per-payment "
                        "processing boundary."
                    ),
                )

                handler_source = ast.get_source_segment(
                    source,
                    broad_handlers[0],
                )

                self.assertIsNotNone(handler_source)
                self.assertIn(
                    'counters["errors"] += 1',
                    handler_source,
                )
                self.assertIn(
                    "error=processing_failed",
                    handler_source,
                )
                self.assertIn(
                    "error_type=%s",
                    handler_source,
                )
                self.assertNotIn(
                    "logger.exception",
                    handler_source,
                )
                self.assertNotIn(
                    "error={exc}",
                    handler_source,
                )
