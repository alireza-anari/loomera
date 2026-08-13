from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ManagerDashboardCompletionBatch53StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_content_hub_has_three_task_oriented_sections(self):
        source = self.read("templates/dashboards/content_hub.html")
        self.assertIn('data-lm-task-tabs-anchor="manager-content"', source)
        self.assertIn('data-lm-task-key="manage"', source)
        self.assertIn('data-lm-task-key="create"', source)
        self.assertIn('data-lm-task-key="submissions"', source)
        self.assertNotIn('data-lm-task-key="article"', source)
        self.assertNotIn('data-lm-task-key="story"', source)
        self.assertIn("content_summary.team_pending", source)
        self.assertIn('data-content-type-filter', source)

    def test_content_create_errors_can_activate_create_task(self):
        source = self.read("templates/dashboards/content_hub.html")
        self.assertIn("article_form.errors", source)
        self.assertIn("story_form.errors", source)
        self.assertGreaterEqual(source.count("text-loomera-danger"), 2)

    def test_add_customer_uses_current_dashboard_form_language(self):
        source = self.read("templates/accounts/add_customer.html")
        self.assertIn('{% extends "dashboard_template.html" %}', source)
        self.assertIn("data-lm-submit-label", source)
        self.assertIn("اطلاعات اصلی", source)
        self.assertNotIn("text-slate-", source)
        self.assertNotIn("border-slate-", source)
        self.assertNotIn("bg-slate-", source)

    def test_profile_subpages_support_direct_edit_mode(self):
        templates = [
            "templates/dashboards/salon_profile_creator_step1.html",
            "templates/dashboards/salon_profile_creator_step2.html",
            "templates/dashboards/salon_profile_creator_step3.html",
            "templates/dashboards/salon_profile_creator_step6.html",
            "templates/dashboards/salon_profile_creator_step7.html",
            "templates/dashboards/salon_profile_creator_step8.html",
        ]
        for relative in templates:
            with self.subTest(relative=relative):
                source = self.read(relative)
                self.assertIn("پروفایل مجموعه", source)
                self.assertIn("salon_profile_url", source)
        for relative in templates[3:]:
            with self.subTest(no_old_wizard_copy=relative):
                source = self.read(relative)
                self.assertNotIn("ذخیره و ادامه", source)

    def test_public_activation_is_canonical_in_profile_public_tab(self):
        template = self.read("templates/dashboards/salon_profile_view.html")
        views = self.read("apps/dashboards/views.py")
        readiness = self.read("apps/dashboards/readiness.py")
        self.assertIn("data-salon-public-activation-form", template)
        self.assertIn('name="action" value="activate_public_page"', template)
        self.assertIn("activation_prerequisites_met", template)
        self.assertIn("next_activation_item", template)
        self.assertIn('action == "activate_public_page"', views)
        self.assertIn('?tab=public', views)
        public_item = readiness.split('key="public_active"', 1)[1].split("),", 1)[0]
        self.assertIn('dashboards:salon_profile', public_item)
        self.assertIn('?tab=public', public_item)
        self.assertNotIn('salon_profile_creator_step10', public_item)

    def test_notifications_use_one_filter_action_and_modal(self):
        source = self.read("templates/dashboards/notifications_center.html")
        self.assertIn("data-notification-filter-open", source)
        self.assertIn("data-notification-filter-modal", source)
        self.assertIn("data-notification-active-filter-label", source)
        self.assertIn('event.key === "Escape"', source)
        self.assertNotIn('aria-label="فیلتر سریع اعلان‌ها"', source)

    def test_manager_dashboard_routes_have_single_canonical_destinations(self):
        source = self.read("apps/dashboards/urls.py")
        self.assertIn('RedirectView.as_view(pattern_name="dashboards:salon_manager_dashboard"', source)
        self.assertIn('path("quick-links/", ManagerQuickLinksView.as_view(), name="quick_links")', source)
        for route_name in (
            "finance_cost_center",
            "finance_profit_report",
            "appointment_material_usage",
        ):
            self.assertEqual(source.count(f'name="{route_name}"'), 1, route_name)

    def test_manager_quick_links_keep_dedicated_management_page(self):
        source = self.read("apps/dashboards/urls.py")
        self.assertIn(
            'path("quick-links/", ManagerQuickLinksView.as_view(), name="quick_links")',
            source,
        )
        quick_link_view_source = self.read("apps/dashboards/quick_link_views.py")
        self.assertIn("class ManagerQuickLinksView", quick_link_view_source)
        self.assertIn('template_name = "dashboards/quick_links/index.html"', quick_link_view_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
