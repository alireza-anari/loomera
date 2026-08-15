from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceTeamWithdrawalsBatch47StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_withdrawal_page_separates_open_work_from_history(self):
        source = self.read("templates/dashboards/manager_stylist_withdrawals.html")
        self.assertIn('data-lm-task-label="در انتظار اقدام"', source)
        self.assertIn('data-lm-task-label="سابقه بررسی"', source)
        self.assertNotIn("<table", source)
        self.assertNotIn("لیست درخواست‌ها", source)

    def test_pending_requests_use_compact_detail_cards_with_destination_first(self):
        source = self.read("templates/dashboards/manager_stylist_withdrawals.html")
        pending = source.split('id="team-withdrawals-pending"', 1)[1].split(
            'id="team-withdrawals-history"', 1
        )[0]
        self.assertIn("lm-compact-record", pending)
        self.assertIn("حساب مقصد", pending)
        self.assertIn("صاحب حساب", pending)
        self.assertIn("شماره شبا", pending)
        self.assertIn("ثبت پرداخت", pending)
        self.assertIn("رد و بازگشت مبلغ", pending)
        self.assertNotIn('value="cancel"', pending)

    def test_payment_confirmation_and_optional_receipt_are_explicit(self):
        source = self.read("templates/dashboards/manager_stylist_withdrawals.html")
        self.assertIn("data-withdrawal-payment-confirmation", source)
        self.assertIn("پرداخت این درخواست انجام شده است", source)
        self.assertIn("رسید واریز", source)
        self.assertIn("اختیاری", source)
        self.assertIn('accept="image/jpeg,image/png,.pdf,application/pdf"', source)

    def test_history_is_read_only_and_filterable(self):
        source = self.read("templates/dashboards/manager_stylist_withdrawals.html")
        history = source.split('id="team-withdrawals-history"', 1)[1]
        for key in ("all", "approved", "returned"):
            self.assertIn(f'data-withdrawal-history-filter="{key}"', history)
        self.assertIn("مشاهده رسید پرداخت", history)
        self.assertIn("یادداشت بررسی", history)
        self.assertNotIn('name="action"', history)

    def test_view_supplies_action_and_history_collections(self):
        source = self.read("apps/dashboards/finance_withdrawal_views.py")
        block = source.split("class ManagerStylistWithdrawalRequestsView", 1)[1]
        get_block = block.split("    def get(self, request):", 1)[1].split(
            "    def post(self, request):", 1
        )[0]
        self.assertIn('"pending_withdrawals": pending[:100]', get_block)
        self.assertIn('"reviewed_withdrawals": reviewed[:100]', get_block)
        self.assertIn("status__in=[", get_block)
        self.assertIn("Status.REJECTED", get_block)
        self.assertIn("Status.CANCELLED", get_block)

    def test_summary_distinguishes_pending_paid_and_restored_money(self):
        source = self.read("templates/dashboards/manager_stylist_withdrawals.html")
        for label in (
            "در انتظار اقدام",
            "مبلغ در انتظار پرداخت",
            "پرداخت‌شده",
            "برگشت به موجودی",
        ):
            self.assertIn(label, source)
        view = self.read("apps/dashboards/finance_withdrawal_views.py")
        self.assertIn('"returned_amount": _money(returned_amount)', view)

    def test_manager_review_still_posts_to_existing_workflow_and_stays_here(self):
        source = self.read("apps/dashboards/finance_withdrawal_views.py")
        block = source.split("class ManagerStylistWithdrawalRequestsView", 1)[1]
        self.assertIn('if action == "approve":', block)
        self.assertIn('elif action == "reject":', block)
        self.assertIn('return redirect("dashboards:finance_stylist_withdrawals")', block)
        template = self.read("templates/dashboards/manager_stylist_withdrawals.html")
        self.assertIn('name="action" value="approve"', template)
        self.assertIn('name="action" value="reject"', template)


if __name__ == "__main__":
    unittest.main(verbosity=2)
