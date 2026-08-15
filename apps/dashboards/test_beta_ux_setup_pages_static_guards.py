from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxSetupPagesStaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_team_navigation_opens_member_list_first(self):
        source = self.read("apps/dashboards/layout.py")
        self.assertIn('"url_name": "dashboards:team_member"', source)
        self.assertIn('"dashboards:team_member",', source)

    def test_service_menu_is_list_first_not_workspace_first(self):
        source = self.read("templates/dashboards/service_menu.html")
        self.assertIn("افزودن خدمت", source)
        self.assertIn("data-service-catalog", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)
        self.assertNotIn("سلامت کاتالوگ خدمات", source)

    def test_add_stylist_uses_clear_task_tabs_and_core_identity_fields(self):
        source = self.read("templates/dashboards/add_stylist.html")
        self.assertIn('data-lm-task-tabs-anchor="add-stylist"', source)
        self.assertIn('data-lm-task-label="اطلاعات اصلی"', source)
        self.assertIn('data-lm-task-label="خدمات"', source)
        self.assertIn('data-lm-task-label="اطلاعات تکمیلی"', source)
        self.assertIn("user_form.name", source)
        self.assertIn("user_form.family", source)
        self.assertIn("user_form.mobile_number", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)

    def test_emergency_contact_is_truly_optional_for_manager_add_flow(self):
        forms_source = self.read("apps/stylists/forms.py")
        views_source = self.read("apps/dashboards/views.py")
        self.assertIn("Beta UX: emergency contact is optional", forms_source)
        self.assertIn("if not any([emergency_name, emergency_family, emergency_phone, relationship])", forms_source)
        self.assertIn("if any([emergency_name, emergency_family, phone, relationship])", views_source)

    def test_successful_setup_actions_return_to_the_relevant_workspace(self):
        source = self.read("apps/dashboards/views.py")

        add_service_block = source[
            source.index("class AddServicesView"):source.index("class RequestServiceView")
        ]
        self.assertIn('service_menu_url = reverse("dashboards:service_menu")', add_service_block)
        self.assertIn('?created_service={service.pk}', add_service_block)
        self.assertNotIn('return redirect("dashboards:add_stylist")', add_service_block)

        add_stylist_block = source[source.index("class AddStylistView"):source.index("class EditStylistView")]
        self.assertIn('team_member_url = reverse("dashboards:team_member")', add_stylist_block)
        self.assertIn('?created_stylist={stylist.user_id}', add_stylist_block)
        self.assertNotIn('return redirect("dashboards:scheduled_shifts")', add_stylist_block)

    def test_team_page_prioritizes_members_and_collapses_advanced_work(self):
        source = self.read("templates/dashboards/team_member.html")
        self.assertIn("اعضای تیم", source)
        self.assertIn("افزودن عضو", source)
        self.assertIn("فیلتر بیشتر", source)
        self.assertIn("دعوت متخصص", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)

    def test_scheduling_is_member_first_and_keeps_request_actions(self):
        source = self.read("templates/dashboards/scheduled_shifts.html")
        self.assertIn("برنامه اعضای تیم", source)
        self.assertIn("تنظیم برنامه منظم", source)
        self.assertIn("scheduled-shifts-section-schedule-requests", source)
        self.assertIn("schedule_request_workspace.pending", source)
        self.assertIn("scheduled-shifts-section-leave-requests", source)
        self.assertIn("leave_request_workspace.pending", source)
        self.assertNotIn("تراکم روزانه برنامه", source)
        self.assertNotIn("توزیع شیفت و مرخصی تیم", source)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
