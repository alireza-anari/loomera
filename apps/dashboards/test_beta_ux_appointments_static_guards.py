from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxAppointmentsStaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_appointments_open_on_today_instead_of_seven_day_report(self):
        source = self.read("apps/dashboards/appointment_management.py")
        self.assertIn("# Beta UX: a normal navigation opens on today", source)
        self.assertIn("has_context_filter = any(", source)
        self.assertIn("default_end = today + timedelta(days=6) if has_context_filter else today", source)

    def test_calendar_is_day_and_list_first(self):
        source = self.read("templates/dashboards/appointment_calendar.html")
        self.assertIn("ثبت نوبت", source)
        self.assertIn("فهرست نوبت‌ها", source)
        self.assertIn("برنامه تیم در این روز", source)
        self.assertIn("data-appointments-filter-modal", source)
        self.assertNotIn("خلاصه عملیاتی", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)
        self.assertNotIn("ارزش رزروها", source)

    def test_calendar_context_exposes_manual_booking_as_primary_action(self):
        source = self.read("apps/dashboards/appointment_management.py")
        template = self.read("templates/dashboards/appointment_calendar.html")
        self.assertIn('"add_booking_url": _safe_reverse(', source)
        self.assertIn('"dashboards:add_booking"', source)
        self.assertIn("appointment_management.add_booking_url", template)

    def test_mobile_appointment_cards_prioritize_time_customer_and_one_tap_management(self):
        source = self.read("templates/dashboards/components/appointments_table.html")
        self.assertIn("{{ row.time_label }}", source)
        self.assertIn("{{ row.customer_name }}", source)
        self.assertIn("{{ row.service_name }} • {{ row.stylist_name }}", source)
        self.assertIn("مدیریت نوبت", source)
        self.assertIn('href="{{ row.detail_url }}"', source)
        self.assertIn("انتخاب و عملیات گروهی", source)

    def test_appointment_detail_puts_lifecycle_action_before_advanced_details(self):
        source = self.read("templates/dashboards/appointment_detail.html")
        action_pos = source.index('id="appointment-section-actions"')
        services_pos = source.index('id="appointment-section-services"')
        finance_pos = source.index('id="appointment-section-finance"')
        self.assertLess(action_pos, services_pos)
        self.assertLess(services_pos, finance_pos)
        self.assertIn("این نوبت نیاز به اقدام دارد", source)
        self.assertIn("detail.timeline_hint", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)
        self.assertNotIn("detail.finance_totals", source)

    def test_detail_keeps_finance_material_dispute_and_customer_paths(self):
        source = self.read("templates/dashboards/appointment_detail.html")
        self.assertIn("item.material_url", source)
        self.assertIn("item.finance_finalize_url", source)
        self.assertIn("finalize_order", source)
        self.assertIn("finalize_detail", source)
        self.assertIn("detail.customer_url", source)
        self.assertIn("detail.has_dispute_cases", source)
        self.assertIn("detail.dispute_cases", source)
        self.assertIn("detail.finance_summary", source)

    def test_manual_booking_is_task_oriented_and_has_mobile_primary_submit(self):
        source = self.read("templates/dashboards/manual_booking_form.html")
        self.assertIn('data-lm-task-tabs-anchor="manual-booking"', source)
        self.assertEqual(source.count('data-lm-task-panel="manual-booking"'), 3)
        self.assertIn('data-lm-task-label="مشتری و خدمت"', source)
        self.assertIn('data-lm-task-label="تاریخ و ساعت"', source)
        self.assertIn('data-lm-task-label="یادداشت"', source)
        self.assertIn('id="manualBookingForm"', source)
        self.assertIn('form="manualBookingForm"', source)
        self.assertIn("bottom-[calc(env(safe-area-inset-bottom,0px)+5.25rem)]", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)
        self.assertNotIn("منبع رزرو", source)

    def test_manual_booking_keeps_all_javascript_contract_ids(self):
        source = self.read("templates/dashboards/manual_booking_form.html")
        required = [
            "manualBookingData",
            "customerAutocomplete",
            "customerSuggestions",
            "id_customer",
            "serviceAutocomplete",
            "serviceSuggestions",
            "id_service",
            "stylistAutocomplete",
            "stylistSuggestions",
            "id_stylist",
            "manualBookingDatePicker",
            "id_appointment_date",
            "id_start_time",
            "manualBookingCalendar",
            "manualBookingMonthTitle",
            "manualBookingCalendarHint",
            "manualBookingTimeSlots",
            "manualBookingSelectedDateLabel",
            "manualBookingSummaryCustomer",
            "manualBookingSummaryService",
            "manualBookingSummaryStylist",
            "manualBookingSummaryDate",
            "manualBookingSummaryTime",
            "manualBookingSummaryStatus",
        ]
        for item in required:
            self.assertIn(f'id="{item}"', source)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
