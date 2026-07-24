from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class CheckoutMobileUXAssetsTests(SimpleTestCase):
    def setUp(self):
        base_dir = Path(settings.BASE_DIR)

        self.template = (
            base_dir / "templates" / "orders" / "reservation_preview.html"
        ).read_text(encoding="utf-8")

        self.script = (
            base_dir / "static" / "js" / "pages" / "booking_checkout_submit_guard.js"
        ).read_text(encoding="utf-8")

    def test_checkout_template_has_payment_selection_hooks(self):
        self.assertIn("data-checkout-payment-methods", self.template)
        self.assertIn("data-payment-option", self.template)
        self.assertIn('data-selected="0"', self.template)
        self.assertIn("data-[selected=1]:border-loomera-primary", self.template)

    def test_checkout_template_has_mobile_keyboard_hooks(self):
        self.assertIn("data-checkout-coupon-input", self.template)
        self.assertIn("data-checkout-mobile-bar", self.template)
        self.assertIn('data-keyboard-hidden="false"', self.template)
        self.assertIn(
            "data-[keyboard-hidden=true]:translate-y-full",
            self.template,
        )

    def test_checkout_cta_changes_by_payment_method(self):
        self.assertIn("پرداخت و ثبت رزرو", self.script)
        self.assertIn("پرداخت از کیف پول", self.script)
        self.assertIn("ثبت رزرو", self.script)
        self.assertIn("در حال انتقال به درگاه", self.script)

    def test_checkout_guard_still_blocks_duplicate_confirm(self):
        self.assertIn(
            'form.dataset.checkoutSubmitting === "1"',
            self.script,
        )
        self.assertIn("event.preventDefault()", self.script)
        self.assertIn("ensureConfirmActionProxy(form)", self.script)

    def test_pageshow_restores_dynamic_checkout_state(self):
        self.assertIn(
            'window.addEventListener("pageshow"',
            self.script,
        )
        self.assertIn(
            "updatePaymentPresentation(form)",
            self.script,
        )
        self.assertIn(
            "setMobileBarKeyboardHidden(form, false)",
            self.script,
        )
