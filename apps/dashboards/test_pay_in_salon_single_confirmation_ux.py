from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class PayInSalonSingleConfirmationUxTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = Path(settings.BASE_DIR)
        cls.finance = (base / "apps/payments/finance.py").read_text(encoding="utf-8")
        cls.orders = (base / "apps/orders/views.py").read_text(encoding="utf-8")
        cls.dash = (base / "apps/dashboards/views.py").read_text(encoding="utf-8")
        cls.customer = (base / "templates/orders/appointment_detail.html").read_text(encoding="utf-8")
        cls.stylist = (base / "templates/dashboards/stylist_appointment_detail.html").read_text(encoding="utf-8")

    def test_customer_cash_confirmation_is_removed(self):
        self.assertNotIn('value="cash"', self.customer)
        self.assertNotIn("تأیید پرداخت نقدی", self.customer)
        self.assertIn("نیازی به تأیید شما نیست", self.customer)

    def test_finance_finalizes_from_collection_side_only(self):
        block = self.finance.split("def confirm_pay_in_salon_cash_payment", 1)[1].split("def _allocate_amount_to_details", 1)[0]
        self.assertIn('if role != "stylist"', block)
        self.assertIn("payment.mark_success(", block)
        self.assertIn("sync_settlement_for_order(", block)
        self.assertIn("mark_review_requested(", block)
        self.assertNotIn("customer_confirmed and stylist_confirmed", block)

    def test_stylist_fast_flow_contains_receive_money_action(self):
        allowed = self.dash.split("def _get_allowed_stylist_lifecycle_actions", 1)[1].split("def _apply_stylist_lifecycle_action", 1)[0]
        self.assertIn('"key": "confirm_cash_payment"', allowed)
        self.assertIn('"label": "دریافت وجه شد"', allowed)
        serializer = self.dash.split("def _serialize_stylist_appointment_card", 1)[1].split("def _serialize_stylist_schedule_row", 1)[0]
        self.assertIn('"confirm_cash_payment"', serializer)
        self.assertNotIn("cash_payment_state", self.stylist)

    def test_customer_cash_post_does_not_call_finance(self):
        settlement = self.orders.split("class PayInSalonSettlementView", 1)[1]
        cash = settlement.split('if action == "cash":', 1)[1].split("with transaction.atomic():", 1)[0]
        self.assertIn("نیازی به تأیید شما نیست", cash)
        self.assertNotIn("confirm_pay_in_salon_cash_payment(", cash)
