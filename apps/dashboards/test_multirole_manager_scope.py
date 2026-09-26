"""Safety gate for two-salon managers while legacy manager views are migrated."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager, Stylist, UserWorkspacePreference
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerEntryTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user)
        self.salon_a = self.make_salon(manager=self.manager)
        self.salon_b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.client.force_login(self.user)
        self.chooser = reverse("accounts:workspace_choose")
        self.overview_b = reverse(
            "dashboards:multirole_manager_salon_overview",
            kwargs={"salon_id": self.salon_b.pk},
        )

    def test_chooser_selects_exact_salon_and_persists_without_legacy_dashboard(self):
        response = self.client.post(
            self.chooser, {"kind": "manager", "salon_id": str(self.salon_b.pk)}
        )
        self.assertRedirects(response, self.overview_b, fetch_redirect_response=False)
        pref = UserWorkspacePreference.objects.get(user=self.user)
        self.assertEqual(pref.kind, "manager")
        self.assertEqual(pref.salon_id, self.salon_b.pk)
        self.assertTrue(pref.has_chosen_multirole_workspace)
        response = self.client.get(self.overview_b)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.salon_b.salon_name)
        self.assertEqual(response.context["salon"], self.salon_b)
        # Other owned salons are intentionally visible once in the workspace switcher.
        # They must not become the business-data scope of this explicit salon URL.
        self.assertContains(response, self.salon_a.salon_name, count=1)
        self.assertNotContains(response, self.foreign.salon_name)
        self.client.logout()
        response = self.client.post(
            reverse("accounts:login"),
            {"mobile_number": self.user.mobile_number, "password": "pass12345"},
        )
        self.assertRedirects(response, self.overview_b, fetch_redirect_response=False)

    def test_foreign_and_malformed_targets_cannot_open_manager_overview(self):
        foreign_url = reverse(
            "dashboards:multirole_manager_salon_overview",
            kwargs={"salon_id": self.foreign.pk},
        )
        self.assertIn(self.client.get(foreign_url).status_code, (403, 404))
        self.assertIn(self.client.post(foreign_url).status_code, (403, 404, 405))
        self.assertEqual(self.client.post(
            self.chooser, {"kind": "manager", "salon_id": str(self.foreign.pk)}
        ).status_code, 403)

    def test_legacy_manager_pages_and_mutations_fail_closed_for_two_salons(self):
        for name in (
            "dashboards:salon_manager_dashboard",
            "dashboards:service_menu",
        ):
            with self.subTest(name=name):
                url = reverse(name)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(
                    url, {"salon_id": str(self.salon_a.pk)}
                ).status_code, 403)

    def test_manager_can_still_use_customer_and_stylist_workspaces(self):
        Stylist.objects.create(user=self.user)
        self.assertNotEqual(
            self.client.get(reverse("accounts:customer_panel")).status_code, 403
        )
        self.assertNotEqual(
            self.client.get(reverse("dashboards:stylist_dashboard")).status_code, 403
        )

    def test_revoked_salon_is_not_authorized_by_stale_preference(self):
        self.client.post(
            self.chooser, {"kind": "manager", "salon_id": str(self.salon_b.pk)}
        )
        self.salon_b.salon_manager = self.make_salon_manager()
        self.salon_b.save(update_fields=["salon_manager"])
        self.assertIn(self.client.get(self.overview_b).status_code, (403, 404))
        self.client.logout()
        response = self.client.post(
            reverse("accounts:login"),
            {"mobile_number": self.user.mobile_number, "password": "pass12345"},
        )
        self.assertRedirects(
            response, reverse("dashboards:salon_manager_dashboard"),
            fetch_redirect_response=False,
        )

    def test_single_salon_manager_remains_on_legacy_dashboard(self):
        other_user = self.make_user()
        other_manager = SalonManager.objects.create(user=other_user)
        self.make_salon(manager=other_manager)
        self.client.force_login(other_user)
        self.assertNotEqual(
            self.client.get(reverse("dashboards:salon_manager_dashboard")).status_code,
            403,
        )
