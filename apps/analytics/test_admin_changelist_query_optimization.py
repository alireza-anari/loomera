from datetime import timedelta

from django.contrib import admin
from django.contrib.contenttypes.models import (
    ContentType,
)
from django.test import (
    RequestFactory,
    TestCase,
)
from django.utils import timezone

from apps.analytics.admin import (
    AnalyticsEventAdmin,
    DailyContentMetricAdmin,
    DailyPlatformMetricAdmin,
    DailySalonMetricAdmin,
    DailySearchMetricAdmin,
    DailyStaffMetricAdmin,
    ReportExportJobAdmin,
)
from apps.analytics.models import (
    AnalyticsEvent,
    DailyContentMetric,
    DailyPlatformMetric,
    DailySalonMetric,
    DailySearchMetric,
    DailyStaffMetric,
    ReportExportJob,
)
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class AnalyticsAdminChangelistQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )
        self.stylist = self.make_stylist()

        self.day = timezone.localdate()

        self.content_type = ContentType.objects.get_for_model(
            self.salon,
            for_concrete_model=False,
        )

        self.request = RequestFactory().get("/admin/analytics/")
        self.request.user = self.manager.user

        self.admin_site = admin.AdminSite()

        self._create_rows(25)

    def _create_rows(self, count):
        for index in range(count):
            day = self.day - timedelta(days=index)

            AnalyticsEvent.objects.create(
                category="system",
                event_type=(f"admin-query-test-{index}"),
                salon=self.salon,
                stylist=self.stylist,
            )

            DailyPlatformMetric.objects.create(
                date=day,
                appointments_count=index,
            )

            DailySalonMetric.objects.create(
                salon=self.salon,
                date=day,
                appointments_count=index,
            )

            DailyStaffMetric.objects.create(
                stylist=self.stylist,
                salon=self.salon,
                date=day,
                appointments_count=index,
            )

            DailyContentMetric.objects.create(
                content_type=self.content_type,
                object_id=self.salon.pk,
                content_kind="salon",
                salon=self.salon,
                date=day,
                views=index,
            )

            DailySearchMetric.objects.create(
                date=day,
                normalized_query=(f"جستجو {index}"),
                query=f"جستجو {index}",
                filters_hash="",
                searches_count=index,
            )

            ReportExportJob.objects.create(
                requested_by=self.manager.user,
                report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
                filters={},
            )

    def _model_admin(
        self,
        admin_class,
        model,
    ):
        return admin_class(
            model,
            self.admin_site,
        )

    def test_shared_changelist_limits_are_enabled(
        self,
    ):
        cases = [
            (
                AnalyticsEventAdmin,
                AnalyticsEvent,
                (
                    "salon",
                    "stylist__user",
                ),
            ),
            (
                DailyPlatformMetricAdmin,
                DailyPlatformMetric,
                (),
            ),
            (
                DailySalonMetricAdmin,
                DailySalonMetric,
                ("salon",),
            ),
            (
                DailyStaffMetricAdmin,
                DailyStaffMetric,
                (
                    "stylist__user",
                    "salon",
                ),
            ),
            (
                DailyContentMetricAdmin,
                DailyContentMetric,
                ("salon",),
            ),
            (
                DailySearchMetricAdmin,
                DailySearchMetric,
                (),
            ),
            (
                ReportExportJobAdmin,
                ReportExportJob,
                ("requested_by",),
            ),
        ]

        for (
            admin_class,
            model,
            expected_related,
        ) in cases:
            with self.subTest(
                admin_class=(admin_class.__name__),
            ):
                model_admin = self._model_admin(
                    admin_class,
                    model,
                )

                self.assertFalse(model_admin.show_full_result_count)
                self.assertEqual(
                    model_admin.list_per_page,
                    50,
                )
                self.assertEqual(
                    tuple(model_admin.get_list_select_related(self.request) or ()),
                    expected_related,
                )

    def test_analytics_event_relations_use_one_query(
        self,
    ):
        model_admin = self._model_admin(
            AnalyticsEventAdmin,
            AnalyticsEvent,
        )

        queryset = model_admin.get_queryset(self.request).order_by("pk")

        with self.assertNumQueries(1):
            rows = [
                (
                    str(event.salon),
                    str(event.stylist),
                )
                for event in queryset
            ]

        self.assertEqual(
            len(rows),
            25,
        )

    def test_daily_salon_relations_use_one_query(
        self,
    ):
        model_admin = self._model_admin(
            DailySalonMetricAdmin,
            DailySalonMetric,
        )

        queryset = model_admin.get_queryset(self.request).order_by("pk")

        with self.assertNumQueries(1):
            rows = [str(metric.salon) for metric in queryset]

        self.assertEqual(
            len(rows),
            25,
        )

    def test_daily_staff_relations_use_one_query(
        self,
    ):
        model_admin = self._model_admin(
            DailyStaffMetricAdmin,
            DailyStaffMetric,
        )

        queryset = model_admin.get_queryset(self.request).order_by("pk")

        with self.assertNumQueries(1):
            rows = [
                (
                    str(metric.stylist),
                    str(metric.salon),
                )
                for metric in queryset
            ]

        self.assertEqual(
            len(rows),
            25,
        )

    def test_daily_content_relations_use_one_query(
        self,
    ):
        model_admin = self._model_admin(
            DailyContentMetricAdmin,
            DailyContentMetric,
        )

        queryset = model_admin.get_queryset(self.request).order_by("pk")

        with self.assertNumQueries(1):
            rows = [str(metric.salon) for metric in queryset]

        self.assertEqual(
            len(rows),
            25,
        )

    def test_report_export_requesters_use_one_query(
        self,
    ):
        model_admin = self._model_admin(
            ReportExportJobAdmin,
            ReportExportJob,
        )

        queryset = model_admin.get_queryset(self.request).order_by("pk")

        with self.assertNumQueries(1):
            rows = [str(job.requested_by) for job in queryset]

        self.assertEqual(
            len(rows),
            25,
        )
