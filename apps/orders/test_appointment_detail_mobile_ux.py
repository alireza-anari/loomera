from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class AppointmentDetailMobileUXTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = (
            Path(settings.BASE_DIR)
            / "templates"
            / "orders"
            / "appointment_detail.html"
        ).read_text(encoding="utf-8")

    def test_mobile_has_single_overview_and_essential_flow(self):
        self.assertEqual(
            self.template.count('aria-label="نوبت در یک نگاه"'),
            1,
        )
        self.assertEqual(
            self.template.count("data-mobile-appointment-essential-flow"),
            1,
        )

    def test_secondary_information_is_collapsed(self):
        self.assertIn("data-mobile-appointment-more", self.template)
        self.assertIn("جزئیات بیشتر", self.template)
        self.assertIn(
            "پرداخت، قوانین و اطلاعات مجموعه",
            self.template,
        )

    def test_desktop_sidebar_is_hidden_on_mobile(self):
        self.assertIn(
            'aside class="hidden space-y-4 '
            'lg:sticky lg:top-24 lg:block lg:self-start"',
            self.template,
        )

    def test_brand_accents_are_used(self):
        self.assertIn("data-mobile-current-status", self.template)
        self.assertIn("data-mobile-services-heading-icon", self.template)
        self.assertIn("data-mobile-more-heading-icon", self.template)
        self.assertIn("var(--lm-primary-canvas)", self.template)
        self.assertIn("var(--lm-accent-soft)", self.template)

    def test_mobile_manage_cta_is_context_aware(self):
        self.assertIn(
            'data-mobile-manageable="'
            "{% if show_manage_cta %}1{% else %}0{% endif %}"
            '"',
            self.template,
        )
        self.assertIn(
            "{% if show_manage_cta %}\n"
            "<div data-mobile-primary-action",
            self.template,
        )
        self.assertIn("openManageModal()", self.template)

    def test_manage_cta_sits_above_global_bottom_nav(self):
        self.assertIn(
            "bottom: calc("
            "var(--lm-bottom-nav-space, 4.75rem) + 0.4rem"
            ")",
            self.template,
        )
        self.assertIn(
            '[data-appointment-detail-page]'
            '[data-mobile-manageable="1"]',
            self.template,
        )

    def test_calendar_is_secondary_for_upcoming_appointment(self):
        self.assertIn("{% if is_upcoming %}", self.template)
        self.assertIn("افزودن به تقویم", self.template)

    def test_critical_actions_are_preserved(self):
        self.assertIn("confirmCancel()", self.template)
        self.assertIn("openReviewModal", self.template)
        self.assertIn("pay_in_salon_action_url", self.template)
        self.assertIn("openNavigation()", self.template)
