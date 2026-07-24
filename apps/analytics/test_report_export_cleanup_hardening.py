from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import (
    TestCase,
    override_settings,
)
from django.utils import timezone

from apps.analytics.models import (
    ReportExportJob,
)
from apps.analytics.services import (
    _report_export_retention_delta,
    cleanup_expired_report_exports,
    process_report_export_job,
)


@override_settings(
    LOOMERA_EXPORT_RETENTION_DAYS=7,
    STORAGES={
        "default": {
            "BACKEND": ("django.core.files.storage." "FileSystemStorage"),
        },
        "staticfiles": {
            "BACKEND": ("django.contrib.staticfiles.storage." "StaticFilesStorage"),
        },
    },
)
class ReportExportCleanupHardeningTests(
    TestCase,
):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_settings = self.settings(
            MEDIA_ROOT=(self.media_directory.name),
        )
        self.media_settings.enable()

        self.now = timezone.now()

    def tearDown(self):
        self.media_settings.disable()
        self.media_directory.cleanup()

        super().tearDown()

    def _make_job(
        self,
        *,
        status=(ReportExportJob.Status.COMPLETED),
        expires_at=None,
        completed_at=None,
        created_at=None,
        updated_at=None,
        with_file=True,
    ):
        job = ReportExportJob.objects.create(
            report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
            status=status,
            filters={},
            expires_at=expires_at,
            completed_at=completed_at,
        )

        if with_file:
            job.file.save(
                f"cleanup-{job.pk}.csv",
                ContentFile(b"date,appointments\n"),
                save=True,
            )

        updates = {}

        if created_at is not None:
            updates["created_at"] = created_at

        if updated_at is not None:
            updates["updated_at"] = updated_at

        if updates:
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).update(**updates)

        job.refresh_from_db()

        return job

    def test_expired_completed_job_deletes_file_and_row(
        self,
    ):
        job = self._make_job(
            expires_at=(self.now - timedelta(minutes=1)),
            completed_at=(self.now - timedelta(days=7)),
        )

        file_name = job.file.name
        storage = job.file.storage

        self.assertTrue(storage.exists(file_name))

        stats = cleanup_expired_report_exports(
            now=self.now,
            limit=10,
        )

        self.assertEqual(
            stats,
            {
                "matched": 1,
                "deleted": 1,
                "files_deleted": 1,
                "failed": 0,
            },
        )

        self.assertFalse(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )
        self.assertFalse(storage.exists(file_name))

    def test_future_expiry_preserves_old_completed_job(
        self,
    ):
        job = self._make_job(
            expires_at=(self.now + timedelta(days=1)),
            completed_at=(self.now - timedelta(days=20)),
            created_at=(self.now - timedelta(days=30)),
        )

        file_name = job.file.name
        storage = job.file.storage

        stats = cleanup_expired_report_exports(
            now=self.now,
            limit=10,
        )

        self.assertEqual(
            stats["matched"],
            0,
        )
        self.assertTrue(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )
        self.assertTrue(storage.exists(file_name))

    def test_legacy_completed_job_uses_retention_fallback(
        self,
    ):
        job = self._make_job(
            expires_at=None,
            completed_at=(self.now - timedelta(days=8)),
        )

        stats = cleanup_expired_report_exports(
            now=self.now,
            limit=10,
        )

        self.assertEqual(
            stats["deleted"],
            1,
        )
        self.assertFalse(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )

    def test_recent_legacy_completed_job_is_preserved(
        self,
    ):
        job = self._make_job(
            expires_at=None,
            completed_at=(self.now - timedelta(days=2)),
        )

        stats = cleanup_expired_report_exports(
            now=self.now,
            limit=10,
        )

        self.assertEqual(
            stats["matched"],
            0,
        )
        self.assertTrue(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )

    def test_old_failed_job_is_cleaned(
        self,
    ):
        job = self._make_job(
            status=(ReportExportJob.Status.FAILED),
            completed_at=(self.now - timedelta(days=8)),
            with_file=False,
        )

        stats = cleanup_expired_report_exports(
            now=self.now,
            limit=10,
        )

        self.assertEqual(
            stats["deleted"],
            1,
        )
        self.assertEqual(
            stats["files_deleted"],
            0,
        )
        self.assertFalse(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )

    def test_dry_run_does_not_modify_storage_or_database(
        self,
    ):
        job = self._make_job(
            expires_at=(self.now - timedelta(minutes=1)),
        )

        file_name = job.file.name
        storage = job.file.storage

        stats = cleanup_expired_report_exports(
            now=self.now,
            dry_run=True,
            limit=10,
        )

        self.assertEqual(
            stats,
            {
                "matched": 1,
                "deleted": 0,
                "files_deleted": 0,
                "failed": 0,
            },
        )
        self.assertTrue(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )
        self.assertTrue(storage.exists(file_name))

    def test_cleanup_limit_bounds_each_batch(
        self,
    ):
        jobs = [
            self._make_job(
                expires_at=(self.now - timedelta(minutes=index + 1)),
            )
            for index in range(3)
        ]

        first = cleanup_expired_report_exports(
            now=self.now,
            limit=2,
        )

        self.assertEqual(
            first["matched"],
            2,
        )
        self.assertEqual(
            first["deleted"],
            2,
        )

        self.assertEqual(
            ReportExportJob.objects.filter(
                pk__in=[job.pk for job in jobs],
            ).count(),
            1,
        )

        second = cleanup_expired_report_exports(
            now=self.now,
            limit=2,
        )

        self.assertEqual(
            second["deleted"],
            1,
        )

    def test_storage_failure_keeps_database_row(
        self,
    ):
        job = self._make_job(
            expires_at=(self.now - timedelta(minutes=1)),
        )

        with patch(
            "apps.analytics.services." "_delete_report_export_file",
            side_effect=RuntimeError("storage unavailable"),
        ):
            stats = cleanup_expired_report_exports(
                now=self.now,
                limit=10,
            )

        self.assertEqual(
            stats["matched"],
            1,
        )
        self.assertEqual(
            stats["deleted"],
            0,
        )
        self.assertEqual(
            stats["failed"],
            1,
        )
        self.assertTrue(
            ReportExportJob.objects.filter(
                pk=job.pk,
            ).exists()
        )

    @override_settings(
        LOOMERA_EXPORT_RETENTION_DAYS=3,
    )
    def test_new_export_uses_configured_retention(
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
            result.expires_at - result.completed_at,
            timedelta(days=3),
        )

    @override_settings(
        LOOMERA_EXPORT_RETENTION_DAYS=0,
    )
    def test_retention_has_safe_minimum(
        self,
    ):
        self.assertEqual(
            _report_export_retention_delta(),
            timedelta(days=1),
        )
