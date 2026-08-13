from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceCostBatch44StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_cost_page_has_three_task_based_sections_only(self):
        source = self.read("templates/dashboards/finance_cost_center.html")
        self.assertNotIn("cost-section-forms", source)
        self.assertNotIn("cost-section-actions", source)
        self.assertIn('data-lm-task-tabs-anchor="cost-center"', source)
        self.assertEqual(source.count('data-lm-task-panel="cost-center"'), 3)
        for label in ("مواد مصرفی", "هزینه هر خدمت", "سهم متخصصان"):
            self.assertIn(f'data-lm-task-label="{label}"', source)

    def test_create_and_manage_live_in_same_section(self):
        source = self.read("templates/dashboards/finance_cost_center.html")
        self.assertIn('value="create_material"', source)
        self.assertIn('value="update_material"', source)
        self.assertIn('value="create_template"', source)
        self.assertIn('value="update_template"', source)
        self.assertIn('value="create_rule"', source)
        self.assertIn('value="update_rule"', source)
        self.assertNotIn('value="delete_rule"', source)

    def test_page_does_not_duplicate_profit_report_numbers(self):
        source = self.read("templates/dashboards/finance_cost_center.html")
        view = self.read("apps/dashboards/finance_cost_views.py")
        class_block = view.split("class SalonCostCenterView", 1)[1].split("class AppointmentMaterialUsageView", 1)[0]
        self.assertNotIn("finance_overview", source)
        self.assertNotIn('"summary_cards"', class_block)
        self.assertNotIn("OrderDetailFinancialSnapshot.objects.filter(salon=salon)", class_block)
        self.assertIn('"setup_cards"', class_block)
        self.assertIn("دیدن سود خالص", source)

    def test_material_cost_precedence_is_explained(self):
        source = self.read("templates/dashboards/finance_cost_center.html")
        self.assertIn("این قانون اولویت دارد", source)
        self.assertIn("پرداخت‌کننده پیش‌فرض", source)
        self.assertIn("نادیده گرفته می‌شود", source)

    def test_rule_form_uses_plain_language_and_conditional_fields(self):
        forms = self.read("apps/dashboards/finance_forms.py")
        template = self.read("templates/dashboards/finance_cost_center.html")
        for phrase in (
            "روش محاسبه سهم",
            "سهم از چه مبلغی محاسبه شود؟",
            "بعد از کسر کارمزد لومرا",
            "هزینه مواد این متخصص چگونه تقسیم شود؟",
        ):
            self.assertIn(phrase, forms)
        self.assertIn('data-rule-editor', template)
        self.assertIn('data-rule-field="percent"', template)
        self.assertIn('data-rule-field="fixed_amount"', template)
        self.assertIn('data-rule-field="stylist_material_cost_percent"', template)
        self.assertIn('syncRuleEditor', template)

    def test_inactive_records_are_not_mislabeled_as_urgent_issues(self):
        source = self.read("templates/dashboards/finance_cost_center.html")
        view = self.read("apps/dashboards/finance_cost_views.py")
        self.assertNotIn("نیازمند اقدام", source)
        self.assertNotIn('"issues"', view.split("class SalonCostCenterView", 1)[1].split("class AppointmentMaterialUsageView", 1)[0])
        self.assertIn("موارد غیرفعال", view)


    def test_edit_forms_keep_their_current_inactive_relations_valid(self):
        forms = self.read("apps/dashboards/finance_forms.py")
        self.assertIn("service_filter |= Q(pk=self.instance.service_id)", forms)
        self.assertIn("material_filter |= Q(pk=self.instance.material_id)", forms)
        self.assertIn("stylist_filter |= Q(pk=self.instance.stylist_id)", forms)

    def test_finance_group_wording_is_consistent(self):
        nav = self.read("templates/dashboards/partials/finance/workspace_nav.html")
        hub_view = self.read("apps/dashboards/payment_views.py")
        self.assertIn("سود و هزینه", nav)
        self.assertIn('"title": "سود و هزینه"', hub_view)
        self.assertIn('"label": "هزینه و سهم"', hub_view)
        self.assertIn('"label": "سود خالص"', hub_view)


if __name__ == "__main__":
    unittest.main(verbosity=2)
