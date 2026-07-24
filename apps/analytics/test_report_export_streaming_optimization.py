import csv
import io
from datetime import timedelta
from tempfile import (
    SpooledTemporaryFile,
    TemporaryDirectory,
)

from django.contrib.contenttypes.models import (
    ContentType,
)
from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import (
    DailyContentMetric,
    DailyPlatformMetric,
    DailySalonMetric,
    DailySearchMetric,
    DailyStaffMetric,
    ReportExportJob,
)
from apps.analytics.services import (
    REPORT_EXPORT_SPOOL_MAX_SIZE,
    _rows,
    _write_report_export_csv,
    process_report_export_job,
)
from tests_stage1_helpers import (
    Stage1DomainFactoryMixin,
)


class ReportExportStreamingOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_settings = self.settings(
            MEDIA_ROOT=(self.media_directory.name),
        )
        self.media_settings.enable()

        self.day = timezone.localdate()

        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(
            manager=self.manager,
        )
        self.stylist = self.make_stylist()

        self.platform_metric = DailyPlatformMetric.objects.create(
            date=self.day,
            appointments_count=3,
            completed_count=2,
            gross_revenue=100_000,
            salon_net_profit=50_000,
            staff_net_profit=30_000,
            searches_count=4,
        )

        self.salon_metric = DailySalonMetric.objects.create(
            salon=self.salon,
            date=self.day,
            appointments_count=4,
            completed_count=3,
            gross_revenue=120_000,
            salon_net_profit=60_000,
        )

        self.staff_metric = DailyStaffMetric.objects.create(
            stylist=self.stylist,
            salon=self.salon,
            date=self.day,
            appointments_count=2,
            completed_count=1,
            net_profit=25_000,
        )

        content_type = ContentType.objects.get_for_model(
            self.salon,
            for_concrete_model=False,
        )

        self.content_metric = DailyContentMetric.objects.create(
            content_type=content_type,
            object_id=self.salon.pk,
            content_kind="salon",
            salon=self.salon,
            date=self.day,
            views=10,
            cta_clicks=2,
            reports_count=1,
        )

        self.search_metric = DailySearchMetric.objects.create(
            date=self.day,
            normalized_query="رنگ مو",
            query="رنگ مو",
            filters_hash="",
            searches_count=5,
            results_total=18,
            no_result_count=1,
            clicks_count=3,
            booking_completed=2,
        )

    def tearDown(self):
        self.media_settings.disable()
        self.media_directory.cleanup()

        super().tearDown()

    def test_each_report_type_uses_one_select_query(
        self,
    ):
        cases = [
            (
                ReportExportJob.ReportType.PLATFORM_DAILY,
                [
                    "date",
                    "appointments",
                    "completed",
                    "gross",
                    "salon_profit",
                    "staff_profit",
                    "searches",
                ],
                (
                    self.day,
                    3,
                    2,
                    100_000,
                    50_000,
                    30_000,
                    4,
                ),
            ),
            (
                ReportExportJob.ReportType.SALON_DAILY,
                [
                    "date",
                    "salon",
                    "appointments",
                    "completed",
                    "gross",
                    "profit",
                ],
                (
                    self.day,
                    self.salon.pk,
                    4,
                    3,
                    120_000,
                    60_000,
                ),
            ),
            (
                ReportExportJob.ReportType.STAFF_DAILY,
                [
                    "date",
                    "stylist",
                    "salon",
                    "appointments",
                    "completed",
                    "net",
                ],
                (
                    self.day,
                    self.stylist.pk,
                    self.salon.pk,
                    2,
                    1,
                    25_000,
                ),
            ),
            (
                ReportExportJob.ReportType.CONTENT_DAILY,
                [
                    "date",
                    "kind",
                    "object",
                    "salon",
                    "views",
                    "clicks",
                    "reports",
                ],
                (
                    self.day,
                    "salon",
                    self.salon.pk,
                    self.salon.pk,
                    10,
                    2,
                    1,
                ),
            ),
            (
                ReportExportJob.ReportType.SEARCH_DAILY,
                [
                    "date",
                    "query",
                    "searches",
                    "results",
                    "no_result",
                    "clicks",
                    "booked",
                ],
                (
                    self.day,
                    "رنگ مو",
                    5,
                    18,
                    1,
                    3,
                    2,
                ),
            ),
        ]

        for (
            report_type,
            expected_header,
            expected_row,
        ) in cases:
            with self.subTest(
                report_type=report_type,
            ):
                job = ReportExportJob(
                    report_type=report_type,
                    filters={},
                )

                header, rows = _rows(job)

                self.assertEqual(
                    header,
                    expected_header,
                )

                with self.assertNumQueries(1):
                    exported_rows = list(rows)

                self.assertEqual(
                    exported_rows,
                    [expected_row],
                )

    def test_query_count_does_not_grow_with_more_rows(
        self,
    ):
        for index in range(50):
            DailySearchMetric.objects.create(
                date=(self.day - timedelta(days=index + 1)),
                normalized_query=(f"جستجو {index}"),
                query=f"جستجو {index}",
                filters_hash="",
                searches_count=index,
            )

        job = ReportExportJob(
            report_type=(ReportExportJob.ReportType.SEARCH_DAILY),
            filters={},
        )

        _header, rows = _rows(job)

        with self.assertNumQueries(1):
            exported_rows = list(rows)

        self.assertEqual(
            len(exported_rows),
            51,
        )

    def test_csv_writer_preserves_bom_and_row_count(
        self,
    ):
        job = ReportExportJob(
            report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
            filters={},
        )

        with SpooledTemporaryFile(
            max_size=(REPORT_EXPORT_SPOOL_MAX_SIZE),
            mode="w+b",
        ) as output:
            rows_count = _write_report_export_csv(
                job,
                output,
            )

            output.seek(0)
            content = output.read()

        self.assertEqual(
            rows_count,
            1,
        )
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))

        decoded = content.decode("utf-8-sig")

        csv_rows = list(csv.reader(io.StringIO(decoded)))

        self.assertEqual(
            len(csv_rows),
            2,
        )
        self.assertEqual(
            csv_rows[0][0],
            "date",
        )
        self.assertEqual(
            csv_rows[1][1],
            "3",
        )

    def test_process_job_completes_and_saves_file(
        self,
    ):
        job = ReportExportJob.objects.create(
            report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
            filters={},
        )

        result = process_report_export_job(job)

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            ReportExportJob.Status.COMPLETED,
        )
        self.assertEqual(
            result.rows_count,
            1,
        )
        self.assertTrue(result.file.name)
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.completed_at)
        self.assertIsNotNone(result.expires_at)

        with result.file.open("rb") as exported:
            content = exported.read()

        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))

        decoded = content.decode("utf-8-sig")
        csv_rows = list(csv.reader(io.StringIO(decoded)))

        self.assertEqual(
            len(csv_rows),
            2,
        )
