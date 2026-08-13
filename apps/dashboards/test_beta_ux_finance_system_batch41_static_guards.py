from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceSystemBatch41CompatibilityGuards(unittest.TestCase):
    """Compatibility guard for the finance IA after Batches 42–48 superseded B41."""

    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_finance_hub_keeps_four_task_groups(self):
        view = self.read("apps/dashboards/payment_views.py")
        template = self.read("templates/dashboards/finance_hub.html")
        self.assertIn("finance_groups = [", view)
        for title in ("پول مجموعه", "سود و هزینه", "مالی متخصصان", "تخفیف"):
            self.assertIn(title, view)
        self.assertIn("finance_summary_cards", view)
        self.assertIn("finance_groups", template)
        self.assertNotIn("finance_sections", view)

    def test_manager_finance_pages_keep_final_task_based_surfaces(self):
        checks = {
            "payout_settings.html": ("اطلاعات پرداخت", "قوانین مالی", "سابقه"),
            "finance_reports.html": ("گزارش تراکنش‌ها", "روش‌های دریافت", "نیازمند بررسی"),
            "finance_cost_center.html": ("مواد مصرفی", "هزینه هر خدمت", "سهم متخصصان"),
            "finance_profit_report.html": ("روش محاسبه", "ریز خدمات", "نیازمند بررسی"),
            "salon_stylist_wallets.html": ("درآمد متخصصان", "قابل دریافت"),
            "manager_stylist_withdrawals.html": ("در انتظار اقدام", "سابقه بررسی"),
        }
        for page, labels in checks.items():
            source = self.read(f"templates/dashboards/{page}")
            with self.subTest(page=page):
                for label in labels:
                    self.assertIn(label, source)

    def test_discount_pages_use_final_manage_create_pattern(self):
        for page in ("finance_coupons.html", "finance_baskets.html", "finance_campaigns.html"):
            source = self.read(f"templates/dashboards/{page}")
            with self.subTest(page=page):
                self.assertIn("مدیریت", source)
                self.assertIn("ساخت", source)
        self.assertIn("پیشنهاد خدمات", self.read("templates/dashboards/finance_baskets.html"))

    def test_finance_routes_are_unique_and_profit_filter_is_modal(self):
        urls = self.read("apps/dashboards/urls.py")
        self.assertEqual(urls.count('name="finance_cost_center"'), 1)
        self.assertEqual(urls.count('name="finance_profit_report"'), 1)
        self.assertEqual(urls.count('name="appointment_material_usage"'), 1)
        profit = self.read("templates/dashboards/finance_profit_report.html")
        self.assertIn("data-profit-filter-open", profit)
        self.assertIn("data-profit-filter-modal", profit)

    def test_stylist_finance_and_withdrawals_have_separate_jobs(self):
        finance = self.read("templates/dashboards/stylist_finance.html")
        withdrawals = self.read("templates/dashboards/stylist_withdrawals.html")
        self.assertIn("درآمد من", finance)
        self.assertIn("دریافت درآمد", withdrawals)
        self.assertNotIn("Bank Account", withdrawals)
        self.assertNotIn(">Note<", withdrawals)


if __name__ == "__main__":
    unittest.main()
