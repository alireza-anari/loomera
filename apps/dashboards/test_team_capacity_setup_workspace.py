from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.salons.models import SalonMembership, SalonMembershipStatus
from tests_stage1_helpers import Stage1DomainFactoryMixin


class TeamCapacitySetupWorkspaceTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)
        self.client.force_login(self.manager.user)

    def _activate_member(self, stylist):
        self.salon.stylists.add(stylist)
        SalonMembership.objects.update_or_create(
            salon=self.salon,
            stylist=stylist,
            defaults={
                "status": SalonMembershipStatus.ACTIVE,
                "accepted_at": timezone.now(),
                "invited_by": self.manager.user,
            },
        )
        return stylist

    def _get_page(self):
        with patch(
            "apps.dashboards.views._redirect_to_required_onboarding",
            return_value=None,
        ):
            return self.client.get(
                reverse("dashboards:online_booking")
            )

    @staticmethod
    def _gap_for(workspace, stylist, key):
        return next(
            item
            for item in workspace["gaps"]
            if item["stylist_id"] == stylist.pk
            and item["key"] == key
        )

    def test_hidden_member_is_reported_as_visibility_gap(self):
        stylist = self._activate_member(
            self.make_stylist(
                public_visibility=Stylist.PublicVisibility.HIDDEN,
            )
        )

        response = self._get_page()

        self.assertEqual(response.status_code, 200)

        workspace = response.context["team_capacity_setup"]
        gap = self._gap_for(workspace, stylist, "visibility")

        self.assertEqual(gap["action_url"], reverse(
            "dashboards:edit_stylist",
            kwargs={"stylist_id": stylist.user_id},
        ))
        self.assertContains(response, 'data-team-capacity-gap="visibility"')

    def test_visible_member_without_bookable_service_is_reported(self):
        stylist = self._activate_member(self.make_stylist())

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]
        self._gap_for(workspace, stylist, "service")

        self.assertEqual(workspace["ready_count"], 0)
        self.assertEqual(workspace["incomplete_count"], 1)
        self.assertContains(response, "بدون خدمت")

    def test_member_with_service_but_without_future_schedule_is_reported(self):
        stylist = self._activate_member(self.make_stylist())
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]
        gap = self._gap_for(workspace, stylist, "schedule")

        self.assertEqual(
            gap["action_url"],
            reverse(
                "dashboards:set_regular_shifts",
                kwargs={
                    "stylist_id": stylist.pk,
                    "salon_id": self.salon.pk,
                },
            ),
        )
        self.assertContains(response, "بدون ظرفیت آینده")

    def test_past_schedule_does_not_complete_capacity_setup(self):
        stylist = self._activate_member(self.make_stylist())
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=service,
            date_value=timezone.localdate() - timedelta(days=1),
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]
        self._gap_for(workspace, stylist, "schedule")

        self.assertFalse(workspace["is_ready"])

    def test_general_future_schedule_completes_capacity_setup(self):
        stylist = self._activate_member(self.make_stylist())
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=None,
            date_value=timezone.localdate() + timedelta(days=1),
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]

        self.assertTrue(workspace["is_ready"])
        self.assertEqual(workspace["ready_count"], 1)
        self.assertEqual(workspace["incomplete_count"], 0)
        self.assertContains(response, "data-team-capacity-ready")

    def test_matching_service_schedule_completes_capacity_setup(self):
        stylist = self._activate_member(self.make_stylist())
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )
        self.add_schedule(
            stylist=stylist,
            salon=self.salon,
            service=service,
            date_value=timezone.localdate() + timedelta(days=1),
            start=timezone.datetime.strptime("14:00", "%H:%M").time(),
            end=timezone.datetime.strptime("16:00", "%H:%M").time(),
        )

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]

        self.assertTrue(workspace["is_ready"])
        self.assertEqual(workspace["ready_count"], 1)

    def test_foreign_salon_member_is_not_in_workspace(self):
        other_manager = self.make_salon_manager()
        other_salon = self.make_salon(manager=other_manager)
        foreign_stylist = self.make_stylist()

        other_salon.stylists.add(foreign_stylist)
        SalonMembership.objects.create(
            salon=other_salon,
            stylist=foreign_stylist,
            status=SalonMembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]

        self.assertEqual(workspace["members_count"], 0)
        self.assertNotContains(
            response,
            foreign_stylist.get_fullName(),
        )

    def test_inactive_membership_is_not_in_capacity_workspace(self):
        stylist = self.make_stylist()
        self.salon.stylists.add(stylist)

        SalonMembership.objects.create(
            salon=self.salon,
            stylist=stylist,
            status=SalonMembershipStatus.PAUSED,
        )

        response = self._get_page()

        workspace = response.context["team_capacity_setup"]

        self.assertEqual(workspace["members_count"], 0)
        self.assertNotContains(
            response,
            'data-team-capacity-setup',
        )

    def test_capacity_setup_is_not_rendered_on_work_schedule_page(self):
        with patch(
            "apps.dashboards.views._redirect_to_required_onboarding",
            return_value=None,
        ):
            response = self.client.get(
                reverse("dashboards:scheduled_shifts")
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-team-capacity-setup")
        self.assertNotIn("team_capacity_setup", response.context)

