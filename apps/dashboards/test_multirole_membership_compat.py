"""Multi-role manager/stylist membership boundaries and invite recipient tests."""

from django.http import Http404
from django.test import RequestFactory, TestCase
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse

from apps.accounts.models import SalonManager, Stylist
from apps.accounts.services.access import resolve_stylist_membership
from apps.orders.booking_utils import stylist_is_bookable_for_salon
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.stylists.models import EmergencyInfo
from apps.dashboards.views import _respond_to_manager_invite
from tests_stage1_helpers import Stage1DomainFactoryMixin


class MultiroleMembershipCompatibilityTests(Stage1DomainFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.make_user()
        self.manager = SalonManager.objects.create(user=self.user)
        self.first = self.make_salon(manager=self.manager)
        self.second = self.make_salon(manager=self.manager)
        self.foreign = self.make_salon(manager=self.make_salon_manager())
        self.client.force_login(self.user)

    def _add_stylist(self):
        response = self.client.post(
            reverse("accounts:add_role", kwargs={"kind": "stylist"}),
            {"expert": "آرایش"},
        )
        self.assertEqual(response.status_code, 302)
        stylist = Stylist.objects.get(user=self.user)
        self.assertFalse(SalonMembership.objects.filter(stylist=stylist).exists())
        return stylist

    def _invite(self, salon, phone=None):
        return self.client.post(
            reverse("dashboards:multirole_manager_team_invite", kwargs={"salon_id": salon.pk}),
            {
                "salon_id": str(salon.pk),
                "mobile_number": phone or self.user.mobile_number,
                "role_title": "متخصص",
            },
        )

    def _invite_response_request(self, membership, user=None):
        request = RequestFactory().post("/", {"membership_id": str(membership.pk)})
        request.user = user or self.user
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def _complete_stylist_profile(self, stylist):
        stylist.expert = "آرایش"
        stylist.is_active = True
        stylist.resume_headline = "عنوان حرفه‌ای"
        stylist.resume_summary = "خلاصه رزومه"
        stylist.description = "توضیحات حرفه‌ای"
        stylist.save(update_fields=[
            "expert", "is_active", "resume_headline", "resume_summary", "description",
        ])
        EmergencyInfo.objects.create(
            stylist=stylist, emergency_contact="09120000000", relationship="همکار",
            full_name="مخاطب اضطراری",
        )

    def test_manager_becoming_stylist_does_not_auto_join_owned_salons(self):
        stylist = self._add_stylist()
        for salon in (self.first, self.second):
            self.assertFalse(salon.stylists.filter(pk=stylist.pk).exists())
            self.assertFalse(SalonMembership.objects.filter(salon=salon, stylist=stylist).exists())
            self.assertFalse(stylist_is_bookable_for_salon(salon=salon, stylist=stylist))

    def test_manager_self_invitation_needs_explicit_stylist_acceptance(self):
        stylist = self._add_stylist()
        self._complete_stylist_profile(stylist)
        self.assertEqual(self._invite(self.second).status_code, 302)
        invite = SalonMembership.objects.get(salon=self.second, stylist=stylist)
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)
        self.assertFalse(self.second.stylists.filter(pk=stylist.pk).exists())
        self.assertFalse(SalonMembership.objects.filter(salon=self.first, stylist=stylist).exists())

        request = self._invite_response_request(invite)
        self.assertEqual(
            _respond_to_manager_invite(request, stylist, accepted=True).status_code, 302,
        )
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.ACTIVE)
        self.assertEqual(resolve_stylist_membership(self.user, self.second.pk).pk, invite.pk)
        self.assertFalse(SalonMembership.objects.filter(salon=self.first, stylist=stylist).exists())
        self.assertTrue(self.second.stylists.filter(pk=stylist.pk).exists())
        self.assertFalse(self.first.stylists.filter(pk=stylist.pk).exists())
        self.assertTrue(stylist_is_bookable_for_salon(salon=self.second, stylist=stylist))
        self.assertFalse(stylist_is_bookable_for_salon(salon=self.first, stylist=stylist))

    def test_same_stylist_can_be_active_in_one_salon_and_paused_in_another(self):
        stylist = self._add_stylist()
        stylist.is_active = True
        stylist.save(update_fields=["is_active"])
        self.first.stylists.add(stylist)
        self.second.stylists.add(stylist)
        first = SalonMembership.objects.create(
            salon=self.first, stylist=stylist, status=SalonMembershipStatus.ACTIVE,
        )
        second = SalonMembership.objects.create(
            salon=self.second, stylist=stylist, status=SalonMembershipStatus.PAUSED,
        )
        self.assertEqual(resolve_stylist_membership(self.user, self.first.pk).pk, first.pk)
        self.assertTrue(stylist_is_bookable_for_salon(salon=self.first, stylist=stylist))
        self.assertFalse(stylist_is_bookable_for_salon(salon=self.second, stylist=stylist))
        self.assertEqual(SalonMembership.objects.get(pk=second.pk).status, SalonMembershipStatus.PAUSED)

    def test_bound_invitation_for_different_phone_cannot_be_accepted(self):
        stylist = self._add_stylist()
        self._complete_stylist_profile(stylist)
        other = self.make_user()
        invite = SalonMembership.objects.create(
            salon=self.second,
            stylist=stylist,
            invited_phone=other.mobile_number,
            status=SalonMembershipStatus.INVITED,
            metadata={"invited_by_manager": True},
        )
        request = self._invite_response_request(invite)
        with self.assertRaises(Http404):
            _respond_to_manager_invite(request, stylist, accepted=True)
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.INVITED)
        self.assertFalse(self.second.stylists.filter(pk=stylist.pk).exists())

    def test_blank_phone_legacy_bound_invitation_remains_acceptable(self):
        stylist = self._add_stylist()
        self._complete_stylist_profile(stylist)
        invite = SalonMembership.objects.create(
            salon=self.first, stylist=stylist, invited_phone="",
            status=SalonMembershipStatus.INVITED,
            metadata={"invited_by_manager": True},
        )
        self.assertEqual(
            _respond_to_manager_invite(self._invite_response_request(invite), stylist, accepted=True).status_code,
            302,
        )
        invite.refresh_from_db()
        self.assertEqual(invite.status, SalonMembershipStatus.ACTIVE)
        self.assertEqual(invite.invited_phone, self.user.mobile_number)
        self.assertFalse(self.second.stylists.filter(pk=stylist.pk).exists())
