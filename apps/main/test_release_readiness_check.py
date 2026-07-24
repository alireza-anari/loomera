from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.main.release_readiness import (
    OPERATIONAL_DRY_RUN_COMMANDS,
    RELEASE_READINESS_STAGES,
    RELEASE_READINESS_TEST_LABELS,
    RELEASE_REGRESSION_SUITE,
    STRUCTURAL_GUARD_SUITE,
    validate_release_readiness_plan,
)


COMMAND_MODULE = (
    "apps.main.management.commands."
    "release_readiness_check"
)


class ReleaseReadinessPlanTests(SimpleTestCase):
    def test_readiness_plan_is_complete_and_valid(self):
        self.assertEqual(
            RELEASE_READINESS_STAGES,
            (
                "system-check",
                "migration-check",
                "infrastructure-preflight",
                "product-preflight",
                "operational-dry-runs",
                "structural-guards",
                "release-regression",
            ),
        )
        self.assertEqual(
            validate_release_readiness_plan(
                Path(settings.BASE_DIR)
            ),
            (),
        )
        self.assertEqual(
            len(OPERATIONAL_DRY_RUN_COMMANDS),
            6,
        )

    def test_test_stages_are_unique_and_disjoint(self):
        self.assertEqual(
            len(STRUCTURAL_GUARD_SUITE),
            len(set(STRUCTURAL_GUARD_SUITE)),
        )
        self.assertEqual(
            len(RELEASE_REGRESSION_SUITE),
            len(set(RELEASE_REGRESSION_SUITE)),
        )
        self.assertFalse(
            set(STRUCTURAL_GUARD_SUITE).intersection(
                RELEASE_REGRESSION_SUITE
            )
        )
        self.assertEqual(
            len(RELEASE_READINESS_TEST_LABELS),
            len(STRUCTURAL_GUARD_SUITE)
            + len(RELEASE_REGRESSION_SUITE),
        )


class ReleaseReadinessCommandTests(SimpleTestCase):
    def test_command_runs_all_stages_in_stable_order(self):
        stdout = StringIO()
        command_names: list[str] = []

        def fake_call_command(name, *args, **kwargs):
            command_names.append(name)

        with (
            patch(
                f"{COMMAND_MODULE}.call_command",
                side_effect=fake_call_command,
            ),
            patch(
                f"{COMMAND_MODULE}.DiscoverRunner"
            ) as runner_class,
        ):
            runner = runner_class.return_value
            runner.run_tests.return_value = 0

            call_command(
                "release_readiness_check",
                keepdb=True,
                verbosity_inner=2,
                stdout=stdout,
            )

        self.assertEqual(
            command_names,
            [
                "check",
                "makemigrations",
                "infrastructure_preflight_check",
                "pre_beta_check",
                *[
                    name
                    for name, _kwargs
                    in OPERATIONAL_DRY_RUN_COMMANDS
                ],
            ],
        )
        self.assertEqual(runner_class.call_count, 2)
        runner_class.assert_any_call(
            verbosity=2,
            interactive=False,
            keepdb=True,
            failfast=False,
        )
        self.assertEqual(
            runner.run_tests.call_args_list[0].args[0],
            STRUCTURAL_GUARD_SUITE,
        )
        self.assertEqual(
            runner.run_tests.call_args_list[1].args[0],
            RELEASE_REGRESSION_SUITE,
        )
        self.assertIn(
            "Summary: 7 passed, 0 failed, 0 skipped.",
            stdout.getvalue(),
        )
        self.assertIn(
            "Loomera release readiness: PASSED",
            stdout.getvalue(),
        )

    def test_failed_stage_returns_exit_code_one_and_summary(self):
        stdout = StringIO()
        stderr = StringIO()
        call_count = 0

        def fake_call_command(name, *args, **kwargs):
            nonlocal call_count
            call_count += 1

            if name == "makemigrations":
                raise CommandError(
                    "sensitive migration details"
                )

        with (
            patch(
                f"{COMMAND_MODULE}.call_command",
                side_effect=fake_call_command,
            ),
            patch(
                f"{COMMAND_MODULE}.DiscoverRunner"
            ) as runner_class,
        ):
            runner = runner_class.return_value
            runner.run_tests.return_value = 0

            with self.assertRaises(SystemExit) as context:
                call_command(
                    "release_readiness_check",
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(context.exception.code, 1)
        self.assertGreater(call_count, 2)
        self.assertIn(
            "Summary: 6 passed, 1 failed, 0 skipped.",
            stdout.getvalue(),
        )
        output = stdout.getvalue() + stderr.getvalue()
        self.assertIn("migration-check", output)
        self.assertNotIn(
            "sensitive migration details",
            output,
        )
        self.assertIn(
            "Loomera release readiness: FAILED",
            stderr.getvalue(),
        )

    def test_failfast_skips_remaining_stages(self):
        stdout = StringIO()
        stderr = StringIO()

        with (
            patch(
                f"{COMMAND_MODULE}.call_command",
                side_effect=CommandError(
                    "system failed"
                ),
            ),
            patch(
                f"{COMMAND_MODULE}.DiscoverRunner"
            ) as runner_class,
        ):
            with self.assertRaises(SystemExit):
                call_command(
                    "release_readiness_check",
                    failfast=True,
                    stdout=stdout,
                    stderr=stderr,
                )

        runner_class.assert_not_called()
        output = stdout.getvalue() + stderr.getvalue()
        self.assertIn(
            "Summary: 0 passed, 1 failed, 6 skipped.",
            output,
        )

    def test_skip_options_produce_explicit_summary(self):
        stdout = StringIO()

        with (
            patch(
                f"{COMMAND_MODULE}.call_command"
            ),
            patch(
                f"{COMMAND_MODULE}.DiscoverRunner"
            ) as runner_class,
        ):
            runner = runner_class.return_value
            runner.run_tests.return_value = 0

            call_command(
                "release_readiness_check",
                skip_migrations=True,
                skip_operational_dry_runs=True,
                skip_regression=True,
                stdout=stdout,
            )

        runner_class.assert_called_once()
        self.assertIn(
            "Summary: 4 passed, 0 failed, 3 skipped.",
            stdout.getvalue(),
        )
        self.assertIn(
            "Loomera release readiness: PASSED",
            stdout.getvalue(),
        )

    def test_custom_test_labels_preserve_legacy_cli_compatibility(
        self,
    ):
        stdout = StringIO()
        custom_labels = (
            "apps.main.test_release_quality",
        )

        with (
            patch(
                f"{COMMAND_MODULE}.call_command"
            ),
            patch(
                f"{COMMAND_MODULE}.DiscoverRunner"
            ) as runner_class,
        ):
            runner = runner_class.return_value
            runner.run_tests.return_value = 0

            call_command(
                "release_readiness_check",
                run_tests=True,
                test_label=list(custom_labels),
                stdout=stdout,
            )

        self.assertEqual(
            runner.run_tests.call_args_list[1].args[0],
            custom_labels,
        )

    def test_unexpected_stage_error_is_sanitized(self):
        stdout = StringIO()
        stderr = StringIO()

        with (
            patch(
                f"{COMMAND_MODULE}.call_command",
                side_effect=RuntimeError(
                    "sensitive backend details"
                ),
            ),
            patch(
                f"{COMMAND_MODULE}.DiscoverRunner"
            ),
        ):
            with self.assertRaises(SystemExit):
                call_command(
                    "release_readiness_check",
                    failfast=True,
                    stdout=stdout,
                    stderr=stderr,
                )

        output = stdout.getvalue() + stderr.getvalue()
        self.assertIn("RuntimeError", output)
        self.assertNotIn(
            "sensitive backend details",
            output,
        )


from datetime import date as _date
from io import StringIO as _StringIO
from types import SimpleNamespace as _SimpleNamespace
from unittest.mock import call as _call
from unittest.mock import patch as _patch

from django.core.management import (
    call_command as _django_call_command,
)
from django.test import (
    SimpleTestCase as _SimpleTestCase,
)


class ScheduledTaskDryRunSafetyTests(
    _SimpleTestCase
):
    def test_dry_run_executes_only_native_dry_run_commands(
        self,
    ):
        from apps.main.infrastructure import (
            run_scheduled_tasks,
        )

        with (
            _patch(
                "apps.main.infrastructure.call_command"
            ) as call_command_mock,
            _patch(
                "apps.main.infrastructure.operational_job"
            ) as operational_job_mock,
            _patch(
                "apps.main.infrastructure.timezone.localdate",
                return_value=_date(2026, 7, 12),
            ),
        ):
            results = run_scheduled_tasks(
                daily_metrics=True,
                dry_run=True,
                limit=7,
            )

        self.assertEqual(
            call_command_mock.call_args_list,
            [
                _call(
                    "confirm_no_show_after_window",
                    dry_run=True,
                ),
                _call(
                    "expire_salon_stories",
                    dry_run=True,
                ),
            ],
        )
        operational_job_mock.assert_not_called()

        self.assertEqual(
            results,
            [
                {
                    "command": (
                        "dispatch_appointment_notifications"
                    ),
                    "status": (
                        "skipped_no_native_dry_run"
                    ),
                },
                {
                    "command": (
                        "process_notification_deliveries"
                    ),
                    "status": (
                        "skipped_no_native_dry_run"
                    ),
                },
                {
                    "command": (
                        "confirm_no_show_after_window"
                    ),
                    "status": "dry_run",
                },
                {
                    "command": "expire_salon_stories",
                    "status": "dry_run",
                },
                {
                    "command": "process_report_exports",
                    "status": (
                        "skipped_no_native_dry_run"
                    ),
                },
                {
                    "command": "build_daily_metrics",
                    "status": (
                        "skipped_no_native_dry_run"
                    ),
                },
            ],
        )

    def test_normal_mode_preserves_existing_task_execution(
        self,
    ):
        from apps.main.infrastructure import (
            run_scheduled_tasks,
        )

        with (
            _patch(
                "apps.main.infrastructure.call_command"
            ) as call_command_mock,
            _patch(
                "apps.main.infrastructure.operational_job"
            ) as operational_job_mock,
            _patch(
                "apps.main.infrastructure.timezone.localdate",
                return_value=_date(2026, 7, 12),
            ),
        ):
            operational_job_mock.return_value.__enter__.return_value = (
                _SimpleNamespace(pk=901)
            )

            results = run_scheduled_tasks(
                daily_metrics=True,
                dry_run=False,
                limit=7,
            )

        self.assertEqual(
            call_command_mock.call_args_list,
            [
                _call(
                    "dispatch_appointment_notifications",
                    limit=7,
                ),
                _call(
                    "process_notification_deliveries",
                    limit=7,
                ),
                _call(
                    "confirm_no_show_after_window",
                    dry_run=False,
                ),
                _call(
                    "expire_salon_stories",
                    dry_run=False,
                ),
                _call(
                    "process_report_exports",
                    limit=7,
                ),
                _call(
                    "build_daily_metrics",
                    date="2026-07-12",
                ),
            ],
        )

        self.assertEqual(
            len(results),
            6,
        )
        self.assertTrue(
            all(
                result.get("run_id") == 901
                for result in results
            )
        )

    def test_management_command_reports_skipped_tasks(
        self,
    ):
        results = [
            {
                "command": "native-one",
                "status": "dry_run",
            },
            {
                "command": "native-two",
                "status": "dry_run",
            },
            {
                "command": "unsafe-one",
                "status": (
                    "skipped_no_native_dry_run"
                ),
            },
            {
                "command": "unsafe-two",
                "status": (
                    "skipped_no_native_dry_run"
                ),
            },
            {
                "command": "unsafe-three",
                "status": (
                    "skipped_no_native_dry_run"
                ),
            },
            {
                "command": "unsafe-four",
                "status": (
                    "skipped_no_native_dry_run"
                ),
            },
        ]
        stdout = _StringIO()

        with _patch(
            (
                "apps.main.management.commands."
                "run_scheduled_tasks."
                "run_scheduled_tasks"
            ),
            return_value=results,
        ):
            _django_call_command(
                "run_scheduled_tasks",
                dry_run=True,
                stdout=stdout,
            )

        output = stdout.getvalue()

        self.assertIn(
            "native_dry_runs=2",
            output,
        )
        self.assertIn(
            "skipped_without_native_dry_run=4",
            output,
        )
        self.assertIn(
            "total=6",
            output,
        )
