from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ManagerProfileBatch51StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_manager_form_owns_only_personal_identity_fields(self):
        source = self.read("apps/accounts/forms.py")
        block = source.split("class SalonManagerUpdateProfileForm", 1)[1].split(
            "class CustomerAddressForm", 1
        )[0]
        self.assertIn('fields = ["name", "family", "email"]', block)
        self.assertNotIn('fields = ["name", "family", "email", "mobile_number"]', block)
        self.assertNotIn('address = forms.CharField', block)
        self.assertNotIn('salon_number = forms.CharField', block)
        self.assertNotIn('manager_instance.address =', block)
        self.assertNotIn('manager_instance.salon_number =', block)

    def test_mobile_is_display_only_and_salon_data_is_not_repeated(self):
        source = self.read("templates/dashboards/manager_profile.html")
        self.assertIn("data-manager-account-mobile", source)
        self.assertIn("{{ request.user.mobile_number }}", source)
        self.assertNotIn("form.mobile_number", source)
        self.assertNotIn("form.salon_number", source)
        self.assertNotIn("form.address", source)
        self.assertNotIn("شماره تماس مجموعه", source)

    def test_profile_does_not_duplicate_settings_or_messaging_destinations(self):
        source = self.read("templates/dashboards/manager_profile.html")
        self.assertNotIn("bale_connect_card", source)
        self.assertNotIn("messaging_connect", source)
        self.assertNotIn("salon_profile_url", source)
        self.assertIn("workspace_settings_url", source)

    def test_profile_keeps_direct_edit_contract(self):
        source = self.read("templates/dashboards/manager_profile.html")
        self.assertIn("data-direct-edit-form", source)
        self.assertIn("data-direct-edit-savebar", source)
        self.assertIn("data-direct-edit-status", source)
        self.assertNotIn("data-dashboard-workspace-tabs", source)

    def test_old_readiness_ui_and_javascript_are_removed(self):
        template = self.read("templates/dashboards/manager_profile.html")
        script = self.read("static/js/pages/dashboard_manager_profile.js")
        for marker in (
            "data-manager-readiness-percent",
            "data-manager-readiness-bar",
            "data-manager-status-name",
            "data-manager-status-salon-phone",
            "data-manager-review-title",
        ):
            self.assertNotIn(marker, template)
            self.assertNotIn(marker, script)
        self.assertIn("data-manager-avatar-preview", template)
        self.assertIn("data-manager-preview-name", template)

    def test_manager_profile_copy_keeps_salon_profile_as_separate_source(self):
        source = self.read("templates/dashboards/manager_profile.html")
        self.assertIn("اطلاعات عمومی مجموعه", source)
        self.assertIn("اطلاعات حساب مدیر", source)
        self.assertIn("اطلاعات مجموعه از این صفحه تغییر نمی‌کند", source)


if __name__ == "__main__":
    unittest.main()
