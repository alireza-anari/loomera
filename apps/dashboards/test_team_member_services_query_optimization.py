from django.test import TestCase

from apps.dashboards.views import (
    SalonMembershipStatus,
    TeamMemberView,
    _build_team_member_stylists_queryset,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class TeamMemberServicesQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )

        self.stylist = self.make_stylist()

        self.current_services = []

        for name in [
            "اصلاح ابرو",
            "پاک‌سازی پوست",
            "رنگ مو",
            "کوتاهی مو",
            "میکاپ",
        ]:
            service = self.make_service(name=name)
            self.connect_service(
                salon=self.salon,
                stylist=self.stylist,
                service=service,
            )
            self.current_services.append(service)

        outside_manager = self.make_salon_manager()
        self.outside_salon = self.make_salon(
            manager=outside_manager,
        )
        self.outside_service = self.make_service(
            name="خدمت سالن دیگر",
        )

        self.connect_service(
            salon=self.outside_salon,
            stylist=self.stylist,
            service=self.outside_service,
        )

    def _prepared_stylists(self):
        return list(_build_team_member_stylists_queryset(self.salon).order_by("pk"))

    def test_team_members_and_salon_services_use_two_queries(self):
        with self.assertNumQueries(2):
            stylists = self._prepared_stylists()

        self.assertEqual(
            [stylist.pk for stylist in stylists],
            [self.stylist.pk],
        )

        prepared_services = getattr(
            stylists[0],
            "_team_member_salon_services",
        )

        self.assertEqual(
            {service.pk for service in prepared_services},
            {service.pk for service in self.current_services},
        )
        self.assertNotIn(
            self.outside_service.pk,
            {service.pk for service in prepared_services},
        )

    def test_card_serialization_runs_no_queries(self):
        stylist = self._prepared_stylists()[0]
        stylist.membership_status_for_salon = SalonMembershipStatus.ACTIVE

        view = TeamMemberView()

        with self.assertNumQueries(0):
            card = view._serialize_stylist(
                stylist,
                self.salon,
            )

        self.assertEqual(
            card["services_count"],
            5,
        )
        self.assertEqual(
            len(card["service_names"]),
            3,
        )
        self.assertTrue(
            card["has_more_services"],
        )
        self.assertEqual(
            card["extra_services_count_label"],
            "۲",
        )
        self.assertNotIn(
            self.outside_service.service_name,
            card["service_names"],
        )

    def test_service_names_keep_existing_alphabetical_order(self):
        stylist = self._prepared_stylists()[0]
        stylist.membership_status_for_salon = SalonMembershipStatus.ACTIVE

        card = TeamMemberView()._serialize_stylist(
            stylist,
            self.salon,
        )

        expected_names = list(
            self.stylist.services_of_stylist.filter(
                pk__in=[service.pk for service in self.current_services],
                services_of_salon=self.salon,
            )
            .order_by(
                "service_name",
                "pk",
            )
            .values_list(
                "service_name",
                flat=True,
            )[:3]
        )

        self.assertEqual(
            card["service_names"],
            expected_names,
        )

    def test_query_count_does_not_grow_with_more_team_members(self):
        for index in range(15):
            stylist = self.make_stylist(
                user_kwargs={
                    "mobile_number": f"0912777{index:04d}",
                    "email": (f"team-query-{index}@example.com"),
                },
            )
            service = self.make_service(
                name=f"خدمت عضو {index}",
            )
            self.connect_service(
                salon=self.salon,
                stylist=stylist,
                service=service,
            )

        with self.assertNumQueries(2):
            stylists = self._prepared_stylists()

        for stylist in stylists:
            stylist.membership_status_for_salon = SalonMembershipStatus.ACTIVE

        view = TeamMemberView()

        with self.assertNumQueries(0):
            cards = [
                view._serialize_stylist(
                    stylist,
                    self.salon,
                )
                for stylist in stylists
            ]

        self.assertEqual(
            len(cards),
            16,
        )

    def test_unprepared_stylist_remains_backward_compatible(self):
        self.stylist.membership_status_for_salon = SalonMembershipStatus.ACTIVE

        card = TeamMemberView()._serialize_stylist(
            self.stylist,
            self.salon,
        )

        self.assertEqual(
            card["services_count"],
            5,
        )
        self.assertEqual(
            len(card["service_names"]),
            3,
        )
