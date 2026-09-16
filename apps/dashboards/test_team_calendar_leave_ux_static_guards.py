from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]


class TeamCalendarLeaveUxStaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_team_pages_do_not_render_leave_or_service_coverage_tabs(self):
        team_member = self.read("templates/dashboards/team_member.html")
        team_management = self.read("templates/dashboards/team_management.html")
        for source in (team_member, team_management):
            self.assertNotIn('data-lm-task-key="timeoff"', source)
            self.assertNotIn('data-lm-task-key="coverage"', source)
        self.assertNotIn('team-member-section-timeoff', team_member)
        self.assertNotIn('team-member-section-coverage', team_member)
        self.assertNotIn('team-section-timeoff', team_management)
        self.assertNotIn('team-section-coverage', team_management)

    def test_member_profile_uses_completed_appointments_and_satisfaction_percent(self):
        template = self.read("templates/dashboards/stylist_overview.html")
        view = self.read("apps/dashboards/views.py")
        self.assertNotIn('{{ workload_hint }}', template)
        self.assertNotIn('مشتریان یکتا', template)
        self.assertIn('نوبت‌های انجام‌شده', template)
        self.assertIn('درصد رضایت', template)
        self.assertIn('order__status="completed"', view)
        self.assertIn('satisfaction_percent_label', view)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
