from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.views import (
    SalonsCustomersPageView,
    _build_customer_workspace_metrics,
    _build_salon_customers_queryset,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class CustomerWorkspaceQueryOptimizationTests(
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
        self.service = self.make_service()

        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

        self.recent_customer = self.make_customer()
        recent_order = self.make_order(
            customer=self.recent_customer,
            salon=self.salon,
            status="confirmed",
            is_finally=True,
        )
        self.make_order_detail(
            order=recent_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.today,
            start=time(9, 0),
            end=time(9, 30),
            price=300_000,
        )

        self.dormant_customer = self.make_customer()
        dormant_order = self.make_order(
            customer=self.dormant_customer,
            salon=self.salon,
            status="completed",
            is_finally=True,
        )
        self.make_order_detail(
            order=dormant_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.today - timedelta(days=100),
            start=time(10, 0),
            end=time(10, 30),
            price=200_000,
        )

        self.added_only_customer = self.make_customer(
            added_by_salon=self.salon,
        )

        # This customer belongs to another context and must not leak.
        self.outside_customer = self.make_customer()

    def _customers(self, *, query="", sort_by="recent"):
        return list(
            _build_salon_customers_queryset(
                salon=self.salon,
                query=query,
                sort_by=sort_by,
            )
        )

    def test_customer_queryset_uses_one_query(self):
        with self.assertNumQueries(1):
            customers = self._customers()

        self.assertEqual(
            {customer.pk for customer in customers},
            {
                self.recent_customer.pk,
                self.dormant_customer.pk,
                self.added_only_customer.pk,
            },
        )
        self.assertNotIn(
            self.outside_customer.pk,
            {
                customer.pk
                for customer in customers
            },
        )

    def test_workspace_metrics_run_no_queries(self):
        customers = self._customers()

        with self.assertNumQueries(0):
            metrics = _build_customer_workspace_metrics(
                customers,
                today=self.today,
            )

        self.assertEqual(metrics["total_customers"], 3)
        self.assertEqual(metrics["with_appointments"], 2)
        self.assertEqual(metrics["vip_customers"], 2)
        self.assertEqual(metrics["recent_customers"], 1)
        self.assertEqual(metrics["needs_follow_up"], 2)

    def test_card_serialization_runs_no_queries(self):
        customers = self._customers()
        view = SalonsCustomersPageView()

        with self.assertNumQueries(0):
            cards = [
                view._serialize_customer(
                    customer,
                    self.salon,
                    self.today,
                )
                for customer in customers
            ]

        self.assertEqual(len(cards), 3)

    def test_query_count_does_not_grow_with_more_customers(self):
        for index in range(20):
            self.make_customer(
                added_by_salon=self.salon,
                user_kwargs={
                    "mobile_number": f"0912888{index:04d}",
                    "email": f"workspace-{index}@example.com",
                },
            )

        with self.assertNumQueries(1):
            customers = self._customers()

        with self.assertNumQueries(0):
            metrics = _build_customer_workspace_metrics(
                customers,
                today=self.today,
            )

        self.assertEqual(
            metrics["total_customers"],
            23,
        )

    def test_search_and_sort_behavior_is_preserved(self):
        mobile = self.recent_customer.user.mobile_number

        with self.assertNumQueries(1):
            customers = self._customers(
                query=mobile,
                sort_by="top_spend",
            )

        self.assertEqual(
            [customer.pk for customer in customers],
            [self.recent_customer.pk],
        )