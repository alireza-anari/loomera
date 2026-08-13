from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]


class BetaUxFinanceHubBatch40StaticGuards(TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_finance_hub_uses_four_task_groups_instead_of_flat_card_catalog(self):
        template = self.read("templates/dashboards/finance_hub.html")
        view = self.read("apps/dashboards/payment_views.py")
        self.assertIn("finance_groups", template)
        self.assertIn('data-finance-group="{{ group.key }}"', template)
        self.assertNotIn("finance_sections", template)
        self.assertNotIn('"finance_sections": finance_sections', view)
        for title in ["پول مجموعه", "سود و هزینه", "مالی متخصصان", "تخفیف‌ها"]:
            self.assertIn(f'"title": "{title}"', view)

    def test_finance_hub_keeps_only_four_primary_metrics(self):
        view = self.read("apps/dashboards/payment_views.py")
        block = view.split('"finance_summary_cards": [', 1)[1].split('                ],\n            }', 1)[0]
        self.assertEqual(block.count('"label":'), 4)
        for label in ["موجودی قابل برداشت", "در انتظار آزادشدن", "فروش ثبت‌شده", "سود مجموعه"]:
            self.assertIn(f'"label": "{label}"', block)
        self.assertNotIn('"label": "خالص قابل تسویه سالن"', block)
        self.assertNotIn('"label": "سهم متخصصان"', block)

    def test_finance_hub_does_not_keep_unused_status_cards(self):
        view = self.read("apps/dashboards/payment_views.py")
        self.assertNotIn("finance_status_cards", view)

    def test_finance_alerts_are_action_only_and_optional(self):
        template = self.read("templates/dashboards/finance_hub.html")
        self.assertIn("{% if finance_alerts %}", template)
        self.assertIn("نیازمند اقدام", template)
        self.assertNotIn("همه چیز مرتب است", template)

    def test_finance_group_icons_use_shared_minimal_svg_set(self):
        template = self.read("templates/dashboards/finance_hub.html")
        icons = self.read("templates/partials/dashboard/nav_icon.html")
        self.assertIn('include "partials/dashboard/nav_icon.html" with key=group.icon', template)
        for key in ["finance_wallet", "finance_cost", "finance_team", "finance_discount"]:
            self.assertIn(f'icon_key == "{key}"', icons)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
