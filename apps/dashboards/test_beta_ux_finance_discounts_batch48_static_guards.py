from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinanceDiscountsBatch48StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_discount_navigation_uses_customer_facing_service_offer_language(self):
        nav = self.read("templates/dashboards/partials/finance/discount_nav.html")
        hub = self.read("apps/dashboards/payment_views.py")
        self.assertIn("پیشنهاد خدمات", nav)
        self.assertIn('"label": "پیشنهاد خدمات"', hub)
        self.assertNotIn("پکیج تخفیف", nav)

    def test_all_discount_pages_default_to_management_and_keep_creation_separate(self):
        expectations = {
            "templates/dashboards/finance_coupons.html": "finance-coupons",
            "templates/dashboards/finance_baskets.html": "finance-baskets",
            "templates/dashboards/finance_campaigns.html": "finance-campaigns",
        }
        for relative, group in expectations.items():
            text = self.read(relative)
            self.assertIn(f'data-lm-task-panel="{group}" data-lm-task-key="list"', text)
            self.assertIn('data-lm-task-default', text)
            self.assertIn(f'data-lm-task-panel="{group}" data-lm-task-key="form"', text)
            self.assertIn("data-discount-management", text)
            self.assertIn("finance_discounts.js", text)

    def test_discount_state_is_time_aware(self):
        views = self.read("apps/dashboards/payment_views.py")
        self.assertIn("def _discount_state_counts", views)
        self.assertIn("start_date__lte=now, end_date__gte=now", views)
        self.assertIn("start_date__gt=now", views)
        self.assertIn("end_date__lt=now", views)
        self.assertIn("discount_now = timezone.now()", views)

    def test_service_offer_form_only_adds_active_services_but_preserves_legacy_selection(self):
        forms = self.read("apps/discounts/forms.py")
        self.assertIn('service_qs = service_qs.filter(is_active=True)', forms)
        self.assertIn('Q(is_active=True) | Q(pk__in=selected_ids)', forms)
        self.assertIn('label="خدمات شامل تخفیف"', forms)
        self.assertIn("مشتری لازم نیست همه خدمات را با هم رزرو کند", forms)

    def test_campaign_type_is_inferred_instead_of_asking_user(self):
        forms = self.read("apps/discounts/forms.py")
        campaign = self.read("templates/dashboards/finance_campaigns.html")
        self.assertNotIn("{{ form.campaign_type", campaign)
        self.assertIn("instance.campaign_type = DiscountCampaign.CampaignType.MIXED", forms)
        self.assertIn("instance.campaign_type = DiscountCampaign.CampaignType.COUPON", forms)
        self.assertIn("instance.campaign_type = DiscountCampaign.CampaignType.BASKET", forms)
        self.assertIn("نوع کمپین را لازم نیست انتخاب کنی", campaign)

    def test_duplicate_archive_actions_are_removed_from_coupon_and_service_offer_ui(self):
        coupon = self.read("templates/dashboards/finance_coupons.html")
        basket = self.read("templates/dashboards/finance_baskets.html")
        campaign = self.read("templates/dashboards/finance_campaigns.html")
        self.assertNotIn("finance_coupon_delete", coupon)
        self.assertNotIn("finance_basket_delete", basket)
        self.assertIn("finance_campaign_delete", campaign)

    def test_shared_search_and_state_filter_script_is_small_and_generic(self):
        js = self.read("static/js/pages/finance_discounts.js")
        self.assertIn("data-discount-search", js)
        self.assertIn("data-discount-filter-button", js)
        self.assertIn("data-discount-card", js)
        self.assertIn("data-selection-count", js)

    def test_campaign_and_offer_copy_explains_actual_behavior(self):
        basket = self.read("templates/dashboards/finance_baskets.html")
        campaign = self.read("templates/dashboards/finance_campaigns.html")
        self.assertIn("پکیج اجباری", basket)
        self.assertIn("کمپین خودش درصد تخفیف جدیدی نمی‌سازد", campaign)
        self.assertIn("کدها و پیشنهادهای خدماتی", campaign)


if __name__ == "__main__":
    unittest.main()
