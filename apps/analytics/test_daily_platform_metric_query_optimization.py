from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import (
    ContentType,
)
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Customer, Stylist
from apps.analytics.models import DailyPlatformMetric
from apps.analytics.services import (
    _collect_daily_platform_metric_payload,
    _day_bounds,
    build_daily_platform_metric,
)
from apps.articles.models import ContentReport
from apps.main.models import DisputeCase, SupportTicket
from apps.notifications.models import (
    Notification,
    NotificationAudienceRole,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationRecipient,
)
from apps.orders.models import OrderDetail
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
)
from apps.salons.models import Salon
from apps.search.models import SearchLog
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class DailyPlatformMetricQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.day = timezone.localdate()
        self.old_time = timezone.now() - timedelta(days=2)

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

        self.customer = self.make_customer()

        completed_detail = self._make_detail(
            status="completed",
            lifecycle_status="completed",
            start=time(9, 0),
            price=100_000,
        )
        self._make_snapshot(
            completed_detail,
            gross=100_000,
            paid=90_000,
            commission=10_000,
            salon_profit=50_000,
            staff_share=35_000,
            material_cost=5_000,
        )

        self._make_detail(
            status="cancelled",
            lifecycle_status="awaiting_confirmation",
            start=time(10, 0),
            price=200_000,
        )

        self._make_detail(
            status="confirmed",
            lifecycle_status="no_show_pending_review",
            start=time(11, 0),
            price=300_000,
        )

        self._make_detail(
            status="confirmed",
            lifecycle_status="disputed",
            start=time(12, 0),
            price=400_000,
        )

        self._make_detail(
            status="cancelled",
            lifecycle_status="awaiting_confirmation",
            start=time(10, 0),
            price=200_000,
        )
        self._make_detail(
            status="confirmed",
            lifecycle_status="no_show_pending_review",
            start=time(11, 0),
            price=300_000,
        )
        self._make_detail(
            status="confirmed",
            lifecycle_status="disputed",
            start=time(12, 0),
            price=400_000,
        )

        self._create_content_reports()
        self._create_support_and_disputes()
        self._create_notification_deliveries()
        self._create_search_logs()

    def _make_detail(
        self,
        *,
        status,
        lifecycle_status,
        start,
        price,
    ):
        order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            status=status,
            is_paid=(status == "completed"),
            is_finally=True,
        )

        start_minutes = start.hour * 60 + start.minute
        end_minutes = start_minutes + 30

        return self.make_order_detail(
            order=order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.day,
            start=start,
            end=time(
                end_minutes // 60,
                end_minutes % 60,
            ),
            price=price,
            lifecycle_status=lifecycle_status,
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

    def _create_content_reports(self):
        content_type = ContentType.objects.get_for_model(
            self.salon,
            for_concrete_model=False,
        )

        for _index in range(2):
            ContentReport.objects.create(
                target_content_type=content_type,
                target_object_id=self.salon.pk,
                reported_by=self.customer.user,
                reason=ContentReport.Reason.OTHER,
                description="گزارش امروز",
            )

        old_report = ContentReport.objects.create(
            target_content_type=content_type,
            target_object_id=self.salon.pk,
            reported_by=self.customer.user,
            reason=ContentReport.Reason.OTHER,
            description="گزارش قدیمی",
        )
        ContentReport.objects.filter(
            pk=old_report.pk,
        ).update(
            created_at=self.old_time,
        )

    def _create_support_and_disputes(self):
        SupportTicket.objects.create(
            user=self.customer.user,
            email="open@example.com",
            issue_type="other",
            subject="تیکت باز",
            status="open",
        )
        SupportTicket.objects.create(
            user=self.customer.user,
            email="cancelled@example.com",
            issue_type="other",
            subject="تیکت لغوشده",
            status="cancelled",
        )
        SupportTicket.objects.create(
            user=self.customer.user,
            email="resolved@example.com",
            issue_type="other",
            subject="تیکت حل‌شده",
            status="resolved",
        )

        DisputeCase.objects.create(
            opened_by=self.customer.user,
            dispute_type="general",
            status="opened",
            customer=self.customer,
            salon=self.salon,
        )
        DisputeCase.objects.create(
            opened_by=self.customer.user,
            dispute_type="financial",
            status="under_review",
            customer=self.customer,
            salon=self.salon,
        )
        DisputeCase.objects.create(
            opened_by=self.customer.user,
            dispute_type="general",
            status="closed",
            customer=self.customer,
            salon=self.salon,
        )

    def _create_delivery(
        self,
        *,
        status,
        title,
    ):
        notification = Notification.objects.create(
            event_type=f"analytics.{title}",
            title=title,
            salon=self.salon,
        )
        recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.manager.user,
            audience_role=(NotificationAudienceRole.MANAGER),
        )
        return NotificationDelivery.objects.create(
            recipient=recipient,
            channel=NotificationChannel.DASHBOARD,
            status=status,
        )

    def _create_notification_deliveries(self):
        self._create_delivery(
            status=NotificationDeliveryStatus.FAILED,
            title="failed-today",
        )
        self._create_delivery(
            status=NotificationDeliveryStatus.SENT,
            title="sent-today",
        )
        old_failed = self._create_delivery(
            status=NotificationDeliveryStatus.FAILED,
            title="failed-old",
        )
        NotificationDelivery.objects.filter(
            pk=old_failed.pk,
        ).update(
            created_at=self.old_time,
        )

    def _create_search_logs(self):
        SearchLog.objects.create(
            user=self.customer.user,
            session_key="platform-metric-test",
            query="رنگ مو",
            normalized_query="رنگ مو",
            results_count=5,
            no_result=False,
        )
        SearchLog.objects.create(
            user=self.customer.user,
            session_key="platform-metric-test",
            query="خدمت ناموجود",
            normalized_query="خدمت ناموجود",
            results_count=0,
            no_result=True,
        )

        old_log = SearchLog.objects.create(
            user=self.customer.user,
            session_key="platform-metric-old",
            query="جستجوی قدیمی",
            normalized_query="جستجوی قدیمی",
            results_count=20,
            no_result=False,
        )
        SearchLog.objects.filter(
            pk=old_log.pk,
        ).update(
            created_at=self.old_time,
        )

    def test_payload_collection_uses_eleven_queries(self):
        expected_appointments = OrderDetail.objects.filter(
            date=self.day,
        ).count()

        with self.assertNumQueries(11):
            payload = _collect_daily_platform_metric_payload(self.day)

        self.assertEqual(
            payload["appointments_count"],
            expected_appointments,
        )

    def test_payload_values_preserve_existing_semantics(self):
        User = get_user_model()
        start, end = _day_bounds(self.day)

        expected = {
            "users_total": User.objects.count(),
            "customers_total": Customer.objects.count(),
            "salons_total": Salon.objects.count(),
            "stylists_total": Stylist.objects.count(),
            "appointments_count": (
                OrderDetail.objects.filter(
                    date=self.day,
                ).count()
            ),
            "completed_count": (
                OrderDetail.objects.filter(
                    date=self.day,
                    lifecycle_status="completed",
                ).count()
            ),
            "cancelled_count": (
                OrderDetail.objects.filter(
                    date=self.day,
                    order__status="cancelled",
                ).count()
            ),
            "no_show_count": (
                OrderDetail.objects.filter(
                    date=self.day,
                    lifecycle_status__in=[
                        "no_show_pending_review",
                        "no_show_confirmed",
                    ],
                ).count()
            ),
            "disputed_count": (
                OrderDetail.objects.filter(
                    date=self.day,
                    lifecycle_status="disputed",
                ).count()
            ),
            "content_reports_count": (
                ContentReport.objects.filter(
                    created_at__gte=start,
                    created_at__lt=end,
                ).count()
            ),
            "support_open_count": (
                SupportTicket.objects.exclude(
                    status__in=[
                        "closed",
                        "resolved",
                    ],
                ).count()
            ),
            "disputes_open_count": (
                DisputeCase.objects.exclude(
                    status__in=[
                        "closed",
                        "rejected",
                        "resolved_for_customer",
                        "resolved_for_salon",
                        "resolved_partially",
                    ],
                ).count()
            ),
            "notifications_failed_count": (
                NotificationDelivery.objects.filter(
                    status=(NotificationDeliveryStatus.FAILED),
                    created_at__gte=start,
                    created_at__lt=end,
                ).count()
            ),
            "searches_count": (
                SearchLog.objects.filter(
                    created_at__gte=start,
                    created_at__lt=end,
                ).count()
            ),
            "no_result_searches_count": (
                SearchLog.objects.filter(
                    created_at__gte=start,
                    created_at__lt=end,
                    no_result=True,
                ).count()
            ),
        }

        payload = _collect_daily_platform_metric_payload(self.day)

        for key, value in expected.items():
            self.assertEqual(
                payload[key],
                value,
                key,
            )

        self.assertEqual(
            payload["gross_revenue"],
            100_000,
        )
        self.assertEqual(
            payload["customer_paid_total"],
            90_000,
        )
        self.assertEqual(
            payload["platform_commission"],
            10_000,
        )
        self.assertEqual(
            payload["salon_net_profit"],
            50_000,
        )
        self.assertEqual(
            payload["staff_net_profit"],
            35_000,
        )
        self.assertEqual(
            payload["material_cost_total"],
            5_000,
        )

        # Preserve the current definition: cancelled support tickets
        # are not excluded from support_open_count.
        self.assertEqual(
            payload["support_open_count"],
            2,
        )
        self.assertEqual(
            payload["disputes_open_count"],
            2,
        )

    def test_query_count_does_not_grow_with_more_data(self):
        start, end = _day_bounds(self.day)

        baseline_appointments = OrderDetail.objects.filter(
            date=self.day,
        ).count()

        baseline_searches = SearchLog.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
        ).count()
        for index in range(20):
            customer = self.make_customer()

            order = self.make_order(
                customer=customer,
                salon=self.salon,
                status="confirmed",
                is_paid=False,
                is_finally=True,
            )
            self.make_order_detail(
                order=order,
                service=self.service,
                stylist=self.stylist,
                salon=self.salon,
                date_value=self.day,
                start=time(
                    13 + (index // 4),
                    (index % 4) * 15,
                ),
                end=time(
                    13 + (index // 4),
                    ((index % 4) * 15 + 30) % 60,
                ),
                price=50_000,
            )

            SearchLog.objects.create(
                user=customer.user,
                session_key=f"platform-{index}",
                query=f"جستجو {index}",
                normalized_query=f"جستجو {index}",
                results_count=index,
                no_result=False,
            )

        with self.assertNumQueries(11):
            payload = _collect_daily_platform_metric_payload(self.day)

        self.assertEqual(
            payload["appointments_count"],
            baseline_appointments + 20,
        )
        self.assertEqual(
            payload["searches_count"],
            baseline_searches + 20,
        )

    def test_bulk_upsert_is_idempotent_and_updates_metric(self):
        expected_before = OrderDetail.objects.filter(
            date=self.day,
        ).count()

        first = build_daily_platform_metric(self.day)

        self.assertEqual(
            DailyPlatformMetric.objects.filter(
                date=self.day,
            ).count(),
            1,
        )

        first.refresh_from_db()

        self.assertEqual(
            first.appointments_count,
            expected_before,
        )

        extra_order = self.make_order(
            customer=self.customer,
            salon=self.salon,
            status="confirmed",
            is_paid=False,
            is_finally=True,
        )

        extra_detail = self.make_order_detail(
            order=extra_order,
            service=self.service,
            stylist=self.stylist,
            salon=self.salon,
            date_value=self.day,
            start=time(18, 0),
            end=time(18, 30),
            price=80_000,
        )

        # Checkpoint 1: the new appointment is stored on the target date.
        self.assertEqual(
            extra_detail.date,
            self.day,
        )
        self.assertTrue(
            OrderDetail.objects.filter(
                pk=extra_detail.pk,
                date=self.day,
            ).exists()
        )

        expected_after = OrderDetail.objects.filter(
            date=self.day,
        ).count()

        # Checkpoint 2: the database actually contains one more appointment.
        self.assertEqual(
            expected_after,
            expected_before + 1,
        )

        payload_after = _collect_daily_platform_metric_payload(self.day)

        # Checkpoint 3: the optimized collector sees the new appointment.
        self.assertEqual(
            payload_after["appointments_count"],
            expected_after,
        )

        second = build_daily_platform_metric(self.day)

        self.assertEqual(
            DailyPlatformMetric.objects.filter(
                date=self.day,
            ).count(),
            1,
        )

        metric = DailyPlatformMetric.objects.get(
            date=self.day,
        )

        # Checkpoint 4: conflict update persisted the new payload.
        self.assertEqual(
            metric.appointments_count,
            expected_after,
        )
        self.assertEqual(
            second.appointments_count,
            expected_after,
        )
