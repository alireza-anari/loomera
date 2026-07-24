from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class CheckoutSubmitGuardAssetTests(SimpleTestCase):
    def _read(self, relative_path):
        return (Path(settings.BASE_DIR) / relative_path).read_text(encoding="utf-8")

    def test_checkout_templates_load_shared_submit_guard_asset(self):
        for template_path in [
            "templates/orders/reservation_preview.html",
            "templates/orders/checkout.html",
        ]:
            with self.subTest(template=template_path):
                content = self._read(template_path)

                self.assertIn("data-checkout-guard-form", content)
                self.assertIn("data-checkout-final-submit", content)
                self.assertIn(
                    "{% static 'js/pages/booking_checkout_submit_guard.js' %}",
                    content,
                )

    def test_checkout_submit_guard_preserves_confirm_action_and_blocks_duplicate_submit(
        self,
    ):
        script = self._read("static/js/pages/booking_checkout_submit_guard.js")

        self.assertIn("confirm_checkout", script)
        self.assertRegex(
            script,
            r"\.dataset\.checkoutSubmitting\s*===\s*['\"]1['\"]",
        )
        self.assertIn("event.preventDefault()", script)
        self.assertIn("data-checkout-action-proxy", script)
        self.assertRegex(
            script,
            r"window\.addEventListener\(\s*['\"]pageshow['\"]",
        )

    def test_coupon_actions_are_not_locked_by_confirm_submit_guard(self):
        script = self._read("static/js/pages/booking_checkout_submit_guard.js")

        self.assertIn("if (action !== CONFIRM_ACTION)", script)
        self.assertIn("removeActionProxy(form)", script)
