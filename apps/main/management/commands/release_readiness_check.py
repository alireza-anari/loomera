from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Callable

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.test import override_settings
from django.test.runner import DiscoverRunner

from apps.main.release_readiness import (
    OPERATIONAL_DRY_RUN_COMMANDS,
    RELEASE_READINESS_STAGES,
    RELEASE_REGRESSION_SUITE,
    STRUCTURAL_GUARD_SUITE,
    validate_release_readiness_plan,
)


class ReadinessStageFailure(Exception):
    """Represent a controlled failure in one readiness stage."""


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    detail: str


class Command(BaseCommand):
    help = (
        "Run Loomera release-readiness checks in a stable order "
        "and print a final stage summary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--keepdb",
            action="store_true",
            help="Preserve the test database between test stages.",
        )
        parser.add_argument(
            "--failfast",
            action="store_true",
            help=(
                "Stop orchestration after the first failed stage "
                "and enable Django test-runner failfast."
            ),
        )
        parser.add_argument(
            "--verbosity-inner",
            type=int,
            choices=(0, 1, 2, 3),
            default=1,
            help="Verbosity passed to nested commands and test runners.",
        )
        parser.add_argument(
            "--skip-migrations",
            action="store_true",
            help="Skip makemigrations --check --dry-run.",
        )
        parser.add_argument(
            "--skip-operational-dry-runs",
            action="store_true",
            help="Skip operational management-command dry-runs.",
        )
        parser.add_argument(
            "--skip-regression",
            action="store_true",
            help=(
                "Run checks, preflights and structural guards "
                "without the broader release regression stage."
            ),
        )
        parser.add_argument(
            "--run-tests",
            action="store_true",
            help=(
                "Deprecated compatibility flag. Tests now run by "
                "default unless --skip-regression is used."
            ),
        )
        parser.add_argument(
            "--test-label",
            action="append",
            default=[],
            help=(
                "Compatibility override for release-regression "
                "labels. Can be passed multiple times."
            ),
        )

    def _call_management_command(
        self,
        command_name: str,
        **kwargs,
    ) -> None:
        output = StringIO()
        call_command(
            command_name,
            stdout=output,
            stderr=output,
            verbosity=kwargs.pop(
                "verbosity",
                self.inner_verbosity,
            ),
            **kwargs,
        )

        if self.inner_verbosity >= 3:
            rendered = output.getvalue().strip()

            if rendered:
                self.stdout.write(rendered)

    def _run_system_check(self, _options):
        self._call_management_command(
            "check",
            verbosity=0,
        )
        return "Django system checks passed."

    def _run_migration_check(self, _options):
        self._call_management_command(
            "makemigrations",
            check=True,
            dry_run=True,
            interactive=False,
            verbosity=0,
        )
        return "No model changes require migrations."

    def _run_infrastructure_preflight(self, _options):
        self._call_management_command("infrastructure_preflight_check")
        return "Infrastructure preflight passed."

    def _run_product_preflight(self, _options):
        self._call_management_command("pre_beta_check")
        return "Product pre-beta/pre-release preflight passed."

    def _run_operational_dry_runs(self, _options):
        failures: list[str] = []

        for command_name, kwargs in OPERATIONAL_DRY_RUN_COMMANDS:
            try:
                self._call_management_command(
                    command_name,
                    **kwargs,
                )
            except CommandError:
                failures.append(command_name)
            except SystemExit as exc:
                code = exc.code
                normalized_code = code if isinstance(code, int) else 1

                if normalized_code:
                    failures.append(command_name)
            except Exception:
                failures.append(command_name)

        if failures:
            raise ReadinessStageFailure(
                f"{len(failures)} operational dry-run(s) failed"
            )

        return f"{len(OPERATIONAL_DRY_RUN_COMMANDS)} " "operational dry-run(s) passed."

    def _run_test_labels(
        self,
        labels: tuple[str, ...],
        options,
    ) -> str:
        runner = DiscoverRunner(
            verbosity=options["verbosity_inner"],
            interactive=False,
            keepdb=options["keepdb"],
            failfast=options["failfast"],
        )
        # Regression tests validate application behavior, not the outer
        # HTTP-to-HTTPS redirect enforced by staging/production settings.
        # Individual security tests may still enable SSL redirect explicitly.
        with override_settings(SECURE_SSL_REDIRECT=False):
            failures = runner.run_tests(labels)

        if failures:
            raise ReadinessStageFailure(f"{failures} test failure(s)")

        return f"{len(labels)} test module(s) passed."

    def _run_structural_guards(self, options):
        plan_errors = validate_release_readiness_plan(Path(settings.BASE_DIR))

        if plan_errors:
            raise ReadinessStageFailure(
                f"readiness plan invalid ({len(plan_errors)} error(s))"
            )

        return self._run_test_labels(
            STRUCTURAL_GUARD_SUITE,
            options,
        )

    def _run_release_regression(self, options):
        labels = tuple(options["test_label"] or RELEASE_REGRESSION_SUITE)

        return self._run_test_labels(
            labels,
            options,
        )

    def _execute_stage(
        self,
        name: str,
        callback: Callable[[dict], str],
        options,
    ) -> StageResult:
        self.stdout.write(self.style.HTTP_INFO(f"[RUN ] {name}"))

        try:
            detail = callback(options)
        except ReadinessStageFailure as exc:
            return StageResult(
                name=name,
                status="FAIL",
                detail=str(exc),
            )
        except CommandError as exc:
            return StageResult(
                name=name,
                status="FAIL",
                detail=("management command failed: " f"{type(exc).__name__}"),
            )
        except SystemExit as exc:
            code = exc.code
            normalized_code = code if isinstance(code, int) else 1

            if normalized_code == 0:
                return StageResult(
                    name=name,
                    status="PASS",
                    detail="Stage completed successfully.",
                )

            return StageResult(
                name=name,
                status="FAIL",
                detail=("stage exited with code " f"{normalized_code}"),
            )
        except Exception as exc:
            return StageResult(
                name=name,
                status="FAIL",
                detail=("unexpected stage error: " f"{type(exc).__name__}"),
            )

        return StageResult(
            name=name,
            status="PASS",
            detail=detail,
        )

    def _print_summary(self, results: list[StageResult]):
        self.stdout.write("")
        self.stdout.write("Loomera release readiness summary:")

        for result in results:
            line = f"[{result.status:<4}] " f"{result.name}: {result.detail}"

            if result.status == "PASS":
                self.stdout.write(self.style.SUCCESS(line))
            elif result.status == "SKIP":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stderr.write(self.style.ERROR(line))

        counts = {
            status: sum(result.status == status for result in results)
            for status in ("PASS", "FAIL", "SKIP")
        }

        self.stdout.write(
            "Summary: "
            f"{counts['PASS']} passed, "
            f"{counts['FAIL']} failed, "
            f"{counts['SKIP']} skipped."
        )

    def handle(self, *args, **options):
        self.inner_verbosity = options["verbosity_inner"]

        callbacks = {
            "system-check": self._run_system_check,
            "migration-check": self._run_migration_check,
            "infrastructure-preflight": (self._run_infrastructure_preflight),
            "product-preflight": self._run_product_preflight,
            "operational-dry-runs": (self._run_operational_dry_runs),
            "structural-guards": self._run_structural_guards,
            "release-regression": self._run_release_regression,
        }
        results: list[StageResult] = []
        stop_remaining = False

        self.stdout.write(self.style.HTTP_INFO("Loomera release readiness started."))

        for stage_name in RELEASE_READINESS_STAGES:
            skip_reason = None

            if stage_name == "migration-check" and options["skip_migrations"]:
                skip_reason = "Skipped by --skip-migrations."
            elif (
                stage_name == "operational-dry-runs"
                and options["skip_operational_dry_runs"]
            ):
                skip_reason = "Skipped by --skip-operational-dry-runs."
            elif stage_name == "release-regression" and options["skip_regression"]:
                skip_reason = "Skipped by --skip-regression."

            if skip_reason is not None:
                results.append(
                    StageResult(
                        name=stage_name,
                        status="SKIP",
                        detail=skip_reason,
                    )
                )
                continue

            if stop_remaining:
                results.append(
                    StageResult(
                        name=stage_name,
                        status="SKIP",
                        detail="Skipped after an earlier failure.",
                    )
                )
                continue

            result = self._execute_stage(
                stage_name,
                callbacks[stage_name],
                options,
            )
            results.append(result)

            if result.status == "FAIL" and options["failfast"]:
                stop_remaining = True

        self._print_summary(results)

        failures = sum(result.status == "FAIL" for result in results)

        if failures:
            self.stderr.write(self.style.ERROR("Loomera release readiness: FAILED"))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("Loomera release readiness: PASSED"))
