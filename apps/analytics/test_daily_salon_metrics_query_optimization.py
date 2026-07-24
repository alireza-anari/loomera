from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import DailySalonMetric
from apps.analytics.services import (
    _collect_daily_salon_metric_payloads,
    build_daily_salon_metrics,
)
from apps.comments_scores_favories.models import (
    Comments,
    Scoring,
)
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
)
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class DailySalonMetricsQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.day = timezone.localdate()
        self.now = timezone.now()

        self.manager_a = self.make_salon_manager()
        self.salon_a = self.make_salon(
            manager=self.manager_a,
        )
        self.stylist_a = self.make_stylist()
        self.service_a = self.make_service()

        self.connect_service(
            salon=self.salon_a,
            stylist=self.stylist_a,
            service=self.service_a,
        )

        self.manager_b = self.make_salon_manager()
        self.salon_b = self.make_salon(
            manager=self.manager_b,
        )
        self.stylist_b = self.make_stylist()
        self.service_b = self.make_service()

        self.connect_service(
            salon=self.salon_b,
            stylist=self.stylist_b,
            service=self.service_b,
        )

        self.recurring_customer = self.make_customer()
        self.new_customer = self.make_customer()
        self.salon_b_customer = self.make_customer()

        prior_order = self.make_order(
            customer=self.recurring_customer,
            salon=self.salon_a,
            status="completed",
            is_paid=True,
        )
        self.make_order_detail(
            order=prior_order,
            service=self.service_a,
            stylist=self.stylist_a,
            salon=self.salon_a,
            date_value=(self.day - timedelta(days=10)),
            start=time(8, 0),
            end=time(8, 30),
            price=50_000,
            lifecycle_status="completed",
        )

        first_detail = self._make_today_detail(
            salon=self.salon_a,
            stylist=self.stylist_a,
            service=self.service_a,
            customer=self.recurring_customer,
            status="completed",
            start=time(9, 0),
            price=100_000,
            lifecycle_status="completed",
            client_late_recorded_at=self.now,
            service_overrun_recorded_at=self.now,
        )
        self._make_snapshot(
            first_detail,
            gross=100_000,
            paid=90_000,
            commission=10_000,
            salon_profit=50_000,
            staff_share=35_000,
            material_cost=5_000,
        )

        second_detail = self._make_today_detail(
            salon=self.salon_a,
            stylist=self.stylist_a,
            service=self.service_a,
            customer=self.new_customer,
            status="confirmed",
            start=time(10, 0),
            price=200_000,
            lifecycle_status=("no_show_pending_review"),
        )
        self._make_snapshot(
            second_detail,
            gross=200_000,
            paid=180_000,
            commission=20_000,
            salon_profit=100_000,
            staff_share=60_000,
            material_cost=20_000,
        )

        self._make_today_detail(
            salon=self.salon_a,
            stylist=self.stylist_a,
            service=self.service_a,
            customer=self.new_customer,
            status="cancelled",
            start=time(11, 0),
            price=300_000,
        )

        salon_b_detail = self._make_today_detail(
            salon=self.salon_b,
            stylist=self.stylist_b,
            service=self.service_b,
            customer=self.salon_b_customer,
            status="completed",
            start=time(12, 0),
            price=400_000,
            lifecycle_status="completed",
        )
        self._make_snapshot(
            salon_b_detail,
            gross=400_000,
            paid=400_000,
            commission=40_000,
            salon_profit=220_000,
            staff_share=120_000,
            material_cost=20_000,
        )

        self._create_reviews_and_scores()

    def _make_today_detail(
        self,
        *,
        salon,
        stylist,
        service,
        customer,
        status,
        start,
        price,
        **detail_kwargs,
    ):
        order = self.make_order(
            customer=customer,
            salon=salon,
            status=status,
            is_paid=(status in {"paid", "completed"}),
            is_finally=True,
        )

        start_minutes = start.hour * 60 + start.minute
        end_minutes = start_minutes + 30

        return self.make_order_detail(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            date_value=self.day,
            start=start,
            end=time(
                end_minutes // 60,
                end_minutes % 60,
            ),
            price=price,
            **detail_kwargs,
        )

    def _make_snapshot(
        self,
        detail,
        *,
        gross,
        paid,
        commission,
        salon_profit,
        staff_share,
        material_cost,
    ):
        return OrderDetailFinancialSnapshot.objects.create(
            order_detail=detail,
            order=detail.order,
            salon=detail.salon,
            stylist=detail.stylist,
            service=detail.service,
            payment_method=(detail.order.selected_payment_method),
            gross_amount=gross,
            paid_amount_allocated=paid,
            total_customer_paid=paid,
            platform_commission_allocated=(commission),
            net_after_platform=max(
                gross - commission,
                0,
            ),
            share_base_amount=max(
                gross - commission,
                0,
            ),
            stylist_gross_share=staff_share,
            stylist_net_share=staff_share,
            salon_gross_share=salon_profit,
            salon_net_share=salon_profit,
            salon_net_profit=salon_profit,
            material_cost_total=material_cost,
            status=(OrderDetailFinancialSnapshot.Status.FINALIZED),
            finalized_at=timezone.now(),
        )

    def _create_reviews_and_scores(self):
        for score in (5, 3):
            comment = Comments.objects.create(
                comment_user=self.new_customer,
                salon=self.salon_a,
                stylist=self.stylist_a,
                service=self.service_a,
                is_active=True,
                comment_text="نظر فعال تست",
            )
            Scoring.objects.create(
                comment=comment,
                scoring_user=self.new_customer,
                salon=self.salon_a,
                stylist=self.stylist_a,
                service=self.service_a,
                score=score,
            )

        Comments.objects.create(
            comment_user=self.new_customer,
            salon=self.salon_a,
            stylist=self.stylist_a,
            service=self.service_a,
            is_active=False,
            comment_text="نظر غیرفعال تست",
        )

        Scoring.objects.create(
            scoring_user=self.salon_b_customer,
            salon=self.salon_b,
            stylist=self.stylist_b,
            service=self.service_b,
            score=2,
        )

    def _payloads(self):
        return _collect_daily_salon_metric_payloads(self.day)

    def test_payload_collection_uses_five_queries(self):
        with self.assertNumQueries(5):
            payloads = self._payloads()

        self.assertEqual(len(payloads), 2)

    def test_payload_values_preserve_existing_semantics(self):
        payloads = {payload["salon_id"]: payload for payload in self._payloads()}

        salon_a = payloads[self.salon_a.pk]

        self.assertEqual(
            salon_a["appointments_count"],
            3,
        )
        self.assertEqual(
            salon_a["completed_count"],
            1,
        )
        self.assertEqual(
            salon_a["cancelled_count"],
            1,
        )
        self.assertEqual(
            salon_a["no_show_count"],
            1,
        )
        self.assertEqual(
            salon_a["late_count"],
            1,
        )
        self.assertEqual(
            salon_a["overrun_count"],
            1,
        )
        self.assertEqual(
            salon_a["unique_customers"],
            2,
        )
        self.assertEqual(
            salon_a["new_customers"],
            1,
        )
        self.assertEqual(
            salon_a["repeat_customers"],
            1,
        )

        self.assertEqual(
            salon_a["gross_revenue"],
            300_000,
        )
        self.assertEqual(
            salon_a["customer_paid_total"],
            270_000,
        )
        self.assertEqual(
            salon_a["platform_commission"],
            30_000,
        )
        self.assertEqual(
            salon_a["salon_net_profit"],
            150_000,
        )
        self.assertEqual(
            salon_a["staff_payout_total"],
            95_000,
        )
        self.assertEqual(
            salon_a["material_cost_total"],
            25_000,
        )

        self.assertEqual(
            salon_a["reviews_count"],
            2,
        )
        self.assertEqual(
            salon_a["average_rating"],
            Decimal("4.00"),
        )

        salon_b = payloads[self.salon_b.pk]

        self.assertEqual(
            salon_b["unique_customers"],
            1,
        )
        self.assertEqual(
            salon_b["new_customers"],
            1,
        )
        self.assertEqual(
            salon_b["repeat_customers"],
            0,
        )
        self.assertEqual(
            salon_b["average_rating"],
            Decimal("2.00"),
        )

    def test_query_count_does_not_grow_with_more_salons_or_customers(
        self,
    ):
        for index in range(10):
            manager = self.make_salon_manager()
            salon = self.make_salon(
                manager=manager,
            )
            stylist = self.make_stylist()
            service = self.make_service()

            self.connect_service(
                salon=salon,
                stylist=stylist,
                service=service,
            )

            for customer_index in range(3):
                customer = self.make_customer()
                self._make_today_detail(
                    salon=salon,
                    stylist=stylist,
                    service=service,
                    customer=customer,
                    status="confirmed",
                    start=time(
                        13 + customer_index,
                        0,
                    ),
                    price=50_000 + index,
                )

        with self.assertNumQueries(5):
            payloads = self._payloads()

        self.assertEqual(len(payloads), 12)

    def test_bulk_upsert_is_idempotent_and_updates_existing_metric(
        self,
    ):
        build_daily_salon_metrics(self.day)

        self.assertEqual(
            DailySalonMetric.objects.filter(
                date=self.day,
            ).count(),
            2,
        )

        metric = DailySalonMetric.objects.get(
            salon=self.salon_a,
            date=self.day,
        )
        self.assertEqual(
            metric.appointments_count,
            3,
        )

        extra_customer = self.make_customer()
        self._make_today_detail(
            salon=self.salon_a,
            stylist=self.stylist_a,
            service=self.service_a,
            customer=extra_customer,
            status="confirmed",
            start=time(16, 0),
            price=80_000,
        )

        build_daily_salon_metrics(self.day)

        self.assertEqual(
            DailySalonMetric.objects.filter(
                date=self.day,
            ).count(),
            2,
        )

        metric.refresh_from_db()

        self.assertEqual(
            metric.appointments_count,
            4,
        )
        self.assertEqual(
            metric.unique_customers,
            3,
        )
        self.assertEqual(
            metric.new_customers,
            2,
        )
