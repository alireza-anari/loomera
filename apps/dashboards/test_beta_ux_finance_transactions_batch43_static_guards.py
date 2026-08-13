from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BetaUxFinanceTransactionsBatch43StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_reports_have_three_clear_task_tabs(self):
        source = self.read("templates/dashboards/finance_reports.html")
        self.assertIn('data-lm-task-tabs-anchor="finance-reports"', source)
        for label in ("گردش موجودی", "روش‌های دریافت", "نیازمند بررسی"):
            self.assertIn(f'data-lm-task-label="{label}"', source)
        self.assertEqual(source.count('data-lm-task-panel="finance-reports"'), 3)

    def test_reports_use_one_filter_modal_and_correct_export_language(self):
        source = self.read("templates/dashboards/finance_reports.html")
        self.assertIn("data-finance-filter-open", source)
        self.assertIn("data-finance-filter-modal", source)
        self.assertIn("خروجی Excel", source)
        self.assertNotIn(">CSV<", source)

    def test_reconciliation_tab_only_renders_attention_rows(self):
        source = self.read("templates/dashboards/finance_reports.html")
        view = self.read("apps/dashboards/payment_views.py")
        self.assertIn("reconciliation_attention_rows", source)
        self.assertIn('row for row in reconciliation_rows if row["status"] != "ok"', view)
        self.assertIn("موارد سالم از این لیست حذف شده‌اند", source)

    def test_mobile_payment_breakdown_does_not_require_horizontal_table(self):
        source = self.read("templates/dashboards/finance_reports.html")
        self.assertIn('class="grid gap-2.5 md:hidden"', source)
        self.assertIn('class="hidden overflow-hidden rounded-[22px] border border-loomera-borderSoft md:block"', source)

    def test_reports_show_only_four_top_summary_metrics(self):
        view = self.read("apps/dashboards/payment_views.py")
        block = view.split('"transaction_summary_cards": [', 1)[1].split('                ],\n                "reconciliation_attention_rows"', 1)[0]
        self.assertEqual(block.count('"label":'), 4)
        for label in ("دریافتی ثبت‌شده", "بازپرداخت", "سهم مجموعه", "نیازمند بررسی"):
            self.assertIn(label, block)


if __name__ == "__main__":
    unittest.main()
