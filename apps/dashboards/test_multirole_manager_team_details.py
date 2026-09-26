"""Scoped manager edits only a salon-specific team role, never global identity."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import SalonManager
from apps.salons.models import SalonMembership, SalonMembershipStatus
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerTeamDetailsTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.owner = self.make_user()
        self.manager = SalonManager.objects.create(user=self.owner)
        self.a = self.make_salon(manager=self.manager)
        self.b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.stylist = self.make_stylist()
        self.a.stylists.add(self.stylist)
        self.b.stylists.add(self.stylist)
        self.ma = SalonMembership.objects.create(
            salon=self.a, stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE, role_title="الف",
        )
        self.mb = SalonMembership.objects.create(
            salon=self.b, stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE, role_title="ب",
        )
        self.m_foreign = SalonMembership.objects.create(
            salon=self.foreign, stylist=self.stylist,
            status=SalonMembershipStatus.ACTIVE, role_title="خارجی",
        )
        self.client.force_login(self.owner)

    def url(self, salon, membership):
        return reverse("dashboards:multirole_manager_team_member_edit", kwargs={
            "salon_id": salon.pk, "membership_id": membership.pk,
        })

    def post(self, salon, membership, *, form_salon=None, title="متخصص سالن"):
        return self.client.post(self.url(salon, membership), {
            "salon_id": str((form_salon or salon).pk), "role_title": title,
        })

    def test_read_team_member_details_only_for_owned_salon_and_membership(self):
        response = self.client.get(self.url(self.b, self.mb))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ب")
        self.assertNotContains(response, 'value="الف"')
        for salon, member in ((self.a, self.mb), (self.b, self.ma),
                              (self.foreign, self.m_foreign)):
            with self.subTest(salon=salon.pk, member=member.pk):
                self.assertIn(self.client.get(self.url(salon, member)).status_code, (403, 404))

    def test_edit_affects_only_target_membership_not_other_salon_or_identity(self):
        before_password = self.stylist.user.password
        before_stylist_active = self.stylist.is_active
        response = self.post(self.b, self.mb, title="  سرپرست خدمات  ")
        self.assertRedirects(response,
            reverse("dashboards:multirole_manager_salon_team", kwargs={"salon_id": self.b.pk}),
            fetch_redirect_response=False)
        self.ma.refresh_from_db()
        self.mb.refresh_from_db()
        self.stylist.refresh_from_db()
        self.stylist.user.refresh_from_db()
        self.assertEqual(self.ma.role_title, "الف")
        self.assertEqual(self.mb.role_title, "سرپرست خدمات")
        self.assertEqual(self.stylist.user.password, before_password)
        self.assertEqual(self.stylist.is_active, before_stylist_active)

    def test_form_target_and_foreign_or_mismatched_membership_are_rejected(self):
        for salon, member, form_salon in (
            (self.a, self.ma, self.b),
            (self.a, self.mb, self.a),
            (self.b, self.ma, self.b),
            (self.foreign, self.m_foreign, self.foreign),
        ):
            with self.subTest(salon=salon.pk, member=member.pk):
                self.assertIn(self.post(salon, member, form_salon=form_salon).status_code, (403, 404))
        self.ma.refresh_from_db()
        self.mb.refresh_from_db()
        self.m_foreign.refresh_from_db()
        self.assertEqual((self.ma.role_title, self.mb.role_title, self.m_foreign.role_title),
                         ("الف", "ب", "خارجی"))

    def test_two_tabs_do_not_retarget_existing_team_form(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.b.pk),
        })
        self.assertEqual(self.post(self.a, self.ma, title="تخصص الف").status_code, 302)
        self.ma.refresh_from_db()
        self.mb.refresh_from_db()
        self.assertEqual(self.ma.role_title, "تخصص الف")
        self.assertEqual(self.mb.role_title, "ب")

    def test_stale_management_permission_denied(self):
        self.a.salon_manager = self.make_salon_manager()
        self.a.save(update_fields=["salon_manager"])
        self.assertIn(self.post(self.a, self.ma).status_code, (403, 404))
        self.ma.refresh_from_db()
        self.assertEqual(self.ma.role_title, "الف")

    def test_pending_ended_and_paused_memberships_not_editable(self):
        for status in (SalonMembershipStatus.INVITED, SalonMembershipStatus.PAUSED,
                       SalonMembershipStatus.ENDED):
            with self.subTest(status=status):
                self.ma.status = status
                self.ma.save(update_fields=["status"])
                self.assertIn(self.client.get(self.url(self.a, self.ma)).status_code, (403, 404))
                self.assertIn(self.post(self.a, self.ma).status_code, (403, 404))
        self.ma.refresh_from_db()
        self.assertEqual(self.ma.role_title, "الف")

    def test_invalid_role_title_does_not_write(self):
        for title in ("", " ", "x" * 129):
            with self.subTest(title=title):
                self.assertEqual(self.post(self.a, self.ma, title=title).status_code, 200)
                self.ma.refresh_from_db()
                self.assertEqual(self.ma.role_title, "الف")

    def test_only_get_and_post_and_only_manager_can_edit(self):
        self.assertEqual(self.client.put(self.url(self.a, self.ma)).status_code, 405)
        self.client.force_login(self.make_user())
        self.assertIn(self.post(self.a, self.ma).status_code, (403, 404))
        self.ma.refresh_from_db()
        self.assertEqual(self.ma.role_title, "الف")

    def test_team_page_links_active_membership_only_in_its_own_salon(self):
        response = self.client.get(reverse("dashboards:multirole_manager_salon_team",
                                           kwargs={"salon_id": self.b.pk}))
        self.assertContains(response, self.url(self.b, self.mb))
        self.assertNotContains(response, self.url(self.a, self.ma))
        self.mb.status = SalonMembershipStatus.PAUSED
        self.mb.save(update_fields=["status"])
        response = self.client.get(reverse("dashboards:multirole_manager_salon_team",
                                           kwargs={"salon_id": self.b.pk}))
        self.assertNotContains(response, self.url(self.b, self.mb))

    def test_can_not_alter_membership_status_or_visibility_with_extra_fields(self):
        response = self.client.post(self.url(self.a, self.ma), {
            "salon_id": str(self.a.pk), "role_title": "متخصص الف",
            "status": SalonMembershipStatus.ENDED,
            "show_on_salon_profile": "false", "stylist": str(self.ma.stylist_id),
        })
        self.assertEqual(response.status_code, 302)
        self.ma.refresh_from_db()
        self.assertEqual(self.ma.status, SalonMembershipStatus.ACTIVE)
        self.assertTrue(self.ma.show_on_salon_profile)
        self.assertEqual(self.ma.role_title, "متخصص الف")
