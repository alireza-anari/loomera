from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceProfitBatch45StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def profit_view_block(self):
        source = self.read("apps/dashboards/finance_cost_views.py")
        return source.split("class SalonProfitReportView", 1)[1].split(
            "class SalonStylistWalletsView", 1
        )[0]

    def test_profit_page_defaults_to_finalized_finance_only(self):
        view = self.profit_view_block()
        template = self.read("templates/dashboards/finance_profit_report.html")
        self.assertIn("OrderDetailFinancialSnapshot.Status.FINALIZED", view)
        self.assertIn('if status != "all"', view)
        self.assertIn("پیش‌فرض این صفحه فقط خدمات قطعی است", template)
        self.assertIn("قطعی — پیش‌فرض سود", template)

    def test_profit_page_has_three_task_sections_and_no_team_wallet_duplication(self):
        source = self.read("templates/dashboards/finance_profit_report.html")
        self.assertIn('data-lm-task-tabs-anchor="profit-report"', source)
        for label in ("روش محاسبه", "ریز خدمات", "نیازمند بررسی"):
            self.assertIn(f'data-lm-task-label="{label}"', source)
        self.assertEqual(source.count('data-lm-task-panel="profit-report"'), 3)
        self.assertNotIn("profit-section-wallets", source)
        self.assertNotIn("مانده مالی متخصصان", source)
        self.assertNotIn("stylist_wallet_rows", self.profit_view_block())

    def test_top_summary_uses_relevant_profit_components_without_duplicate_total_material_claim(self):
        source = self.read("templates/dashboards/finance_profit_report.html")
        for label in (
            "دریافتی خدمات",
            "کارمزد لومرا",
            "مواد با مجموعه",
            "سهم متخصصان",
            "سود خالص مجموعه",
        ):
            self.assertIn(label, source)
        self.assertIn("profit_overview.salon_materials", source)
        self.assertNotIn("فروش خدمت − تخفیف و کارمزد − هزینه مواد − سهم تیم", source)

    def test_filter_adds_date_scope_and_keeps_historical_inactive_records_filterable(self):
        view = self.profit_view_block()
        template = self.read("templates/dashboards/finance_profit_report.html")
        self.assertIn('request.GET.get("start")', view)
        self.assertIn('request.GET.get("end")', view)
        self.assertIn("order_detail__date__gte", view)
        self.assertIn("order_detail__date__lte", view)
        self.assertIn("salon.services.all()", view)
        self.assertIn("salon.stylists.all()", view)
        self.assertIn('name="start"', template)
        self.assertIn('name="end"', template)
        self.assertIn("— غیرفعال", template)

    def test_profit_detail_rows_explain_each_service_and_link_back_to_source(self):
        source = self.read("templates/dashboards/finance_profit_report.html")
        for token in (
            "item.paid_amount_allocated",
            "item.platform_commission_allocated",
            "item.material_cost_total",
            "item.stylist_net_share",
            "item.salon_net_profit",
        ):
            self.assertIn(token, source)
        self.assertIn("dashboards:appointment_material_usage", source)
        self.assertIn("بررسی جزئیات خدمت", source)

    def test_review_tab_separates_drafts_and_material_warnings(self):
        view = self.profit_view_block()
        source = self.read("templates/dashboards/finance_profit_report.html")
        self.assertIn("draft_review_rows", view)
        self.assertIn("material_review_rows", view)
        self.assertIn("خدماتی که محاسبه مالی‌شان هنوز قطعی نشده", source)
        self.assertIn("خدمات قطعی با الگوی مواد اما بدون مصرف ثبت‌شده", source)
        self.assertIn("مورد فوری برای بررسی پیدا نشد", source)

    def test_old_unused_profit_context_is_removed(self):
        view = self.profit_view_block()
        for old_name in ("formula_cards", "summary_cards", "stylist_wallet_rows"):
            self.assertNotIn(old_name, view)

    def test_plain_language_page_title_is_consistent(self):
        template = self.read("templates/dashboards/finance_profit_report.html")
        layout = self.read("apps/dashboards/layout.py")
        self.assertIn("{% block title %}سود خالص{% endblock %}", template)
        self.assertNotIn("جزئیات درآمد و سود", template)
        self.assertIn('"label": "سود خالص",', layout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
