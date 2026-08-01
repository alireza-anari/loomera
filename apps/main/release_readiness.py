from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from apps.main.regression_suites import RELEASE_CHECK_SUITE

STRUCTURAL_GUARD_SUITE = (
    "apps.main.test_runtime_debug_output_security",
    "apps.main.test_frontend_console_security",
    "apps.main.test_sensitive_bare_exception_guard",
    "apps.main.test_sensitive_broad_exception_allowlist",
    "apps.main.test_python_source_encoding_integrity",
    "apps.main.test_production_settings_hygiene",
    "apps.main.test_build_release_archive",
    "apps.main.test_liara_deployment_config",
    "apps.payments.test_gateway_contract_documentation",
    "apps.orders.test_booking_checkout_contract_documentation",
    "apps.api.tests.test_api_v1_otp_auth_contract_documentation",
    "apps.messaging.test_messaging_bale_contract_documentation",
    "apps.main.test_regression_suite_registry",
    "apps.main.test_phase6_closure_manifest",
    "apps.main.test_phase9_acceptance_registry",
    "apps.main.test_phase9_closure_manifest",
)


def _deduplicate(labels: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(labels))


_RELEASE_CHECK_LABELS = frozenset(RELEASE_CHECK_SUITE)

RELEASE_REGRESSION_SUITE = tuple(
    label for label in RELEASE_CHECK_SUITE if label not in STRUCTURAL_GUARD_SUITE
)

RELEASE_READINESS_TEST_LABELS = _deduplicate(
    (
        *STRUCTURAL_GUARD_SUITE,
        *RELEASE_REGRESSION_SUITE,
    )
)

RELEASE_READINESS_STAGES = (
    "system-check",
    "migration-check",
    "infrastructure-preflight",
    "product-preflight",
    "operational-dry-runs",
    "structural-guards",
    "release-regression",
)

OPERATIONAL_DRY_RUN_COMMANDS = (
    (
        "confirm_no_show_after_window",
        {"dry_run": True},
    ),
    (
        "expire_salon_stories",
        {"dry_run": True},
    ),
    (
        "sync_legacy_notifications",
        {"dry_run": True},
    ),
    (
        "sync_support_threads",
        {"dry_run": True},
    ),
    (
        "sync_discount_records",
        {"dry_run": True},
    ),
    (
        "run_scheduled_tasks",
        {"dry_run": True},
    ),
)


def module_path_from_label(
    base_dir: Path,
    label: str,
) -> Path:
    """Return the expected Python path for a module test label."""

    return (base_dir / Path(*label.split("."))).with_suffix(".py")


def validate_release_readiness_plan(
    base_dir: Path,
) -> tuple[str, ...]:
    """Return validation errors for the immutable readiness plan."""

    errors: list[str] = []

    if len(STRUCTURAL_GUARD_SUITE) != len(set(STRUCTURAL_GUARD_SUITE)):
        errors.append("STRUCTURAL_GUARD_SUITE contains duplicate labels.")

    if len(RELEASE_REGRESSION_SUITE) != len(set(RELEASE_REGRESSION_SUITE)):
        errors.append("RELEASE_REGRESSION_SUITE contains duplicate labels.")

    overlap = sorted(set(STRUCTURAL_GUARD_SUITE).intersection(RELEASE_REGRESSION_SUITE))

    if overlap:
        errors.append("Structural and regression stages overlap: " + ", ".join(overlap))

    release_guard_labels = tuple(
        label for label in STRUCTURAL_GUARD_SUITE if label in _RELEASE_CHECK_LABELS
    )
    reconstructed_release_check = _deduplicate(
        (
            *release_guard_labels,
            *RELEASE_REGRESSION_SUITE,
        )
    )

    if set(reconstructed_release_check) != set(RELEASE_CHECK_SUITE):
        errors.append(
            "Readiness test stages do not cover the complete " "release-check suite."
        )

    for label in RELEASE_READINESS_TEST_LABELS:
        path = module_path_from_label(
            base_dir,
            label,
        )

        if not path.is_file():
            errors.append(f"Missing readiness test module: {label}")

    return tuple(errors)
