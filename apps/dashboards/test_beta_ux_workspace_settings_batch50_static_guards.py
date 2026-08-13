from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class WorkspaceSettingsBatch50StaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_settings_page_is_not_a_duplicate_dashboard_menu(self):
        view = self.read("apps/dashboards/views.py")
        block = view[view.index("class WorkspaceSettingsHubView"):]
        for route_name in (
            "appointment_calendar",
            "team_member",
            "service_menu",
            "reports_dashboard",
            "products",
            "stocktakes",
            "finance_hub",
            "payout_settings",
            "catalog",
            "membership",
        ):
            self.assertNotIn(route_name, block)

    def test_settings_has_only_configuration_destinations(self):
        view = self.read("apps/dashboards/views.py")
        block = view[view.index("class WorkspaceSettingsHubView"):]
        for route_name in (
            'dashboards:salon_profile',
            'dashboards:online_booking',
            'dashboards:manager_profile',
            'accounts:change_password',
            'dashboards:manager_communication_settings',
        ):
            self.assertIn(route_name, block)
        self.assertNotIn("?audience_role=manager", block)
        self.assertNotIn('messaging:preferences', block)
        self.assertNotIn('messaging:status', block)

    def test_search_and_fake_readiness_filters_are_removed(self):
        template = self.read("templates/dashboards/workspace_settings.html")
        self.assertNotIn("data-settings-search", template)
        self.assertNotIn("data-settings-filter", template)
        self.assertNotIn("نیاز به تکمیل", template)
        self.assertNotIn("در دسترس", template)
        self.assertNotIn("workspace_settings_summary", template)

    def test_page_explains_operational_pages_live_in_main_navigation(self):
        template = self.read("templates/dashboards/workspace_settings.html")
        self.assertIn("کارهای روزانه", template)
        self.assertIn("از منوی اصلی مدیریت می‌شوند", template)

    def test_legal_links_are_secondary_not_primary_settings_groups(self):
        view = self.read("apps/dashboards/views.py")
        template = self.read("templates/dashboards/workspace_settings.html")
        self.assertIn("workspace_settings_legal_links", view)
        self.assertIn("اطلاعات حقوقی", template)
        self.assertIn('accounts:privacy_policy', view)
        self.assertIn('accounts:terms_of_use', view)

    def test_settings_copy_is_simplified_in_layout(self):
        layout = self.read("apps/dashboards/layout.py")
        self.assertIn('"title": "تنظیمات"', layout)
        self.assertIn('"caption": "پروفایل، حساب، امنیت و اعلان‌ها"', layout)
        self.assertNotIn('"caption": "تنظیمات محیط کاری، حساب مدیر و پیکربندی مجموعه"', layout)
    def test_manager_change_password_returns_to_manager_settings(self):
        view = self.read("apps/accounts/views.py")
        template = self.read("templates/accounts/change_password.html")
        self.assertIn('reverse("dashboards:workspace_settings")', view)
        self.assertIn('"password_return_url": self._return_url(request)', view)
        self.assertIn('href="{{ password_return_url }}"', template)
        self.assertNotIn("{% url 'accounts:customer_settings' %}", template)
