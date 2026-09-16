from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class SelectDateTimeAvailabilityContractStaticTests(SimpleTestCase):
    def test_public_monthly_availability_reuses_canonical_blocking_queryset(self):
        views = (ROOT / "apps/orders/views.py").read_text(encoding="utf-8")
        booking_utils = (ROOT / "apps/orders/booking_utils.py").read_text(encoding="utf-8")

        api_block = views.split("class StylistAvailabilityAPI", 1)[1].split(
            "class StylistsForServiceAPI", 1
        )[0]
        self.assertIn("get_blocking_order_details_queryset", api_block)
        self.assertNotIn("service__is_platform_catalog", api_block.split("booked_items =", 1)[1])
        self.assertIn('response["Cache-Control"] = "no-store, private"', api_block)

        helper_block = booking_utils.split(
            "def get_blocking_order_details_queryset", 1
        )[1].split("def _get_booking_windows", 1)[0]
        self.assertIn("order__status__in", helper_block)
        self.assertIn("Q(order__is_finally=True) | Q(order__is_paid=True)", helper_block)
        self.assertNotIn("service__is_active", helper_block)
        self.assertNotIn("service__is_platform_catalog", helper_block)

    def test_selected_future_date_loads_its_exact_month_before_slot_calculation(self):
        script = (ROOT / "static/js/select_datetime.js").read_text(encoding="utf-8")
        load_month_block = script.split("async function loadAvailabilityForMonth", 1)[1].split("function getJalaliMonthForIsoDate", 1)[0]
        load_times_block = script.split("async function loadTimesForDate", 1)[1].split("function renderTimeSlots", 1)[0]

        self.assertIn("clearAvailabilityCache();", load_month_block)
        self.assertIn("const targetMonth = getJalaliMonthForIsoDate(dateStr);", load_times_block)
        self.assertIn("await loadAvailabilityForMonth(targetMonth.year, targetMonth.month);", load_times_block)
        self.assertLess(
            load_times_block.index("await loadAvailabilityForMonth"),
            load_times_block.index("await getAvailabilityForDate"),
        )

    def test_select_datetime_refreshes_before_accepting_or_submitting_slots(self):
        script = (ROOT / "static/js/select_datetime.js").read_text(encoding="utf-8")
        self.assertIn("cache: 'no-store'", script)
        self.assertIn("refreshAvailabilityForDates([state.currentDate])", script)
        self.assertIn("findStalePickedSelection", script)
        self.assertIn("clearPickedFromIndex", script)
        self.assertIn("از فهرست زمان‌های آزاد حذف شد", script)
