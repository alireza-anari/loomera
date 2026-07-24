from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.appointment_management import (
    TAB_DEFINITIONS,
    _apply_tab_filter,
    _build_appointment_summary_metrics,
    _build_appointment_tab_counts,
    _build_summary_cards,
)
from apps.orders.models import OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class AppointmentManagementMetricsQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.today = timezone.localdate()
        self.now = timezone.now()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )
        self.stylist = self.make_stylist()
        self.service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

        self.first_customer = self.make_customer()
        self.second_customer = self.make_customer()
        self.third_customer = self.make_customer()

        self._make_appointment(
            customer=self.first_customer,
            status="confirmed",
            is_paid=False,
            date_value=self.today,
            start=time(9, 0),
            price=100_000,
        )

        self._make_appointment(
            customer=self.second_customer,
            status="paid",
            is_paid=True,
            date_value=self.today + timedelta(days=1),
            start=time(10, 0),
            price=200_000,
            stylist_confirmed_at=self.now,
        )

        self._make_appointment(
            customer=self.first_customer,
            status="completed",
            is_paid=True,
            date_value=self.today - timedelta(days=1),
            start=time(11, 0),
            price=300_000,
            stylist_confirmed_at=self.now,
            customer_arrived_at=self.now,
            service_started_at=self.now,
            service_completed_at=self.now,
        )

        self._make_appointment(
            customer=self.third_customer,
            status="cancelled",
            is_paid=False,
            date_value=self.today,
            start=time(12, 0),
            price=400_000,
        )

        self._make_appointment(
            customer=self.third_customer,
            status="confirmed",
            is_paid=False,
            date_value=self.today,
            start=time(13, 0),
            price=500_000,
            stylist_confirmed_at=self.now,
            customer_arrived_at=self.now,
        )

        self._make_appointment(
            customer=self.second_customer,
            status="confirmed",
            is_paid=False,
            date_value=self.today,
            start=time(14, 0),
            price=600_000,
            stylist_confirmed_at=self.now,
            customer_arrived_at=self.now,
            service_started_at=self.now,
        )

        self._make_appointment(
            customer=self.first_customer,
            status="completed",
            is_paid=False,
            date_value=self.today,
            start=time(15, 0),
            price=700_000,
            stylist_confirmed_at=self.now,
            customer_arrived_at=self.now,
            service_started_at=self.now,
            service_completed_at=self.now,
        )

    def _make_appointment(
        self,
        *,
        customer,
        status,
        is_paid,
        date_value,
        start,
        price,
        **lifecycle,
    ):
        order = self.make_order(
            customer=customer,
            salon=self.salon,
            status=status,
            is_paid=is_paid,
            **lifecycle,
        )

        start_minutes = start.hour * 60 + start.minute
        end_minutes = start_minutes + 30

        end = time(
            end_minutes // 60,
            end_minutes % 60,
        )

        return self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=date_value,
            start=start,
            end=end,
            price=price,
        )

    def _base_qs(self):
        return OrderDetail.objects.filter(
            salon=self.salon,
            date__range=(
                self.today - timedelta(days=7),
                self.today + timedelta(days=7),
            ),
        )

    def test_tabs_and_summary_use_two_queries(self):
        filtered_base = self._base_qs()
        filtered_qs = _apply_tab_filter(
            filtered_base,
            "all",
            self.today,
        )

        with self.assertNumQueries(2):
            tab_counts = _build_appointment_tab_counts(
                filtered_base,
                self.today,
            )
            metrics = _build_appointment_summary_metrics(
                filtered_qs,
                self.today,
            )

        self.assertEqual(
            tab_counts["all"],
            7,
        )
        self.assertEqual(
            metrics["rows_count"],
            7,
        )
        self.assertEqual(
            metrics["total_value"],
            2_800_000,
        )

    def test_tab_aggregate_matches_existing_tab_filters(self):
        filtered_base = self._base_qs()

        expected = {
            tab_key: _apply_tab_filter(
                filtered_base,
                tab_key,
                self.today,
            ).count()
            for tab_key, _label in TAB_DEFINITIONS
        }

        with self.assertNumQueries(1):
            actual = _build_appointment_tab_counts(
                filtered_base,
                self.today,
            )

        self.assertEqual(actual, expected)

    def test_summary_metrics_preserve_current_semantics(self):
        metrics = _build_appointment_summary_metrics(
            self._base_qs(),
            self.today,
        )

        self.assertEqual(metrics["rows_count"], 7)
        self.assertEqual(metrics["unpaid_count"], 4)
        self.assertEqual(metrics["paid_count"], 2)
        self.assertEqual(metrics["cancelled_count"], 1)
        self.assertEqual(metrics["completed_count"], 2)
        self.assertEqual(metrics["awaiting_confirm_count"], 1)
        self.assertEqual(metrics["arrived_count"], 1)
        self.assertEqual(metrics["in_service_count"], 1)
        self.assertEqual(
            metrics["pay_in_salon_pending_count"],
            1,
        )
        self.assertEqual(metrics["upcoming_count"], 4)
        self.assertEqual(
            metrics["unique_customers_count"],
            3,
        )
        self.assertEqual(
            metrics["unique_team_count"],
            1,
        )

    def test_summary_cards_run_no_queries(self):
        metrics = _build_appointment_summary_metrics(
            self._base_qs(),
            self.today,
        )

        with self.assertNumQueries(0):
            cards = _build_summary_cards(metrics)

        self.assertEqual(len(cards), 6)

    def test_query_count_does_not_grow_with_more_appointments(self):
        for index in range(20):
            customer = self.make_customer()
            self._make_appointment(
                customer=customer,
                status="confirmed",
                is_paid=False,
                date_value=self.today,
                start=time(
                    8 + (index // 4),
                    (index % 4) * 15,
                ),
                price=50_000,
            )

        filtered_base = self._base_qs()

        with self.assertNumQueries(2):
            tab_counts = _build_appointment_tab_counts(
                filtered_base,
                self.today,
            )
            metrics = _build_appointment_summary_metrics(
                filtered_base,
                self.today,
            )

        self.assertEqual(tab_counts["all"], 27)
        self.assertEqual(metrics["rows_count"], 27)

    def test_other_salon_data_does_not_enter_metrics(self):
        outside_manager = self.make_salon_manager()
        outside_salon = self.make_salon(
            manager=outside_manager,
        )
        outside_customer = self.make_customer()

        outside_order = self.make_order(
            customer=outside_customer,
            salon=outside_salon,
            status="completed",
            is_paid=True,
        )
        self.make_order_detail(
            order=outside_order,
            service=self.service,
            stylist=self.stylist,
            salon=outside_salon,
            date_value=self.today,
            start=time(16, 0),
            end=time(16, 30),
            price=9_000_000,
        )

        metrics = _build_appointment_summary_metrics(
            self._base_qs(),
            self.today,
        )

        self.assertEqual(metrics["rows_count"], 7)
        self.assertEqual(
            metrics["total_value"],
            2_800_000,
        )
