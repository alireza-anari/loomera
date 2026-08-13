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

    def test_select_datetime_refreshes_before_accepting_or_submitting_slots(self):
        script = (ROOT / "static/js/select_datetime.js").read_text(encoding="utf-8")
        self.assertIn("cache: 'no-store'", script)
        self.assertIn("refreshAvailabilityForDates([state.currentDate])", script)
        self.assertIn("findStalePickedSelection", script)
        self.assertIn("clearPickedFromIndex", script)
        self.assertIn("از فهرست زمان‌های آزاد حذف شد", script)
