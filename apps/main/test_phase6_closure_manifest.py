from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.main.phase6_closure import (
    PHASE6_COMPLETED_WORKSTREAMS,
    PHASE6_LOCAL_REHEARSAL,
    PHASE6_RELEASE_COMMANDS,
    PHASE6_REPORT_RELATIVE_PATH,
    PHASE6_REQUIRED_ARTIFACTS,
    collect_missing_phase6_artifacts,
    load_phase6_closure_manifest,
)
from apps.main.release_readiness import (
    STRUCTURAL_GUARD_SUITE,
)


class Phase6ClosureManifestTests(SimpleTestCase):
    migration_relative_path = (
        "apps/notifications/migrations/"
        "0003_align_notification_choice_labels.py"
    )

    def test_required_phase6_artifacts_exist(self):
        self.assertEqual(
            collect_missing_phase6_artifacts(
                Path(settings.BASE_DIR)
            ),
            (),
        )

    def test_manifest_matches_closure_source_of_truth(self):
        manifest = load_phase6_closure_manifest(
            Path(settings.BASE_DIR)
        )

        self.assertEqual(
            manifest["phase"],
            "6",
        )
        self.assertEqual(
            manifest["status"],
            "local_completed",
        )
        self.assertEqual(
            manifest["required_artifacts"],
            list(PHASE6_REQUIRED_ARTIFACTS),
        )
        self.assertEqual(
            manifest["completed_workstreams"],
            list(PHASE6_COMPLETED_WORKSTREAMS),
        )
        self.assertEqual(
            manifest["release_commands"],
            list(PHASE6_RELEASE_COMMANDS),
        )
        self.assertEqual(
            manifest["last_local_rehearsal"],
            PHASE6_LOCAL_REHEARSAL,
        )
        self.assertEqual(
            manifest["environment_status"],
            {
                "local": "completed",
                "staging": (
                    "not_executed_budget_postponed"
                ),
                "production": "unchanged",
            },
        )

    def test_quality_report_matches_closure_status(self):
        report_path = (
            Path(settings.BASE_DIR)
            / PHASE6_REPORT_RELATIVE_PATH
        )
        report = report_path.read_text(
            encoding="utf-8"
        )
        normalized = " ".join(report.split())

        self.assertIn(
            "**Overall status:** Completed",
            report,
        )
        self.assertIn(
            "**Staging:** Not executed",
            report,
        )
        self.assertIn(
            "**Production:** Unchanged",
            report,
        )
        self.assertIn(
            "all seven readiness stages successfully",
            normalized,
        )
        self.assertIn(
            "347 tests",
            normalized,
        )
        self.assertIn(
            "11 modules / 56 tests",
            normalized,
        )
        self.assertIn(
            "Phase 6 is complete on Local",
            report,
        )

        for item in PHASE6_COMPLETED_WORKSTREAMS:
            with self.subTest(
                workstream=item["id"]
            ):
                self.assertIn(
                    f"| {item['id']} |",
                    report,
                )

    def test_notification_alignment_migration_is_state_only(
        self,
    ):
        path = (
            Path(settings.BASE_DIR)
            / self.migration_relative_path
        )
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(
            source,
            filename=str(path),
        )

        migration_classes = [
            node
            for node in tree.body
            if (
                isinstance(node, ast.ClassDef)
                and node.name == "Migration"
            )
        ]
        self.assertEqual(
            len(migration_classes),
            1,
        )

        operations = None

        for node in migration_classes[0].body:
            if not isinstance(node, ast.Assign):
                continue

            if any(
                isinstance(target, ast.Name)
                and target.id == "operations"
                for target in node.targets
            ):
                operations = node.value
                break

        self.assertIsInstance(
            operations,
            ast.List,
        )

        operation_names = []
        altered_fields = set()

        for operation in operations.elts:
            self.assertIsInstance(
                operation,
                ast.Call,
            )
            self.assertIsInstance(
                operation.func,
                ast.Attribute,
            )

            operation_names.append(
                operation.func.attr
            )

            values = {
                keyword.arg: keyword.value
                for keyword in operation.keywords
                if keyword.arg
            }

            model_node = values["model_name"]
            field_node = values["name"]

            self.assertIsInstance(
                model_node,
                ast.Constant,
            )
            self.assertIsInstance(
                field_node,
                ast.Constant,
            )

            altered_fields.add(
                (
                    model_node.value,
                    field_node.value,
                )
            )

        self.assertEqual(
            operation_names,
            ["AlterField"] * 6,
        )
        self.assertEqual(
            altered_fields,
            {
                ("notification", "category"),
                (
                    "notificationpreference",
                    "audience_role",
                ),
                (
                    "notificationpreference",
                    "category",
                ),
                (
                    "notificationrecipient",
                    "audience_role",
                ),
                (
                    "notificationtemplate",
                    "audience_role",
                ),
                (
                    "notificationtemplate",
                    "category",
                ),
            },
        )

        for forbidden in (
            "RunPython",
            "RunSQL",
            "AddField",
            "RemoveField",
            "DeleteModel",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

    def test_closure_guard_is_in_structural_readiness_suite(
        self,
    ):
        self.assertIn(
            "apps.main.test_phase6_closure_manifest",
            STRUCTURAL_GUARD_SUITE,
        )
        self.assertEqual(
            STRUCTURAL_GUARD_SUITE.count(
                "apps.main.test_phase6_closure_manifest"
            ),
            1,
        )
