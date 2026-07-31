from __future__ import annotations

from datetime import timedelta
from io import StringIO
import uuid

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.payments.models import Payment
from tests_stage1_helpers import Stage1DomainFactoryMixin


@override_settings(
    PAYMENT_MODE="mock",
    PAYMENT_PROVIDER="zibal",
    ONLINE_PAYMENT_ENABLED=False,
    ALLOWED_HOSTS=["testserver", "localhost"],
    CSRF_TRUSTED_ORIGINS=[
        "https://staging.loomera.ir",
    ],
    SITE_URL="https://staging.loomera.ir",
    ZIBAL_VERIFY_URL="https://gateway.zibal.ir/v1/verify",
)
class PaymentPreflightCommandTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        super().setUp()

        self.customer = self.make_customer(password="StrongPass123!")

    def test_preflight_runs_without_printing_secrets(self):
        out = StringIO()

        call_command(
            "payment_preflight_check",
            stdout=out,
        )

        output = out.getvalue()

        self.assertIn(
            "Loomera payment preflight check",
            output,
        )
        self.assertIn(
            "PAYMENT_MODE=mock",
            output,
        )
        self.assertIn(
            "secrets.redaction",
            output,
        )
        self.assertNotIn(
            "SECRET_KEY",
            output,
        )
        self.assertNotIn(
            "TOKEN",
            output,
        )
        self.assertNotIn(
            "PASSWORD",
            output,
        )

    @override_settings(
        PAYMENT_MODE="live",
        PAYMENT_PROVIDER="zibal",
        ONLINE_PAYMENT_ENABLED=True,
        ZIBAL_MERCHANT="live-merchant",
    )
    def test_live_mode_requires_allow_live_in_strict_mode(self):
        out = StringIO()

        with self.assertRaises(SystemExit):
            call_command(
                "payment_preflight_check",
                "--strict",
                stdout=out,
            )

        self.assertIn(
            "payment.live.blocked",
            out.getvalue(),
        )

    @override_settings(
        PAYMENT_MODE="live",
        PAYMENT_PROVIDER="zibal",
        ONLINE_PAYMENT_ENABLED=True,
        ZIBAL_MERCHANT="live-merchant",
    )
    def test_live_mode_allowed_when_flag_is_explicit(self):
        out = StringIO()

        call_command(
            "payment_preflight_check",
            "--strict",
            "--allow-live",
            stdout=out,
        )

        self.assertIn(
            "zibal.live_merchant",
            out.getvalue(),
        )

    def test_pending_payment_without_track_id_is_reported(self):
        Payment.objects.create(
            customer=self.customer,
            amount=120_000,
            description="preflight missing track id",
            provider=Payment.Provider.ZIBAL,
            purpose=Payment.Purpose.WALLET,
            state=Payment.State.PENDING,
            is_finally=False,
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
        )

        out = StringIO()

        with self.assertRaises(SystemExit):
            call_command(
                "payment_preflight_check",
                "--strict",
                stdout=out,
            )

        self.assertIn(
            "payments.pending.missing_track_id",
            out.getvalue(),
        )

    def test_stale_pending_payment_is_warning_not_error(self):
        payment = Payment.objects.create(
            customer=self.customer,
            amount=120_000,
            description="preflight stale pending",
            provider=Payment.Provider.ZIBAL,
            purpose=Payment.Purpose.WALLET,
            state=Payment.State.PENDING,
            is_finally=False,
            gateway_track_id=f"track-{uuid.uuid4().hex}",
            callback_token=uuid.uuid4().hex,
            idempotency_key=uuid.uuid4().hex,
            sandbox_mode=True,
        )

        Payment.objects.filter(pk=payment.pk).update(
            update_date=timezone.now() - timedelta(hours=48)
        )

        out = StringIO()

        call_command(
            "payment_preflight_check",
            "--strict",
            "--max-pending-age-hours=24",
            stdout=out,
        )

        output = out.getvalue()

        self.assertIn(
            "payments.pending.stale",
            output,
        )
        self.assertIn(
            "warnings=",
            output,
        )

    @override_settings(PAYMENT_TIMEOUT_SECONDS=15)
    def test_runtime_payment_timeout_setting_is_accepted(self):
        out = StringIO()

        call_command(
            "payment_preflight_check",
            "--strict",
            stdout=out,
        )

        output = out.getvalue()

        self.assertIn("payment.timeout", output)
        self.assertNotIn("payment.timeout.default", output)
        self.assertNotIn("payment.timeout.missing", output)

    @override_settings(PAYMENT_TIMEOUT_SECONDS="invalid")
    def test_invalid_runtime_payment_timeout_is_rejected(self):
        out = StringIO()

        with self.assertRaises(SystemExit) as raised:
            call_command(
                "payment_preflight_check",
                "--strict",
                stdout=out,
            )

        self.assertEqual(raised.exception.code, 1)
        self.assertIn(
            "payment.timeout.invalid",
            out.getvalue(),
        )
