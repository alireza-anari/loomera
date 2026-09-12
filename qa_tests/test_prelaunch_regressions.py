from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class PreLaunchQaStaticRegressionTests(unittest.TestCase):
    def test_lm_qa_001_requirements_dev_has_no_shell_command(self):
        self.assertNotIn("python manage.py test", read("requirements-dev.txt"))

    def test_lm_qa_002_readme_does_not_reference_missing_phase9_script(self):
        self.assertNotIn("apply_phase9_closure.py", read("README.md"))

    def test_lm_qa_003_verify_template_has_balanced_if_tags(self):
        source = read("templates/accounts/verify.html")
        self.assertEqual(len(re.findall(r"{%\\s*if\\b", source)), len(re.findall(r"{%\\s*endif\\s*%}", source)))

    def test_lm_qa_004_authenticated_html_is_no_store(self):
        middleware = read("middlewares/middlewares.py")
        settings = read("loomera/settings/base.py")
        self.assertIn("AuthenticatedHtmlNoStoreMiddleware", middleware)
        self.assertIn('private, no-store, no-cache', middleware)
        self.assertIn("middlewares.middlewares.AuthenticatedHtmlNoStoreMiddleware", settings)

    def test_lm_qa_005_exact_service_filter_understands_catalog_clone_identity(self):
        source = read("apps/search/utils.py")
        self.assertIn("catalog_source_id=canonical_id", source)
        self.assertIn("_find_salon_service_variant", source)

    def test_lm_qa_006_today_slots_drop_past_times(self):
        source = read("apps/search/utils.py")
        self.assertIn("_slot_is_past(current_date, start_minutes)", source)
        self.assertIn("timezone.localtime(timezone.now())", source)

    def test_lm_qa_007_weekly_search_date_is_jalali(self):
        source = read("apps/search/utils.py")
        self.assertIn("JalaliDate(value)", source)
        self.assertIn("_format_search_date_label(current_date)", source)

    def test_lm_qa_008_distance_only_surfaces_for_nearest_sort(self):
        source = read("apps/search/utils.py")
        template = read("templates/search/search_results.html")
        self.assertIn('search_show_distance', source)
        self.assertIn('salon.search_show_distance', template)

    def test_lm_qa_009_map_reveal_focuses_corresponding_result_card(self):
        map_js = read("static/js/search/map.js")
        filters_js = read("static/js/search/filters.js")
        self.assertIn("setDesktopResultsOpen", map_js)
        self.assertIn("scrollIntoView", map_js)
        self.assertIn("card.focus", map_js)
        self.assertIn("setDesktopResultsOpen", filters_js)

    def test_lm_qa_010_selected_booking_state_has_explicit_accessible_treatment(self):
        source = read("static/js/select_datetime.js")
        self.assertIn("انتخاب‌شده", source)
        self.assertRegex(source, r"ring-|aria-")

    def test_lm_qa_011_completed_booking_clears_client_draft(self):
        view = read("apps/orders/views.py")
        template = read("templates/orders/appointments.html")
        self.assertIn("booking_completed_cleanup_client", view)
        self.assertIn("sessionStorage.removeItem", template)

    def test_lm_qa_012_initial_availability_renders_without_blocking_future_preload(self):
        source = read("static/js/select_datetime.js")
        self.assertIn("preloadAvailabilityWindow", source)
        self.assertIn("render", source)

    def test_lm_qa_013_checkout_conflict_notice_is_attempt_scoped(self):
        source = read("apps/orders/views.py")
        self.assertIn('request.session.pop("checkout_slot_lost_notice", None)', source)
        self.assertIn("_pop_checkout_slot_lost_notice", source)

    def test_lm_qa_014_multiservice_validation_uses_item_index(self):
        source = read("static/js/select_datetime.js")
        self.assertIn("getEarliestMinutesForDate(dateStr, index", source)
        self.assertIn("getAvailabilityForDate(selection, dateStr, index", source)

    def test_lm_qa_015_inactive_service_fails_with_validation_error_not_get_exception(self):
        source = read("apps/orders/booking_utils.py")
        self.assertIn("Services.objects.filter(", source)
        self.assertIn("دیگر فعال یا قابل رزرو نیست", source)

    def test_lm_qa_016_cancelled_private_page_cannot_be_bfcache_restored(self):
        self.test_lm_qa_004_authenticated_html_is_no_store()

    def test_lm_qa_017_stale_reschedule_requires_active_specialist(self):
        source = read("apps/orders/booking_utils.py")
        self.assertIn("user_id=int(requested_stylist_id)", source)
        self.assertGreaterEqual(source.count("is_active=True"), 4)

    def test_lm_qa_018_inactive_specialist_filtered_from_booking_candidates(self):
        source = read("apps/orders/booking_utils.py")
        self.assertIn("salon.stylists.filter(", source)
        self.assertIn("services_of_stylist=service", source)
        self.assertIn("is_active=True", source)

    def test_lm_qa_019_schedule_rewrite_detects_existing_booking_conflicts(self):
        source = read("apps/dashboards/views.py")
        self.assertIn("get_blocking_order_details_queryset", source)
        self.assertIn("conflicting_bookings", source)
        self.assertIn("هیچ نوبتی خودکار جابه‌جا نشد", source)

    def test_lm_qa_020_appointment_duration_uses_snapshot_semantics(self):
        model = read("apps/orders/models.py")
        detail = read("templates/orders/appointment_detail.html")
        self.assertIn("def display_duration_minutes", model)
        self.assertIn("scheduled_duration_minutes", model)
        self.assertIn("display_duration_minutes", detail)

    def test_lm_qa_021_stale_checkout_price_requires_reconsent(self):
        source = read("apps/orders/views.py")
        self.assertIn("_checkout_price_consent_snapshot", source)
        self.assertIn("_checkout_price_consent_changed", source)
        self.assertIn("دوباره تأیید کنید", source)

    def test_lm_qa_022_calendar_selection_syncs_day_strip_and_slots(self):
        source = read("static/js/select_datetime.js")
        self.assertIn("syncCalendarStripToCurrentDate", source)
        self.assertIn("scrollIntoView", source)
        self.assertIn("datepicker", source)

    def test_lm_qa_023_schedule_request_action_is_normalized_before_review(self):
        source = read("apps/dashboards/views.py")
        self.assertIn('"approved": "approve"', source)
        self.assertIn('"rejected": "reject"', source)
        self.assertIn("review_schedule_request", source)

    def test_lm_qa_024_customer_notification_timestamp_uses_localtime(self):
        source = read("apps/accounts/views.py")
        self.assertIn("timezone.localtime(notification.created_at)", source)

    def test_lm_qa_025_partner_notifications_poll_without_creating_events(self):
        source = read("static/js/pages/dashboard_layout.js")
        self.assertIn("refreshDashboardNotifications", source)
        self.assertIn("window.setInterval(refreshDashboardNotifications, 30000)", source)
        self.assertIn('cache: "no-store"', source)

    def test_lm_qa_026_cancellation_deeplink_is_object_specific(self):
        source = read("apps/accounts/notifications.py")
        self.assertIn("action_url=action_url or _order_detail_action_url(order)", source)

    def test_lm_qa_027_reschedule_generates_customer_notification(self):
        notifications = read("apps/accounts/notifications.py")
        orders = read("apps/orders/views.py")
        self.assertIn("def notify_booking_rescheduled", notifications)
        self.assertIn("notify_booking_rescheduled", orders)

    def test_lm_qa_028_read_state_is_persisted_across_legacy_and_unified_layers(self):
        source = read("apps/accounts/views.py")
        self.assertIn("NotificationRecipient.objects.filter", source)
        self.assertIn('notification__metadata__legacy_model="CustomerNotification"', source)
        self.assertIn('Cache-Control"] = "private, no-store"', source)

    def test_lm_qa_029_completion_notifies_customer(self):
        source = read("apps/orders/appointment_lifecycle.py")
        block = source.split("def complete_service", 1)[1].split("def mark_no_show_pending", 1)[0]
        self.assertIn('_notify_appointment_lifecycle', block)
        self.assertIn('include_customer=True', block)

    def test_lm_qa_030_review_modal_is_localized(self):
        source = read("templates/orders/appointment_detail.html")
        self.assertNotIn('>Review</p>', source)
        self.assertIn('>دیدگاه</p>', source)

    def test_lm_qa_031_salon_review_date_is_jalali(self):
        source = read("apps/salons/views.py")
        self.assertIn('"date": format_jalali_numeric(c.register_date)', source)

    def test_lm_qa_032_duplicate_review_is_server_side_prevented(self):
        service = read("apps/comments_scores_favories/review_service.py")
        appointment = read("apps/orders/views.py")
        salon = read("apps/comments_scores_favories/views.py")
        self.assertIn("select_for_update", service)
        self.assertIn("DuplicateReviewError", service)
        self.assertIn("create_customer_review_once", appointment)
        self.assertIn("create_customer_review_once", salon)

    def test_lm_qa_033_salon_review_eligibility_uses_completed_history_even_if_now_inactive(self):
        form = read("apps/comments_scores_favories/forms.py")
        salon = read("apps/salons/views.py")
        self.assertIn("order__review_completed_at__isnull=True", form)
        self.assertNotRegex(form, r'pk__in=eligible_stylist_ids,\s*is_active=True')
        self.assertIn("form.eligible_order_details.exists()", salon)

    def test_lm_qa_034_profile_form_retains_customer_instance_for_image_save(self):
        source = read("apps/accounts/forms.py")
        self.assertIn("self.customer_instance = customer_instance", source)
        self.assertIn("validate_customer_profile_image_upload", source)

    def test_lm_qa_035_customer_notification_category_counts_use_full_queryset(self):
        source = read("apps/accounts/views.py")
        self.assertIn("category_counts", source)
        self.assertIn("all_notifications.filter(category=category).count()", source)

    def test_lm_qa_036_calendar_status_is_textual_not_color_only(self):
        source = read("templates/dashboards/components/appointments_calendar_board.html")
        self.assertIn("data-calendar-status", source)
        self.assertIn("item.status.label", source)
        self.assertIn("fa-circle-info", source)

    def test_lm_qa_037_customer_unread_visual_hierarchy_is_explicit(self):
        template = read("templates/accounts/notifications.html")
        js = read("static/js/pages/customer_notifications.js")
        self.assertIn("data-notification-unread", template)
        self.assertIn("ring-1 ring-loomera-primary/10", template)
        self.assertIn("markCardAsRead", js)

    def test_lm_qa_038_rag_excludes_future_payment_docs_and_has_beta_truth(self):
        retrieval = read("apps/help_center/retrieval.py")
        truth = read("apps/help_center/product_truth.py")
        docs = json.loads(read("apps/help_center/data/production_docs.json"))
        self.assertIn("BETA_INACTIVE_HELP_ARTICLE_KEYS", retrieval)
        self.assertIn("pay_at_salon_only", truth)
        article = next(item for item in docs["articles"] if item["key"] == "customer.payment.beta-pay-at-salon-only")
        self.assertIn("فقط در مجموعه", article["summary"])
        self.assertIn("کیف پول مشتری", article["body"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
