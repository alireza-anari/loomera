from __future__ import annotations

from django.test import SimpleTestCase

from apps.main.regression_suites import (
    QUICK_LINK_RELEASE_TESTS,
    REGRESSION_SUITES,
)


class QuickLinkReleaseRegistryTests(SimpleTestCase):
    def test_every_quick_link_test_is_registered_once_in_booking_suite(self):
        booking_labels = REGRESSION_SUITES["booking"]

        for label in QUICK_LINK_RELEASE_TESTS:
            self.assertEqual(
                booking_labels.count(label),
                1,
                f"{label} must appear exactly once in booking suite.",
            )

    def test_every_quick_link_test_is_registered_once_in_release_check(self):
        release_labels = REGRESSION_SUITES["release-check"]

        for label in QUICK_LINK_RELEASE_TESTS:
            self.assertEqual(
                release_labels.count(label),
                1,
                f"{label} must appear exactly once in release-check.",
            )

    def test_quick_link_tests_are_not_registered_in_unrelated_suites(self):
        unrelated_labels = {
            label
            for suite_name in ("security", "payments", "messaging")
            for label in REGRESSION_SUITES[suite_name]
        }

        for label in QUICK_LINK_RELEASE_TESTS:
            self.assertNotIn(label, unrelated_labels)
