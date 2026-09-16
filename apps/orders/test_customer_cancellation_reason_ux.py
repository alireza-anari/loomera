from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class CustomerCancellationReasonUxTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = (
            Path(settings.BASE_DIR) / "templates/orders/appointment_detail.html"
        ).read_text(encoding="utf-8")

    def test_reason_is_rendered_for_cancelled_appointment(self):
        self.assertEqual(
            self.template.count("data-customer-cancellation-reason"),
            2,
        )
        self.assertIn(
            'appointment.order.status == "cancelled"',
            self.template,
        )
        self.assertIn(
            "{{ appointment.order.cancellation_reason }}",
            self.template,
        )
        self.assertIn("دلیل لغو نوبت", self.template)

    def test_refund_amount_is_rendered_when_available(self):
        self.assertIn(
            "appointment.order.refunded_to_wallet_amount",
            self.template,
        )
        self.assertIn(
            "به کیف پول شما بازگشت داده شده است",
            self.template,
        )
