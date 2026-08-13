from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceTeamIncomeBatch46StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_income_and_withdrawals_are_separate_destinations(self):
        income = self.read("templates/dashboards/salon_stylist_wallets.html")
        nav = self.read("templates/dashboards/partials/finance/team_nav.html")
        withdrawals_view = self.read("apps/dashboards/finance_withdrawal_views.py")
        self.assertIn("درآمد متخصصان", nav)
        self.assertIn("برداشت متخصصان", nav)
        self.assertNotIn("stylist-wallets-section-withdrawals", income)
        self.assertNotIn("stylist-wallets-section-documents", income)
        manager_block = withdrawals_view.split("class ManagerStylistWithdrawalRequestsView", 1)[1]
        get_block = manager_block.split("    def get(self, request):", 1)[1].split("    def post(self, request):", 1)[0]
        self.assertIn("return render(request, self.template_name, context)", get_block)
        self.assertNotIn('return redirect("dashboards:finance_stylist_wallets")', get_block)

    def test_income_summary_uses_four_decision_metrics(self):
        source = self.read("templates/dashboards/salon_stylist_wallets.html")
        for label in (
            "درآمد قطعی متخصصان",
            "قابل دریافت",
            "در انتظار آزادشدن",
            "درخواست در انتظار پرداخت",
        ):
            self.assertIn(label, source)
        self.assertNotIn("فروش خام", source)
        self.assertNotIn("سود خالص مجموعه", source)

    def test_income_history_counts_only_finalized_financial_snapshots(self):
        source = self.read("apps/dashboards/finance_cost_views.py")
        block = source.split("class SalonStylistWalletsView", 1)[1].split(
            "class ManagerFinalizeAppointmentFinanceView", 1
        )[0]
        self.assertIn("OrderDetailFinancialSnapshot.Status.FINALIZED", block)
        self.assertIn('status=OrderDetailFinancialSnapshot.Status.FINALIZED', block)
        self.assertNotIn('summary_cards": [', block)

    def test_finance_keeps_inactive_team_member_history_visible(self):
        source = self.read("apps/dashboards/finance_cost_views.py")
        block = source.split("class SalonStylistWalletsView", 1)[1].split(
            "class ManagerFinalizeAppointmentFinanceView", 1
        )[0]
        self.assertIn('current_stylist_ids = set(salon.stylists.values_list("pk", flat=True))', block)
        self.assertIn("financial_stylist_ids", block)
        self.assertNotIn("salon.stylists.filter(is_active=True)", block)
        template = self.read("templates/dashboards/salon_stylist_wallets.html")
        self.assertIn("عضو سابق", template)

    def test_income_has_search_and_actionable_balance_filters(self):
        source = self.read("templates/dashboards/salon_stylist_wallets.html")
        self.assertIn("data-team-wallet-search", source)
        for key in ("all", "available", "pending", "withdrawal"):
            self.assertIn(f'data-team-wallet-filter="{key}"', source)

    def test_hub_points_withdrawal_action_to_real_withdrawal_page(self):
        source = self.read("apps/dashboards/payment_views.py")
        team_block = source.split('"key": "team"', 1)[1].split('"key": "discounts"', 1)[0]
        self.assertIn('"title": "مالی متخصصان"', team_block)
        self.assertIn('reverse("dashboards:finance_stylist_withdrawals")', team_block)

    def test_shared_workspace_uses_finance_specialists_wording(self):
        source = self.read("templates/dashboards/partials/finance/workspace_nav.html")
        self.assertIn("مالی متخصصان", source)
        self.assertNotIn("پرداخت به تیم", source)

    def test_manager_review_stays_on_withdrawal_page(self):
        source = self.read("apps/dashboards/finance_withdrawal_views.py")
        block = source.split("class ManagerStylistWithdrawalRequestsView", 1)[1]
        self.assertIn('return redirect("dashboards:finance_stylist_withdrawals")', block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
