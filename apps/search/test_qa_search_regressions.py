from pathlib import Path

from django.test import SimpleTestCase

from apps.search.utils import _format_search_date_label, _slot_is_past


ROOT = Path(__file__).resolve().parents[2]


class SearchQaRegressionTests(SimpleTestCase):
    def test_exact_service_filter_supports_catalog_clones(self):
        source = (ROOT / "apps/search/utils.py").read_text(encoding="utf-8")
        self.assertIn("services__catalog_source_id=canonical_id", source)
        self.assertIn("_find_salon_service_variant", source)

    def test_today_availability_filters_past_start_times(self):
        source = (ROOT / "apps/search/utils.py").read_text(encoding="utf-8")
        self.assertIn("_slot_is_past(current_date, start_minutes)", source)

    def test_weekly_availability_uses_jalali_label_helper(self):
        source = (ROOT / "apps/search/utils.py").read_text(encoding="utf-8")
        self.assertIn("_format_search_date_label(current_date)", source)

    def test_distance_badge_is_limited_to_nearest_sort(self):
        template = (ROOT / "templates/search/search_results.html").read_text(encoding="utf-8")
        self.assertIn("salon.search_show_distance and salon.search_distance_km", template)

    def test_map_popup_focus_opens_results_and_focuses_card(self):
        map_js = (ROOT / "static/js/search/map.js").read_text(encoding="utf-8")
        filters_js = (ROOT / "static/js/search/filters.js").read_text(encoding="utf-8")
        self.assertIn("setDesktopResultsOpen", map_js)
        self.assertIn("card.focus", map_js)
        self.assertIn("setDesktopResultsOpen,", filters_js)
