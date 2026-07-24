from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

from apps.main.regression_suites import (
    BOOKING_SUITE,
    MESSAGING_SUITE,
    PAYMENTS_SUITE,
    REGRESSION_SUITES,
    RELEASE_CHECK_SUITE,
    SECURITY_SUITE,
    get_regression_suite,
)


class RegressionSuiteRegistryTests(SimpleTestCase):
    expected_suite_names = (
        "security",
        "payments",
        "booking",
        "messaging",
        "release-check",
    )

    @staticmethod
    def _module_path(label: str) -> Path:
        return (
            Path(settings.BASE_DIR)
            / Path(*label.split("."))
        ).with_suffix(".py")

    def test_registry_has_expected_stable_entry_points(self):
        self.assertEqual(
            tuple(REGRESSION_SUITES),
            self.expected_suite_names,
        )

        self.assertIs(
            get_regression_suite("security"),
            SECURITY_SUITE,
        )
        self.assertIs(
            get_regression_suite("payments"),
            PAYMENTS_SUITE,
        )
        self.assertIs(
            get_regression_suite("booking"),
            BOOKING_SUITE,
        )
        self.assertIs(
            get_regression_suite("messaging"),
            MESSAGING_SUITE,
        )
        self.assertIs(
            get_regression_suite("release-check"),
            RELEASE_CHECK_SUITE,
        )

    def test_each_suite_uses_unique_module_labels(self):
        for name, labels in REGRESSION_SUITES.items():
            with self.subTest(suite=name):
                self.assertIsInstance(labels, tuple)
                self.assertTrue(labels)
                self.assertEqual(
                    len(labels),
                    len(set(labels)),
                )

                for label in labels:
                    self.assertTrue(
                        label.startswith("apps."),
                        msg=(
                            f"{name}: non-project test "
                            f"label {label!r}"
                        ),
                    )

    def test_all_registered_test_modules_exist(self):
        missing = []

        for suite_name, labels in (
            (
                name,
                labels,
            )
            for name, labels in REGRESSION_SUITES.items()
            if name != "release-check"
        ):
            for label in labels:
                path = self._module_path(label)

                if not path.is_file():
                    missing.append(
                        f"{suite_name}: {label}"
                    )

        self.assertEqual(missing, [])

    def test_release_check_is_deduplicated_union(self):
        expected = tuple(
            dict.fromkeys(
                (
                    "apps.main.test_release_quality",
                    *SECURITY_SUITE,
                    *PAYMENTS_SUITE,
                    *BOOKING_SUITE,
                    *MESSAGING_SUITE,
                )
            )
        )

        self.assertEqual(
            RELEASE_CHECK_SUITE,
            expected,
        )

    def test_list_mode_does_not_start_test_runner(self):
        stdout = StringIO()

        with patch(
            "apps.main.management.commands."
            "run_regression_suite.DiscoverRunner"
        ) as runner_class:
            call_command(
                "run_regression_suite",
                list_suites=True,
                stdout=stdout,
            )

        runner_class.assert_not_called()

        output = stdout.getvalue()

        for name in self.expected_suite_names:
            self.assertIn(f"- {name}:", output)

    def test_command_passes_suite_and_runner_options(self):
        stdout = StringIO()

        with patch(
            "apps.main.management.commands."
            "run_regression_suite.DiscoverRunner"
        ) as runner_class:
            runner = runner_class.return_value
            runner.run_tests.return_value = 0

            call_command(
                "run_regression_suite",
                "payments",
                keepdb=True,
                failfast=True,
                verbosity_inner=2,
                stdout=stdout,
            )

        runner_class.assert_called_once_with(
            verbosity=2,
            interactive=False,
            keepdb=True,
            failfast=True,
        )
        runner.run_tests.assert_called_once_with(
            PAYMENTS_SUITE
        )
        self.assertIn(
            "Regression suite 'payments' passed.",
            stdout.getvalue(),
        )

    def test_command_returns_nonzero_on_failed_suite(self):
        stderr = StringIO()

        with patch(
            "apps.main.management.commands."
            "run_regression_suite.DiscoverRunner"
        ) as runner_class:
            runner = runner_class.return_value
            runner.run_tests.return_value = 2

            with self.assertRaises(SystemExit) as context:
                call_command(
                    "run_regression_suite",
                    "security",
                    stderr=stderr,
                )

        self.assertEqual(context.exception.code, 1)
        self.assertIn(
            "failed with 2 failure(s)",
            stderr.getvalue(),
        )

    def test_unknown_suite_helper_fails_explicitly(self):
        with self.assertRaisesRegex(
            ValueError,
            "Unknown regression suite",
        ):
            get_regression_suite("unknown")
