from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SpecialistDashboardCompletionBatch54StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_specialist_navigation_exposes_core_mobile_tasks_and_more_panel(self):
        layout = self.read("apps/dashboards/layout.py")
        self.assertIn('STYLIST_MOBILE_NAV_KEYS = ["overview", "my_appointments", "my_schedule"]', layout)
        for key in ['"my_finance"', '"quick_links"', '"my_content"', '"my_profile"', '"my_settings"']:
            self.assertIn(key, layout)
        self.assertIn('"label": "بیشتر"', layout)
        self.assertIn('"key": "management"', layout)

    def test_specialist_settings_notifications_and_communications_have_real_routes(self):
        urls = self.read("apps/dashboards/urls.py")
        views = self.read("apps/dashboards/views.py")
        settings_views = self.read("apps/dashboards/manager_settings_views.py")
        accounts = self.read("apps/accounts/views.py")
        for name in [
            'name="stylist_notifications"',
            'name="stylist_settings"',
            'name="stylist_communication_settings"',
            'name="stylist_quick_link_options"',
        ]:
            self.assertIn(name, urls)
        self.assertIn("class StylistNotificationCenterView", views)
        self.assertIn("class StylistSettingsHubView", views)
        self.assertIn("class StylistCommunicationSettingsView", settings_views)
        self.assertIn("NotificationAudienceRole.STYLIST", settings_views)
        self.assertIn('reverse("dashboards:stylist_settings")', accounts)

    def test_self_profile_cannot_edit_login_mobile_and_keeps_account_boundary(self):
        forms = self.read("apps/stylists/forms.py")
        views = self.read("apps/dashboards/views.py")
        template = self.read("templates/dashboards/stylist_profile.html")
        self.assertIn("allow_mobile_edit=True", forms)
        self.assertIn('self.fields.pop("mobile_number", None)', forms)
        profile_block = views.split("class StylistProfileView", 1)[1].split("\nclass ", 1)[0]
        self.assertIn("allow_mobile_edit=False", profile_block)
        self.assertIn("شماره موبایل ورود", template)
        self.assertIn("شناسه ورود حساب است", template)
        self.assertNotIn("bale_connect_card", template)

    def test_schedule_and_appointments_remove_duplicate_tasks(self):
        schedule = self.read("templates/dashboards/stylist_schedule.html")
        appointments = self.read("templates/dashboards/stylist_appointments.html")
        for label in ["شیفت‌ها", "درخواست برنامه", "مرخصی"]:
            self.assertIn(f'data-lm-task-label="{label}"', schedule)
        self.assertNotIn('data-lm-task-key="services"', schedule)
        for label in ["امروز", "آینده", "گذشته"]:
            self.assertIn(f'data-lm-task-label="{label}"', appointments)
        self.assertNotIn('data-lm-task-label="همه"', appointments)
        # Keep the production/runtime scoped context contract without
        # re-introducing a duplicate "all" task in the UI.
        self.assertIn("all_appointment_cards", self.read("apps/dashboards/views.py"))

    def test_income_uses_only_finalized_financial_snapshots_and_withdrawals_are_separate(self):
        views = self.read("apps/dashboards/views.py")
        finance_block = views.split("class StylistFinanceView", 1)[1].split("\nclass ", 1)[0]
        self.assertIn("OrderDetailFinancialSnapshot.Status.FINALIZED", finance_block)
        self.assertIn('.exclude(transaction_type__in=["withdraw_request", "withdraw_restore"])', finance_block)
        self.assertNotIn("build_stylist_finance_payload(", finance_block)
        finance_template = self.read("templates/dashboards/stylist_finance.html")
        self.assertIn("درآمد قطعی خدمات من", finance_template)
        self.assertIn('data-lm-task-label="تغییرات درآمد"', finance_template)
        withdrawals = self.read("templates/dashboards/stylist_withdrawals.html")
        self.assertNotIn('data-lm-task-key="transactions"', withdrawals)
        self.assertNotIn("جمع مانده مالی", withdrawals)

    def test_specialist_quick_link_time_mode_reuses_booking_availability(self):
        views = self.read("apps/dashboards/views.py")
        template = self.read("templates/dashboards/stylist_quick_links.html")
        self.assertIn("class StylistQuickLinkOptionsView", views)
        self.assertIn("_quick_link_availability_days", views)
        self.assertIn("get_available_slots_for_service", views)
        self.assertIn("این زمان دیگر برای رزرو در دسترس نیست", views)
        self.assertIn("data-options-url", template)
        self.assertIn("data-quick-link-date", template)
        self.assertIn("data-quick-link-time", template)
        self.assertNotIn("quick_link_workspace.time_options", template)
        self.assertNotIn("def _dashboard_time_options", views)
        self.assertNotIn('name="appointment_date" value=', template)

    def test_content_defaults_to_submission_management_and_removes_overview_task(self):
        template = self.read("templates/dashboards/stylist_content.html")
        content_views = self.read("apps/dashboards/content_views.py")
        self.assertNotIn("creator-overview", template)
        self.assertIn('data-lm-task-label="ارسال‌های من"', template)
        self.assertIn('data-lm-task-label="مقاله جدید"', template)
        self.assertIn('data-lm-task-label="استوری جدید"', template)
        self.assertIn("data-stylist-content-search", template)
        self.assertIn("stylist_content_summary", content_views)

    def test_specialist_home_is_summary_not_duplicate_management_hub(self):
        template = self.read("templates/dashboards/stylist_dashboard.html")
        self.assertIn("نوبت‌های امروز", template)
        self.assertIn("شیفت‌های آینده", template)
        self.assertIn("دسترسی سریع", template)
        self.assertNotIn("مرخصی‌های من", template)
        self.assertNotIn("خدمات من</h2>", template)

    def test_notifications_template_is_role_neutral_and_specialist_context_is_supplied(self):
        template = self.read("templates/dashboards/notifications_center.html")
        views = self.read("apps/dashboards/views.py")
        self.assertIn("notification_center_title", template)
        self.assertIn("notification_center_description", template)
        specialist_block = views.split("class StylistNotificationCenterView", 1)[1].split("\nclass ", 1)[0]
        self.assertIn('"notification_center_title": "مرکز اعلان‌های من"', specialist_block)
        self.assertIn('role="stylist"', specialist_block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
