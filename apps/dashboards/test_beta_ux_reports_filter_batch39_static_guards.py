from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]


class BetaUxReportsFilterBatch39StaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_reports_no_longer_render_standalone_filter_section(self):
        source = self.read("templates/dashboards/reports.html")
        self.assertNotIn('id="reports-section-filters"', source)
        self.assertEqual(source.count('include "dashboards/components/reports_filter_bar.html"'), 1)
        self.assertIn('data-reports-filter-modal', source)

    def test_overview_does_not_repeat_active_filter_chips(self):
        source = self.read("templates/dashboards/reports.html")
        overview = source.split('id="reports-section-overview"', 1)[1].split('id="reports-section-analytics"', 1)[0]
        self.assertNotIn("active_filter_chips", overview)
        self.assertNotIn("فیلترهای فعال:", overview)

    def test_filter_is_inserted_as_first_task_tab_action(self):
        source = self.read("static/js/pages/reports_dashboard.js")
        self.assertIn('data-lm-task-tabs-generated="reports"', source)
        self.assertIn('trigger.dataset.reportsFilterOpen', source)
        self.assertIn('lm-reports-tabs-shell', source)
        self.assertIn('shell.append(trigger, taskTabs)', source)
        self.assertIn('aria-haspopup", "dialog', source)

    def test_filter_dialog_has_one_form_and_mobile_safe_modal(self):
        page = self.read("templates/dashboards/reports.html")
        partial = self.read("templates/dashboards/components/reports_filter_bar.html")
        self.assertIn('role="dialog"', page)
        self.assertIn('sm:max-w-5xl', page)
        self.assertEqual(partial.count('data-reports-filter-form'), 2)  # shell marker + form marker
        self.assertIn('data-reports-filter-close', partial)
        self.assertIn('name="tab" value="{{ reports_dashboard.filters.tab }}"', partial)

    def test_filter_badge_counts_filters_not_notices(self):
        source = self.read("apps/dashboards/reports_components.py")
        count_block = source.split("active_filter_count = sum(", 1)[1].split("stylist_label =", 1)[0]
        self.assertNotIn("report_notices", count_block)
        self.assertIn('tab=tab if tab != "overview" else ""', source)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
