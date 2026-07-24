from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.salons.models import SalonMembership, SalonMembershipStatus
from tests_stage1_helpers import Stage1DomainFactoryMixin


class TeamMemberSetupHandoffUxTests(
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

    def _get_team_page(self, params=None):
        with patch(
            "apps.dashboards.views._redirect_to_required_onboarding",
            return_value=None,
        ):
            return self.client.get(
                reverse("dashboards:team_member"),
                params or {},
            )

    def test_member_without_service_shows_service_assignment_handoff(self):
        stylist = self._activate_member(self.make_stylist())

        response = self._get_team_page(
            {"created_stylist": str(stylist.user_id)}
        )

        self.assertEqual(response.status_code, 200)

        handoff = response.context["stylist_setup_handoff"]
        self.assertIsNotNone(handoff)
        self.assertEqual(handoff["status_tone"], "warning")
        self.assertEqual(
            handoff["primary_url"],
            reverse(
                "dashboards:edit_stylist",
                kwargs={"stylist_id": stylist.user_id},
            ),
        )
        self.assertContains(response, "اتصال خدمات عضو")
        self.assertContains(response, "data-stylist-setup-handoff")

    def test_hidden_member_shows_visibility_handoff_before_services(self):
        stylist = self._activate_member(
            self.make_stylist(
                public_visibility=Stylist.PublicVisibility.HIDDEN,
            )
        )
        service = self.make_service()
        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )

        response = self._get_team_page(
            {"created_stylist": str(stylist.user_id)}
        )

        handoff = response.context["stylist_setup_handoff"]

        self.assertEqual(handoff["status_tone"], "warning")
        self.assertContains(response, "وضعیت نمایش")
        self.assertContains(response, "پروفایل عمومی غیرفعال")

    def test_member_with_service_but_without_schedule_shows_schedule_handoff(self):
        stylist = self._activate_member(self.make_stylist())
        service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=stylist,
            service=service,
        )

        response = self._get_team_page(
            {"created_stylist": str(stylist.user_id)}
        )

        handoff = response.context["stylist_setup_handoff"]

        self.assertEqual(handoff["status_tone"], "primary")
        self.assertEqual(
            handoff["primary_url"],
            reverse("dashboards:scheduled_shifts"),
        )
        self.assertContains(response, "تنظیم برنامه کاری")

    def test_past_schedule_does_not_complete_member_setup(self):
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

        response = self._get_team_page(
            {"created_stylist": str(stylist.user_id)}
        )

        handoff = response.context["stylist_setup_handoff"]

        self.assertEqual(handoff["status_tone"], "primary")
        self.assertContains(response, "منتظر برنامه کاری")

    def test_member_with_service_and_future_schedule_is_ready(self):
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
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:00", "%H:%M").time(),
        )

        response = self._get_team_page(
            {"created_stylist": str(stylist.user_id)}
        )

        handoff = response.context["stylist_setup_handoff"]

        self.assertEqual(handoff["status_tone"], "success")
        self.assertEqual(
            handoff["primary_url"],
            reverse(
                "dashboards:stylist_overview",
                kwargs={"stylist_id": stylist.user_id},
            ),
        )
        self.assertContains(response, "آماده رزرو")

    def test_foreign_salon_member_is_not_exposed(self):
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

        response = self._get_team_page(
            {"created_stylist": str(foreign_stylist.user_id)}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["stylist_setup_handoff"])
        self.assertNotContains(response, foreign_stylist.get_fullName())

    def test_invalid_created_stylist_value_is_ignored(self):
        response = self._get_team_page(
            {"created_stylist": "not-a-number"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["stylist_setup_handoff"])
        self.assertNotContains(response, "data-stylist-setup-handoff")

    def test_add_stylist_success_redirects_to_scoped_handoff(self):
        stylist = self._activate_member(self.make_stylist())
        membership = SalonMembership.objects.get(
            salon=self.salon,
            stylist=stylist,
        )

        class FakeForm:
            def __init__(self, cleaned_data=None, saved_object=None):
                self.cleaned_data = cleaned_data or {}
                self.saved_object = saved_object

            def is_valid(self):
                return True

            def save(self, *args, **kwargs):
                return self.saved_object

        emergency = SimpleNamespace(
            stylist=None,
            full_name="",
            emergency_contact="",
            relationship="",
            save=lambda: None,
        )

        user_form = FakeForm(
            {
                "name": "عضو",
                "family": "جدید",
                "mobile_number": "09120000000",
                "email": "",
            }
        )
        profile_form = FakeForm({})
        job_form = FakeForm({})
        emergency_form = FakeForm(
            {
                "emergency_contact_name": "",
                "emergency_contact_family": "",
                "emergency_phone_prefix": "",
                "emergency_phone": "",
                "relationship": "",
            },
            emergency,
        )

        with (
            patch(
                "apps.dashboards.views._redirect_to_required_onboarding",
                return_value=None,
            ),
            patch(
                "apps.dashboards.views.StylistUserForm",
                return_value=user_form,
            ),
            patch(
                "apps.dashboards.views.StylistProfileForm",
                return_value=profile_form,
            ),
            patch(
                "apps.dashboards.views.JobDetailsForm",
                return_value=job_form,
            ),
            patch(
                "apps.dashboards.views.EmergencyInfoForm",
                return_value=emergency_form,
            ),
            patch(
                "apps.dashboards.views.invite_or_attach_stylist",
                return_value=(stylist, membership, False),
            ),
            patch(
                "apps.dashboards.views._ensure_active_staff_membership_for_salon",
                return_value=membership,
            ),
        ):
            response = self.client.post(
                reverse("dashboards:add_stylist"),
                data={},
            )

        expected_url = (
            f"{reverse('dashboards:team_member')}"
            f"?created_stylist={stylist.user_id}"
        )
        self.assertRedirects(
            response,
            expected_url,
            fetch_redirect_response=False,
        )