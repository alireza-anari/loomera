from __future__ import annotations

from collections.abc import Iterable

SECURITY_SUITE = (
    "apps.main.test_runtime_debug_output_security",
    "apps.main.test_frontend_console_security",
    "apps.main.test_sensitive_bare_exception_guard",
    "apps.main.test_sensitive_broad_exception_allowlist",
    "apps.main.test_python_source_encoding_integrity",
    "apps.main.test_production_security_audit",
    "apps.main.test_secrets_static_media_audit",
    "apps.main.test_media_proxy_security",
    "apps.accounts.test_stage1_auth_access",
    "apps.accounts.test_otp_rate_limit_security",
    "apps.api.tests.test_api_v1_auth_security",
    "apps.api.tests.test_api_v1_auth_payload_parsing",
    "apps.api.tests.test_api_v1_otp_cache_delete_policy",
    "apps.api.tests.test_api_v1_otp_auth_contract_documentation",
    "apps.bale_bot.test_webhook_security",
    "apps.messaging.tests_security",
    "apps.search.test_mapir_proxy_security",
    "apps.orders.test_public_booking_api_security",
)

QUICK_LINK_RELEASE_TESTS = (
    "apps.dashboards.test_manager_quick_link_creation",
    "apps.dashboards.test_manager_quick_links_page",
    "apps.dashboards.test_quick_link_detail_page",
    "apps.dashboards.test_quick_link_management",
    "apps.dashboards.test_quick_link_qr_endpoints",
    "apps.dashboards.test_stylist_quick_links_stats_page",
    "apps.dashboards.test_quick_link_print_templates",
    "apps.dashboards.test_quick_link_mirror_label_artwork",
    "apps.dashboards.test_quick_link_business_card_dashboard",
    "apps.dashboards.test_quick_link_business_card_print_fidelity",
    "apps.dashboards.test_quick_link_table_stand_artwork",
    "apps.orders.test_booking_quick_link_attribution",
    "apps.orders.test_booking_quick_link_model_contract",
    "apps.orders.test_booking_quick_link_open_analytics",
    "apps.orders.test_booking_quick_link_qr_service",
    "apps.orders.test_booking_quick_link_salon_mode",
    "apps.orders.test_booking_quick_link_start_analytics",
    "apps.orders.test_booking_quick_link_stats",
    "apps.orders.test_quick_link_readiness_check",
)

PAYMENTS_SUITE = (
    "apps.payments.test_gateway_contract_documentation",
    "apps.payments.test_gateway_init_response_parsing",
    "apps.payments.test_gateway_verify_resilience",
    "apps.payments.test_payment_command_exception_boundary",
    "apps.payments.test_payment_preflight_check",
    "apps.payments.test_abandoned_online_checkout",
    "apps.payments.test_safe_numeric_conversion",
    "apps.payments.test_multi_salon_financial_scope",
    "apps.payments.test_appointment_payment_result_state_ux",
    "apps.payments.test_appointment_payment_pending_result_ux",
    "apps.payments.test_appointment_payment_result_mobile_ux",
    "apps.orders.test_pay_in_salon_settlement_security",
    "apps.main.test_local_beta_metrics_export_cleanup_acceptance",
)

BOOKING_SUITE = (
    "apps.orders.test_booking_checkout_contract_documentation",
    "apps.orders.test_booking_session_security",
    "apps.orders.test_checkout_coupon_security",
    "apps.orders.test_checkout_slot_lost_ux",
    "apps.orders.test_checkout_submit_guard_assets",
    "apps.orders.test_checkout_mobile_ux_assets",
    "apps.orders.test_stage1_booking_finance",
    "apps.main.test_local_beta_booking_acceptance",
    "apps.orders.test_no_show_lifecycle_stage",
    "apps.dashboards.test_no_show_operational_status",
    "apps.main.test_local_beta_operational_scope_acceptance",
    "apps.dashboards.test_beta_salon_bookability_readiness",
    "apps.dashboards.test_service_setup_handoff_ux",
    "apps.dashboards.test_team_member_setup_handoff_ux",
    "apps.dashboards.test_team_capacity_setup_workspace",
    "apps.dashboards.test_dashboard_home_setup_priority",
    "apps.dashboards.test_beta_salon_readiness_command",
    "apps.platform_admin.test_salon_beta_readiness_panel",
    "apps.orders.test_public_booking_api_security",
    "apps.orders.test_quick_booking_link_security",
    "apps.orders.test_reschedule_payload_exception_scope",
    "apps.orders.test_order_detail_field_inspection",
    "apps.orders.test_appointment_ics_security",
    "apps.orders.test_appointment_review_security",
    "apps.api.tests.test_api_v1_booking_security",
    "apps.api.tests.test_api_v1_booking_draft_validation",
    "apps.api.tests.test_api_v1_booking_draft_summary",
    "apps.api.tests.test_api_v1_booking_confirm",
    "apps.api.tests.test_api_v1_availability",
    "apps.api.tests.test_api_v1_next_available",
    "apps.main.test_local_beta_acceptance_seed",
    "apps.main.test_staging_acceptance_seed",
    *QUICK_LINK_RELEASE_TESTS,
)

MESSAGING_SUITE = (
    "apps.messaging.test_messaging_bale_contract_documentation",
    "apps.bale_bot.test_webhook_security",
    "apps.messaging.tests_security",
    "apps.messaging.test_promotion_bot_url_exception_scope",
    "apps.messaging.test_bot_url_exception_scope",
    "apps.messaging.test_management_command_exception_scope",
    "apps.messaging.test_bale_queue_readiness",
    "apps.messaging.test_bale_account_link_check",
    "apps.messaging.test_bale_delivery_queue_check",
    "apps.messaging.test_bale_disconnect_hardening",
    "apps.messaging.test_bale_webhook_event_check",
    "apps.messaging.test_bale_webhook_admin",
    "apps.messaging.test_bale_final_readiness_check",
    "apps.messaging.test_messaging_qa_check",
    "apps.main.test_local_beta_notification_acceptance",
)


def _deduplicate(labels: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(labels))


RELEASE_CHECK_SUITE = _deduplicate(
    (
        "apps.main.test_release_quality",
        *SECURITY_SUITE,
        *PAYMENTS_SUITE,
        *BOOKING_SUITE,
        *MESSAGING_SUITE,
    )
)


REGRESSION_SUITES = {
    "security": SECURITY_SUITE,
    "payments": PAYMENTS_SUITE,
    "booking": BOOKING_SUITE,
    "messaging": MESSAGING_SUITE,
    "release-check": RELEASE_CHECK_SUITE,
}


def get_regression_suite(name: str) -> tuple[str, ...]:
    "Return the immutable Django test-label tuple for a named suite."

    try:
        return REGRESSION_SUITES[name]
    except KeyError as exc:
        choices = ", ".join(REGRESSION_SUITES)
        raise ValueError(
            f"Unknown regression suite {name!r}. " f"Available suites: {choices}."
        ) from exc
