from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Stylist
from apps.api.v1.public_views import _visible_stylists_for_salon
from apps.salons.models import (
    SalonMembership,
    SalonMembershipStatus,
)
from apps.stylists.profile_services import (
    can_show_stylist_on_salon_profile,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class PublicSalonMembershipQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

    def _make_public_stylist(self, index):
        stylist = self.make_stylist(
            user_kwargs={
                "mobile_number": f"091244410{index:02d}",
                "email": f"public-stylist-{index}@example.com",
                "name": "متخصص",
                "family": f"شماره {index}",
            },
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )
        self.salon.stylists.add(stylist)
        return stylist

    def test_prefetched_memberships_remove_per_stylist_queries(self):
        active_stylist = self._make_public_stylist(1)
        hidden_membership_stylist = self._make_public_stylist(2)
        paused_membership_stylist = self._make_public_stylist(3)
        legacy_stylist = self._make_public_stylist(4)

        SalonMembership.objects.create(
            salon=self.salon,
            stylist=active_stylist,
            status=SalonMembershipStatus.ACTIVE,
            show_on_salon_profile=True,
        )
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=hidden_membership_stylist,
            status=SalonMembershipStatus.ACTIVE,
            show_on_salon_profile=False,
        )
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=paused_membership_stylist,
            status=SalonMembershipStatus.PAUSED,
            show_on_salon_profile=True,
        )

        with self.assertNumQueries(2):
            stylists = list(_visible_stylists_for_salon(self.salon))

        by_id = {stylist.pk: stylist for stylist in stylists}

        with self.assertNumQueries(0):
            active_access = can_show_stylist_on_salon_profile(
                salon=self.salon,
                stylist=by_id[active_stylist.pk],
                legacy_membership_confirmed=True,
            )
            hidden_access = can_show_stylist_on_salon_profile(
                salon=self.salon,
                stylist=by_id[hidden_membership_stylist.pk],
                legacy_membership_confirmed=True,
            )
            paused_access = can_show_stylist_on_salon_profile(
                salon=self.salon,
                stylist=by_id[paused_membership_stylist.pk],
                legacy_membership_confirmed=True,
            )
            legacy_access = can_show_stylist_on_salon_profile(
                salon=self.salon,
                stylist=by_id[legacy_stylist.pk],
                legacy_membership_confirmed=True,
            )

        self.assertTrue(active_access.allowed)
        self.assertEqual(active_access.membership.salon_id, self.salon.pk)

        self.assertFalse(hidden_access.allowed)
        self.assertEqual(hidden_access.reason, "membership_hidden")

        self.assertFalse(paused_access.allowed)
        self.assertEqual(paused_access.reason, "membership_not_active")

        self.assertTrue(legacy_access.allowed)
        self.assertEqual(legacy_access.reason, "legacy_membership")

    def test_query_count_does_not_grow_with_more_stylists(self):
        for index in range(10, 20):
            self._make_public_stylist(index)

        with self.assertNumQueries(2):
            stylists = list(_visible_stylists_for_salon(self.salon))

        with self.assertNumQueries(0):
            results = [
                can_show_stylist_on_salon_profile(
                    salon=self.salon,
                    stylist=stylist,
                    legacy_membership_confirmed=True,
                )
                for stylist in stylists
            ]

        self.assertEqual(len(results), 10)
        self.assertTrue(all(result.allowed for result in results))

    def test_public_stylist_api_uses_fixed_three_query_budget(self):
        active_stylist = self._make_public_stylist(30)
        hidden_stylist = self._make_public_stylist(31)

        SalonMembership.objects.create(
            salon=self.salon,
            stylist=active_stylist,
            status=SalonMembershipStatus.ACTIVE,
            show_on_salon_profile=True,
        )
        SalonMembership.objects.create(
            salon=self.salon,
            stylist=hidden_stylist,
            status=SalonMembershipStatus.ACTIVE,
            show_on_salon_profile=False,
        )

        url = reverse(
            "api:v1:public_salon_stylists",
            kwargs={"salon_slug": self.salon.slug},
        )

        with self.assertNumQueries(3):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        stylist_ids = {item["id"] for item in response.json()["data"]}

        self.assertIn(active_stylist.pk, stylist_ids)
        self.assertNotIn(hidden_stylist.pk, stylist_ids)

    def test_unprepared_call_remains_backward_compatible(self):
        stylist = self._make_public_stylist(40)

        access = can_show_stylist_on_salon_profile(
            salon=self.salon,
            stylist=stylist,
        )

        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "legacy_membership")
