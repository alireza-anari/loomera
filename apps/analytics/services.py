from __future__ import annotations
import csv, io
from datetime import date, datetime, timedelta
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from tempfile import SpooledTemporaryFile

from django.core.files import File
from django.db import connection, transaction
from django.db.models import (
    Avg,
    Count,
    Exists,
    Min,
    OuterRef,
    Q,
    Sum,
)
from django.utils import timezone
from .models import (
    AnalyticsEvent,
    DailyPlatformMetric,
    DailySalonMetric,
    DailyStaffMetric,
    DailyContentMetric,
    DailySearchMetric,
    ReportExportJob,
)

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


REPORT_EXPORT_CLEANUP_BATCH_SIZE = 100

DAILY_SALON_METRIC_UPDATE_FIELDS = (
    "appointments_count",
    "completed_count",
    "cancelled_count",
    "no_show_count",
    "late_count",
    "overrun_count",
    "unique_customers",
    "new_customers",
    "repeat_customers",
    "gross_revenue",
    "customer_paid_total",
    "platform_commission",
    "salon_net_profit",
    "staff_payout_total",
    "material_cost_total",
    "reviews_count",
    "average_rating",
)

DAILY_STAFF_METRIC_UPDATE_FIELDS = (
    "appointments_count",
    "completed_count",
    "late_count",
    "overrun_count",
    "no_show_count",
    "gross_share",
    "net_profit",
    "material_deduction",
    "payable_amount",
    "reviews_count",
    "average_rating",
    "updated_at",
)

DAILY_CONTENT_METRIC_UPDATE_FIELDS = (
    "content_kind",
    "salon",
    "views",
    "cta_clicks",
    "reports_count",
    "updated_at",
)

DAILY_SEARCH_METRIC_UPDATE_FIELDS = (
    "query",
    "searches_count",
    "results_total",
    "no_result_count",
    "clicks_count",
    "booking_starts",
    "booking_completed",
    "updated_at",
)

DAILY_PLATFORM_METRIC_UPDATE_FIELDS = (
    "users_total",
    "customers_total",
    "salons_total",
    "stylists_total",
    "appointments_count",
    "completed_count",
    "cancelled_count",
    "no_show_count",
    "disputed_count",
    "gross_revenue",
    "customer_paid_total",
    "platform_commission",
    "salon_net_profit",
    "staff_net_profit",
    "material_cost_total",
    "content_reports_count",
    "support_open_count",
    "disputes_open_count",
    "notifications_failed_count",
    "searches_count",
    "no_result_searches_count",
    "updated_at",
)

REPORT_EXPORT_ITERATOR_CHUNK_SIZE = 1000

REPORT_EXPORT_SPOOL_MAX_SIZE = 5 * 1024 * 1024


def _day_bounds(day: date):
    tz = timezone.get_current_timezone()
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    return timezone.make_aware(start, tz), timezone.make_aware(end, tz)


def _i(v):
    try:
        return int(v or 0)
    except Exception:
        return 0


def _avg(v):
    try:
        return Decimal(str(v or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def record_analytics_event(
    *,
    category,
    event_type,
    actor=None,
    salon=None,
    stylist=None,
    order=None,
    order_detail=None,
    target=None,
    occurred_at=None,
    source="",
    session_key="",
    metadata=None,
    request=None,
):
    try:
        ct = obj_id = None
        if target is not None:
            ct = ContentType.objects.get_for_model(target, for_concrete_model=False)
            obj_id = getattr(target, "pk", None)
        ip = None
        ua = ""
        if request is not None:
            actor = actor or getattr(request, "user", None)
            if getattr(actor, "is_anonymous", False):
                actor = None
            session_key = (
                session_key
                or getattr(getattr(request, "session", None), "session_key", "")
                or ""
            )
            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
                0
            ].strip() or request.META.get("REMOTE_ADDR")
            ua = request.META.get("HTTP_USER_AGENT", "")[:1000]
        return AnalyticsEvent.objects.create(
            category=category,
            event_type=event_type,
            occurred_at=occurred_at or timezone.now(),
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            salon=salon,
            stylist=stylist,
            order=order,
            order_detail=order_detail,
            target_content_type=ct,
            target_object_id=obj_id,
            source=source or "",
            session_key=session_key or "",
            metadata=metadata or {},
            ip_address=ip,
            user_agent=ua,
        )
    except Exception:
        return None


def _collect_daily_platform_metric_payload(day):
    """Collect the platform-wide daily snapshot with a fixed query budget.

    Platform totals, open operational counters and daily event counters keep
    their previous semantics. Appointment and search counters are consolidated
    into one aggregate query per model.
    """

    from django.contrib.auth import get_user_model

    from apps.accounts.models import Customer, Stylist
    from apps.articles.models import ContentReport
    from apps.main.models import DisputeCase, SupportTicket
    from apps.notifications.models import (
        NotificationDelivery,
        NotificationDeliveryStatus,
    )
    from apps.orders.models import OrderDetail
    from apps.payments.models import (
        OrderDetailFinancialSnapshot,
    )
    from apps.salons.models import Salon
    from apps.search.models import SearchLog

    start, end = _day_bounds(day)
    User = get_user_model()

    appointment_metrics = OrderDetail.objects.filter(
        date=day,
    ).aggregate(
        appointments_count=Count("id"),
        completed_count=Count(
            "id",
            filter=Q(
                lifecycle_status="completed",
            ),
        ),
        cancelled_count=Count(
            "id",
            filter=Q(
                order__status="cancelled",
            ),
        ),
        no_show_count=Count(
            "id",
            filter=Q(
                lifecycle_status__in=[
                    "no_show_pending_review",
                    "no_show_confirmed",
                ],
            ),
        ),
        disputed_count=Count(
            "id",
            filter=Q(
                lifecycle_status="disputed",
            ),
        ),
    )

    financial_metrics = OrderDetailFinancialSnapshot.objects.filter(
        order_detail__date=day,
    ).aggregate(
        gross_revenue=Sum("gross_amount"),
        customer_paid_total=Sum("total_customer_paid"),
        platform_commission=Sum("platform_commission_allocated"),
        salon_net_profit=Sum("salon_net_profit"),
        staff_net_profit=Sum("stylist_net_share"),
        material_cost_total=Sum("material_cost_total"),
    )

    search_metrics = SearchLog.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
    ).aggregate(
        searches_count=Count("id"),
        no_result_searches_count=Count(
            "id",
            filter=Q(no_result=True),
        ),
    )

    return {
        # These are cumulative platform totals, preserving the old behavior.
        "users_total": User.objects.count(),
        "customers_total": Customer.objects.count(),
        "salons_total": Salon.objects.count(),
        "stylists_total": Stylist.objects.count(),
        "appointments_count": _i(appointment_metrics["appointments_count"]),
        "completed_count": _i(appointment_metrics["completed_count"]),
        "cancelled_count": _i(appointment_metrics["cancelled_count"]),
        "no_show_count": _i(appointment_metrics["no_show_count"]),
        "disputed_count": _i(appointment_metrics["disputed_count"]),
        "gross_revenue": _i(financial_metrics["gross_revenue"]),
        "customer_paid_total": _i(financial_metrics["customer_paid_total"]),
        "platform_commission": _i(financial_metrics["platform_commission"]),
        "salon_net_profit": _i(financial_metrics["salon_net_profit"]),
        "staff_net_profit": _i(financial_metrics["staff_net_profit"]),
        "material_cost_total": _i(financial_metrics["material_cost_total"]),
        "content_reports_count": (
            ContentReport.objects.filter(
                created_at__gte=start,
                created_at__lt=end,
            ).count()
        ),
        # Preserve the previous definitions exactly.
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
        "searches_count": _i(search_metrics["searches_count"]),
        "no_result_searches_count": _i(search_metrics["no_result_searches_count"]),
    }


@transaction.atomic
def build_daily_platform_metric(day):
    """Build the daily platform snapshot with aggregate reads and one upsert."""

    payload = _collect_daily_platform_metric_payload(day)

    metric = DailyPlatformMetric(
        date=day,
        updated_at=timezone.now(),
        **payload,
    )

    results = DailyPlatformMetric.objects.bulk_create(
        [metric],
        update_conflicts=True,
        update_fields=list(DAILY_PLATFORM_METRIC_UPDATE_FIELDS),
        unique_fields=[
            "date",
        ],
    )

    return results[0]


def _report_export_retention_delta():
    """Return the configured report-export retention period."""

    raw_days = getattr(
        settings,
        "LOOMERA_EXPORT_RETENTION_DAYS",
        7,
    )

    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        days = 7

    return timedelta(
        days=max(days, 1),
    )


def _report_export_cleanup_queryset(
    *,
    now=None,
):
    """Return export jobs whose files and metadata may be removed.

    Modern completed jobs use expires_at. Legacy rows without expires_at
    fall back to completed_at or created_at and the configured retention.
    Failed and already-expired rows use the same retention fallback.
    """

    now = now or timezone.now()

    legacy_cutoff = now - _report_export_retention_delta()

    completed_legacy_scope = Q(
        status=(ReportExportJob.Status.COMPLETED),
        expires_at__isnull=True,
        completed_at__lt=legacy_cutoff,
    ) | Q(
        status=(ReportExportJob.Status.COMPLETED),
        expires_at__isnull=True,
        completed_at__isnull=True,
        created_at__lt=legacy_cutoff,
    )

    failed_scope = Q(
        status=(ReportExportJob.Status.FAILED),
        completed_at__lt=legacy_cutoff,
    ) | Q(
        status=(ReportExportJob.Status.FAILED),
        completed_at__isnull=True,
        created_at__lt=legacy_cutoff,
    )

    expired_scope = Q(
        status=(ReportExportJob.Status.EXPIRED),
        updated_at__lt=legacy_cutoff,
    )

    return (
        ReportExportJob.objects.filter(
            Q(
                status=(ReportExportJob.Status.COMPLETED),
                expires_at__lte=now,
            )
            | completed_legacy_scope
            | failed_scope
            | expired_scope
        )
        .only(
            "id",
            "status",
            "file",
            "expires_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        .order_by(
            "expires_at",
            "created_at",
            "pk",
        )
    )


def _delete_report_export_file(job):
    """Delete the export file from its configured storage backend."""

    if not job.file:
        return False

    file_name = (job.file.name or "").strip()

    if not file_name:
        return False

    job.file.storage.delete(file_name)

    return True


def cleanup_expired_report_exports(
    *,
    now=None,
    dry_run=False,
    limit=REPORT_EXPORT_CLEANUP_BATCH_SIZE,
):
    """Delete expired export files and their database rows safely."""

    now = now or timezone.now()

    try:
        limit = max(
            int(limit),
            0,
        )
    except (TypeError, ValueError):
        limit = REPORT_EXPORT_CLEANUP_BATCH_SIZE

    stats = {
        "matched": 0,
        "deleted": 0,
        "files_deleted": 0,
        "failed": 0,
    }

    if limit == 0:
        return stats

    jobs = list(
        _report_export_cleanup_queryset(
            now=now,
        )[:limit]
    )

    stats["matched"] = len(jobs)

    if dry_run or not jobs:
        return stats

    deletable_ids = []

    for job in jobs:
        try:
            file_deleted = _delete_report_export_file(job)
        except Exception:
            stats["failed"] += 1

            logger.exception(
                "Failed to delete report export file. " "job_id=%s file=%s",
                job.pk,
                getattr(
                    job.file,
                    "name",
                    "",
                ),
            )

            # Keep the database row so the cleanup can be retried.
            continue

        if file_deleted:
            stats["files_deleted"] += 1

        deletable_ids.append(job.pk)

    if deletable_ids:
        _total_deleted, deleted_by_model = ReportExportJob.objects.filter(
            pk__in=deletable_ids,
        ).delete()

        stats["deleted"] = deleted_by_model.get(
            ReportExportJob._meta.label,
            0,
        )

    return stats


def _collect_daily_salon_metric_payloads(day):
    """Collect all salon metric payloads using five fixed read queries.

    Only salons that have at least one OrderDetail on ``day`` are included,
    matching the previous implementation.

    A customer is considered new when they have no appointment in the same
    salon before ``day``. This is equivalent to the previous
    ``first_appointment.date == day`` behavior.
    """

    from apps.comments_scores_favories.models import (
        Comments,
        Scoring,
    )
    from apps.orders.models import OrderDetail
    from apps.payments.models import (
        OrderDetailFinancialSnapshot,
    )

    appointment_rows = list(
        OrderDetail.objects.filter(
            date=day,
        )
        .order_by()
        .values("salon_id")
        .annotate(
            appointments_count=Count("id"),
            completed_count=Count(
                "id",
                filter=Q(
                    lifecycle_status="completed",
                ),
            ),
            cancelled_count=Count(
                "id",
                filter=Q(
                    order__status="cancelled",
                ),
            ),
            no_show_count=Count(
                "id",
                filter=Q(
                    lifecycle_status__in=[
                        "no_show_pending_review",
                        "no_show_confirmed",
                    ],
                ),
            ),
            late_count=Count(
                "id",
                filter=Q(
                    client_late_recorded_at__isnull=False,
                ),
            ),
            overrun_count=Count(
                "id",
                filter=Q(
                    service_overrun_recorded_at__isnull=False,
                ),
            ),
        )
    )

    if not appointment_rows:
        return []

    payloads = {}

    for row in appointment_rows:
        salon_id = row["salon_id"]

        payloads[salon_id] = {
            "salon_id": salon_id,
            "appointments_count": _i(row["appointments_count"]),
            "completed_count": _i(row["completed_count"]),
            "cancelled_count": _i(row["cancelled_count"]),
            "no_show_count": _i(row["no_show_count"]),
            "late_count": _i(row["late_count"]),
            "overrun_count": _i(row["overrun_count"]),
            "unique_customers": 0,
            "new_customers": 0,
            "repeat_customers": 0,
            "gross_revenue": 0,
            "customer_paid_total": 0,
            "platform_commission": 0,
            "salon_net_profit": 0,
            "staff_payout_total": 0,
            "material_cost_total": 0,
            "reviews_count": 0,
            "average_rating": Decimal("0.00"),
        }

    salon_ids = list(payloads)

    prior_appointment = OrderDetail.objects.filter(
        salon_id=OuterRef("salon_id"),
        order__customer_id=OuterRef("order__customer_id"),
        date__lt=day,
    )

    customer_rows = list(
        OrderDetail.objects.filter(
            date=day,
            salon_id__in=salon_ids,
        )
        .order_by()
        .values(
            "salon_id",
            "order__customer_id",
        )
        .annotate(has_prior_appointment=Exists(prior_appointment))
        .distinct()
    )

    for row in customer_rows:
        payload = payloads[row["salon_id"]]

        payload["unique_customers"] += 1

        if not row["has_prior_appointment"]:
            payload["new_customers"] += 1

    financial_rows = list(
        OrderDetailFinancialSnapshot.objects.filter(
            order_detail__date=day,
            salon_id__in=salon_ids,
        )
        .order_by()
        .values("salon_id")
        .annotate(
            gross_revenue=Sum("gross_amount"),
            customer_paid_total=Sum("total_customer_paid"),
            platform_commission=Sum("platform_commission_allocated"),
            salon_net_profit=Sum("salon_net_profit"),
            staff_payout_total=Sum("stylist_net_share"),
            material_cost_total=Sum("material_cost_total"),
        )
    )

    for row in financial_rows:
        payload = payloads[row["salon_id"]]

        payload["gross_revenue"] = _i(row["gross_revenue"])
        payload["customer_paid_total"] = _i(row["customer_paid_total"])
        payload["platform_commission"] = _i(row["platform_commission"])
        payload["salon_net_profit"] = _i(row["salon_net_profit"])
        payload["staff_payout_total"] = _i(row["staff_payout_total"])
        payload["material_cost_total"] = _i(row["material_cost_total"])

    review_rows = list(
        Comments.objects.filter(
            salon_id__in=salon_ids,
            is_active=True,
            register_date=day,
        )
        .order_by()
        .values("salon_id")
        .annotate(
            reviews_count=Count("id"),
        )
    )

    for row in review_rows:
        payloads[row["salon_id"]]["reviews_count"] = _i(row["reviews_count"])

    rating_rows = list(
        Scoring.objects.filter(
            salon_id__in=salon_ids,
            register_date=day,
        )
        .order_by()
        .values("salon_id")
        .annotate(
            average_rating=Avg("score"),
        )
    )

    for row in rating_rows:
        payloads[row["salon_id"]]["average_rating"] = _avg(row["average_rating"])

    for payload in payloads.values():
        payload["repeat_customers"] = max(
            payload["unique_customers"] - payload["new_customers"],
            0,
        )

    return [payloads[salon_id] for salon_id in sorted(payloads)]


@transaction.atomic
def build_daily_salon_metrics(day):
    """Build or update all daily salon metrics with a fixed query budget."""

    payloads = _collect_daily_salon_metric_payloads(day)

    if not payloads:
        return []

    metrics = [
        DailySalonMetric(
            date=day,
            **payload,
        )
        for payload in payloads
    ]

    return DailySalonMetric.objects.bulk_create(
        metrics,
        update_conflicts=True,
        update_fields=list(DAILY_SALON_METRIC_UPDATE_FIELDS),
        unique_fields=[
            "salon",
            "date",
        ],
    )


def _collect_daily_staff_metric_payloads(day):
    """Collect all staff metrics with four fixed read queries.

    Metrics are grouped by both stylist and salon because the same stylist
    may work in multiple salons with separate appointments and earnings.

    Only stylist/salon pairs with at least one OrderDetail on the requested
    day are returned, preserving the previous behavior.
    """

    from apps.comments_scores_favories.models import (
        Comments,
        Scoring,
    )
    from apps.orders.models import OrderDetail
    from apps.payments.models import StaffEarning

    appointment_rows = list(
        OrderDetail.objects.filter(
            date=day,
        )
        .order_by()
        .values(
            "stylist_id",
            "salon_id",
        )
        .annotate(
            appointments_count=Count("id"),
            completed_count=Count(
                "id",
                filter=Q(
                    lifecycle_status="completed",
                ),
            ),
            late_count=Count(
                "id",
                filter=Q(
                    client_late_recorded_at__isnull=False,
                ),
            ),
            overrun_count=Count(
                "id",
                filter=Q(
                    service_overrun_recorded_at__isnull=False,
                ),
            ),
            no_show_count=Count(
                "id",
                filter=Q(
                    lifecycle_status__in=[
                        "no_show_pending_review",
                        "no_show_confirmed",
                    ],
                ),
            ),
        )
    )

    if not appointment_rows:
        return []

    payloads = {}

    for row in appointment_rows:
        key = (
            row["stylist_id"],
            row["salon_id"],
        )

        payloads[key] = {
            "stylist_id": row["stylist_id"],
            "salon_id": row["salon_id"],
            "appointments_count": _i(row["appointments_count"]),
            "completed_count": _i(row["completed_count"]),
            "late_count": _i(row["late_count"]),
            "overrun_count": _i(row["overrun_count"]),
            "no_show_count": _i(row["no_show_count"]),
            "gross_share": 0,
            "net_profit": 0,
            "material_deduction": 0,
            "payable_amount": 0,
            "reviews_count": 0,
            "average_rating": Decimal("0.00"),
        }

    earning_rows = list(
        StaffEarning.objects.filter(
            order_detail__date=day,
        )
        .order_by()
        .values(
            "stylist_id",
            "salon_id",
        )
        .annotate(
            total_gross_share=Sum("gross_share"),
            total_net_profit=Sum("net_profit"),
            total_material_deduction=Sum("material_deduction"),
            total_payable_amount=Sum(
                "net_profit",
                filter=Q(
                    status=StaffEarning.Status.PAYABLE,
                ),
            ),
        )
    )
    for row in earning_rows:
        key = (
            row["stylist_id"],
            row["salon_id"],
        )

        payload = payloads.get(key)

        if payload is None:
            continue

        payload["gross_share"] = _i(row["total_gross_share"])
        payload["net_profit"] = _i(row["total_net_profit"])
        payload["material_deduction"] = _i(row["total_material_deduction"])
        payload["payable_amount"] = _i(row["total_payable_amount"])

    review_rows = list(
        Comments.objects.filter(
            register_date=day,
            is_active=True,
            stylist_id__isnull=False,
            salon_id__isnull=False,
        )
        .order_by()
        .values(
            "stylist_id",
            "salon_id",
        )
        .annotate(
            reviews_count=Count("id"),
        )
    )

    for row in review_rows:
        key = (
            row["stylist_id"],
            row["salon_id"],
        )

        payload = payloads.get(key)

        if payload is not None:
            payload["reviews_count"] = _i(row["reviews_count"])

    rating_rows = list(
        Scoring.objects.filter(
            register_date=day,
            stylist_id__isnull=False,
            salon_id__isnull=False,
        )
        .order_by()
        .values(
            "stylist_id",
            "salon_id",
        )
        .annotate(
            average_rating=Avg("score"),
        )
    )

    for row in rating_rows:
        key = (
            row["stylist_id"],
            row["salon_id"],
        )

        payload = payloads.get(key)

        if payload is not None:
            payload["average_rating"] = _avg(row["average_rating"])

    return [
        payloads[key]
        for key in sorted(
            payloads,
            key=lambda item: (
                item[1],  # salon_id
                item[0],  # stylist_id
            ),
        )
    ]


@transaction.atomic
def build_daily_staff_metrics(day):
    """Build or update all daily staff metrics with a fixed query budget."""

    payloads = _collect_daily_staff_metric_payloads(day)

    if not payloads:
        return []

    updated_at = timezone.now()

    metrics = [
        DailyStaffMetric(
            date=day,
            updated_at=updated_at,
            **payload,
        )
        for payload in payloads
    ]

    return DailyStaffMetric.objects.bulk_create(
        metrics,
        update_conflicts=True,
        update_fields=list(DAILY_STAFF_METRIC_UPDATE_FIELDS),
        unique_fields=[
            "stylist",
            "salon",
            "date",
        ],
    )


def _collect_daily_content_metric_payloads(day):
    """Collect all daily content payloads with a fixed query budget.

    The existing per-model limit of 1000 objects is intentionally preserved.
    Views and clicks remain cumulative snapshots from the source models.
    """

    from apps.accounts.models import WorkSamples
    from apps.articles.models import (
        Article,
        ContentReport,
        SalonStory,
    )

    start, end = _day_bounds(day)

    model_specs = (
        {
            "model": Article,
            "kind": "article",
            "salon_field": "author_salon_id",
            "views_field": "view_count",
            "clicks_field": None,
        },
        {
            "model": SalonStory,
            "kind": "story",
            "salon_field": "salon_id",
            "views_field": "view_count",
            "clicks_field": "click_count",
        },
        {
            "model": WorkSamples,
            "kind": "work_sample",
            "salon_field": "salon_id",
            "views_field": None,
            "clicks_field": "like_count",
        },
    )

    content_types = ContentType.objects.get_for_models(
        Article,
        SalonStory,
        WorkSamples,
        for_concrete_models=False,
    )

    payloads = []
    payload_by_target = {}
    object_ids_by_content_type = {}

    for spec in model_specs:
        model = spec["model"]
        content_type = content_types[model]

        selected_fields = [
            "pk",
            spec["salon_field"],
        ]

        if spec["views_field"]:
            selected_fields.append(spec["views_field"])

        if spec["clicks_field"]:
            selected_fields.append(spec["clicks_field"])

        # Do not clear model ordering here. The previous implementation used
        # Model.objects.all()[:1000], so its default ordering is preserved.
        rows = list(model.objects.values(*selected_fields)[:1000])

        target_ids = []

        for row in rows:
            object_id = row["pk"]
            target_ids.append(object_id)

            payload = {
                "content_type_id": content_type.pk,
                "object_id": object_id,
                "content_kind": spec["kind"],
                "salon_id": row[spec["salon_field"]],
                "views": _i(row.get(spec["views_field"]) if spec["views_field"] else 0),
                "cta_clicks": _i(
                    row.get(spec["clicks_field"]) if spec["clicks_field"] else 0
                ),
                "reports_count": 0,
            }

            payloads.append(payload)

            payload_by_target[
                (
                    content_type.pk,
                    object_id,
                )
            ] = payload

        object_ids_by_content_type[content_type.pk] = target_ids

    reports_scope = Q()
    has_report_targets = False

    for content_type_id, object_ids in object_ids_by_content_type.items():
        if not object_ids:
            continue

        has_report_targets = True
        reports_scope |= Q(
            target_content_type_id=content_type_id,
            target_object_id__in=object_ids,
        )

    if has_report_targets:
        report_rows = (
            ContentReport.objects.filter(
                reports_scope,
                created_at__gte=start,
                created_at__lt=end,
            )
            .order_by()
            .values(
                "target_content_type_id",
                "target_object_id",
            )
            .annotate(
                reports_count=Count("id"),
            )
        )

        for row in report_rows:
            payload = payload_by_target.get(
                (
                    row["target_content_type_id"],
                    row["target_object_id"],
                )
            )

            if payload is not None:
                payload["reports_count"] = _i(row["reports_count"])

    return payloads


@transaction.atomic
def build_daily_content_metrics(day):
    """Build daily content snapshots with a fixed query budget."""

    payloads = _collect_daily_content_metric_payloads(day)

    if not payloads:
        return []

    updated_at = timezone.now()

    metrics = [
        DailyContentMetric(
            date=day,
            updated_at=updated_at,
            **payload,
        )
        for payload in payloads
    ]

    return DailyContentMetric.objects.bulk_create(
        metrics,
        update_conflicts=True,
        update_fields=list(DAILY_CONTENT_METRIC_UPDATE_FIELDS),
        unique_fields=[
            "content_type",
            "object_id",
            "date",
        ],
    )


def _collect_daily_search_metric_payloads(day):
    """Collect daily search metrics using three fixed read queries.

    Search logs are grouped by normalized query because DailySearchMetric has
    one unique row for each date/normalized-query/filters-hash combination.

    Clicks and conversions are counted only when both the source SearchLog and
    the related event belong to the requested day. This preserves the previous
    event-window behavior.
    """

    from apps.search.models import (
        SearchConversion,
        SearchLog,
        SearchResultClick,
    )

    start, end = _day_bounds(day)

    logs = SearchLog.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
    )

    log_rows = list(
        logs.order_by()
        .values("normalized_query")
        .annotate(
            representative_query=Min("query"),
            searches_count=Count("id"),
            results_total=Sum("results_count"),
            no_result_count=Count(
                "id",
                filter=Q(no_result=True),
            ),
        )
        .order_by("normalized_query")
    )

    if not log_rows:
        return []

    payloads = {}

    for row in log_rows:
        normalized_query = row["normalized_query"] or ""

        payloads[normalized_query] = {
            "normalized_query": normalized_query,
            "query": (row["representative_query"] or normalized_query),
            "filters_hash": "",
            "searches_count": _i(row["searches_count"]),
            "results_total": _i(row["results_total"]),
            "no_result_count": _i(row["no_result_count"]),
            "clicks_count": 0,
            "booking_starts": 0,
            "booking_completed": 0,
        }

    click_rows = list(
        SearchResultClick.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            search_log__created_at__gte=start,
            search_log__created_at__lt=end,
        )
        .order_by()
        .values(
            "search_log__normalized_query",
        )
        .annotate(
            clicks_count=Count("id"),
        )
    )

    for row in click_rows:
        normalized_query = row["search_log__normalized_query"] or ""

        payload = payloads.get(normalized_query)

        if payload is not None:
            payload["clicks_count"] = _i(row["clicks_count"])

    conversion_rows = list(
        SearchConversion.objects.filter(
            created_at__gte=start,
            created_at__lt=end,
            search_log__created_at__gte=start,
            search_log__created_at__lt=end,
        )
        .order_by()
        .values(
            "search_log__normalized_query",
        )
        .annotate(
            booking_starts=Count(
                "id",
                filter=Q(
                    conversion_type=("booking_started"),
                ),
            ),
            booking_completed=Count(
                "id",
                filter=Q(
                    conversion_type=("booking_completed"),
                ),
            ),
        )
    )

    for row in conversion_rows:
        normalized_query = row["search_log__normalized_query"] or ""

        payload = payloads.get(normalized_query)

        if payload is not None:
            payload["booking_starts"] = _i(row["booking_starts"])
            payload["booking_completed"] = _i(row["booking_completed"])

    return [payloads[normalized_query] for normalized_query in sorted(payloads)]


@transaction.atomic
def build_daily_search_metrics(day):
    """Build daily search metrics with a fixed query budget."""

    payloads = _collect_daily_search_metric_payloads(day)

    if not payloads:
        return []

    updated_at = timezone.now()

    metrics = [
        DailySearchMetric(
            date=day,
            updated_at=updated_at,
            **payload,
        )
        for payload in payloads
    ]

    return DailySearchMetric.objects.bulk_create(
        metrics,
        update_conflicts=True,
        update_fields=list(DAILY_SEARCH_METRIC_UPDATE_FIELDS),
        unique_fields=[
            "date",
            "normalized_query",
            "filters_hash",
        ],
    )


def build_daily_metrics(day=None):
    day = day or timezone.localdate()
    return {
        "platform": build_daily_platform_metric(day),
        "salons": build_daily_salon_metrics(day),
        "staff": build_daily_staff_metrics(day),
        "content": build_daily_content_metrics(day),
        "search": build_daily_search_metrics(day),
    }


def create_report_export_job(*, user, report_type, filters=None):
    return ReportExportJob.objects.create(
        requested_by=user, report_type=report_type, filters=filters or {}
    )


def _filter(qs, filters):
    if filters.get("start_date"):
        qs = qs.filter(date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(date__lte=filters["end_date"])
    return qs


def _rows(job):
    """Return a CSV header and a chunked values iterator.

    Only columns required by the selected report are fetched. Using
    values_list() avoids model construction, while iterator() prevents
    Django from caching the complete queryset in memory.
    """

    filters = job.filters or {}
    report_type = job.report_type

    if report_type == ReportExportJob.ReportType.SALON_DAILY:
        queryset = _filter(
            DailySalonMetric.objects.order_by(
                "date",
                "pk",
            ),
            filters,
        )

        if filters.get("salon_id"):
            queryset = queryset.filter(
                salon_id=filters["salon_id"],
            )

        rows = queryset.values_list(
            "date",
            "salon_id",
            "appointments_count",
            "completed_count",
            "gross_revenue",
            "salon_net_profit",
        )

        return (
            [
                "date",
                "salon",
                "appointments",
                "completed",
                "gross",
                "profit",
            ],
            rows.iterator(
                chunk_size=(REPORT_EXPORT_ITERATOR_CHUNK_SIZE),
            ),
        )

    if report_type == ReportExportJob.ReportType.STAFF_DAILY:
        queryset = _filter(
            DailyStaffMetric.objects.order_by(
                "date",
                "pk",
            ),
            filters,
        )

        rows = queryset.values_list(
            "date",
            "stylist_id",
            "salon_id",
            "appointments_count",
            "completed_count",
            "net_profit",
        )

        return (
            [
                "date",
                "stylist",
                "salon",
                "appointments",
                "completed",
                "net",
            ],
            rows.iterator(
                chunk_size=(REPORT_EXPORT_ITERATOR_CHUNK_SIZE),
            ),
        )

    if report_type == ReportExportJob.ReportType.CONTENT_DAILY:
        queryset = _filter(
            DailyContentMetric.objects.order_by(
                "date",
                "pk",
            ),
            filters,
        )

        rows = queryset.values_list(
            "date",
            "content_kind",
            "object_id",
            "salon_id",
            "views",
            "cta_clicks",
            "reports_count",
        )

        return (
            [
                "date",
                "kind",
                "object",
                "salon",
                "views",
                "clicks",
                "reports",
            ],
            rows.iterator(
                chunk_size=(REPORT_EXPORT_ITERATOR_CHUNK_SIZE),
            ),
        )

    if report_type == ReportExportJob.ReportType.SEARCH_DAILY:
        queryset = _filter(
            DailySearchMetric.objects.order_by(
                "date",
                "pk",
            ),
            filters,
        )

        rows = queryset.values_list(
            "date",
            "normalized_query",
            "searches_count",
            "results_total",
            "no_result_count",
            "clicks_count",
            "booking_completed",
        )

        return (
            [
                "date",
                "query",
                "searches",
                "results",
                "no_result",
                "clicks",
                "booked",
            ],
            rows.iterator(
                chunk_size=(REPORT_EXPORT_ITERATOR_CHUNK_SIZE),
            ),
        )

    queryset = _filter(
        DailyPlatformMetric.objects.order_by(
            "date",
            "pk",
        ),
        filters,
    )

    rows = queryset.values_list(
        "date",
        "appointments_count",
        "completed_count",
        "gross_revenue",
        "salon_net_profit",
        "staff_net_profit",
        "searches_count",
    )

    return (
        [
            "date",
            "appointments",
            "completed",
            "gross",
            "salon_profit",
            "staff_profit",
            "searches",
        ],
        rows.iterator(
            chunk_size=(REPORT_EXPORT_ITERATOR_CHUNK_SIZE),
        ),
    )


def _write_report_export_csv(
    job,
    binary_output,
):
    """Write one report to a binary stream without buffering it twice."""

    header, rows = _rows(job)

    # Preserve Excel-compatible UTF-8 BOM.
    binary_output.write(b"\xef\xbb\xbf")

    text_output = io.TextIOWrapper(
        binary_output,
        encoding="utf-8",
        newline="",
        write_through=True,
    )

    rows_count = 0

    try:
        writer = csv.writer(text_output)
        writer.writerow(header)

        for row in rows:
            writer.writerow(row)
            rows_count += 1

        text_output.flush()
    finally:
        # Keep the underlying SpooledTemporaryFile open.
        text_output.detach()

    return rows_count


def _mark_report_export_job_processing(job):
    """Atomically claim one pending export job.

    Returning False means another worker already claimed or completed the
    job, so the caller must not generate or upload its file.
    """

    if not job.pk:
        return False

    started_at = timezone.now()

    updated = ReportExportJob.objects.filter(
        pk=job.pk,
        status=(ReportExportJob.Status.PENDING),
    ).update(
        status=(ReportExportJob.Status.PROCESSING),
        started_at=started_at,
        error_message="",
        updated_at=started_at,
    )

    if updated != 1:
        job.refresh_from_db()
        return False

    job.status = ReportExportJob.Status.PROCESSING
    job.started_at = started_at
    job.error_message = ""
    job.updated_at = started_at

    return True


def _process_claimed_report_export_job(job):
    """Generate and store a job that has already been claimed."""

    if job.status != ReportExportJob.Status.PROCESSING:
        return job

    try:
        with SpooledTemporaryFile(
            max_size=(REPORT_EXPORT_SPOOL_MAX_SIZE),
            mode="w+b",
        ) as output:
            rows_count = _write_report_export_csv(
                job,
                output,
            )

            output.seek(0)

            filename = f"{job.report_type}_" f"{timezone.now():%Y%m%d_%H%M%S}" ".csv"

            job.file.save(
                filename,
                File(output),
                save=False,
            )

        completed_at = timezone.now()

        job.rows_count = rows_count
        job.status = ReportExportJob.Status.COMPLETED
        job.completed_at = completed_at
        job.expires_at = completed_at + _report_export_retention_delta()

        job.save(
            update_fields=[
                "file",
                "rows_count",
                "status",
                "completed_at",
                "expires_at",
                "updated_at",
            ]
        )

    except Exception as exc:
        job.status = ReportExportJob.Status.FAILED
        job.error_message = str(exc)[:1000]
        job.completed_at = timezone.now()

        job.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )

    return job


def _report_export_stale_after():
    """Return the configured stale-processing timeout."""

    raw_minutes = getattr(
        settings,
        "LOOMERA_REPORT_EXPORT_STALE_AFTER_MINUTES",
        60,
    )

    try:
        minutes = int(raw_minutes)
    except (TypeError, ValueError):
        minutes = 60

    return timedelta(
        minutes=max(minutes, 1),
    )


def _recover_stale_report_export_jobs(
    *,
    now=None,
):
    """Return stale processing jobs to the pending queue.

    A processing job is considered stale when its started_at is older than
    the configured timeout. Processing rows without started_at are invalid
    legacy/incomplete claims and are also recovered.
    """

    now = now or timezone.now()

    stale_before = now - _report_export_stale_after()

    return (
        ReportExportJob.objects.filter(
            status=(ReportExportJob.Status.PROCESSING),
        )
        .filter(
            Q(
                started_at__lt=stale_before,
            )
            | Q(
                started_at__isnull=True,
            )
        )
        .update(
            status=(ReportExportJob.Status.PENDING),
            started_at=None,
            completed_at=None,
            expires_at=None,
            rows_count=0,
            error_message="",
            updated_at=now,
        )
    )


def process_report_export_job(job):
    """Claim and process one pending export job safely."""

    claimed = _mark_report_export_job_processing(job)

    if not claimed:
        return job

    return _process_claimed_report_export_job(job)


def _claim_pending_report_export_jobs(
    limit=10,
):
    """Recover stale jobs and claim a non-overlapping pending batch."""

    try:
        limit = max(
            int(limit),
            0,
        )
    except (TypeError, ValueError):
        limit = 10

    if limit == 0:
        return []

    lock_options = {}

    if connection.features.has_select_for_update_skip_locked:
        lock_options["skip_locked"] = True

    with transaction.atomic():
        started_at = timezone.now()

        # Recovery and claim happen in the same short transaction.
        _recover_stale_report_export_jobs(
            now=started_at,
        )

        jobs = list(
            ReportExportJob.objects.select_for_update(**lock_options)
            .filter(
                status=(ReportExportJob.Status.PENDING),
            )
            .only(
                "id",
                "report_type",
                "filters",
                "status",
                "file",
                "created_at",
            )
            .order_by(
                "created_at",
                "pk",
            )[:limit]
        )

        if not jobs:
            return []

        job_ids = [job.pk for job in jobs]

        updated = ReportExportJob.objects.filter(
            pk__in=job_ids,
            status=(ReportExportJob.Status.PENDING),
        ).update(
            status=(ReportExportJob.Status.PROCESSING),
            started_at=started_at,
            error_message="",
            updated_at=started_at,
        )

        if updated != len(jobs):
            claimed_ids = set(
                ReportExportJob.objects.filter(
                    pk__in=job_ids,
                    status=(ReportExportJob.Status.PROCESSING),
                    started_at=started_at,
                ).values_list(
                    "pk",
                    flat=True,
                )
            )

            jobs = [job for job in jobs if job.pk in claimed_ids]

        for job in jobs:
            job.status = ReportExportJob.Status.PROCESSING
            job.started_at = started_at
            job.error_message = ""
            job.updated_at = started_at

    return jobs


def process_pending_report_exports(
    limit=10,
):
    jobs = _claim_pending_report_export_jobs(
        limit=limit,
    )

    for job in jobs:
        _process_claimed_report_export_job(job)

    return jobs
