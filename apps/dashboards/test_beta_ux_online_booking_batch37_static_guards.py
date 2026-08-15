from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxOnlineBookingBatch37StaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_public_salon_mode_is_supported_end_to_end(self):
        template = self.read("templates/dashboards/quick_links/_create_form.html")
        dashboard_views = self.read("apps/dashboards/views.py")
        order_views = self.read("apps/orders/views.py")
        quick_links = self.read("apps/orders/quick_links.py")
        models = self.read("apps/orders/models.py")
        self.assertIn('"value": "salon", "label": "صفحه اصلی سالن"', dashboard_views)
        self.assertIn('SALON = "salon"', models)
        self.assertIn('mode == "salon"', order_views)
        self.assertIn('BookingQuickLink.Mode.SALON', quick_links)
        self.assertIn("data-quick-link-mode", template)

    def test_service_drives_stylists_and_real_availability(self):
        views = self.read("apps/dashboards/views.py")
        template = self.read("templates/dashboards/quick_links/_create_form.html")
        urls = self.read("apps/dashboards/urls.py")
        self.assertIn("class OnlineBookingQuickLinkOptionsView", views)
        self.assertIn("_quick_link_stylists_for_service", views)
        self.assertIn("get_available_slots_for_service", views)
        self.assertIn("online_booking_quick_link_options", urls)
        self.assertIn('data-quick-link-service', template)
        self.assertIn('data-quick-link-stylist', template)
        self.assertIn('data-quick-link-date', template)
        self.assertIn('disabled', template)
        self.assertIn('data-quick-link-time', template)
        self.assertIn('fetchOptions', template)
        self.assertNotIn("زمان‌ها بر اساس ساعات سالن پیشنهاد می‌شوند", template)

    def test_production_campaign_schema_is_preserved_without_compat_migrations(self):
        model = self.read("apps/orders/models.py")
        quick_links = self.read("apps/orders/quick_links.py")
        self.assertIn("campaign_name = models.CharField", model)
        self.assertIn('campaign_name=""', quick_links)
        self.assertIn("internal_note = models.", model)
        # Production already owns these columns. The temporary UX compatibility
        # migrations must never be reintroduced into the tested migration graph.
        for name in (
            "0003_bookingquicklink_campaign_compat_and_salon_mode.py",
            "0005_merge_bookingquicklink_campaign_and_salon_mode.py",
            "0006_bookingquicklink_legacy_column_compat.py",
            "0007_bookingquicklink_force_legacy_nullable.py",
        ):
            self.assertFalse((ROOT / "apps" / "orders" / "migrations" / name).exists())

    def test_old_slot_technical_copy_is_removed(self):
        views = self.read("apps/dashboards/views.py")
        self.assertNotIn("مسیر رزرو واقعی Slot دارد", views)
        self.assertIn("لینک‌های رزرو، QR و آمار هر مسیر", views)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
