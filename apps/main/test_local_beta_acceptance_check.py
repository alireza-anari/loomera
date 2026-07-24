from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import (
    CommandError,
    call_command,
)
from django.test import (
    SimpleTestCase,
    override_settings,
)

from apps.main.management.commands.local_beta_acceptance_check import (
    LOCAL_BETA_ACCEPTANCE_SALON_SLUGS,
)

SAFE_LOCAL_SETTINGS = {
    "DEBUG": True,
    "ONLINE_PAYMENT_ENABLED": False,
    "MESSAGING_OUTBOUND_ENABLED": False,
    "EMAIL_BACKEND": ("django.core.mail.backends." "dummy.EmailBackend"),
}


@override_settings(**SAFE_LOCAL_SETTINGS)
class LocalBetaAcceptanceCheckTests(SimpleTestCase):
    @patch(
        "apps.main.management.commands." "local_beta_acceptance_check." "call_command"
    )
    @patch(
        "apps.main.management.commands."
        "local_beta_acceptance_check."
        "Command._get_active_seed_slugs"
    )
    def test_command_runs_readiness_checks(
        self,
        active_seed_slugs,
        nested_call_command,
    ):
        active_seed_slugs.return_value = tuple(
            sorted(LOCAL_BETA_ACCEPTANCE_SALON_SLUGS)
        )

        stdout = StringIO()

        call_command(
            "local_beta_acceptance_check",
            keepdb=True,
            failfast=True,
            verbosity_inner=2,
            stdout=stdout,
        )

        self.assertEqual(
            [item.args[0] for item in nested_call_command.call_args_list],
            [
                "beta_salon_readiness_check",
                "release_readiness_check",
            ],
        )

        beta_kwargs = nested_call_command.call_args_list[0].kwargs

        self.assertEqual(
            beta_kwargs["slugs"],
            list(LOCAL_BETA_ACCEPTANCE_SALON_SLUGS),
        )
        self.assertTrue(beta_kwargs["active_only"])
        self.assertTrue(beta_kwargs["strict"])
        self.assertEqual(
            beta_kwargs["verbosity"],
            2,
        )

        release_kwargs = nested_call_command.call_args_list[1].kwargs

        self.assertTrue(release_kwargs["keepdb"])
        self.assertTrue(release_kwargs["failfast"])
        self.assertEqual(
            release_kwargs["verbosity_inner"],
            2,
        )

        output = stdout.getvalue()

        self.assertIn(
            "[PASS] local-runtime-policy",
            output,
        )
        self.assertIn(
            "[PASS] five-salon-dataset",
            output,
        )
        self.assertIn(
            "[PASS] five-salon-readiness",
            output,
        )
        self.assertIn(
            "[PASS] release-readiness",
            output,
        )
        self.assertIn(
            ("Loomera Local Beta " "Acceptance: PASSED"),
            output,
        )

    @patch(
        "apps.main.management.commands."
        "local_beta_acceptance_check."
        "Command._get_active_seed_slugs"
    )
    def test_command_rejects_missing_seed_salon(
        self,
        active_seed_slugs,
    ):
        active_seed_slugs.return_value = tuple(
            sorted(LOCAL_BETA_ACCEPTANCE_SALON_SLUGS[:-1])
        )

        with self.assertRaisesMessage(
            CommandError,
            "missing=local-seed-salon-5",
        ):
            call_command(
                "local_beta_acceptance_check",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(DEBUG=False)
    def test_command_rejects_debug_false(self):
        with self.assertRaisesMessage(
            CommandError,
            "DEBUG must be True",
        ):
            call_command(
                "local_beta_acceptance_check",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(ONLINE_PAYMENT_ENABLED=True)
    def test_command_rejects_online_payment(
        self,
    ):
        with self.assertRaisesMessage(
            CommandError,
            ("ONLINE_PAYMENT_ENABLED " "must be False"),
        ):
            call_command(
                "local_beta_acceptance_check",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(MESSAGING_OUTBOUND_ENABLED=True)
    def test_command_rejects_messaging_outbound(
        self,
    ):
        with self.assertRaisesMessage(
            CommandError,
            ("MESSAGING_OUTBOUND_ENABLED " "must be False"),
        ):
            call_command(
                "local_beta_acceptance_check",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(
        EMAIL_BACKEND=("django.core.mail.backends." "console.EmailBackend")
    )
    def test_command_rejects_real_email_backend(
        self,
    ):
        with self.assertRaisesMessage(
            CommandError,
            ("EMAIL_BACKEND must use " "Django's dummy backend"),
        ):
            call_command(
                "local_beta_acceptance_check",
                stdout=StringIO(),
                stderr=StringIO(),
            )
