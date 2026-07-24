from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.reports_components import (
    _build_chart,
    _build_overview_rows,
    _build_table,
    _currency,
    _customer_ids_by_date,
    _daily_rollup,
    _iter_periods,
    _percent,
)
from apps.dashboards.jalali_utils import to_persian_digits
from apps.orders.models import OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class ReportsOverviewRollupQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.today = timezone.localdate()
        self.start_date = self.today - timedelta(days=6)
        self.end_date = self.today

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

        first_order = self.make_order(
            customer=self.first_customer,
            salon=self.salon,
            status="confirmed",
            is_finally=True,
        )
        self.make_order_detail(
            order=first_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.start_date,
            start=time(9, 0),
            end=time(9, 30),
            price=100_000,
        )

        # Same customer on another day. Weekly unique customers must not
        # count this customer twice.
        second_order = self.make_order(
            customer=self.first_customer,
            salon=self.salon,
            status="completed",
            is_finally=True,
        )
        self.make_order_detail(
            order=second_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.start_date + timedelta(days=1),
            start=time(10, 0),
            end=time(10, 30),
            price=200_000,
        )

        cancelled_order = self.make_order(
            customer=self.second_customer,
            salon=self.salon,
            status="cancelled",
            is_finally=True,
        )
        self.make_order_detail(
            order=cancelled_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.start_date + timedelta(days=1),
            start=time(11, 0),
            end=time(11, 30),
            price=300_000,
        )

    def _filtered_qs(self):
        return OrderDetail.objects.filter(
            salon=self.salon,
            date__range=(
                self.start_date,
                self.end_date,
            ),
        )

    def test_overview_rows_use_two_queries_regardless_of_period_count(
        self,
    ):
        filtered_qs = self._filtered_qs()

        with self.assertNumQueries(2):
            rows = _build_overview_rows(
                filtered_qs,
                self.start_date,
                self.end_date,
                "day",
            )

        self.assertEqual(len(rows), 7)

    def test_prepared_rollup_builds_chart_and_table_without_queries(
        self,
    ):
        filtered_qs = self._filtered_qs()

        with self.assertNumQueries(2):
            daily = _daily_rollup(filtered_qs)
            customers_by_date = _customer_ids_by_date(filtered_qs)

        periods = _iter_periods(
            self.start_date,
            self.end_date,
            "week",
        )

        with self.assertNumQueries(0):
            chart = _build_chart(
                filtered_qs,
                self.start_date,
                self.end_date,
                "week",
                daily=daily,
                periods=periods,
            )
            table = _build_table(
                filtered_qs,
                tab="overview",
                start_date=self.start_date,
                end_date=self.end_date,
                group_by="week",
                daily=daily,
                customers_by_date=customers_by_date,
                periods=periods,
            )

        self.assertEqual(len(chart["bars"]), 1)
        self.assertEqual(len(table["rows"]), 1)

    def test_weekly_values_preserve_existing_report_semantics(self):
        filtered_qs = self._filtered_qs()

        daily = _daily_rollup(filtered_qs)
        customers_by_date = _customer_ids_by_date(filtered_qs)
        periods = _iter_periods(
            self.start_date,
            self.end_date,
            "week",
        )

        with self.assertNumQueries(0):
            rows = _build_overview_rows(
                filtered_qs,
                self.start_date,
                self.end_date,
                "week",
                daily=daily,
                customers_by_date=customers_by_date,
                periods=periods,
            )

        row = rows[0]

        self.assertEqual(
            row["appointments_label"],
            to_persian_digits(3),
        )
        self.assertEqual(
            row["customers_label"],
            to_persian_digits(2),
        )
        self.assertEqual(
            row["revenue_label"],
            _currency(300_000),
        )
        self.assertEqual(
            row["completion_label"],
            _percent(100 / 3),
        )

    def test_query_count_does_not_grow_for_long_daily_range(self):
        long_start = self.today - timedelta(days=89)
        customer = self.make_customer()

        for offset in range(60):
            order = self.make_order(
                customer=customer,
                salon=self.salon,
                status=("completed" if offset % 2 else "confirmed"),
                is_finally=True,
            )
            self.make_order_detail(
                order=order,
                service=self.service,
                stylist=self.stylist,
                salon=self.salon,
                date_value=long_start + timedelta(days=offset),
                start=time(12, 0),
                end=time(12, 30),
                price=50_000,
            )

        filtered_qs = OrderDetail.objects.filter(
            salon=self.salon,
            date__range=(
                long_start,
                self.today,
            ),
        )

        with self.assertNumQueries(2):
            rows = _build_overview_rows(
                filtered_qs,
                long_start,
                self.today,
                "day",
            )

        self.assertEqual(len(rows), 90)

    def test_other_salon_data_does_not_enter_rollup(self):
        outside_manager = self.make_salon_manager()
        outside_salon = self.make_salon(
            manager=outside_manager,
        )
        outside_customer = self.make_customer()

        outside_order = self.make_order(
            customer=outside_customer,
            salon=outside_salon,
            status="completed",
            is_finally=True,
        )
        self.make_order_detail(
            order=outside_order,
            service=self.service,
            stylist=self.stylist,
            salon=outside_salon,
            date_value=self.start_date,
            start=time(14, 0),
            end=time(14, 30),
            price=900_000,
        )

        filtered_qs = self._filtered_qs()

        rows = _build_overview_rows(
            filtered_qs,
            self.start_date,
            self.end_date,
            "week",
        )

        self.assertEqual(
            rows[0]["appointments_label"],
            to_persian_digits(3),
        )
        self.assertEqual(
            rows[0]["revenue_label"],
            _currency(300_000),
        )
