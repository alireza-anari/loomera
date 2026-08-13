from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CustomerExperienceCompletionBatch55StaticGuards(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_customer_profile_cannot_edit_login_mobile_or_duplicate_addresses(self):
        forms = self.read("apps/accounts/forms.py")
        block = forms.split("class CustomerUpdateProfileForm", 1)[1].split("\nclass ", 1)[0]
        self.assertIn('fields = ["name", "family", "email"]', block)
        self.assertNotIn('"mobile_number": forms.', block)
        profile = self.read("templates/accounts/customer_profile.html")
        edit = self.read("templates/accounts/edit_profile.html")
        self.assertIn("شماره موبایل ورود", profile)
        self.assertIn("شناسه ورود", edit)
        self.assertNotIn("form.mobile_number", edit)
        views = self.read("apps/accounts/views.py")
        profile_view = views.split("class CustomerProfilePageView", 1)[1].split("\nclass ", 1)[0]
        self.assertNotIn("addresses", profile_view)

    def test_customer_account_and_settings_are_task_hubs_not_duplicate_menus(self):
        panel = self.read("templates/accounts/customer_panel.html")
        settings = self.read("templates/accounts/customer_settings.html")
        for label in ["نوبت‌های من", "علاقه‌مندی‌ها", "کیف پول", "رزرو جدید"]:
            self.assertIn(label, panel)
        self.assertEqual(panel.count("نوبت‌های من"), 1)
        self.assertEqual(panel.count("علاقه‌مندی‌ها"), 1)
        for label in ["پروفایل", "آدرس‌ها", "رمز عبور", "اعلان‌ها و ارتباطات"]:
            self.assertIn(label, settings)

    def test_customer_communications_exposes_only_usable_channels_and_role_scope(self):
        urls = self.read("apps/accounts/urls.py")
        view = self.read("apps/accounts/customer_communication_views.py")
        template = self.read("templates/accounts/customer_communication_settings.html")
        self.assertIn('name="customer_communication_settings"', urls)
        self.assertIn("NotificationAudienceRole.CUSTOMER", view)
        self.assertIn("NotificationChannel.BALE.value", view)
        self.assertIn("پیامک", template)
        self.assertIn("ایمیل", template)
        self.assertIn("اتصال بله", template)
        for future_channel in ["واتس‌اپ", "تلگرام", "روبیکا"]:
            self.assertNotIn(future_channel, template)
        self.assertEqual(template.count("<form"), template.count("</form>"))

    def test_notification_center_has_one_canonical_customer_route_and_filter_sheet(self):
        root_urls = self.read("loomera/urls.py")
        account_urls = self.read("apps/accounts/urls.py")
        template = self.read("templates/accounts/notifications.html")
        self.assertIn('include("apps.notifications.urls", namespace="notifications")', root_urls)
        self.assertIn('CustomerNotificationsView.as_view()', account_urls)
        self.assertNotIn('customer_notifications_root', root_urls)
        self.assertIn("data-notification-filter-modal", template)
        self.assertIn("فیلتر اعلان‌ها", template)
        self.assertIn("accounts:customer_communication_settings", template)

    def test_wallet_hides_disabled_beta_operations_and_removes_fake_points(self):
        view = self.read("apps/payments/views.py")
        detail = self.read("templates/payments/wallet_detail.html")
        withdraw = self.read("templates/payments/wallet_withdraw.html")
        self.assertIn('"wallet_operations_enabled": _wallet_operations_enabled()', view)
        self.assertNotIn("points_total", view)
        self.assertNotIn("points_earned", view)
        self.assertIn("شارژ و برداشت در نسخه بتا فعال نیست", detail)
        self.assertIn("{% if not wallet_operations_enabled %}", detail)
        self.assertIn("_saved_destination", view)
        self.assertIn('post_data.get("destination_mode") == "saved"', view)
        self.assertIn("مقصد برداشت", withdraw)

    def test_support_separates_request_creation_from_history(self):
        view = self.read("apps/main/views.py")
        contact = self.read("templates/main/support/contact_form.html")
        tickets = self.read("templates/main/support/ticket_list.html")
        support_block = view.split("class SupportView", 1)[1].split("\nclass SupportTicketListView", 1)[0]
        self.assertNotIn("support_tickets", support_block)
        self.assertIn('redirect("main:support_ticket_detail", pk=ticket.pk)', support_block)
        self.assertIn('redirect("main:success")', support_block)
        self.assertNotIn("support_tickets", contact)
        self.assertIn("درخواست‌های من", contact)
        self.assertIn("درخواست جدید", tickets)

    def test_discovery_uses_three_clear_customer_buckets(self):
        views = self.read("apps/salons/views.py")
        template = self.read("templates/pages/show_salons.html")
        self.assertIn("for_you_salons", views)
        self.assertIn("discover_salons", views)
        for label in ["رزرو دوباره", "برای تو", "کشف بیشتر"]:
            self.assertIn(label, template)
        for legacy_heading in ["بیشترین تخفیف", "برترین مجموعه‌ها", "جدیدترین مجموعه‌ها", "محبوب‌ترین مجموعه‌ها"]:
            self.assertNotIn(legacy_heading, template)

    def test_public_salon_keeps_booking_engine_but_simplifies_content_navigation(self):
        template = self.read("templates/pages/detail_salon.html")
        script = self.read("static/js/pages/detail_salon.js")
        self.assertIn('id="services"', template)
        self.assertIn('id="bookingBar"', template)
        self.assertIn("bookingSelectionDraft", script)
        self.assertNotIn("data-section-nav-floating", template)
        self.assertNotIn("data-section-nav-floating", script)
        self.assertNotIn("updateTabsTransfer", script)
        self.assertIn('href="#about"', template)
        self.assertNotIn('href="#extra"', template)
        self.assertIn("اطلاعات مجموعه", template)

    def test_public_stylist_and_story_explore_use_new_customer_patterns(self):
        stylist = self.read("templates/pages/salon_stylist_profile.html")
        stories = self.read("templates/articles/story_explore.html")
        self.assertIn("book_with_stylist_url", stylist)
        self.assertIn("خدمات قابل رزرو", stylist)
        self.assertIn("نمونه‌کارها", stylist)
        self.assertIn("data-story-filter-modal", stories)
        self.assertIn("فیلتر", stories)
        self.assertIn("data-story-filter-open", stories)

    def test_customer_facing_salon_links_use_canonical_slug_urls(self):
        for relative in [
            "templates/components/salon_card.html",
            "templates/components/book_again_card.html",
            "templates/pages/home.html",
            "templates/csf/partials/favorite_salons.html",
            "templates/search/search_results.html",
            "templates/orders/select_stylists.html",
        ]:
            source = self.read(relative)
            self.assertNotIn("{% url 'salons:detail_salon'", source, relative)
            self.assertIn("get_absolute_url", source, relative)
        search_utils = self.read("apps/search/utils.py")
        self.assertIn('"detail_url": salon.get_absolute_url()', search_utils)

    def test_legacy_customer_routes_are_redirects_and_dead_templates_are_removed(self):
        orders_urls = self.read("apps/orders/urls.py")
        search_urls = self.read("apps/search/urls.py")
        self.assertIn('pattern_name="orders:quick_booking_entry"', orders_urls)
        self.assertIn('pattern_name="orders:appointment_detail"', orders_urls)
        self.assertIn('pattern_name="search:search_page"', search_urls)
        for relative in [
            "templates/orders/select_stylist.html",
            "templates/pages/orders.html",
            "templates/pages/profile.html",
            "templates/payments/appointment_result.html.before-5.5B.bak",
        ]:
            self.assertFalse((ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
