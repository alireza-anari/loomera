from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BetaUxFinanceSimplificationBatch41StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_manager_finance_has_one_shared_mental_model(self):
        nav = self.read("templates/dashboards/partials/finance/workspace_nav.html")
        for label in ["مرور مالی", "پول مجموعه", "سود و هزینه", "مالی متخصصان", "تخفیف‌ها"]:
            self.assertIn(label, nav)
        self.assertIn("sticky", nav)

    def test_finance_hub_does_not_repeat_workspace_nav(self):
        source = self.read("templates/dashboards/finance_hub.html")
        self.assertNotIn('workspace_nav.html" with active="overview"', source)
        self.assertIn("finance_groups", source)
        self.assertIn("چهار کار اصلی", source)

    def test_money_page_has_four_plain_language_tasks(self):
        source = self.read("templates/dashboards/payout_settings.html")
        for label in ["برداشت", "اطلاعات پرداخت", "قوانین مالی", "سابقه"]:
            self.assertIn(f'data-lm-task-label="{label}"', source)
        self.assertNotIn("تنظیمات تسویه", source)

    def test_income_cost_page_uses_plain_language_tabs(self):
        source = self.read("templates/dashboards/finance_cost_center.html")
        for label in ["مواد مصرفی", "هزینه هر خدمت", "سهم متخصصان"]:
            self.assertIn(f'data-lm-task-label="{label}"', source)
        self.assertNotIn("cost-section-forms", source)
        self.assertNotIn("cost-section-actions", source)
        self.assertIn("دیدن سود خالص", source)

    def test_team_finance_separates_income_from_withdrawal_workflow(self):
        income = self.read("templates/dashboards/salon_stylist_wallets.html")
        local_nav = self.read("templates/dashboards/partials/finance/team_nav.html")
        withdrawal_view = self.read("apps/dashboards/finance_withdrawal_views.py")
        self.assertIn("درآمد متخصصان", local_nav)
        self.assertIn("برداشت متخصصان", local_nav)
        self.assertNotIn("stylist-wallets-section-withdrawals", income)
        self.assertNotIn("stylist-wallets-section-documents", income)
        manager_block = withdrawal_view.split("class ManagerStylistWithdrawalRequestsView", 1)[1]
        self.assertIn('return render(request, self.template_name, context)', manager_block)

    def test_legacy_material_finance_page_redirects_to_canonical_page(self):
        view = self.read("apps/dashboards/finance_settings_views.py")
        get_block = view.split("    def get(self, request):", 1)[1].split("    def post(self, request):", 1)[0]
        self.assertIn('redirect("dashboards:finance_cost_center")', get_block)
        self.assertNotIn("render(request, self.template_name", get_block)

    def test_discount_pages_have_one_local_switcher(self):
        partial = self.read("templates/dashboards/partials/finance/discount_nav.html")
        for label in ["کد تخفیف", "پیشنهاد خدمات", "کمپین تخفیف"]:
            self.assertIn(label, partial)
        expected = {
            "finance_coupons.html": "codes",
            "finance_baskets.html": "packages",
            "finance_campaigns.html": "campaigns",
        }
        for name, active in expected.items():
            source = self.read(f"templates/dashboards/{name}")
            self.assertIn(f'active_discount="{active}"', source)

    def test_stylist_finance_is_reduced_to_four_metrics_and_two_tasks(self):
        view = self.read("apps/dashboards/views.py")
        marker = '"summary_cards": ['
        stylist_block = view.split('class StylistFinanceView', 1)[1]
        cards = stylist_block.split(marker, 1)[1].split("                ],", 1)[0]
        self.assertEqual(cards.count('"label":'), 4)
        template = self.read("templates/dashboards/stylist_finance.html")
        for label in ["درآمد خدمات", "تغییرات درآمد"]:
            self.assertIn(f'data-lm-task-label="{label}"', template)
        self.assertNotIn('data-lm-task-label="تراکنش‌ها"', template)

    def test_sidebar_finance_language_is_simple(self):
        layout = self.read("apps/dashboards/layout.py")
        self.assertIn('"label": "مالی"', layout)
        self.assertIn('"caption": "موجودی، درآمد، پرداخت تیم و تخفیف‌ها"', layout)
        self.assertIn('"label": "درآمد من"', layout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
