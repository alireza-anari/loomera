from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class SafeMergeCustomerFilterRouteStaticGuard(TestCase):
    def test_non_ajax_customer_filter_returns_to_canonical_manager_customers_page(self):
        source = (ROOT / "apps/search/views.py").read_text(encoding="utf-8")
        urls = (ROOT / "apps/dashboards/urls.py").read_text(encoding="utf-8")
        self.assertIn('return redirect("dashboards:salons_customers_page")', source)
        self.assertNotIn('return redirect("dashboards:salons_customers")', source)
        self.assertIn('name="salons_customers_page"', urls)
