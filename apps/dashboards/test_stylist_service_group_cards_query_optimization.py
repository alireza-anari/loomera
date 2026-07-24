from django.test import TestCase

from apps.dashboards.views import (
    AddStylistView,
    EditStylistView,
    _build_salon_service_group_cards,
)
from apps.services.models import GroupServices
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class StylistServiceGroupCardsQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )

        outside_manager = self.make_salon_manager()
        self.outside_salon = self.make_salon(
            manager=outside_manager,
        )

        self.first_service = self.make_service(
            name="Service A",
        )
        self.first_group = self.first_service.service_group.get()
        self.first_group.group_title = "Group A"
        self.first_group.save(update_fields=["group_title"])
        self.salon.services.add(self.first_service)

        self.second_service = self.make_service(
            name="Service B",
        )
        self.second_service.service_group.clear()
        self.second_service.service_group.add(self.first_group)
        self.salon.services.add(self.second_service)

        self.inactive_service = self.make_service(
            name="Service C",
            is_active=False,
        )
        self.second_group = self.inactive_service.service_group.get()
        self.second_group.group_title = "Group B"
        self.second_group.save(update_fields=["group_title"])
        self.salon.services.add(self.inactive_service)

        # This service shares Group A but belongs only to another salon.
        self.outside_service = self.make_service(
            name="Outside Service",
        )
        self.outside_service.service_group.clear()
        self.outside_service.service_group.add(self.first_group)
        self.outside_salon.services.add(self.outside_service)

        # A group without services in the current salon must not appear.
        self.unused_group = GroupServices.objects.create(
            group_title="Unused Group",
        )

    def _cards(self):
        return _build_salon_service_group_cards(
            salon=self.salon,
        )

    def test_groups_and_services_use_two_queries(self):
        with self.assertNumQueries(2):
            cards = self._cards()

        self.assertEqual(
            [card["id"] for card in cards],
            [
                self.first_group.pk,
                self.second_group.pk,
            ],
        )

    def test_prepared_cards_run_no_additional_queries(self):
        cards = self._cards()

        with self.assertNumQueries(0):
            payload = [
                {
                    "group_id": card["id"],
                    "title": card["title"],
                    "service_ids": [service.pk for service in card["services"]],
                    "service_names": [
                        service.service_name for service in card["services"]
                    ],
                    "count": card["services_count_label"],
                }
                for card in cards
            ]

        self.assertEqual(len(payload), 2)

    def test_services_are_scoped_to_current_salon(self):
        cards = self._cards()

        services_by_group = {
            card["id"]: {service.pk for service in card["services"]} for card in cards
        }

        self.assertEqual(
            services_by_group[self.first_group.pk],
            {
                self.first_service.pk,
                self.second_service.pk,
            },
        )
        self.assertNotIn(
            self.outside_service.pk,
            services_by_group[self.first_group.pk],
        )

        # Existing behavior includes inactive salon services.
        self.assertIn(
            self.inactive_service.pk,
            services_by_group[self.second_group.pk],
        )

        self.assertNotIn(
            self.unused_group.pk,
            services_by_group,
        )

    def test_service_order_matches_existing_database_order(self):
        cards = self._cards()
        first_group_card = next(
            card for card in cards if card["id"] == self.first_group.pk
        )

        expected_names = list(
            self.first_group.services_of_group.filter(
                services_of_salon=self.salon,
            )
            .distinct()
            .order_by(
                "service_name",
                "pk",
            )
            .values_list(
                "service_name",
                flat=True,
            )
        )

        self.assertEqual(
            [service.service_name for service in first_group_card["services"]],
            expected_names,
        )

    def test_query_count_does_not_grow_with_more_groups(self):
        for index in range(20):
            service = self.make_service(
                name=f"Additional Service {index:02d}",
            )
            group = service.service_group.get()
            group.group_title = f"Additional Group {index:02d}"
            group.save(update_fields=["group_title"])
            self.salon.services.add(service)

        with self.assertNumQueries(2):
            cards = self._cards()

        with self.assertNumQueries(0):
            service_count = sum(len(card["services"]) for card in cards)

        self.assertEqual(
            len(cards),
            22,
        )
        self.assertEqual(
            service_count,
            23,
        )

    def test_add_and_edit_views_use_shared_builder(self):
        with self.assertNumQueries(2):
            add_cards = AddStylistView()._get_service_group_cards(self.salon)

        with self.assertNumQueries(2):
            edit_cards = EditStylistView()._get_service_group_cards(self.salon)

        self.assertEqual(
            [
                (
                    card["id"],
                    [service.pk for service in card["services"]],
                )
                for card in add_cards
            ],
            [
                (
                    card["id"],
                    [service.pk for service in card["services"]],
                )
                for card in edit_cards
            ],
        )
