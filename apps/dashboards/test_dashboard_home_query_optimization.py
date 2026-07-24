from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.home_components import (
    _build_manager_metrics,
    _build_stats,
    _build_workspace,
)
from apps.orders.models import OrderDetail
from tests_stage1_helpers import Stage1DomainFactoryMixin


class DashboardHomeQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.today = timezone.localdate()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

        self.stylist = self.make_stylist()
        self.service = self.make_service()
        self.connect_service(
            salon=self.salon,
            stylist=self.stylist,
            service=self.service,
        )

        inactive_stylist = self.make_stylist()
        inactive_stylist.is_active = False
        inactive_stylist.save(update_fields=["is_active"])
        self.salon.stylists.add(inactive_stylist)

        inactive_service = self.make_service(is_active=False)
        self.salon.services.add(inactive_service)

        first_customer = self.make_customer()
        second_customer = self.make_customer()

        today_order = self.make_order(
            customer=first_customer,
            salon=self.salon,
            is_paid=True,
            is_finally=True,
        )
        self.make_order_detail(
            order=today_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.today,
            start=time(9, 0),
            end=time(9, 30),
            price=100_000,
        )

        yesterday_order = self.make_order(
            customer=first_customer,
            salon=self.salon,
            is_paid=True,
            is_finally=True,
        )
        self.make_order_detail(
            order=yesterday_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.today - timedelta(days=1),
            start=time(10, 0),
            end=time(10, 30),
            price=200_000,
        )

        upcoming_order = self.make_order(
            customer=second_customer,
            salon=self.salon,
            is_paid=False,
            is_finally=False,
        )
        self.make_order_detail(
            order=upcoming_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.today + timedelta(days=1),
            start=time(11, 0),
            end=time(11, 30),
            price=300_000,
        )

    def test_manager_metrics_use_two_queries(self):
        base_qs = OrderDetail.objects.filter(salon=self.salon).select_related("order")

        with self.assertNumQueries(2):
            metrics = _build_manager_metrics(
                self.salon,
                base_qs,
                self.today,
            )

        self.assertEqual(metrics["sales_7d"], 300_000)
        self.assertEqual(metrics["appointments_today"], 1)
        self.assertEqual(metrics["upcoming_7d"], 2)
        self.assertEqual(metrics["unique_customers_30d"], 1)
        self.assertEqual(metrics["unpaid_count"], 1)
        self.assertEqual(metrics["active_team_members"], 1)
        self.assertEqual(metrics["active_services_count"], 1)

    def test_stats_and_workspace_do_not_run_queries(self):
        base_qs = OrderDetail.objects.filter(salon=self.salon)
        metrics = _build_manager_metrics(
            self.salon,
            base_qs,
            self.today,
        )

        with self.assertNumQueries(0):
            stats = _build_stats(metrics)
            workspace = _build_workspace(
                self.salon,
                metrics,
            )

        self.assertEqual(len(stats), 5)
        self.assertEqual(
            workspace["page_title"],
            f"خانه مدیریتی {self.salon.salon_name}",
        )
        self.assertEqual(len(workspace["badges"]), 5)

    def test_metrics_query_count_does_not_grow_with_more_orders(self):
        customer = self.make_customer()

        for offset in range(10):
            order = self.make_order(
                customer=customer,
                salon=self.salon,
                is_paid=offset % 2 == 0,
                is_finally=True,
            )
            self.make_order_detail(
                order=order,
                service=self.service,
                stylist=self.stylist,
                salon=self.salon,
                date_value=self.today + timedelta(days=offset % 3),
                start=time(12, 0),
                end=time(12, 30),
                price=50_000,
            )

        base_qs = OrderDetail.objects.filter(salon=self.salon)

        with self.assertNumQueries(2):
            metrics = _build_manager_metrics(
                self.salon,
                base_qs,
                self.today,
            )

        self.assertGreater(metrics["appointments_today"], 0)
