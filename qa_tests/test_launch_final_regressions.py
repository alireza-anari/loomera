from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LaunchFinalRegressionGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_mobile_profile_points_to_customer_profile_not_home(self):
        template = self.read("templates/partials/shell/customer_mobile_nav.html")
        profile_block = template.split("{# حساب من #}", 1)[1].split("{# مجله #}", 1)[0]
        self.assertIn("dashboards:manager_profile", profile_block)
        self.assertIn("dashboards:stylist_profile", profile_block)
        self.assertIn("accounts:customerProfile", profile_block)
        self.assertIn("accounts:login", profile_block)
        self.assertNotIn("salons:home", profile_block)
        self.assertNotIn("accounts:customer_panel", profile_block)

    def test_lumi_fab_is_smaller_without_changing_panel_avatar(self):
        css = self.read("static/css/components/help_assistant.css")
        final = css.split("/* Closed state: the avatar itself IS the floating control. No white card/frame. */", 1)[1]
        fab = final.split(".lm-help-assistant__fab {", 1)[1].split("}", 1)[0]
        icon = final.split(".lm-help-assistant__fab-icon {", 1)[1].split("}", 1)[0]
        self.assertIn("width: 62px", fab)
        self.assertIn("height: 62px", fab)
        self.assertIn("width: 62px", icon)
        self.assertIn("height: 62px", icon)
        self.assertIn(".lm-help-assistant__avatar {\n  width: 54px", final)

    def test_post_signup_prompt_is_role_aware_and_uses_existing_messaging_settings(self):
        wrapper = self.read("templates/partials/messaging_welcome_prompt.html")
        body = self.read("templates/partials/messaging_welcome_prompt_body.html")
        public_base = self.read("templates/base.html")
        dashboard_base = self.read("templates/dashboard_template.html")
        accounts_views = self.read("apps/accounts/views.py")

        self.assertIn("show_messaging_connect_prompt", accounts_views)
        self.assertIn("manager", wrapper)
        self.assertIn("stylist", wrapper)
        self.assertIn("customer", wrapper)
        self.assertIn("messaging:preferences", body)
        self.assertIn("بله", body)
        self.assertIn("تلگرام", body)
        self.assertIn("از بخش تنظیمات", body)
        self.assertIn("accounts:dismiss_messaging_welcome", body)
        self.assertIn('partials/messaging_welcome_prompt.html', public_base)
        self.assertIn('partials/messaging_welcome_prompt.html', dashboard_base)

    def test_future_date_slot_load_is_not_background_only(self):
        script = self.read("static/js/select_datetime.js")
        load_times = script.split("async function loadTimesForDate", 1)[1].split("function renderTimeSlots", 1)[0]
        self.assertIn("getJalaliMonthForIsoDate(dateStr)", load_times)
        self.assertIn("await loadAvailabilityForMonth(targetMonth.year, targetMonth.month)", load_times)
        self.assertLess(load_times.index("loadAvailabilityForMonth"), load_times.index("getAvailabilityForDate"))


if __name__ == "__main__":
    unittest.main()
