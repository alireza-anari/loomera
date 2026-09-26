"""Cross-channel customer capability and explicit manager salon scope."""

from django.test import TestCase

from apps.accounts.models import Customer, SalonManager
from apps.bale_bot.menus import manager_menu, menu_for_role
from apps.messaging.manager_bot import _resolve_salon, render_manager_today_summary
from apps.messaging.promotion_bot import render_manager_promotion_pack
from apps.messaging.roles import detect_user_bot_roles
from apps.orders.models import BookingQuickLink
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleChannelScopeTests(Stage1DomainFactoryMixin, TestCase):
    base_url = "https://loomera.test"

    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user, is_active=True)
        self.first = self.make_salon(manager=self.manager, salon_name="سالن الف")
        self.second = self.make_salon(manager=self.manager, salon_name="سالن ب")
        self.foreign = self.make_salon(manager=self.make_salon_manager(), salon_name="سالن غیرمجاز")

    def test_account_has_customer_bot_capability_without_creating_customer_profile(self):
        self.assertFalse(Customer.objects.filter(user=self.user).exists())
        context = detect_user_bot_roles(self.user)
        self.assertTrue(context.has_role("customer"))
        self.assertTrue(context.has_role("manager"))
        self.assertFalse(Customer.objects.filter(user=self.user).exists())

    def test_revoked_and_inactive_identity_is_not_authorized_via_cached_role(self):
        self.assertIsNotNone(self.user.salon_manager_profile)
        SalonManager.objects.filter(user=self.user).delete()
        self.assertFalse(detect_user_bot_roles(self.user).has_role("manager"))
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertFalse(detect_user_bot_roles(self.user).has_roles)

    def test_multi_salon_manager_without_scope_must_choose_salon(self):
        self.assertIsNone(_resolve_salon(self.user))
        text, markup = render_manager_today_summary(self.user, self.base_url)
        self.assertIn("انتخاب", text)
        callbacks = {button.get("callback_data") for row in markup["inline_keyboard"] for button in row}
        self.assertIn("menu:manager", callbacks)
        text, chooser = menu_for_role(self.base_url, self.user, "manager")
        self.assertIn("کدام سالن", text)
        selected = {button.get("callback_data") for row in chooser["inline_keyboard"] for button in row}
        self.assertIn(f"menu:manager_salon:{self.first.pk}", selected)
        self.assertIn(f"menu:manager_salon:{self.second.pk}", selected)

    def test_only_explicit_owned_salon_can_be_resolved(self):
        self.assertEqual(_resolve_salon(self.user, self.second.pk).pk, self.second.pk)
        for invalid in (self.foreign.pk, "wrong", "", -1, 0, True, f"0{self.first.pk}"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(_resolve_salon(self.user, invalid))

    def test_direct_manager_menu_without_scope_does_not_select_first_salon(self):
        role = detect_user_bot_roles(self.user).get_role("manager")
        menu = manager_menu(self.base_url, role)
        callbacks = {button.get("callback_data") for row in menu["inline_keyboard"] for button in row}
        self.assertIn(f"menu:manager_salon:{self.first.pk}", callbacks)
        self.assertIn(f"menu:manager_salon:{self.second.pk}", callbacks)
        self.assertNotIn("menu:manager_today", callbacks)

    def test_promotion_requires_owned_explicit_salon_and_has_no_side_effect_on_rejection(self):
        service = self.make_service(name="خدمت اختصاصی")
        self.first.services.add(service)
        baseline = BookingQuickLink.objects.count()
        for invalid in (None, self.foreign.pk, "invalid"):
            with self.subTest(invalid=invalid):
                text, menu = render_manager_promotion_pack(self.user, self.base_url, salon_id=invalid)
                self.assertIn("سالن", text)
                self.assertEqual(BookingQuickLink.objects.count(), baseline)
                callbacks = {button.get("callback_data") for row in menu["inline_keyboard"] for button in row}
                self.assertIn("menu:manager", callbacks)
        text, _ = render_manager_promotion_pack(self.user, self.base_url, salon_id=self.first.pk)
        self.assertIn("سالن الف", text)
        self.assertNotIn("سالن ب", text)
        self.assertEqual(BookingQuickLink.objects.filter(salon=self.second).count(), 0)

    def test_single_salon_manager_keeps_legacy_unscoped_entry(self):
        self.second.delete()
        self.assertEqual(_resolve_salon(self.user).pk, self.first.pk)
        text, _ = render_manager_promotion_pack(self.user, self.base_url)
        self.assertIn("سالن الف", text)
