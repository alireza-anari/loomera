from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceMoneyBatch42StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_money_page_has_one_clear_four_task_structure(self):
        source = self.read("templates/dashboards/payout_settings.html")
        self.assertIn('data-lm-task-tabs-anchor="payout"', source)
        self.assertEqual(source.count('data-lm-task-panel="payout"'), 4)
        for label in ("برداشت", "اطلاعات پرداخت", "قوانین مالی", "سابقه"):
            self.assertIn(f'data-lm-task-label="{label}"', source)
        self.assertNotIn("حساب و قوانین", source)
        self.assertNotIn("سابقه پول", source)

    def test_summary_removes_redundant_total_and_surfaces_actionable_state(self):
        source = self.read("templates/dashboards/payout_settings.html")
        self.assertNotIn("جمع موجودی", source)
        self.assertIn("درخواست برداشت در انتظار", source)
        self.assertIn("حساب مقصد برداشت", source)
        self.assertIn("pending_withdrawal_count", source)

    def test_withdrawal_uses_saved_payment_destination_instead_of_reasking(self):
        template = self.read("templates/dashboards/payout_settings.html")
        view = self.read("apps/dashboards/payment_views.py")
        self.assertNotIn("{{ withdraw_form.iban }}", template)
        self.assertNotIn("{{ withdraw_form.account_holder_name }}", template)
        self.assertIn('withdraw_data["iban"] = salon.payout_iban or ""', view)
        self.assertIn('withdraw_data["account_holder_name"] = salon.payout_account_holder_name or ""', view)
        self.assertIn("برای تغییر مقصد، از تب «اطلاعات پرداخت» استفاده کن", template)

    def test_payment_information_and_financial_rules_are_not_mixed(self):
        source = self.read("templates/dashboards/payout_settings.html")
        payment = source.split('id="finance-payment"', 1)[1].split('id="finance-rules"', 1)[0]
        rules = source.split('id="finance-rules"', 1)[1].split('id="finance-history"', 1)[0]
        self.assertIn("payout_iban", payment)
        self.assertIn("payout_contact_mobile", payment)
        self.assertNotIn("cancellation_window_hours", payment)
        self.assertIn("cancellation_window_hours", rules)
        self.assertIn("payout_delay_days", rules)
        self.assertNotIn("payout_iban", rules)

    def test_page_does_not_repeat_finance_back_navigation(self):
        source = self.read("templates/dashboards/payout_settings.html")
        self.assertIn("workspace_nav.html", source)
        self.assertNotIn("بازگشت به مالی", source)
        self.assertIn("گزارش کامل", source)


if __name__ == "__main__":
    unittest.main()
