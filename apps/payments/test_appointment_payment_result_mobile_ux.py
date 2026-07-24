from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class AppointmentPaymentResultMobileUXTests(SimpleTestCase):
    def setUp(self):
        self.template = (
            Path(settings.BASE_DIR)
            / "templates"
            / "payments"
            / "appointment_result.html"
        ).read_text(encoding="utf-8")

    def test_result_page_has_mobile_root_and_safe_area(self):
        self.assertIn("data-payment-result-mobile", self.template)
        self.assertIn(
            "pb-[calc(7rem+env(safe-area-inset-bottom))]",
            self.template,
        )

    def test_result_hero_has_mobile_layout_hooks(self):
        self.assertIn("data-payment-result-hero", self.template)
        self.assertIn("items-stretch", self.template)
        self.assertIn("whitespace-normal", self.template)
        self.assertIn("sm:w-auto", self.template)

    def test_result_details_stack_safely_on_mobile(self):
        self.assertIn("data-payment-result-details", self.template)
        self.assertIn("data-payment-result-details-list", self.template)
        self.assertIn("[&>div]:flex-col", self.template)
        self.assertIn("sm:[&>div]:flex-row", self.template)
        self.assertIn("[&_dd]:break-words", self.template)

    def test_result_actions_have_mobile_hook(self):
        self.assertIn("data-payment-result-actions", self.template)
        self.assertIn("scroll-mt-24", self.template)

    def test_all_payment_result_states_are_preserved(self):
        self.assertIn("is_success", self.template)
        self.assertIn("is_payment_pending_review", self.template)
        self.assertIn("is_expired_checkout", self.template)
        self.assertIn("is_cancelled", self.template)
        self.assertIn("pay_in_salon_online_failed", self.template)
