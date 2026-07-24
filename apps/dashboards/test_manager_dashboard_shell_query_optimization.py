from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.dashboards.jalali_utils import (
    to_persian_digits,
)
from apps.dashboards.layout import (
    _build_manager_shell_snapshot,
    _build_page_meta,
    _build_shell_metrics,
)
from apps.orders.models import OrderDetail
from apps.salons.models import Salon
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class ManagerDashboardShellQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.today = timezone.localdate()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )

        self.active_stylist = self.make_stylist()
        self.active_service = self.make_service(
            is_active=True,
        )

        self.connect_service(
            salon=self.salon,
            stylist=self.active_stylist,
            service=self.active_service,
        )

        self.inactive_stylist = self.make_stylist()
        self.inactive_stylist.is_active = False
        self.inactive_stylist.save(update_fields=["is_active"])
        self.salon.stylists.add(self.inactive_stylist)

        self.inactive_service = self.make_service(
            is_active=False,
        )
        self.salon.services.add(self.inactive_service)

        customer = self.make_customer()

        self._make_appointment(
            customer=customer,
            status="pending",
            is_paid=False,
            date_value=self.today,
            start=time(9, 0),
            price=100_000,
        )

        self._make_appointment(
            customer=customer,
            status="cancelled",
            is_paid=False,
            date_value=self.today,
            start=time(10, 0),
            price=200_000,
        )

        self._make_appointment(
            customer=customer,
            status="paid",
            is_paid=True,
            date_value=(self.today + timedelta(days=1)),
            start=time(11, 0),
            price=300_000,
        )

        self._make_appointment(
            customer=customer,
            status="completed",
            is_paid=True,
            date_value=(self.today - timedelta(days=1)),
            start=time(12, 0),
            price=400_000,
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
    ):
        order = self.make_order(
            customer=customer,
            salon=self.salon,
            status=status,
            is_paid=is_paid,
            is_finally=True,
        )

        start_minutes = start.hour * 60 + start.minute
        end_minutes = start_minutes + 30

        return self.make_order_detail(
            order=order,
            service=self.active_service,
            stylist=self.active_stylist,
            salon=self.salon,
            date_value=date_value,
            start=start,
            end=time(
                end_minutes // 60,
                end_minutes % 60,
            ),
            price=price,
        )

    def test_manager_snapshot_uses_two_queries(self):
        with self.assertNumQueries(2):
            snapshot = _build_manager_shell_snapshot(
                self.salon,
                today=self.today,
            )

        self.assertEqual(
            snapshot["pending_approvals"],
            1,
        )
        self.assertEqual(
            snapshot["today_count"],
            1,
        )
        self.assertEqual(
            snapshot["upcoming_count"],
            2,
        )
        self.assertEqual(
            snapshot["unpaid_count"],
            1,
        )
        self.assertEqual(
            snapshot["active_services_count"],
            1,
        )
        self.assertEqual(
            snapshot["active_team_count"],
            1,
        )

    def test_snapshot_matches_previous_query_semantics(self):
        base_qs = OrderDetail.objects.filter(
            salon=self.salon,
        )
        upcoming_end = self.today + timedelta(days=6)

        expected = {
            "pending_approvals": (
                base_qs.filter(
                    order__status="pending",
                ).count()
            ),
            "today_count": (
                base_qs.filter(
                    date=self.today,
                )
                .exclude(
                    order__status="cancelled",
                )
                .count()
            ),
            "upcoming_count": (
                base_qs.filter(
                    date__range=(
                        self.today,
                        upcoming_end,
                    )
                )
                .exclude(
                    order__status="cancelled",
                )
                .count()
            ),
            "unpaid_count": (
                base_qs.filter(
                    order__is_paid=False,
                )
                .exclude(
                    order__status="cancelled",
                )
                .count()
            ),
            "active_services_count": (
                self.salon.services.filter(
                    is_active=True,
                ).count()
            ),
            "active_team_count": (
                self.salon.stylists.filter(
                    is_active=True,
                ).count()
            ),
        }

        snapshot = _build_manager_shell_snapshot(
            self.salon,
            today=self.today,
        )

        self.assertEqual(
            snapshot,
            expected,
        )

    def test_shell_cards_use_no_queries_with_snapshot(self):
        snapshot = _build_manager_shell_snapshot(
            self.salon,
            today=self.today,
        )

        with self.assertNumQueries(0):
            cards = _build_shell_metrics(
                self.salon,
                role="manager",
                manager_snapshot=snapshot,
            )

        self.assertEqual(len(cards), 4)
        self.assertEqual(
            cards[0]["value"],
            to_persian_digits(1),
        )
        self.assertEqual(
            cards[2]["value"],
            to_persian_digits(1),
        )

    def test_page_meta_uses_no_team_query_with_snapshot(self):
        prepared_salon = Salon.objects.prefetch_related(
            "opening_hours",
        ).get(pk=self.salon.pk)

        snapshot = _build_manager_shell_snapshot(
            prepared_salon,
            today=self.today,
        )

        with self.assertNumQueries(0):
            page_meta = _build_page_meta(
                "overview",
                prepared_salon,
                role="manager",
                manager_snapshot=snapshot,
            )

        self.assertIn(
            (f"{to_persian_digits(1)} " "عضو فعال تیم"),
            {badge["label"] for badge in page_meta["badges"]},
        )

    def test_query_count_does_not_grow_with_more_data(self):
        for index in range(20):
            stylist = self.make_stylist()
            service = self.make_service(
                is_active=True,
            )
            self.connect_service(
                salon=self.salon,
                stylist=stylist,
                service=service,
            )

            customer = self.make_customer()
            self._make_appointment(
                customer=customer,
                status="confirmed",
                is_paid=False,
                date_value=self.today,
                start=time(
                    13 + (index // 4),
                    (index % 4) * 15,
                ),
                price=50_000,
            )

        with self.assertNumQueries(2):
            snapshot = _build_manager_shell_snapshot(
                self.salon,
                today=self.today,
            )

        self.assertEqual(
            snapshot["active_team_count"],
            21,
        )
        self.assertEqual(
            snapshot["active_services_count"],
            21,
        )
        self.assertEqual(
            snapshot["today_count"],
            21,
        )
