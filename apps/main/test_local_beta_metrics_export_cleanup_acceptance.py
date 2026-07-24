from __future__ import annotations

import csv
import io
from datetime import timedelta
from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.analytics.models import (
    DailyPlatformMetric,
    DailySalonMetric,
    DailyStaffMetric,
    ReportExportJob,
)
from apps.analytics.services import (
    create_report_export_job,
    process_report_export_job,
)
from apps.main.management.commands.seed_local_demo_data import (
    SEED_TAG,
)
from apps.orders.models import Order
from apps.payments.finance import (
    finalize_order_financials,
)
from apps.payments.models import (
    LedgerEntry,
    OrderDetailFinancialSnapshot,
    Payment,
    StaffEarning,
    WalletTransaction,
)


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ],
    ONLINE_PAYMENT_ENABLED=False,
    PAYMENT_MODE="mock",
    MESSAGING_OUTBOUND_ENABLED=False,
    EMAIL_BACKEND=("django.core.mail.backends.dummy.EmailBackend"),
    LOOMERA_EXPORT_RETENTION_DAYS=7,
    LOOMERA_REPORT_EXPORT_STALE_AFTER_MINUTES=60,
    STORAGES={
        "default": {
            "BACKEND": ("django.core.files.storage." "FileSystemStorage"),
        },
        "staticfiles": {
            "BACKEND": ("django.contrib.staticfiles.storage." "StaticFilesStorage"),
        },
    },
)
class LocalBetaMetricsExportCleanupAcceptanceTests(TestCase):
    def _build_metrics(self, day):
        output = StringIO()

        call_command(
            "build_daily_metrics",
            date=day.isoformat(),
            days=1,
            stdout=output,
        )

        self.assertIn(
            f"Built analytics metrics for {day}",
            output.getvalue(),
        )

    def _metric_identity_snapshot(self, day):
        return {
            "platform": tuple(
                DailyPlatformMetric.objects.filter(date=day).values_list(
                    "pk",
                    flat=True,
                )
            ),
            "salons": tuple(
                DailySalonMetric.objects.filter(date=day)
                .order_by("salon_id")
                .values_list(
                    "pk",
                    flat=True,
                )
            ),
            "staff": tuple(
                DailyStaffMetric.objects.filter(date=day)
                .order_by(
                    "salon_id",
                    "stylist_id",
                )
                .values_list(
                    "pk",
                    flat=True,
                )
            ),
        }

    def test_metrics_export_and_cleanup_are_safe_and_idempotent(
        self,
    ):
        with TemporaryDirectory() as media_root:
            with self.settings(
                MEDIA_ROOT=media_root,
            ):
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    beta_acceptance=True,
                    days=14,
                    stdout=StringIO(),
                )

                completed_order = Order.objects.select_related(
                    "salon__salon_manager__user",
                ).get(description=(f"{SEED_TAG}:order:" "completed-manual-payment"))

                completed_payment = (
                    Payment.objects.filter(
                        order=completed_order,
                        state=Payment.State.SUCCESS,
                    )
                    .order_by("pk")
                    .first()
                )

                self.assertIsNotNone(completed_payment)

                manager_user = completed_order.salon.salon_manager.user

                snapshots = finalize_order_financials(
                    completed_order,
                    payment=completed_payment,
                    recorded_by=manager_user,
                    require_all_completed=True,
                )

                self.assertEqual(
                    len(snapshots),
                    1,
                )

                snapshot = snapshots[0]
                day = snapshot.order_detail.date
                salon = snapshot.salon
                stylist = snapshot.stylist

                financial_counts_after_finalization = {
                    "payments": (Payment.objects.count()),
                    "wallet_transactions": (WalletTransaction.objects.count()),
                    "ledger_entries": (LedgerEntry.objects.count()),
                    "staff_earnings": (StaffEarning.objects.count()),
                    "snapshots": (OrderDetailFinancialSnapshot.objects.count()),
                }

                # --------------------------------------
                # Daily metrics — first run
                # --------------------------------------

                self._build_metrics(day)

                platform_metric = DailyPlatformMetric.objects.get(date=day)
                salon_metric = DailySalonMetric.objects.get(
                    date=day,
                    salon=salon,
                )
                staff_metric = DailyStaffMetric.objects.get(
                    date=day,
                    salon=salon,
                    stylist=stylist,
                )

                self.assertEqual(
                    platform_metric.appointments_count,
                    1,
                )
                self.assertEqual(
                    platform_metric.completed_count,
                    1,
                )
                self.assertEqual(
                    platform_metric.gross_revenue,
                    int(snapshot.gross_amount),
                )

                self.assertEqual(
                    salon_metric.appointments_count,
                    1,
                )
                self.assertEqual(
                    salon_metric.completed_count,
                    1,
                )
                self.assertEqual(
                    salon_metric.gross_revenue,
                    int(snapshot.gross_amount),
                )

                self.assertEqual(
                    staff_metric.appointments_count,
                    1,
                )
                self.assertEqual(
                    staff_metric.completed_count,
                    1,
                )
                self.assertEqual(
                    staff_metric.gross_share,
                    int(snapshot.stylist_gross_share),
                )

                self.assertEqual(
                    DailySalonMetric.objects.filter(date=day).count(),
                    1,
                )
                self.assertEqual(
                    DailyStaffMetric.objects.filter(date=day).count(),
                    1,
                )

                first_metric_ids = self._metric_identity_snapshot(day)

                # --------------------------------------
                # Daily metrics — idempotent rerun
                # --------------------------------------

                self._build_metrics(day)

                second_metric_ids = self._metric_identity_snapshot(day)

                self.assertEqual(
                    second_metric_ids,
                    first_metric_ids,
                )
                self.assertEqual(
                    DailyPlatformMetric.objects.filter(date=day).count(),
                    1,
                )
                self.assertEqual(
                    DailySalonMetric.objects.filter(
                        date=day,
                        salon=salon,
                    ).count(),
                    1,
                )
                self.assertEqual(
                    DailyStaffMetric.objects.filter(
                        date=day,
                        salon=salon,
                        stylist=stylist,
                    ).count(),
                    1,
                )

                # --------------------------------------
                # Salon-scoped streaming CSV export
                # --------------------------------------

                export_job = create_report_export_job(
                    user=manager_user,
                    report_type=(ReportExportJob.ReportType.SALON_DAILY),
                    filters={
                        "start_date": (day.isoformat()),
                        "end_date": (day.isoformat()),
                        # Match the real admin form,
                        # which submits salon_id as text.
                        "salon_id": str(salon.pk),
                    },
                )

                process_output = StringIO()

                call_command(
                    "process_report_exports",
                    limit=10,
                    stdout=process_output,
                )

                self.assertIn(
                    "Processed 1 report export " "job(s).",
                    process_output.getvalue(),
                )

                export_job.refresh_from_db()

                self.assertEqual(
                    export_job.status,
                    (ReportExportJob.Status.COMPLETED),
                )
                self.assertEqual(
                    export_job.rows_count,
                    1,
                )
                self.assertTrue(export_job.file.name)
                self.assertIsNotNone(export_job.started_at)
                self.assertIsNotNone(export_job.completed_at)
                self.assertIsNotNone(export_job.expires_at)

                export_file_name = export_job.file.name
                export_storage = export_job.file.storage

                self.assertTrue(export_storage.exists(export_file_name))

                with export_job.file.open("rb") as exported_file:
                    exported_content = exported_file.read()

                self.assertTrue(exported_content.startswith(b"\xef\xbb\xbf"))

                csv_rows = list(
                    csv.reader(io.StringIO(exported_content.decode("utf-8-sig")))
                )

                self.assertEqual(
                    len(csv_rows),
                    2,
                )
                self.assertEqual(
                    csv_rows[0],
                    [
                        "date",
                        "salon",
                        "appointments",
                        "completed",
                        "gross",
                        "profit",
                    ],
                )
                self.assertEqual(
                    csv_rows[1][0],
                    day.isoformat(),
                )
                self.assertEqual(
                    csv_rows[1][1],
                    str(salon.pk),
                )
                self.assertEqual(
                    csv_rows[1][2],
                    "1",
                )
                self.assertEqual(
                    csv_rows[1][3],
                    "1",
                )

                # --------------------------------------
                # A fresh export must survive cleanup
                # --------------------------------------

                fresh_job = create_report_export_job(
                    user=manager_user,
                    report_type=(ReportExportJob.ReportType.PLATFORM_DAILY),
                    filters={
                        "start_date": (day.isoformat()),
                        "end_date": (day.isoformat()),
                    },
                )

                process_report_export_job(fresh_job)
                fresh_job.refresh_from_db()

                self.assertEqual(
                    fresh_job.status,
                    (ReportExportJob.Status.COMPLETED),
                )
                self.assertTrue(fresh_job.file.name)

                fresh_file_name = fresh_job.file.name
                fresh_storage = fresh_job.file.storage

                self.assertTrue(fresh_storage.exists(fresh_file_name))

                # Expire only the salon-scoped export.
                ReportExportJob.objects.filter(pk=export_job.pk).update(
                    expires_at=(timezone.now() - timedelta(minutes=1))
                )

                export_job.refresh_from_db()

                # --------------------------------------
                # Cleanup dry-run
                # --------------------------------------

                dry_run_output = StringIO()

                call_command(
                    "cleanup_operational_data",
                    dry_run=True,
                    job_run_days=30,
                    export_limit=100,
                    stdout=dry_run_output,
                )

                self.assertIn(
                    "report_exports: "
                    "matched=1 deleted=0 "
                    "files_deleted=0 "
                    "failed=0 dry_run=True",
                    dry_run_output.getvalue(),
                )

                self.assertTrue(
                    ReportExportJob.objects.filter(pk=export_job.pk).exists()
                )
                self.assertTrue(export_storage.exists(export_file_name))
                self.assertTrue(
                    ReportExportJob.objects.filter(pk=fresh_job.pk).exists()
                )
                self.assertTrue(fresh_storage.exists(fresh_file_name))

                # --------------------------------------
                # Real cleanup
                # --------------------------------------

                cleanup_output = StringIO()

                call_command(
                    "cleanup_operational_data",
                    dry_run=False,
                    job_run_days=30,
                    export_limit=100,
                    stdout=cleanup_output,
                )

                self.assertIn(
                    "report_exports: "
                    "matched=1 deleted=1 "
                    "files_deleted=1 "
                    "failed=0 dry_run=False",
                    cleanup_output.getvalue(),
                )

                self.assertFalse(
                    ReportExportJob.objects.filter(pk=export_job.pk).exists()
                )
                self.assertFalse(export_storage.exists(export_file_name))

                self.assertTrue(
                    ReportExportJob.objects.filter(pk=fresh_job.pk).exists()
                )
                self.assertTrue(fresh_storage.exists(fresh_file_name))

                # Metrics are source data for exports and
                # must never be removed by export cleanup.
                self.assertTrue(DailyPlatformMetric.objects.filter(date=day).exists())
                self.assertTrue(
                    DailySalonMetric.objects.filter(
                        date=day,
                        salon=salon,
                    ).exists()
                )
                self.assertTrue(
                    DailyStaffMetric.objects.filter(
                        date=day,
                        salon=salon,
                        stylist=stylist,
                    ).exists()
                )

                # Analytics and export processing must not
                # create additional financial artifacts.
                self.assertEqual(
                    Payment.objects.count(),
                    financial_counts_after_finalization["payments"],
                )
                self.assertEqual(
                    WalletTransaction.objects.count(),
                    financial_counts_after_finalization["wallet_transactions"],
                )
                self.assertEqual(
                    LedgerEntry.objects.count(),
                    financial_counts_after_finalization["ledger_entries"],
                )
                self.assertEqual(
                    StaffEarning.objects.count(),
                    financial_counts_after_finalization["staff_earnings"],
                )
                self.assertEqual(
                    OrderDetailFinancialSnapshot.objects.count(),
                    financial_counts_after_finalization["snapshots"],
                )
