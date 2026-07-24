from __future__ import annotations

import json
from pathlib import Path


PHASE9_ACCEPTANCE_SALON_SLUGS = (
    "local-seed-salon-1",
    "local-seed-salon-2",
    "local-seed-salon-3",
    "local-seed-salon-4",
    "local-seed-salon-5",
)

PHASE9_ACCEPTANCE_TEST_REGISTRY = ({'label': 'apps.main.test_local_beta_acceptance_seed', 'suite': 'booking'}, {'label': 'apps.main.test_local_beta_booking_acceptance', 'suite': 'booking'}, {'label': 'apps.orders.test_no_show_lifecycle_stage', 'suite': 'booking'}, {'label': 'apps.dashboards.test_no_show_operational_status', 'suite': 'booking'}, {'label': 'apps.main.test_local_beta_operational_scope_acceptance', 'suite': 'booking'}, {'label': 'apps.main.test_local_beta_notification_acceptance', 'suite': 'messaging'}, {'label': 'apps.main.test_local_beta_metrics_export_cleanup_acceptance', 'suite': 'payments'})

PHASE9_REQUIRED_ARTIFACTS = ('apps/main/management/commands/seed_local_demo_data.py', 'apps/main/test_local_beta_acceptance_seed.py', 'apps/main/test_local_beta_booking_acceptance.py', 'apps/orders/test_no_show_lifecycle_stage.py', 'apps/dashboards/test_no_show_operational_status.py', 'apps/main/test_local_beta_operational_scope_acceptance.py', 'apps/main/test_local_beta_notification_acceptance.py', 'apps/main/test_local_beta_metrics_export_cleanup_acceptance.py', 'apps/main/test_phase9_acceptance_registry.py', 'apps/main/management/commands/local_beta_acceptance_check.py', 'apps/main/test_local_beta_acceptance_check.py', 'apps/main/phase9_closure.py', 'apps/main/phase9_closure_manifest.json', 'apps/main/test_phase9_closure_manifest.py', 'docs/phase_9_local_beta_acceptance_report.md')

PHASE9_COMPLETED_WORKSTREAMS = ({'id': '9.1', 'title': 'Five-Salon Acceptance Dataset', 'status': 'completed'}, {'id': '9.2', 'title': 'Five-Salon Web Booking Acceptance', 'status': 'completed'}, {'id': '9.3A', 'title': 'No-show Operational Handling', 'status': 'completed'}, {'id': '9.3B', 'title': 'Manager and Multi-Salon Stylist Scope Acceptance', 'status': 'completed'}, {'id': '9.4A', 'title': 'Safe Notification Pipeline Acceptance', 'status': 'completed'}, {'id': '9.4B', 'title': 'Metrics, Export and Cleanup Acceptance', 'status': 'completed'}, {'id': '9.5A', 'title': 'Final Acceptance Test Registry Audit', 'status': 'completed'}, {'id': '9.5B', 'title': 'Local Beta Acceptance Command', 'status': 'completed'}, {'id': '9.5C', 'title': 'Final Local Rehearsal and Closure', 'status': 'completed'})

PHASE9_FINAL_COMMANDS = ('python manage.py seed_local_demo_data --reset --beta-acceptance --days 14', 'python manage.py local_beta_acceptance_check --keepdb --failfast')

PHASE9_LOCAL_REHEARSAL = {'date': '2026-07-19', 'status': 'passed', 'five_salon_readiness': {'total': 5, 'ready': 5, 'incomplete': 0, 'without_bookable_path': 0}, 'local_beta_acceptance': {'passed': 4, 'failed': 0, 'skipped': 0}, 'release_readiness': {'passed': 7, 'failed': 0, 'skipped': 0}, 'recorded_structural_guard_modules': 11, 'recorded_structural_tests': 53, 'recorded_release_regression_modules': 66, 'recorded_release_regression_tests': 407}

PHASE9_MANIFEST_RELATIVE_PATH = (
    "apps/main/phase9_closure_manifest.json"
)

PHASE9_REPORT_RELATIVE_PATH = (
    "docs/phase_9_local_beta_acceptance_report.md"
)


def collect_missing_phase9_artifacts(
    base_dir: Path,
) -> tuple[str, ...]:
    """Return required Phase 9 artifacts missing from the repository."""

    return tuple(
        relative_path
        for relative_path in PHASE9_REQUIRED_ARTIFACTS
        if not (base_dir / relative_path).is_file()
    )


def load_phase9_closure_manifest(
    base_dir: Path,
) -> dict:
    """Load the committed Phase 9 closure manifest."""

    path = (
        base_dir
        / PHASE9_MANIFEST_RELATIVE_PATH
    )

    return json.loads(
        path.read_text(encoding="utf-8")
    )
