from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.views import (
    _apply_service_menu_booking_state,
    _build_service_menu_queryset,
    _build_service_menu_workspace_stats,
    _service_future_active_booking_qs,
    _service_has_booking_history,
)
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class ServiceMenuQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.today = timezone.localdate()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )

        self.stylist = self.make_stylist()

        self.future_service = self.make_service(
            name="خدمت دارای رزرو آینده",
            duration_minutes=30,
        )
        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.future_service,
            price=150_000,
        )

        self.history_service = self.make_service(
            name="خدمت دارای سابقه",
            duration_minutes=60,
        )
        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.history_service,
            price=200_000,
        )

        self.unassigned_service = self.make_service(
            name="خدمت بدون متخصص",
            duration_minutes=45,
        )
        self.salon.services.add(self.unassigned_service)

        self.archived_service = self.make_service(
            name="خدمت آرشیوشده",
            duration_minutes=15,
            is_active=False,
        )
        self.salon.services.add(self.archived_service)

        customer = self.make_customer()

        future_order = self.make_order(
            customer=customer,
            salon=self.salon,
            status="confirmed",
            is_finally=True,
        )
        self.make_order_detail(
            order=future_order,
            service=self.future_service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=(self.today + timedelta(days=2)),
            start=time(9, 0),
            end=time(9, 30),
            price=150_000,
        )

        past_order = self.make_order(
            customer=customer,
            salon=self.salon,
            status="completed",
            is_finally=True,
        )
        self.make_order_detail(
            order=past_order,
            service=self.history_service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=(self.today - timedelta(days=10)),
            start=time(10, 0),
            end=time(11, 0),
            price=200_000,
        )

        cancelled_order = self.make_order(
            customer=customer,
            salon=self.salon,
            status="cancelled",
            is_finally=True,
        )
        self.make_order_detail(
            order=cancelled_order,
            service=self.history_service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=(self.today + timedelta(days=3)),
            start=time(11, 0),
            end=time(12, 0),
            price=200_000,
        )

        outside_manager = self.make_salon_manager()
        self.outside_salon = self.make_salon(
            manager=outside_manager,
        )
        self.outside_salon.services.add(self.future_service)
        self.outside_salon.stylists.add(self.stylist)

        outside_customer = self.make_customer()
        outside_order = self.make_order(
            customer=outside_customer,
            salon=self.outside_salon,
            status="confirmed",
            is_finally=True,
        )
        self.make_order_detail(
            order=outside_order,
            service=self.future_service,
            stylist=self.stylist,
            salon=self.outside_salon,
            date_value=(self.today + timedelta(days=1)),
            start=time(13, 0),
            end=time(13, 30),
            price=900_000,
        )

    def _services(self):
        return list(
            _build_service_menu_queryset(
                salon=self.salon,
                today=self.today,
            )
        )

    def test_service_menu_data_uses_three_queries(self):
        with self.assertNumQueries(3):
            services = self._services()

        self.assertEqual(
            len(services),
            4,
        )

    def test_booking_annotations_match_existing_semantics(self):
        services = self._services()
        by_id = {service.pk: service for service in services}

        for service in services:
            expected_future_count = _service_future_active_booking_qs(
                salon=self.salon,
                service=service,
            ).count()
            expected_history = _service_has_booking_history(
                salon=self.salon,
                service=service,
            )

            self.assertEqual(
                int(service.future_active_booking_count or 0),
                expected_future_count,
            )
            self.assertEqual(
                bool(service.booking_history_exists),
                expected_history,
            )

        # Booking from another salon must not inflate this salon.
        self.assertEqual(
            by_id[self.future_service.pk].future_active_booking_count,
            1,
        )

    def test_cards_and_workspace_stats_run_no_queries(self):
        services = self._services()

        with self.assertNumQueries(0):
            for service in services:
                _apply_service_menu_booking_state(service)

                # Relations used by the existing card loop are prepared.
                list(service.service_group.all())

                [
                    member.get_fullName()
                    for member in getattr(
                        service,
                        "dashboard_active_stylists",
                        [],
                    )
                ]

            stats = _build_service_menu_workspace_stats(services)

        self.assertEqual(
            stats["avg_duration"],
            37,
        )
        self.assertEqual(
            stats["priced_count"],
            2,
        )
        self.assertEqual(
            stats["active_count"],
            3,
        )
        self.assertEqual(
            stats["archived_count"],
            1,
        )
        self.assertEqual(
            stats["unassigned_count"],
            2,
        )

    def test_query_count_does_not_grow_with_more_services(self):
        for index in range(20):
            service = self.make_service(
                name=f"خدمت اضافه {index}",
                duration_minutes=30,
            )
            self.salon.services.add(service)

            if index % 2 == 0:
                self.connect_service(
                    salon=self.salon,
                    stylist=self.stylist,
                    service=service,
                    price=100_000 + index,
                )

        with self.assertNumQueries(3):
            services = self._services()

        with self.assertNumQueries(0):
            for service in services:
                _apply_service_menu_booking_state(service)

            stats = _build_service_menu_workspace_stats(services)

        self.assertEqual(
            len(services),
            24,
        )
        self.assertEqual(
            stats["active_count"],
            23,
        )

    def test_booking_state_fields_are_preserved(self):
        services = self._services()
        by_id = {service.pk: service for service in services}

        with self.assertNumQueries(0):
            future_service = _apply_service_menu_booking_state(
                by_id[self.future_service.pk]
            )
            history_service = _apply_service_menu_booking_state(
                by_id[self.history_service.pk]
            )
            empty_service = _apply_service_menu_booking_state(
                by_id[self.unassigned_service.pk]
            )

        self.assertTrue(future_service.has_future_active_bookings)
        self.assertTrue(future_service.has_booking_history)

        self.assertFalse(history_service.has_future_active_bookings)
        self.assertTrue(history_service.has_booking_history)

        self.assertFalse(empty_service.has_future_active_bookings)
        self.assertFalse(empty_service.has_booking_history)
