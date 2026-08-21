from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BetaUxCalendarRegressionStaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_manual_booking_form_defines_shared_field_class(self):
        source = self.read("apps/dashboards/forms.py")
        block = source.split("class DashboardManualBookingForm", 1)[1].split("    def clean", 1)[0]
        self.assertIn("field_class = DASHBOARD_FIELD_CLASS", block)
        self.assertIn('self.fields["appointment_date"].widget.attrs.update', block)

    def test_calendar_view_toggle_has_real_urls_and_visible_active_state(self):
        board = self.read("templates/dashboards/components/appointments_calendar_board.html")
        page = self.read("templates/dashboards/appointment_calendar.html")
        self.assertIn("calendar.day_view_url", board)
        self.assertIn("calendar.week_view_url", board)
        self.assertIn('data-calendar-mode="{{ calendar.view_mode }}"', board)
        self.assertIn('background: #735CBE', page)
        self.assertIn('aria-pressed="true"', board)

    def test_calendar_counts_use_visible_week_and_stylist_counts_ignore_only_stylist_filter(self):
        source = self.read("apps/dashboards/appointment_management.py")
        self.assertIn("calendar_tab_base = _apply_basic_filters", source)
        self.assertIn("start_date=calendar_week_start", source)
        self.assertIn("end_date=calendar_week_end", source)
        self.assertIn("week_count_base = _apply_basic_filters", source)
        self.assertIn("stylist_id=None", source)
        self.assertIn("count_queryset=week_count_qs", source)
        self.assertIn('"calendar_rows_count_label": week_calendar["appointment_count_label"]', source)

    def test_calendar_includes_only_approved_salon_scoped_staff_leave_requests(self):
        source = self.read("apps/dashboards/appointment_management.py")
        board = self.read("templates/dashboards/components/appointments_calendar_board.html")
        self.assertIn("StaffLeaveRequest.objects.filter", source)
        self.assertIn("salon=salon", source)
        self.assertIn("status=StaffLeaveRequest.Status.APPROVED", source)
        self.assertIn("selected_stylist_id", source)
        self.assertIn('item.is_leave', board)
        self.assertIn('مرخصی', board)
        self.assertIn('calendar.has_all_day_leaves', board)

    def test_in_progress_and_attention_tabs_use_lifecycle_events_not_confirmation_only(self):
        source = self.read("apps/dashboards/appointment_management.py")
        self.assertIn('order__service_started_at__isnull=False', source)
        self.assertIn('order__service_completed_at__isnull=True', source)
        self.assertIn('order__stylist_confirmed_at__isnull=True', source)


if __name__ == "__main__":
    unittest.main()
