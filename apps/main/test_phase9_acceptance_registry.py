from __future__ import annotations

from django.test import SimpleTestCase

from apps.main.regression_suites import (
    REGRESSION_SUITES,
)

PHASE9_ACCEPTANCE_TESTS = {
    "booking": (
        "apps.main.test_local_beta_acceptance_seed",
        "apps.main.test_local_beta_booking_acceptance",
        "apps.orders.test_no_show_lifecycle_stage",
        "apps.dashboards.test_no_show_operational_status",
        ("apps.main." "test_local_beta_operational_scope_acceptance"),
    ),
    "messaging": (("apps.main." "test_local_beta_notification_acceptance"),),
    "payments": (("apps.main." "test_local_beta_metrics_export_cleanup_acceptance"),),
}


class Phase9AcceptanceRegistryTests(SimpleTestCase):
    def test_acceptance_tests_are_registered_once(
        self,
    ):
        release_labels = REGRESSION_SUITES["release-check"]

        for suite_name, expected_labels in PHASE9_ACCEPTANCE_TESTS.items():
            suite_labels = REGRESSION_SUITES[suite_name]

            for label in expected_labels:
                self.assertEqual(
                    suite_labels.count(label),
                    1,
                    (f"{label} must appear exactly " f"once in {suite_name}."),
                )

                self.assertEqual(
                    release_labels.count(label),
                    1,
                    (f"{label} must appear exactly " "once in release-check."),
                )

    def test_acceptance_tests_are_not_cross_registered(
        self,
    ):
        for suite_name, expected_labels in PHASE9_ACCEPTANCE_TESTS.items():
            other_suite_labels = {
                label
                for other_name in (
                    "booking",
                    "messaging",
                    "payments",
                )
                if other_name != suite_name
                for label in REGRESSION_SUITES[other_name]
            }

            for label in expected_labels:
                self.assertNotIn(
                    label,
                    other_suite_labels,
                    (f"{label} is registered in " "more than one primary suite."),
                )
