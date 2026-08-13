from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxQuickLinkPrintBatch38StaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_public_salon_quick_link_uses_valid_salon_url_contract(self):
        order_views = self.read("apps/orders/views.py")
        self.assertIn('mode == "salon"', order_views)
        self.assertIn("salon.get_absolute_url()", order_views)
        self.assertNotIn('redirect("salons:detail_salon", pk=salon.id)', order_views)

    def test_each_dashboard_quick_link_exposes_qr_and_print_actions(self):
        quick_links = self.read("apps/orders/quick_links.py")
        manager_template = self.read("templates/dashboards/quick_links/index.html")
        stylist_template = self.read("templates/dashboards/stylist_quick_links.html")
        self.assertIn('"qr_url": qr_url', quick_links)
        self.assertIn('"print_url": print_url', quick_links)
        self.assertIn("quick_link_qr_download", quick_links)
        self.assertIn("quick_link_print_templates", quick_links)
        self.assertIn("link.qr_download_url", manager_template)
        self.assertIn("link.print_url", manager_template)
        self.assertIn("link.qr_download_url", stylist_template)
        self.assertIn("dashboards:stylist_quick_link_print_templates", stylist_template)

    def test_qr_and_print_routes_are_permission_scoped(self):
        urls = self.read("apps/dashboards/urls.py")
        views = self.read("apps/dashboards/quick_link_print_views.py")
        qr_service = self.read("apps/orders/quick_link_qr.py")
        self.assertIn('name="quick_link_qr_download"', urls)
        self.assertIn('name="quick_link_print_templates"', urls)
        self.assertIn('name="stylist_quick_link_qr_download"', urls)
        self.assertIn('name="stylist_quick_link_print_templates"', urls)
        self.assertIn("salon_manager__user=request.user", views)
        self.assertIn("creator=request.user", views)
        self.assertIn("ERROR_CORRECT_H", qr_service)

    def test_print_service_has_required_templates_and_print_quality(self):
        service = self.read("apps/orders/quick_link_print_templates.py")
        gallery = self.read("templates/dashboards/quick_links/print_templates.html")
        for key in ("mirror_label", "business_card", "table_stand"):
            self.assertIn(f'key="{key}"', service)
        self.assertIn("۳۰۰ DPI", gallery)
        self.assertIn("دانلود PNG چاپی", gallery)
        self.assertIn("دانلود ZIP دو رو", gallery)

    def test_qr_engine_uses_pinned_production_dependency(self):
        requirements = self.read("requirements.txt")
        self.assertIn("qrcode==8.2", requirements)
        self.assertFalse((ROOT / "qrcode" / "main.py").exists())


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
