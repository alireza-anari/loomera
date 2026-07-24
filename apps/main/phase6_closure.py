from __future__ import annotations

import json
from pathlib import Path


PHASE6_REQUIRED_ARTIFACTS = ('apps/main/test_runtime_debug_output_security.py', 'apps/main/test_frontend_console_security.py', 'apps/main/test_sensitive_bare_exception_guard.py', 'apps/main/sensitive_exception_inventory.py', 'apps/main/sensitive_broad_exception_allowlist.json', 'apps/main/test_sensitive_broad_exception_allowlist.py', 'apps/main/test_python_source_encoding_integrity.py', 'apps/main/regression_suites.py', 'apps/main/management/commands/run_regression_suite.py', 'apps/main/test_regression_suite_registry.py', 'apps/main/release_readiness.py', 'apps/main/management/commands/release_readiness_check.py', 'apps/main/test_release_readiness_check.py', 'apps/payments/test_safe_numeric_conversion.py', 'apps/payments/test_gateway_init_response_parsing.py', 'apps/payments/test_payment_command_exception_boundary.py', 'apps/payments/payment_gateway_contract_manifest.json', 'apps/payments/test_gateway_contract_documentation.py', 'apps/orders/test_reschedule_payload_exception_scope.py', 'apps/orders/test_booking_session_security.py', 'apps/orders/test_order_detail_field_inspection.py', 'apps/orders/booking_checkout_contract_manifest.json', 'apps/orders/test_booking_checkout_contract_documentation.py', 'apps/api/tests/test_api_v1_otp_cache_delete_policy.py', 'apps/api/tests/test_api_v1_auth_payload_parsing.py', 'apps/api/otp_auth_contract_manifest.json', 'apps/api/tests/test_api_v1_otp_auth_contract_documentation.py', 'apps/messaging/test_bot_url_exception_scope.py', 'apps/messaging/test_management_command_exception_scope.py', 'apps/messaging/test_promotion_bot_url_exception_scope.py', 'apps/messaging/messaging_bale_contract_manifest.json', 'apps/messaging/test_messaging_bale_contract_documentation.py', 'apps/notifications/migrations/0003_align_notification_choice_labels.py')

PHASE6_COMPLETED_WORKSTREAMS = ({'id': '6.1A', 'title': 'Runtime Debug and Logging Audit', 'status': 'completed'}, {'id': '6.1B-1', 'title': 'Frontend Debug Console Cleanup', 'status': 'completed'}, {'id': '6.1B-2', 'title': 'Raw Error and Payload Console Sanitization', 'status': 'completed'}, {'id': '6.2A', 'title': 'Safe Numeric Conversion', 'status': 'completed'}, {'id': '6.2B-1', 'title': 'Booking Session and JSON Exception Scope', 'status': 'completed'}, {'id': '6.2B-2', 'title': 'Booking Metadata Exception Scope', 'status': 'completed'}, {'id': '6.2C-1', 'title': 'OTP Cache Delete Exception Boundary', 'status': 'completed'}, {'id': '6.2C-2', 'title': 'Authentication Payload Parsing', 'status': 'completed'}, {'id': '6.2D-1', 'title': 'Messaging and Bale URL Exception Scope', 'status': 'completed'}, {'id': '6.2D-2', 'title': 'Messaging Command Exception Guard', 'status': 'completed'}, {'id': '6.2E-1', 'title': 'Gateway Init Response Parsing', 'status': 'completed'}, {'id': '6.2E-2', 'title': 'Payment Command Exception Boundary', 'status': 'completed'}, {'id': '6.2F-1', 'title': 'Sensitive Bare Exception Cleanup', 'status': 'completed'}, {'id': '6.2F-2A', 'title': 'Promotion Bot URL Exception Scope', 'status': 'completed'}, {'id': '6.2F-2B', 'title': 'Final Broad Exception Allowlist', 'status': 'completed'}, {'id': '6.2G', 'title': 'Python Source Encoding Integrity', 'status': 'completed'}, {'id': '6.3A', 'title': 'Payment Gateway Contract Documentation', 'status': 'completed'}, {'id': '6.3B', 'title': 'Booking and Checkout Contract Documentation', 'status': 'completed'}, {'id': '6.3C', 'title': 'OTP and Authentication Contract Documentation', 'status': 'completed'}, {'id': '6.3D', 'title': 'Messaging and Bale Delivery Contract Documentation', 'status': 'completed'}, {'id': '6.4A', 'title': 'Regression Suite Registry and Entry Points', 'status': 'completed'}, {'id': '6.4B', 'title': 'Release Check Orchestration and Summary', 'status': 'completed'}, {'id': '6.4B-1', 'title': 'Notification Migration State Alignment', 'status': 'completed'}, {'id': '6.4C', 'title': 'Full Local Release Rehearsal', 'status': 'completed'}, {'id': '6.4C-1', 'title': 'Scheduled Tasks Dry-Run Safety', 'status': 'completed'})

PHASE6_RELEASE_COMMANDS = ('python manage.py run_regression_suite security --keepdb', 'python manage.py run_regression_suite payments --keepdb', 'python manage.py run_regression_suite booking --keepdb', 'python manage.py run_regression_suite messaging --keepdb', 'python manage.py run_regression_suite release-check --keepdb --failfast', 'python manage.py release_readiness_check --keepdb --failfast', 'python manage.py check', 'python manage.py makemigrations --check --dry-run', 'python manage.py migrate --check')

PHASE6_LOCAL_REHEARSAL = {'date': '2026-07-12', 'status': 'passed', 'stages': {'passed': 7, 'failed': 0, 'skipped': 0}, 'recorded_structural_guard_modules': 10, 'recorded_structural_tests': 48, 'dry_run_safety_tests_added_after_rehearsal': 3, 'release_regression_modules': 52, 'release_regression_tests': 347, 'closure_guard_modules_added': 1, 'closure_guard_tests_added': 5, 'expected_final_structural_guard_modules': 11, 'expected_final_structural_tests': 56}

PHASE6_MANIFEST_RELATIVE_PATH = (
    "apps/main/phase6_closure_manifest.json"
)

PHASE6_REPORT_RELATIVE_PATH = (
    "docs/phase_6_local_quality_report.md"
)


def collect_missing_phase6_artifacts(
    base_dir: Path,
) -> tuple[str, ...]:
    """Return required Phase 6 artifacts missing from the repository."""

    return tuple(
        relative_path
        for relative_path in PHASE6_REQUIRED_ARTIFACTS
        if not (base_dir / relative_path).is_file()
    )


def load_phase6_closure_manifest(
    base_dir: Path,
) -> dict:
    """Load the committed Phase 6 closure manifest."""

    path = (
        base_dir
        / PHASE6_MANIFEST_RELATIVE_PATH
    )

    return json.loads(
        path.read_text(encoding="utf-8")
    )
