from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]


class BetaUxCalendarSchedulerStaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_calendar_uses_existing_stylist_colors_and_week_context(self):
        source = self.read("apps/dashboards/appointment_management.py")
        self.assertIn("CALENDAR_FALLBACK_COLORS", source)
        self.assertIn("calendar_color", source)
        self.assertIn("_build_week_calendar", source)
        self.assertIn("_calendar_week_start", source)
        self.assertIn('"week_calendar": week_calendar', source)

    def test_calendar_page_is_calendar_first_and_keeps_list_and_team_views(self):
        source = self.read("templates/dashboards/appointment_calendar.html")
        self.assertIn('data-lm-task-key="calendar"', source)
        self.assertIn('data-lm-task-default', source)
        self.assertIn('data-lm-task-key="list"', source)
        self.assertIn('data-lm-task-key="team"', source)
        self.assertIn('dashboards/components/appointments_calendar_board.html', source)

    def test_calendar_board_supports_week_day_and_specialist_filtering(self):
        source = self.read("templates/dashboards/components/appointments_calendar_board.html")
        self.assertIn('data-calendar-view-toggle="day"', source)
        self.assertIn('data-calendar-view-toggle="week"', source)
        self.assertIn("calendar.stylists", source)
        self.assertIn("calendar.days", source)
        self.assertIn("item.stylist_color", source)
        self.assertIn('href="{{ item.detail_url }}"', source)

    def test_mobile_defaults_to_day_and_desktop_defaults_to_week(self):
        source = self.read("static/js/pages/appointments_management.js")
        self.assertIn('const defaultMode = isMobileViewport() ? "day" : "week";', source)
        self.assertIn("initCalendarViewSwitcher", source)
        self.assertIn("loomera:appointments:calendar-view", source)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
