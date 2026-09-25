"""Explicit-salon invite lifecycle; changing workspace cannot retarget a form."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager
from apps.salons.models import SalonMembership, SalonMembershipStatus
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ScopedManagerTeamInvitesTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.manager_user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.manager_user)
        self.a = self.make_salon(manager=self.manager)
        self.b = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.stylist = self.make_stylist()
        self.client.force_login(self.manager_user)

    def url(self, name, salon, **kw):
        return reverse(f"dashboards:{name}", kwargs={"salon_id": salon.pk, **kw})

    def invite(self, salon, *, phone=None, form_salon=None):
        return self.client.post(
            self.url("multirole_manager_team_invite", salon),
            {
                "salon_id": str((form_salon or salon).pk),
                "mobile_number": self.stylist.user.mobile_number if phone is None else phone,
                "invitee_name": "متخصص آزمایشی",
                "role_title": "آرایشگر",
            },
        )

    def test_invite_targets_only_owned_salon_and_requires_acceptance(self):
        response = self.invite(self.b)
        self.assertRedirects(
            response, self.url("multirole_manager_salon_team", self.b),
            fetch_redirect_response=False,
        )
        invite = SalonMembership.objects.get(salon=self.b, stylist=self.stylist)
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)
        self.assertEqual(invite.invited_by_id, self.manager_user.pk)
        self.assertEqual(invite.invited_phone, self.stylist.user.mobile_number)
        self.assertTrue(invite.expires_at)
        self.assertTrue(invite.metadata["invited_by_manager"])
        self.assertFalse(self.b.stylists.filter(pk=self.stylist.pk).exists())
        self.assertFalse(SalonMembership.objects.filter(salon=self.a, stylist=self.stylist).exists())
        self.assertContains(self.client.get(self.url("multirole_manager_salon_team", self.b)), self.stylist.user.mobile_number)
        self.assertNotContains(self.client.get(self.url("multirole_manager_salon_team", self.a)), self.stylist.user.mobile_number)

    def test_form_salon_and_ownership_mismatch_are_rejected(self):
        for salon, form_salon in ((self.a, self.b), (self.foreign, self.foreign)):
            with self.subTest(salon=salon.pk):
                self.assertIn(self.invite(salon, form_salon=form_salon).status_code, (403, 404))
        self.assertIn(
            self.client.post(self.url("multirole_manager_team_invite", self.a), {
                "mobile_number": self.stylist.user.mobile_number,
            }).status_code,
            (403, 404),
        )
        self.assertEqual(SalonMembership.objects.count(), 0)

    def test_switching_workspace_in_other_tab_does_not_change_invite_target(self):
        self.client.post(reverse("accounts:workspace_choose"), {
            "kind": "manager", "salon_id": str(self.b.pk),
        })
        self.assertEqual(self.invite(self.a).status_code, 302)
        self.assertTrue(SalonMembership.objects.filter(salon=self.a, stylist=self.stylist).exists())
        self.assertFalse(SalonMembership.objects.filter(salon=self.b, stylist=self.stylist).exists())

    def test_repeated_invite_does_not_activate_or_reset_existing_membership(self):
        self.assertEqual(self.invite(self.a).status_code, 302)
        original = SalonMembership.objects.get(salon=self.a, stylist=self.stylist)
        self.assertEqual(self.invite(self.a).status_code, 302)
        self.assertEqual(SalonMembership.objects.filter(salon=self.a, stylist=self.stylist).count(), 1)
        original.status = SalonMembershipStatus.PAUSED
        original.save(update_fields=["status"])
        self.assertEqual(self.invite(self.a).status_code, 302)
        original.refresh_from_db()
        self.assertEqual(original.status, SalonMembershipStatus.PAUSED)
        self.assertFalse(self.a.stylists.filter(pk=self.stylist.pk).exists())

    def test_invite_for_unregistered_phone_does_not_create_user_or_stylist(self):
        phone = "09129998877"
        self.assertFalse(CustomUser.objects.filter(mobile_number=phone).exists())
        self.assertEqual(self.invite(self.a, phone=phone).status_code, 302)
        invite = SalonMembership.objects.get(salon=self.a, invited_phone=phone)
        self.assertIsNone(invite.stylist_id)
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)
        self.assertFalse(CustomUser.objects.filter(mobile_number=phone).exists())
        self.assertEqual(self.invite(self.a, phone=phone).status_code, 302)
        self.assertEqual(SalonMembership.objects.filter(salon=self.a, invited_phone=phone).count(), 1)

    def test_invalid_phone_cannot_create_invite(self):
        for phone in ("", "123", "00989123456789", "0912abc", "0912abc3456789", "09123456789012"):
            with self.subTest(phone=phone):
                self.assertEqual(self.invite(self.a, phone=phone).status_code, 302)
        self.assertEqual(SalonMembership.objects.count(), 0)

    def test_invite_and_cancel_are_post_only(self):
        invite_url = self.url("multirole_manager_team_invite", self.a)
        self.assertEqual(self.client.get(invite_url).status_code, 405)
        self.invite(self.a)
        invite = SalonMembership.objects.get(salon=self.a, stylist=self.stylist)
        cancel_url = self.url(
            "multirole_manager_team_invite_cancel", self.a, membership_id=invite.pk,
        )
        self.assertEqual(self.client.get(cancel_url).status_code, 405)
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)

    def test_cancel_only_targeted_owned_pending_invite(self):
        self.invite(self.a)
        invite = SalonMembership.objects.get(salon=self.a, stylist=self.stylist)
        cancel_a = self.url("multirole_manager_team_invite_cancel", self.a, membership_id=invite.pk)
        for url, form_salon in (
            (self.url("multirole_manager_team_invite_cancel", self.b, membership_id=invite.pk), self.b),
            (self.url("multirole_manager_team_invite_cancel", self.foreign, membership_id=invite.pk), self.foreign),
            (cancel_a, self.b),
        ):
            with self.subTest(url=url, form_salon=form_salon.pk):
                self.assertIn(self.client.post(url, {"salon_id": str(form_salon.pk)}).status_code, (403, 404))
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)
        response = self.client.post(cancel_a, {"salon_id": str(self.a.pk)})
        self.assertRedirects(response, self.url("multirole_manager_salon_team", self.a), fetch_redirect_response=False)
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.CANCELLED_BY_SALON)
        self.assertFalse(self.a.stylists.filter(pk=self.stylist.pk).exists())
        self.assertIn(self.client.post(cancel_a, {"salon_id": str(self.a.pk)}).status_code, (403, 404))

    def test_expired_invite_cannot_be_accepted_after_deadline(self):
        from datetime import timedelta
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory
        from django.utils import timezone
        from apps.dashboards.views import _respond_to_manager_invite

        self.invite(self.a)
        invite = SalonMembership.objects.get(salon=self.a, stylist=self.stylist)
        invite.expires_at = timezone.now() - timedelta(minutes=1)
        invite.save(update_fields=["expires_at"])
        request = RequestFactory().post("/", {"membership_id": str(invite.pk)})
        request.user = self.stylist.user
        SessionMiddleware(lambda req: None).process_request(request)
        request._messages = FallbackStorage(request)
        response = _respond_to_manager_invite(request, self.stylist, accepted=True)
        self.assertEqual(response.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.EXPIRED)
        self.assertFalse(self.a.stylists.filter(pk=self.stylist.pk).exists())

    def test_stale_or_customer_account_cannot_operate_on_invites(self):
        self.invite(self.a)
        invite = SalonMembership.objects.get(salon=self.a, stylist=self.stylist)
        self.a.salon_manager = self.make_salon_manager()
        self.a.save(update_fields=["salon_manager"])
        self.assertIn(self.invite(self.a).status_code, (403, 404))
        self.assertIn(self.client.post(
            self.url("multirole_manager_team_invite_cancel", self.a, membership_id=invite.pk),
            {"salon_id": str(self.a.pk)},
        ).status_code, (403, 404))
        self.client.force_login(self.make_user())
        self.assertIn(self.invite(self.b).status_code, (403, 404))
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)
