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

    def test_calendar_renders_leave_as_a_distinct_non_appointment_event(self):
        source = self.read("templates/dashboards/components/appointments_calendar_board.html")
        page = self.read("templates/dashboards/appointment_calendar.html")
        self.assertIn("calendar.focus_day.all_day_leaves", source)
        self.assertIn("day.events", source)
        self.assertIn("item.is_leave", source)
        self.assertIn("lm-calendar-leave-event", source)
        self.assertIn("lm-calendar-leave-agenda-card", page)
        self.assertIn("مرخصی", source)

    def test_mobile_defaults_to_day_and_desktop_defaults_to_week(self):
        source = self.read("static/js/pages/appointments_management.js")
        self.assertIn('const defaultMode = isMobileViewport() ? "day" : "week";', source)
        self.assertIn("initCalendarViewSwitcher", source)
        self.assertIn("loomera:appointments:calendar-view", source)

    def test_mobile_week_uses_compact_week_agenda_instead_of_desktop_grid(self):
        board = self.read("templates/dashboards/components/appointments_calendar_board.html")
        page = self.read("templates/dashboards/appointment_calendar.html")
        self.assertIn("data-calendar-mobile-week", board)
        self.assertIn("data-calendar-desktop-week", board)
        self.assertIn("data-calendar-mobile-day-strip", board)
        self.assertIn('[data-calendar-mode="week"] [data-calendar-mobile-day-strip]', page)


    def test_day_empty_state_does_not_claim_leave_is_absent(self):
        board = self.read("templates/dashboards/components/appointments_calendar_board.html")
        self.assertIn("برای این روز نوبتی ثبت نشده است", board)
        self.assertNotIn("برای این روز نوبت یا مرخصی ثبت نشده", board)

    def test_mobile_week_days_are_collapsed_native_accordions(self):
        board = self.read("templates/dashboards/components/appointments_calendar_board.html")
        self.assertIn("data-calendar-mobile-week-day", board)
        self.assertIn("<details", board)
        self.assertIn("<summary", board)
        self.assertIn("group-open:rotate-180", board)
        self.assertIn("نمایش این روز", board)
        self.assertNotIn("<details data-calendar-mobile-week-day open", board)

    def test_mobile_week_show_day_link_switches_to_day_view(self):
        source = self.read("apps/dashboards/appointment_management.py")
        self.assertIn('calendar_view="day"', source)
        self.assertIn('start=format_jalali_numeric(day)', source)
        self.assertIn('end=format_jalali_numeric(day)', source)

    def test_calendar_navigation_changes_by_active_view_mode(self):
        board = self.read("templates/dashboards/components/appointments_calendar_board.html")
        source = self.read("apps/dashboards/appointment_management.py")
        self.assertIn("calendar.previous_day_url", board)
        self.assertIn("calendar.next_day_url", board)
        self.assertIn("calendar.previous_week_url", board)
        self.assertIn("calendar.next_week_url", board)
        self.assertIn("calendar.focus_day.full_label", board)
        self.assertIn('"previous_day_url": _build_query_url', source)
        self.assertIn('"next_day_url": _build_query_url', source)

    def test_filter_dates_open_jalali_picker_without_mobile_keyboard(self):
        source = self.read("static/js/pages/appointments_management.js")
        self.assertIn('input.readOnly = mobilePickerOnly', source)
        self.assertIn('mobilePickerOnly ? "none" : "numeric"', source)
        self.assertIn("normalizeJalaliDatePickerLayer", source)
        self.assertIn("initJalaliDatePicker();", source)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
