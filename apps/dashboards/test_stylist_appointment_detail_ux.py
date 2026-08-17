from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class StylistAppointmentDetailUXTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = (
            Path(settings.BASE_DIR)
            / "templates"
            / "dashboards"
            / "stylist_appointment_detail.html"
        ).read_text(encoding="utf-8")

    def test_compact_header_replaces_generic_page_hero(self):
        self.assertIn(
            "data-stylist-appointment-compact-header",
            self.template,
        )
        self.assertNotIn(
            'dashboards/components/page_hero.html',
            self.template,
        )

    def test_primary_actions_are_before_secondary_content(self):
        actions = self.template.index(
            'id="stylist-appointment-section-actions"'
        )
        summary = self.template.index(
            'id="stylist-appointment-section-summary"'
        )
        tabs = self.template.index(
            'data-lm-task-tabs-anchor="stylist-appointment-detail"'
        )

        self.assertLess(actions, summary)
        self.assertLess(summary, tabs)

    def test_lifecycle_actions_are_preserved(self):
        self.assertIn("stylist_lifecycle_actions", self.template)
        self.assertIn('name="action"', self.template)
        self.assertIn('value="{{ item.key }}"', self.template)
        self.assertIn(
            'value="confirm_cash_payment"',
            self.template,
        )

    def test_confirm_and_reject_actions_have_clear_hierarchy(self):
        self.assertIn(
            'class="flex w-full gap-2 lg:w-auto lg:min-w-[360px]"',
            self.template,
        )
        self.assertIn(
            "item.key == 'reject'",
            self.template,
        )
        self.assertIn(
            "border-rose-200 bg-rose-50 text-rose-700",
            self.template,
        )

    def test_redundant_helper_copy_is_removed(self):
        self.assertNotIn(
            "تأیید، رد، رسیدن مشتری، شروع کار، پایان کار و تأیید پرداخت نقدی از همین بخش انجام می‌شود.",
            self.template,
        )
        self.assertNotIn(
            "این بخش بعد از اقدام‌های عملیاتی آمده تا دکمه‌های اصلی نوبت همیشه بالاتر و سریع‌تر در دسترس باشند.",
            self.template,
        )
        self.assertNotIn(
            "رویدادهای واقعی ثبت‌شده برای همین آیتم نوبت.",
            self.template,
        )
        self.assertNotIn(
            ">اقدام نوبت</h2>",
            self.template,
        )

    def test_essential_context_remains_visible(self):
        self.assertIn("appointment.customer_name", self.template)
        self.assertIn("appointment.service_name", self.template)
        self.assertIn("appointment.date_label", self.template)
        self.assertIn("appointment.time_label", self.template)
        self.assertIn("appointment.price_label", self.template)
        self.assertIn("appointment.payment_method", self.template)

    def test_material_entry_uses_progressive_disclosure(self):
        self.assertIn(
            "material_usage_form.errors",
            self.template,
        )
        self.assertIn(
            "ثبت دستی یا افزودن از قالب",
            self.template,
        )
        self.assertIn(
            "group-open:rotate-180",
            self.template,
        )

    def test_mobile_materials_heading_is_not_duplicated(self):
        section = self.template.index(
            'id="stylist-appointment-section-materials"'
        )
        header = self.template.index("<header", section)
        header_end = self.template.index(">", header)
        header_tag = self.template[header:header_end]

        self.assertIn("hidden", header_tag)
        self.assertIn("lg:flex", header_tag)
