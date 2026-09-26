"""Login and workspace preferences: authorization is always recomputed server-side."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager, Stylist, UserWorkspacePreference
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleWorkspaceTests(Stage1DomainFactoryMixin, TestCase):
    def login_as(self, user, *, next_url=""):
        url = reverse("accounts:login")
        return self.client.post(url, {
            "mobile_number": user.mobile_number,
            "password": "pass12345",
            "next": next_url,
        })

    def test_customer_only_login_keeps_legacy_destination_without_preference_row(self):
        user = self.make_user()
        response = self.login_as(user)
        self.assertRedirects(response, reverse("accounts:customer_panel"), fetch_redirect_response=False)
        self.assertFalse(UserWorkspacePreference.objects.filter(user=user).exists())

    def test_one_professional_workspace_does_not_force_chooser(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        response = self.login_as(user)
        self.assertRedirects(response, reverse("dashboards:salon_manager_dashboard"), fetch_redirect_response=False)

    def test_first_manager_plus_stylist_login_shows_chooser(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        response = self.login_as(user)
        self.assertRedirects(response, reverse("accounts:workspace_choose"), fetch_redirect_response=False)
        chooser = self.client.get(reverse("accounts:workspace_choose"))
        self.assertContains(chooser, "مدیریت")
        self.assertContains(chooser, "متخصص")
        self.assertContains(chooser, "مشتری")

    def test_stale_single_workspace_preference_cannot_skip_first_multirole_chooser(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        UserWorkspacePreference.objects.create(user=user, kind="stylist", has_chosen_multirole_workspace=False)
        self.assertRedirects(self.login_as(user), reverse("accounts:workspace_choose"), fetch_redirect_response=False)

    def test_single_role_manual_choice_does_not_skip_first_real_multirole_login(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        self.client.force_login(user)
        response = self.client.post(reverse("accounts:workspace_choose"), {"kind": "manager"})
        self.assertRedirects(response, reverse("dashboards:salon_manager_dashboard"), fetch_redirect_response=False)
        self.assertFalse(UserWorkspacePreference.objects.get(user=user).has_chosen_multirole_workspace)
        Stylist.objects.create(user=user)
        self.client.logout()
        self.assertRedirects(self.login_as(user), reverse("accounts:workspace_choose"), fetch_redirect_response=False)

    def test_explicit_choice_persists_after_logout_and_new_login(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        self.client.force_login(user)
        chooser = reverse("accounts:workspace_choose")
        response = self.client.post(chooser, {"kind": "stylist"})
        self.assertRedirects(response, reverse("dashboards:stylist_dashboard"), fetch_redirect_response=False)
        pref = UserWorkspacePreference.objects.get(user=user)
        self.assertTrue(pref.has_chosen_multirole_workspace)
        self.assertEqual(pref.kind, "stylist")
        self.client.logout()
        self.assertRedirects(self.login_as(user), reverse("dashboards:stylist_dashboard"), fetch_redirect_response=False)

    def test_customer_can_be_chosen_with_professional_roles(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        self.client.force_login(user)
        response = self.client.post(reverse("accounts:workspace_choose"), {"kind": "customer"})
        self.assertRedirects(response, reverse("accounts:customer_panel"), fetch_redirect_response=False)
        self.client.logout()
        self.assertRedirects(self.login_as(user), reverse("accounts:customer_panel"), fetch_redirect_response=False)

    def test_manager_selection_must_match_exact_owned_salon(self):
        user = self.make_user()
        own_manager = SalonManager.objects.create(user=user)
        own = self.make_salon(manager=own_manager)
        foreign_user = self.make_user()
        foreign = self.make_salon(manager=SalonManager.objects.create(user=foreign_user))
        self.client.force_login(user)
        chooser = reverse("accounts:workspace_choose")
        for salon_id in (foreign.pk, "invalid", "-1"):
            response = self.client.post(chooser, {"kind": "manager", "salon_id": salon_id})
            self.assertEqual(response.status_code, 403)
            self.assertFalse(UserWorkspacePreference.objects.filter(user=user).exists())
        response = self.client.post(chooser, {"kind": "manager", "salon_id": str(own.pk)})
        self.assertRedirects(response, reverse("dashboards:salon_manager_dashboard"), fetch_redirect_response=False)
        pref = UserWorkspacePreference.objects.get(user=user)
        self.assertEqual(pref.salon_id, own.pk)
        self.assertTrue(pref.was_salon_workspace)

    def test_revoked_last_manager_workspace_cannot_be_restored_from_preference(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        salon = self.make_salon(manager=manager)
        UserWorkspacePreference.objects.create(
            user=user, kind="manager", salon=salon, has_chosen_multirole_workspace=True,
            was_salon_workspace=True,
        )
        salon.delete()
        response = self.login_as(user)
        # A removed salon cannot silently turn into the onboarding manager
        # workspace when the FK becomes NULL. The user must choose anew.
        self.assertRedirects(response, reverse("accounts:workspace_choose"), fetch_redirect_response=False)
        self.assertFalse(UserWorkspacePreference.objects.get(user=user).salon_id)

    def test_multi_salon_manager_choice_uses_explicit_scoped_overview(self):
        user = self.make_user()
        manager = SalonManager.objects.create(user=user)
        a = self.make_salon(manager=manager)
        b = self.make_salon(manager=manager)
        self.client.force_login(user)
        chooser = reverse("accounts:workspace_choose")
        response = self.client.get(chooser)
        self.assertContains(response, a.salon_name)
        self.assertContains(response, b.salon_name)
        response = self.client.post(chooser, {"kind": "manager", "salon_id": str(b.pk)})
        expected = reverse(
            "dashboards:multirole_manager_salon_overview", kwargs={"salon_id": b.pk}
        )
        self.assertRedirects(response, expected, fetch_redirect_response=False)
        self.assertEqual(UserWorkspacePreference.objects.get(user=user).salon_id, b.pk)
        self.assertEqual(self.client.get(reverse("dashboards:salon_manager_dashboard")).status_code, 403)

    def test_safe_next_has_priority_over_chooser(self):
        user = self.make_user()
        SalonManager.objects.create(user=user)
        Stylist.objects.create(user=user)
        next_url = reverse("accounts:customer_panel")
        response = self.login_as(user, next_url=next_url)
        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertFalse(UserWorkspacePreference.objects.filter(user=user).exists())

    def test_invalid_workspace_and_get_do_not_change_preference(self):
        user = self.make_user()
        self.client.force_login(user)
        chooser = reverse("accounts:workspace_choose")
        self.client.get(chooser)
        self.assertEqual(self.client.post(chooser, {"kind": "manager"}).status_code, 403)
        self.assertFalse(UserWorkspacePreference.objects.filter(user=user).exists())
