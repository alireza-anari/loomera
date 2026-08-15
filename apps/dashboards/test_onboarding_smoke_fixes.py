from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]


class OnboardingSmokeFixStaticTests(TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_step_one_uses_separate_mobile_and_landline_fields(self):
        forms = self.read("apps/salons/forms.py")
        template = self.read("templates/dashboards/salon_profile_creator_step1.html")
        self.assertIn('fields = ["salon_name", "mobile_phone", "landline_phone"]', forms)
        self.assertIn("شماره ثابت را همراه با کد شهر وارد کنید", forms)
        self.assertIn("form.mobile_phone", template)
        self.assertIn("form.landline_phone", template)
        self.assertNotIn("form.phone_number", template)

    def test_location_has_separate_required_plaque_and_unit(self):
        forms = self.read("apps/salons/forms.py")
        template = self.read("templates/dashboards/salon_profile_creator_step2.html")
        js = self.read("static/js/pages/salon_location_step.js")
        self.assertIn('self.fields["address_plaque"].required = True', forms)
        self.assertIn('self.fields["address_unit"].required = True', forms)
        self.assertIn("form.address_plaque", template)
        self.assertIn("form.address_unit", template)
        self.assertIn('document.getElementById("id_address_plaque")', js)
        self.assertIn('document.getElementById("id_address_unit")', js)

    def test_reverse_geocode_does_not_fold_plaque_into_address(self):
        source = self.read("apps/search/views.py")
        address_block = source.split("def _extract_reverse_geocode_address", 1)[1].split(
            "def _extract_reverse_geocode_plaque", 1
        )[0]
        self.assertNotIn('"plaque",', address_block)
        self.assertNotIn('"house_number",', address_block)
        self.assertIn("def _extract_reverse_geocode_plaque", source)
        self.assertIn('"plaque": plaque', source)

    def test_onboarding_copy_cleanup(self):
        step2 = self.read("templates/dashboards/salon_profile_creator_step2.html")
        step3 = self.read("templates/dashboards/salon_profile_creator_step3.html")
        step6 = self.read("templates/dashboards/salon_profile_creator_step6.html")
        step7 = self.read("templates/dashboards/salon_profile_creator_step7.html")
        self.assertIn("موقعیت مکانی روی نقشه", step2)
        self.assertIn("مکانی انتخاب نشده", step2)
        self.assertNotIn(" کشویی</span>", step3)
        self.assertNotIn("ساعت کلی فعالیت مجموعه را ثبت کن", step3)
        self.assertNotIn("تصاویر واقعی فضای مجموعه را مدیریت کن", step6)
        self.assertNotIn("فقط امکانات و ویژگی‌های واقعی را انتخاب کن", step7)

    def test_description_has_no_minimum_suggestions_or_preview(self):
        forms = self.read("apps/salons/forms.py")
        template = self.read("templates/dashboards/salon_profile_creator_step8.html")
        js = self.read("static/js/pages/salon_description_step.js")
        self.assertNotIn("min_length=200", forms)
        self.assertNotIn("حداقل ۲۰۰", template)
        self.assertNotIn("description-section-suggestions", template)
        self.assertNotIn("description-section-preview", template)
        self.assertNotIn("minLength", js)
        self.assertNotIn("descriptionPreviewText", js)
        self.assertNotIn("data-description-chip", js)

    def test_finishing_onboarding_publishes_salon_and_opens_profile_setup(self):
        views = self.read("apps/dashboards/views.py")
        guard = views.split("def _get_required_onboarding_view_name", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("_is_step10_complete", guard)
        self.assertIn("salon.is_active = True", views)
        self.assertIn('?setup=booking', views)
        self.assertIn('"یک خدمت، عضو تیم و برنامه کاری اضافه کن."', views)
