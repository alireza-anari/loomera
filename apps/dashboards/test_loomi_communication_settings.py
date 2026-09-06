from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon


@override_settings(
    MESSAGING_ENABLED=True, MESSAGING_ALLOWED_PROVIDERS=["telegram", "bale"],
    LOOMI_MESSAGING_ENABLED=True, LOOMI_MESSAGING_ALLOWED_PROVIDERS=["telegram", "bale"],
    TELEGRAM_BOT_ENABLED=True, BALE_BOT_ENABLED=True,
    TELEGRAM_BOT_USERNAME="ExampleStagingBot", BALE_BOT_USERNAME="ExampleStagingBot",
    BALE_BOT_START_URL_TEMPLATE="https://ble.ir/{username}?start={payload}",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class LoomiCommunicationSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = CustomUser.objects.create(mobile_number="09120000111", name="مدیر", is_active=True)
        cls.manager = SalonManager.objects.create(user=cls.manager_user, is_active=True)
        cls.salons = [Salon.objects.create(salon_name=name, salon_manager=cls.manager, is_active=True)
                      for name in ("سالن اول", "سالن دوم")]
        other_user = CustomUser.objects.create(mobile_number="09120000112", name="دیگر", is_active=True)
        other_manager = SalonManager.objects.create(user=other_user, is_active=True)
        cls.other_salon = Salon.objects.create(salon_name="سالن غیرمجاز", salon_manager=other_manager, is_active=True)
        cls.stylist_user = CustomUser.objects.create(mobile_number="09120000113", name="متخصص", is_active=True)
        cls.stylist = Stylist.objects.create(user=cls.stylist_user, is_active=True, public_visibility="public")
        cls.salons[0].stylists.add(cls.stylist)
        cls.other_stylist = Stylist.objects.create(user=other_user, is_active=True, public_visibility="public")

    def page(self, role="manager", query=None):
        self.client.force_login(self.manager_user if role == "manager" else self.stylist_user)
        response = self.client.get(reverse(f"dashboards:{role}_communication_settings"), query or {})
        self.assertEqual(response.status_code, 200)
        return response

    def test_manager_sees_all_owned_salons_and_no_foreign_salon(self):
        response = self.page(query={"salon_id": self.other_salon.pk})
        cards = response.context["loomi_share_cards"]
        self.assertEqual({card["label"] for card in cards}, {s.salon_name for s in self.salons})
        for salon in self.salons:
            self.assertContains(response, f"https://t.me/ExampleStagingBot?start=loomi_s_{salon.pk}")
            self.assertContains(response, f"https://ble.ir/ExampleStagingBot?start=loomi_s_{salon.pk}")
        self.assertNotContains(response, f"start=loomi_s_{self.other_salon.pk}")
        self.assertContains(response, "لومی در پیام‌رسان‌ها")
        self.assertContains(response, "data-loomi-copy")

    def test_stylist_only_gets_authenticated_profile_links(self):
        response = self.page("stylist", {"stylist_id": self.other_stylist.pk, "salon_id": self.other_salon.pk})
        self.assertEqual(len(response.context["loomi_share_cards"]), 1)
        self.assertContains(response, f"https://t.me/ExampleStagingBot?start=loomi_p_{self.stylist.pk}")
        self.assertContains(response, f"https://ble.ir/ExampleStagingBot?start=loomi_p_{self.stylist.pk}")
        self.assertNotContains(response, f"start=loomi_p_{self.other_stylist.pk}")
        self.assertContains(response, "لینک لومی من")

    def test_disabled_flags_hide_dashboard_section_for_both_roles(self):
        for flag in ("LOOMI_MESSAGING_ENABLED", "MESSAGING_ENABLED"):
            for role in ("manager", "stylist"):
                with self.subTest(flag=flag, role=role), override_settings(**{flag: False}):
                    response = self.page(role)
                    self.assertEqual(response.context["loomi_share_cards"], [])
                    self.assertNotContains(response, "data-loomi-share")

    def test_each_provider_can_be_disabled_independently(self):
        for disabled, remaining in [("TELEGRAM_BOT_ENABLED", "ble.ir"), ("BALE_BOT_ENABLED", "t.me")]:
            for role in ("manager", "stylist"):
                with self.subTest(flag=disabled, role=role), override_settings(**{disabled: False}):
                    cards = self.page(role).context["loomi_share_cards"]
                    self.assertTrue(cards)
                    for card in cards:
                        self.assertEqual(len(card["links"]), 1)
                        self.assertIn(remaining, card["links"][0]["url"])

    @override_settings(MESSAGING_ALLOWED_PROVIDERS=["bale"])
    def test_disallowed_provider_hidden(self):
        self.assertEqual([link["label"] for link in self.page().context["loomi_share_cards"][0]["links"]], ["بله"])

    @override_settings(TELEGRAM_BOT_USERNAME="", BALE_BOT_USERNAME="")
    def test_missing_urls_hide_section(self):
        self.assertEqual(self.page().context["loomi_share_cards"], [])

    def test_inactive_salons_hidden(self):
        self.salons[0].is_active = False
        self.salons[0].save(update_fields=["is_active"])
        self.assertEqual([c["label"] for c in self.page().context["loomi_share_cards"]], [self.salons[1].salon_name])

    def test_hidden_or_inactive_stylist_links_hidden(self):
        for visibility, active in [("hidden", True), ("resume_only", True), ("public", False)]:
            self.stylist.public_visibility = visibility
            self.stylist.is_active = active
            self.stylist.save(update_fields=["public_visibility", "is_active"])
            self.assertEqual(self.page("stylist").context["loomi_share_cards"], [])

    def test_wrong_role_cannot_open_other_role_settings(self):
        self.client.force_login(self.stylist_user)
        self.assertEqual(self.client.get(reverse("dashboards:manager_communication_settings")).status_code, 302)
        self.client.force_login(self.manager_user)
        self.assertEqual(self.client.get(reverse("dashboards:stylist_communication_settings")).status_code, 302)

    def test_anonymous_request_does_not_expose_links(self):
        for role in ("manager", "stylist"):
            self.assertEqual(self.client.get(reverse(f"dashboards:{role}_communication_settings")).status_code, 302)
