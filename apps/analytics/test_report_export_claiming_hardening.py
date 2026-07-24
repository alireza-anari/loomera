from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import (
    CaptureQueriesContext,
)

from django.utils import timezone

from apps.analytics.models import (
    ReportExportJob,
)
from apps.analytics.services import (
    _claim_pending_report_export_jobs,
    process_pending_report_exports,
    process_report_export_job,
)


class ReportExportClaimingHardeningTests(
    TransactionTestCase,
):
    reset_sequences = True

    def _make_job(
        self,
        *,
        status=ReportExportJob.Status.PENDING,
    ):
        return ReportExportJob.objects.create(
            report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
            status=status,
            filters={},
        )

    def test_claim_batch_marks_jobs_processing_without_overlap(
        self,
    ):
        jobs = [self._make_job() for _index in range(4)]

        first_batch = _claim_pending_report_export_jobs(
            limit=2,
        )

        self.assertEqual(
            [job.pk for job in first_batch],
            [jobs[0].pk, jobs[1].pk],
        )

        first_statuses = dict(
            ReportExportJob.objects.filter(
                pk__in=[
                    jobs[0].pk,
                    jobs[1].pk,
                ],
            ).values_list(
                "pk",
                "status",
            )
        )

        self.assertEqual(
            first_statuses,
            {
                jobs[0].pk: (ReportExportJob.Status.PROCESSING),
                jobs[1].pk: (ReportExportJob.Status.PROCESSING),
            },
        )

        second_batch = _claim_pending_report_export_jobs(
            limit=2,
        )

        self.assertEqual(
            [job.pk for job in second_batch],
            [jobs[2].pk, jobs[3].pk],
        )

        third_batch = _claim_pending_report_export_jobs(
            limit=2,
        )

        self.assertEqual(
            third_batch,
            [],
        )

    def test_claim_sets_processing_metadata(
        self,
    ):
        job = self._make_job()
        job.error_message = "old error"
        job.save(
            update_fields=[
                "error_message",
                "updated_at",
            ]
        )

        claimed = _claim_pending_report_export_jobs(
            limit=1,
        )

        self.assertEqual(
            len(claimed),
            1,
        )

        job.refresh_from_db()

        self.assertEqual(
            job.status,
            ReportExportJob.Status.PROCESSING,
        )
        self.assertIsNotNone(
            job.started_at,
        )
        self.assertEqual(
            job.error_message,
            "",
        )

    def test_claim_skips_non_pending_jobs(self):
        processing = self._make_job(
            status=(
                ReportExportJob
                .Status
                .PROCESSING
            ),
        )

        # Processing jobs without started_at are recovered as stale.
        # Give this job a fresh claim timestamp so it represents an
        # active worker and must not be reclaimed.
        fresh_started_at = timezone.now()

        ReportExportJob.objects.filter(
            pk=processing.pk,
        ).update(
            started_at=fresh_started_at,
        )

        processing.refresh_from_db()

        completed = self._make_job(
            status=(
                ReportExportJob
                .Status
                .COMPLETED
            ),
        )
        failed = self._make_job(
            status=(
                ReportExportJob
                .Status
                .FAILED
            ),
        )
        pending = self._make_job()

        claimed = (
            _claim_pending_report_export_jobs(
                limit=10,
            )
        )

        self.assertEqual(
            [job.pk for job in claimed],
            [pending.pk],
        )

        processing.refresh_from_db()
        completed.refresh_from_db()
        failed.refresh_from_db()

        self.assertEqual(
            processing.status,
            ReportExportJob.Status.PROCESSING,
        )
        self.assertEqual(
            processing.started_at,
            fresh_started_at,
        )
        self.assertEqual(
            completed.status,
            ReportExportJob.Status.COMPLETED,
        )
        self.assertEqual(
            failed.status,
            ReportExportJob.Status.FAILED,
        )

    def test_pending_processor_claims_before_file_processing(
        self,
    ):
        first = self._make_job()
        second = self._make_job()
        third = self._make_job()

        with patch(
            "apps.analytics.services." "_process_claimed_report_export_job"
        ) as processor:
            returned = process_pending_report_exports(
                limit=2,
            )

        self.assertEqual(
            [job.pk for job in returned],
            [first.pk, second.pk],
        )
        self.assertEqual(
            processor.call_count,
            2,
        )

        processed_ids = [call.args[0].pk for call in processor.call_args_list]

        self.assertEqual(
            processed_ids,
            [first.pk, second.pk],
        )

        for call in processor.call_args_list:
            self.assertEqual(
                call.args[0].status,
                ReportExportJob.Status.PROCESSING,
            )

        third.refresh_from_db()

        self.assertEqual(
            third.status,
            ReportExportJob.Status.PENDING,
        )

    def test_direct_processing_does_not_reprocess_non_pending_job(
        self,
    ):
        for status in [
            ReportExportJob.Status.PROCESSING,
            ReportExportJob.Status.COMPLETED,
            ReportExportJob.Status.FAILED,
            ReportExportJob.Status.EXPIRED,
        ]:
            with self.subTest(status=status):
                job = self._make_job(
                    status=status,
                )

                with patch(
                    "apps.analytics.services." "_process_claimed_report_export_job"
                ) as processor:
                    result = process_report_export_job(job)

                processor.assert_not_called()

                result.refresh_from_db()

                self.assertEqual(
                    result.status,
                    status,
                )

    def test_direct_pending_processing_claims_before_processing(
        self,
    ):
        job = self._make_job()

        with patch(
            "apps.analytics.services." "_process_claimed_report_export_job",
            side_effect=lambda claimed_job: (claimed_job),
        ) as processor:
            result = process_report_export_job(job)

        processor.assert_called_once()

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            ReportExportJob.Status.PROCESSING,
        )
        self.assertIsNotNone(
            result.started_at,
        )

    def test_postgresql_claim_query_uses_skip_locked(
        self,
    ):
        if not (connection.features.has_select_for_update_skip_locked):
            self.skipTest("Database backend has no " "SELECT FOR UPDATE SKIP LOCKED.")

        self._make_job()

        with CaptureQueriesContext(connection) as queries:
            _claim_pending_report_export_jobs(
                limit=1,
            )

        sql = "\n".join(query["sql"] for query in queries.captured_queries).upper()

        self.assertIn(
            "FOR UPDATE",
            sql,
        )
        self.assertIn(
            "SKIP LOCKED",
            sql,
        )
