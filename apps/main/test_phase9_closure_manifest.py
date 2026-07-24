from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.main.phase9_closure import (
    PHASE9_ACCEPTANCE_SALON_SLUGS,
    PHASE9_ACCEPTANCE_TEST_REGISTRY,
    PHASE9_COMPLETED_WORKSTREAMS,
    PHASE9_FINAL_COMMANDS,
    PHASE9_LOCAL_REHEARSAL,
    PHASE9_REPORT_RELATIVE_PATH,
    PHASE9_REQUIRED_ARTIFACTS,
    collect_missing_phase9_artifacts,
    load_phase9_closure_manifest,
)
from apps.main.regression_suites import (
    REGRESSION_SUITES,
)
from apps.main.release_readiness import (
    STRUCTURAL_GUARD_SUITE,
)


class Phase9ClosureManifestTests(
    SimpleTestCase
):
    def test_required_phase9_artifacts_exist(
        self,
    ):
        self.assertEqual(
            collect_missing_phase9_artifacts(
                Path(settings.BASE_DIR)
            ),
            (),
        )

    def test_manifest_matches_source_of_truth(
        self,
    ):
        manifest = (
            load_phase9_closure_manifest(
                Path(settings.BASE_DIR)
            )
        )

        self.assertEqual(
            manifest["phase"],
            "9",
        )
        self.assertEqual(
            manifest["status"],
            "local_completed",
        )
        self.assertEqual(
            manifest["acceptance_salon_slugs"],
            list(
                PHASE9_ACCEPTANCE_SALON_SLUGS
            ),
        )
        self.assertEqual(
            manifest["acceptance_tests"],
            list(
                PHASE9_ACCEPTANCE_TEST_REGISTRY
            ),
        )
        self.assertEqual(
            manifest["required_artifacts"],
            list(
                PHASE9_REQUIRED_ARTIFACTS
            ),
        )
        self.assertEqual(
            manifest["completed_workstreams"],
            list(
                PHASE9_COMPLETED_WORKSTREAMS
            ),
        )
        self.assertEqual(
            manifest["final_commands"],
            list(PHASE9_FINAL_COMMANDS),
        )
        self.assertEqual(
            manifest["local_rehearsal"],
            PHASE9_LOCAL_REHEARSAL,
        )

    def test_acceptance_registry_remains_complete(
        self,
    ):
        release_labels = (
            REGRESSION_SUITES[
                "release-check"
            ]
        )

        for item in (
            PHASE9_ACCEPTANCE_TEST_REGISTRY
        ):
            label = item["label"]
            suite_labels = (
                REGRESSION_SUITES[
                    item["suite"]
                ]
            )

            self.assertEqual(
                suite_labels.count(label),
                1,
            )
            self.assertEqual(
                release_labels.count(label),
                1,
            )

    def test_phase9_report_records_local_closure(
        self,
    ):
        report_path = (
            Path(settings.BASE_DIR)
            / PHASE9_REPORT_RELATIVE_PATH
        )
        report = report_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "وضعیت: تکمیل‌شده در Local",
            report,
        )
        self.assertIn(
            "Staging: اجرا نشده",
            report,
        )
        self.assertIn(
            "Production: بدون تغییر",
            report,
        )
        self.assertIn(
            "407",
            report,
        )
        self.assertIn(
            "local_beta_acceptance_check",
            report,
        )

        for item in (
            PHASE9_COMPLETED_WORKSTREAMS
        ):
            self.assertIn(
                f"| {item['id']} |",
                report,
            )

    def test_phase9_guards_are_structural(
        self,
    ):
        expected_labels = (
            (
                "apps.main."
                "test_phase9_acceptance_registry"
            ),
            (
                "apps.main."
                "test_phase9_closure_manifest"
            ),
        )

        for label in expected_labels:
            self.assertEqual(
                STRUCTURAL_GUARD_SUITE.count(
                    label
                ),
                1,
            )
