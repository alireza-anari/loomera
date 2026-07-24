from datetime import time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import DailyStaffMetric
from apps.analytics.services import (
    _collect_daily_staff_metric_payloads,
    build_daily_staff_metrics,
)
from apps.comments_scores_favories.models import (
    Comments,
    Scoring,
)
from apps.payments.models import StaffEarning
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class DailyStaffMetricsQueryOptimizationTests(
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

        self.manager_b = self.make_salon_manager()
        self.salon_b = self.make_salon(
            manager=self.manager_b,
        )

        # The same stylist works in two salons.
        self.stylist = self.make_stylist()

        self.service_a = self.make_service(
            name="خدمت سالن اول",
        )
        self.service_b = self.make_service(
            name="خدمت سالن دوم",
        )

        self.connect_service(
            salon=self.salon_a,
            stylist=self.stylist,
            service=self.service_a,
        )
        self.connect_service(
            salon=self.salon_b,
            stylist=self.stylist,
            service=self.service_b,
        )

        self.customer_a = self.make_customer()
        self.customer_b = self.make_customer()

        first_detail = self._make_detail(
            salon=self.salon_a,
            service=self.service_a,
            customer=self.customer_a,
            status="completed",
            start=time(9, 0),
            lifecycle_status="completed",
            client_late_recorded_at=self.now,
            service_overrun_recorded_at=self.now,
        )
        self._make_earning(
            first_detail,
            gross=100_000,
            net=80_000,
            material=20_000,
            status=StaffEarning.Status.PAYABLE,
        )

        second_detail = self._make_detail(
            salon=self.salon_a,
            service=self.service_a,
            customer=self.customer_a,
            status="confirmed",
            start=time(10, 0),
            lifecycle_status=("no_show_pending_review"),
        )
        self._make_earning(
            second_detail,
            gross=200_000,
            net=170_000,
            material=30_000,
            status=StaffEarning.Status.PENDING,
        )

        self._make_detail(
            salon=self.salon_a,
            service=self.service_a,
            customer=self.customer_b,
            status="cancelled",
            start=time(11, 0),
        )

        salon_b_detail = self._make_detail(
            salon=self.salon_b,
            service=self.service_b,
            customer=self.customer_b,
            status="completed",
            start=time(12, 0),
            lifecycle_status="completed",
        )
        self._make_earning(
            salon_b_detail,
            gross=400_000,
            net=350_000,
            material=50_000,
            status=StaffEarning.Status.PAYABLE,
        )

        self._create_reviews_and_scores()

    def _make_detail(
        self,
        *,
        salon,
        service,
        customer,
        status,
        start,
        lifecycle_status="awaiting_confirmation",
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
            stylist=self.stylist,
            salon=salon,
            date_value=self.day,
            start=start,
            end=time(
                end_minutes // 60,
                end_minutes % 60,
            ),
            price=100_000,
            lifecycle_status=lifecycle_status,
            **detail_kwargs,
        )

    def _make_earning(
        self,
        detail,
        *,
        gross,
        net,
        material,
        status,
    ):
        return StaffEarning.objects.create(
            order_detail=detail,
            salon=detail.salon,
            stylist=detail.stylist,
            gross_share=gross,
            material_deduction=material,
            net_profit=net,
            status=status,
            calculated_at=timezone.now(),
        )

    def _create_reviews_and_scores(self):
        for score in (5, 3):
            comment = Comments.objects.create(
                comment_user=self.customer_a,
                salon=self.salon_a,
                stylist=self.stylist,
                service=self.service_a,
                is_active=True,
                comment_text="نظر فعال متخصص",
            )
            Scoring.objects.create(
                comment=comment,
                scoring_user=self.customer_a,
                salon=self.salon_a,
                stylist=self.stylist,
                service=self.service_a,
                score=score,
            )

        Comments.objects.create(
            comment_user=self.customer_a,
            salon=self.salon_a,
            stylist=self.stylist,
            service=self.service_a,
            is_active=False,
            comment_text="نظر غیرفعال متخصص",
        )

        Scoring.objects.create(
            scoring_user=self.customer_b,
            salon=self.salon_b,
            stylist=self.stylist,
            service=self.service_b,
            score=2,
        )

    def _payloads(self):
        return _collect_daily_staff_metric_payloads(self.day)

    def test_payload_collection_uses_four_queries(self):
        with self.assertNumQueries(4):
            payloads = self._payloads()

        self.assertEqual(len(payloads), 2)

    def test_payload_values_preserve_existing_semantics(self):
        payloads = {
            (
                payload["stylist_id"],
                payload["salon_id"],
            ): payload
            for payload in self._payloads()
        }

        salon_a = payloads[
            (
                self.stylist.pk,
                self.salon_a.pk,
            )
        ]

        self.assertEqual(
            salon_a["appointments_count"],
            3,
        )
        self.assertEqual(
            salon_a["completed_count"],
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
            salon_a["no_show_count"],
            1,
        )

        self.assertEqual(
            salon_a["gross_share"],
            300_000,
        )
        self.assertEqual(
            salon_a["net_profit"],
            250_000,
        )
        self.assertEqual(
            salon_a["material_deduction"],
            50_000,
        )
        self.assertEqual(
            salon_a["payable_amount"],
            80_000,
        )

        self.assertEqual(
            salon_a["reviews_count"],
            2,
        )
        self.assertEqual(
            salon_a["average_rating"],
            Decimal("4.00"),
        )

        salon_b = payloads[
            (
                self.stylist.pk,
                self.salon_b.pk,
            )
        ]

        self.assertEqual(
            salon_b["appointments_count"],
            1,
        )
        self.assertEqual(
            salon_b["gross_share"],
            400_000,
        )
        self.assertEqual(
            salon_b["payable_amount"],
            350_000,
        )
        self.assertEqual(
            salon_b["reviews_count"],
            0,
        )
        self.assertEqual(
            salon_b["average_rating"],
            Decimal("2.00"),
        )

    def test_same_stylist_is_kept_separate_between_salons(self):
        payloads = self._payloads()

        pair_keys = {
            (
                payload["stylist_id"],
                payload["salon_id"],
            )
            for payload in payloads
        }

        self.assertEqual(
            pair_keys,
            {
                (
                    self.stylist.pk,
                    self.salon_a.pk,
                ),
                (
                    self.stylist.pk,
                    self.salon_b.pk,
                ),
            },
        )

    def test_query_count_does_not_grow_with_more_staff_pairs(
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

            customer = self.make_customer()
            order = self.make_order(
                customer=customer,
                salon=salon,
                status="confirmed",
                is_paid=False,
                is_finally=True,
            )
            self.make_order_detail(
                order=order,
                service=service,
                stylist=stylist,
                salon=salon,
                date_value=self.day,
                start=time(13, 0),
                end=time(13, 30),
                price=50_000,
            )

        with self.assertNumQueries(4):
            payloads = self._payloads()

        self.assertEqual(len(payloads), 12)

    def test_bulk_upsert_is_idempotent_and_updates_existing_metric(
        self,
    ):
        build_daily_staff_metrics(self.day)

        self.assertEqual(
            DailyStaffMetric.objects.filter(
                date=self.day,
            ).count(),
            2,
        )

        metric = DailyStaffMetric.objects.get(
            stylist=self.stylist,
            salon=self.salon_a,
            date=self.day,
        )

        self.assertEqual(
            metric.appointments_count,
            3,
        )
        self.assertEqual(
            metric.net_profit,
            250_000,
        )

        extra_customer = self.make_customer()

        extra_detail = self._make_detail(
            salon=self.salon_a,
            service=self.service_a,
            customer=extra_customer,
            status="confirmed",
            start=time(16, 0),
        )
        self._make_earning(
            extra_detail,
            gross=50_000,
            net=40_000,
            material=10_000,
            status=StaffEarning.Status.PAYABLE,
        )

        build_daily_staff_metrics(self.day)

        self.assertEqual(
            DailyStaffMetric.objects.filter(
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
            metric.gross_share,
            350_000,
        )
        self.assertEqual(
            metric.net_profit,
            290_000,
        )
        self.assertEqual(
            metric.payable_amount,
            120_000,
        )
