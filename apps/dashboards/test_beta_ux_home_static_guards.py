from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxHomeStaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_manager_home_mode_comes_from_canonical_readiness(self):
        source = self.read("apps/dashboards/home_components.py")
        self.assertIn('readiness = build_salon_readiness_checklist(salon)', source)
        self.assertIn('mode = "operational" if readiness["is_ready"] else "setup"', source)
        self.assertIn('"next_action": next_action', source)
        self.assertNotIn('"mode": "setup"', source)

    def test_manager_home_prioritizes_daily_operational_facts(self):
        source = self.read("apps/dashboards/home_components.py")
        self.assertIn('pending_appointments = active_qs.filter(', source)
        self.assertIn('StaffScheduleRequest.objects.filter(', source)
        self.assertIn('StaffLeaveRequest.objects.filter(', source)
        self.assertIn('"attention_count_label"', source)
        self.assertIn('"next_appointment"', source)
        self.assertIn('"add_booking_url"', source)

    def test_manager_home_template_has_setup_and_operational_modes(self):
        template = self.read("templates/dashboards/partials/overview_intro.html")
        self.assertIn('data-dashboard-setup-mode', template)
        self.assertIn('data-dashboard-operational-mode', template)
        self.assertIn('data-dashboard-primary-task', template)
        self.assertIn('راه‌اندازی سالن', template)
        self.assertIn('قدم بعدی', template)
        self.assertIn('نوبت بعدی', template)
        self.assertIn('نیازمند اقدام', template)

    def test_home_no_longer_surfaces_analytics_and_feature_catalog_as_primary_content(self):
        template = self.read("templates/dashboards/partials/overview_intro.html")
        forbidden = [
            "شاخص‌های اصلی مجموعه",
            "کارهای اصلی مدیریت مجموعه",
            "فروش ۷ روز اخیر",
            "خدمات محبوب",
            "اعضای برتر تیم",
            "sales_activity_widget.html",
            "ranking_widget.html",
            "salon_readiness_checklist.html",
        ]
        for fragment in forbidden:
            self.assertNotIn(fragment, template)

    def test_today_appointments_are_one_tap_to_detail(self):
        components = self.read("apps/dashboards/home_components.py")
        template = self.read("templates/dashboards/partials/today_widget.html")
        self.assertIn('"detail_url": detail_url', components)
        self.assertIn('"dashboards:appointment_detail"', components)
        self.assertIn('href="{{ item.detail_url }}"', template)
        self.assertIn('مدیریت نوبت', template)
