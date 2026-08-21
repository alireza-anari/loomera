from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxReportsFilterBatch39StaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_each_major_report_section_has_its_own_tab_and_panel(self):
        source = self.read("templates/dashboards/reports.html")
        expected = {
            "overview": "نمای کلی",
            "analytics": "تحلیل روند",
            "rankings": "برترین‌ها",
            "table": "جزئیات",
        }
        for key, label in expected.items():
            self.assertIn(f'data-reports-section-tab="{key}"', source)
            self.assertIn(f'data-reports-section-panel="{key}"', source)
            self.assertIn(label, source)

    def test_only_overview_panel_is_visible_by_default(self):
        source = self.read("templates/dashboards/reports.html")
        overview = source.split('data-reports-section-panel="overview"', 1)[1].split("</section>", 1)[0]
        self.assertNotIn(" hidden", overview)

        for key in ("analytics", "rankings", "table"):
            panel = source.split(f'data-reports-section-panel="{key}"', 1)[1].split(">", 1)[0]
            self.assertIn("hidden", panel)

    def test_filter_is_first_action_but_hidden_on_overview(self):
        source = self.read("templates/dashboards/reports.html")
        tabs = source.split('role="tablist" aria-label="بخش‌های گزارش"', 1)[1].split("</div>", 1)[0]
        self.assertLess(tabs.index("data-reports-filter-open"), tabs.index('data-reports-section-tab="overview"'))
        self.assertIn("lm-reports-filter-tab hidden", tabs)
        self.assertEqual(source.count("data-reports-filter-open"), 1)

    def test_report_section_tabs_are_client_side_panels(self):
        source = self.read("static/js/pages/reports_dashboard.js")
        self.assertIn("const initReportSectionTabs = () =>", source)
        self.assertIn("[data-reports-section-tab]", source)
        self.assertIn("[data-reports-section-panel]", source)
        self.assertIn('const showFilter = key !== "overview"', source)
        self.assertIn("panel.hidden = !active", source)
        self.assertIn("initReportSectionTabs();", source)

    def test_reports_header_is_compact(self):
        source = self.read("templates/dashboards/reports.html")
        self.assertNotIn("مرکز تحلیل عملکرد مجموعه", source)
        self.assertIn("reports_dashboard.active_range_label", source)
        self.assertIn("گزارش PDF", source)

    def test_overview_metrics_are_self_explanatory(self):
        source = self.read("apps/dashboards/reports_components.py")
        for label in (
            "درآمد تأییدشده",
            "کل رزروها",
            "مشتری جدید",
            "میانگین مبلغ هر رزرو",
            "درصد رزروهای تکمیل‌شده",
        ):
            self.assertIn(label, source)

    def test_filter_dialog_remains_mobile_safe(self):
        page = self.read("templates/dashboards/reports.html")
        partial = self.read("templates/dashboards/components/reports_filter_bar.html")
        self.assertIn('role="dialog"', page)
        self.assertIn('sm:max-w-5xl', page)
        self.assertNotIn("گروه‌بندی</span>", partial)
        self.assertIn('type="hidden" name="group_by"', partial)

    def test_mobile_charts_and_ranking_donut_contract(self):
        trend = self.read("templates/dashboards/partials/reports_chart_body.html")
        status = self.read("templates/dashboards/partials/reports_status_widget.html")
        ranking = self.read("templates/dashboards/partials/reports_ranking_chart.html")
        self.assertIn("data-reports-trend-canvas", trend)
        self.assertIn("data-reports-status-canvas", status)
        self.assertIn("conic-gradient(", ranking)
        self.assertIn("widget.center_label", ranking)
        self.assertIn("inset: 21%", ranking)

    def test_pdf_export_has_no_weasyprint_native_dependency(self):
        source = self.read("apps/dashboards/reports_components.py")
        self.assertIn("application/pdf", source)
        self.assertIn("from fpdf import FPDF", source)
        self.assertIn("set_text_shaping", source)
        self.assertIn("YekanBakh-Regular.woff2", source)
        self.assertNotIn("weasyprint", source.lower())
        self.assertNotIn("render_to_string", source)

    def test_pdf_is_branded_and_keeps_legacy_route_contract(self):
        source = self.read("apps/dashboards/reports_components.py")
        page = self.read("templates/dashboards/reports.html")
        self.assertIn("loomera-logo-horizontal-rtl-transparent-360.png", source)
        self.assertIn("loomera.ir", source)
        self.assertIn("گزارش عملکرد", source)
        self.assertIn("def build_reports_csv_response", source)
        self.assertIn(".pdf", source)
        self.assertIn("گزارش PDF", page)

    def test_ranking_widgets_have_explicit_center_labels(self):
        source = self.read("apps/dashboards/reports_components.py")
        self.assertIn('"center_label": "خدمت برتر"', source)
        self.assertIn('"center_label": "عضو برتر"', source)
        self.assertIn('"count_label": to_persian_digits(len(items))', source)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
