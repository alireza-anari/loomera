from datetime import timedelta

from django.test import (
    TransactionTestCase,
    override_settings,
)
from django.utils import timezone

from apps.analytics.models import (
    ReportExportJob,
)
from apps.analytics.services import (
    _claim_pending_report_export_jobs,
    _recover_stale_report_export_jobs,
)


@override_settings(
    LOOMERA_REPORT_EXPORT_STALE_AFTER_MINUTES=30,
)
class ReportExportStaleRecoveryTests(
    TransactionTestCase,
):
    reset_sequences = True

    def _make_job(
        self,
        *,
        status=ReportExportJob.Status.PENDING,
        started_at=None,
        rows_count=0,
        error_message="",
    ):
        job = ReportExportJob.objects.create(
            report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
            status=status,
            filters={},
            rows_count=rows_count,
            error_message=error_message,
        )

        ReportExportJob.objects.filter(
            pk=job.pk,
        ).update(
            started_at=started_at,
        )

        job.refresh_from_db()

        return job

    def test_stale_processing_job_is_returned_to_pending(
        self,
    ):
        now = timezone.now()

        job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=(now - timedelta(minutes=31)),
            rows_count=12,
            error_message="old error",
        )

        recovered = _recover_stale_report_export_jobs(
            now=now,
        )

        self.assertEqual(
            recovered,
            1,
        )

        job.refresh_from_db()

        self.assertEqual(
            job.status,
            ReportExportJob.Status.PENDING,
        )
        self.assertIsNone(
            job.started_at,
        )
        self.assertIsNone(
            job.completed_at,
        )
        self.assertIsNone(
            job.expires_at,
        )
        self.assertEqual(
            job.rows_count,
            0,
        )
        self.assertEqual(
            job.error_message,
            "",
        )

    def test_fresh_processing_job_is_not_recovered(
        self,
    ):
        now = timezone.now()

        job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=(now - timedelta(minutes=5)),
        )

        recovered = _recover_stale_report_export_jobs(
            now=now,
        )

        self.assertEqual(
            recovered,
            0,
        )

        job.refresh_from_db()

        self.assertEqual(
            job.status,
            ReportExportJob.Status.PROCESSING,
        )

    def test_processing_job_without_started_at_is_recovered(
        self,
    ):
        job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=None,
        )

        recovered = _recover_stale_report_export_jobs()

        self.assertEqual(
            recovered,
            1,
        )

        job.refresh_from_db()

        self.assertEqual(
            job.status,
            ReportExportJob.Status.PENDING,
        )

    def test_recovery_does_not_touch_other_statuses(
        self,
    ):
        old_time = timezone.now() - timedelta(hours=2)

        statuses = [
            ReportExportJob.Status.PENDING,
            ReportExportJob.Status.COMPLETED,
            ReportExportJob.Status.FAILED,
            ReportExportJob.Status.EXPIRED,
        ]

        jobs = [
            self._make_job(
                status=status,
                started_at=old_time,
            )
            for status in statuses
        ]

        recovered = _recover_stale_report_export_jobs()

        self.assertEqual(
            recovered,
            0,
        )

        for job, expected_status in zip(
            jobs,
            statuses,
        ):
            job.refresh_from_db()

            self.assertEqual(
                job.status,
                expected_status,
            )

    def test_claim_automatically_recovers_stale_job(
        self,
    ):
        old_started_at = timezone.now() - timedelta(minutes=31)

        stale_job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=old_started_at,
        )

        fresh_job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=(timezone.now() - timedelta(minutes=5)),
        )

        claimed = _claim_pending_report_export_jobs(
            limit=10,
        )

        self.assertEqual(
            [job.pk for job in claimed],
            [stale_job.pk],
        )

        stale_job.refresh_from_db()
        fresh_job.refresh_from_db()

        self.assertEqual(
            stale_job.status,
            ReportExportJob.Status.PROCESSING,
        )
        self.assertIsNotNone(
            stale_job.started_at,
        )
        self.assertGreater(
            stale_job.started_at,
            old_started_at,
        )

        self.assertEqual(
            fresh_job.status,
            ReportExportJob.Status.PROCESSING,
        )

    @override_settings(
        LOOMERA_REPORT_EXPORT_STALE_AFTER_MINUTES=120,
    )
    def test_recovery_respects_configured_timeout(
        self,
    ):
        now = timezone.now()

        recent_job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=(now - timedelta(minutes=60)),
        )

        old_job = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=(now - timedelta(minutes=121)),
        )

        recovered = _recover_stale_report_export_jobs(
            now=now,
        )

        self.assertEqual(
            recovered,
            1,
        )

        recent_job.refresh_from_db()
        old_job.refresh_from_db()

        self.assertEqual(
            recent_job.status,
            ReportExportJob.Status.PROCESSING,
        )
        self.assertEqual(
            old_job.status,
            ReportExportJob.Status.PENDING,
        )

    def test_claim_limit_is_preserved_after_recovery(
        self,
    ):
        old_started_at = timezone.now() - timedelta(hours=2)

        stale_jobs = [
            self._make_job(
                status=(ReportExportJob.Status.PROCESSING),
                started_at=old_started_at,
            )
            for _index in range(3)
        ]

        first_batch = _claim_pending_report_export_jobs(
            limit=2,
        )

        self.assertEqual(
            [job.pk for job in first_batch],
            [
                stale_jobs[0].pk,
                stale_jobs[1].pk,
            ],
        )

        stale_jobs[2].refresh_from_db()

        self.assertEqual(
            stale_jobs[2].status,
            ReportExportJob.Status.PENDING,
        )

        second_batch = _claim_pending_report_export_jobs(
            limit=2,
        )

        self.assertEqual(
            [job.pk for job in second_batch],
            [stale_jobs[2].pk],
        )

    def test_claim_skips_non_pending_jobs(self):
        processing = self._make_job(
            status=(ReportExportJob.Status.PROCESSING),
        )

        # Processing jobs without started_at are intentionally recovered
        # as stale since phase 8.21. Give this job a fresh claim timestamp
        # so this test verifies that genuinely active jobs are skipped.
        fresh_started_at = timezone.now() - timedelta(minutes=5)

        ReportExportJob.objects.filter(
            pk=processing.pk,
        ).update(
            started_at=fresh_started_at,
        )

        processing.refresh_from_db()

        completed = self._make_job(
            status=(ReportExportJob.Status.COMPLETED),
        )
        failed = self._make_job(
            status=(ReportExportJob.Status.FAILED),
        )
        pending = self._make_job()

        claimed = _claim_pending_report_export_jobs(
            limit=10,
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
