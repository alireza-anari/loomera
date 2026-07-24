from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone as datetime_timezone,
)

from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    Count,
    Max,
    Q,
    Subquery,
)
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent

from .models import BookingQuickLink, Order
from .quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)


QUICK_LINK_PERIOD_LABELS = {
    "7": "۷ روز اخیر",
    "30": "۳۰ روز اخیر",
    "90": "۹۰ روز اخیر",
    "all": "همه زمان‌ها",
}

QUICK_LINK_PERIOD_DAYS = {
    "7": 7,
    "30": 30,
    "90": 90,
    "all": None,
}

QUICK_LINK_PERIOD_ALIASES = {
    "7": "7",
    "7d": "7",
    "30": "30",
    "30d": "30",
    "90": "90",
    "90d": "90",
    "all": "all",
    "all_time": "all",
}

QUICK_LINK_SORT_ALIASES = {
    "newest": "newest",
    "unique_visitors": "unique_visitors",
    "visitors": "unique_visitors",
    "conversions": "conversions",
    "bookings": "conversions",
    "conversion_rate": "conversion_rate",
    "last_activity": "last_activity",
}

QUICK_LINK_DEFAULT_PERIOD = "30"
QUICK_LINK_DEFAULT_SORT = "newest"

_MIN_AWARE_DATETIME = datetime.min.replace(
    tzinfo=datetime_timezone.utc
)


def normalize_booking_quick_link_period(value) -> str:
    normalized = str(value or "").strip().lower()

    return QUICK_LINK_PERIOD_ALIASES.get(
        normalized,
        QUICK_LINK_DEFAULT_PERIOD,
    )


def normalize_booking_quick_link_sort(value) -> str:
    normalized = str(value or "").strip().lower()

    return QUICK_LINK_SORT_ALIASES.get(
        normalized,
        QUICK_LINK_DEFAULT_SORT,
    )


def resolve_booking_quick_link_period(
    value,
    *,
    now=None,
) -> dict:
    now = now or timezone.now()

    period_key = normalize_booking_quick_link_period(
        value
    )

    days = QUICK_LINK_PERIOD_DAYS[period_key]

    start_at = (
        now - timedelta(days=days)
        if days is not None
        else None
    )

    return {
        "key": period_key,
        "label": QUICK_LINK_PERIOD_LABELS[
            period_key
        ],
        "days": days,
        "start_at": start_at,
        "end_at": now,
    }


def calculate_booking_quick_link_conversion_rate(
    *,
    converted_count,
    unique_visitors,
) -> float:
    converted_count = max(
        int(converted_count or 0),
        0,
    )

    unique_visitors = max(
        int(unique_visitors or 0),
        0,
    )

    if unique_visitors == 0:
        return 0.0

    return round(
        (
            converted_count
            / unique_visitors
        )
        * 100,
        2,
    )


def _event_rows_by_link(
    *,
    link_ids,
    content_type,
    period,
) -> dict:
    events = AnalyticsEvent.objects.filter(
        target_content_type=content_type,
        target_object_id__in=link_ids,
        event_type__in=[
            BOOKING_QUICK_LINK_OPENED_EVENT,
            BOOKING_QUICK_LINK_STARTED_EVENT,
            BOOKING_QUICK_LINK_CONVERTED_EVENT,
        ],
        occurred_at__lte=period["end_at"],
    )

    if period["start_at"] is not None:
        events = events.filter(
            occurred_at__gte=period["start_at"]
        )

    rows = (
        events.values("target_object_id")
        .annotate(
            total_opens=Count(
                "id",
                filter=Q(
                    event_type=(
                        BOOKING_QUICK_LINK_OPENED_EVENT
                    )
                ),
            ),
            unique_visitors=Count(
                "session_key",
                distinct=True,
                filter=(
                    Q(
                        event_type=(
                            BOOKING_QUICK_LINK_OPENED_EVENT
                        )
                    )
                    & ~Q(session_key="")
                ),
            ),
            started_count=Count(
                "id",
                filter=Q(
                    event_type=(
                        BOOKING_QUICK_LINK_STARTED_EVENT
                    )
                ),
            ),
            converted_count=Count(
                "id",
                filter=Q(
                    event_type=(
                        BOOKING_QUICK_LINK_CONVERTED_EVENT
                    )
                ),
            ),
            last_opened_at=Max(
                "occurred_at",
                filter=Q(
                    event_type=(
                        BOOKING_QUICK_LINK_OPENED_EVENT
                    )
                ),
            ),
            last_started_at=Max(
                "occurred_at",
                filter=Q(
                    event_type=(
                        BOOKING_QUICK_LINK_STARTED_EVENT
                    )
                ),
            ),
            last_converted_at=Max(
                "occurred_at",
                filter=Q(
                    event_type=(
                        BOOKING_QUICK_LINK_CONVERTED_EVENT
                    )
                ),
            ),
            last_activity_at=Max("occurred_at"),
        )
        .order_by()
    )

    return {
        int(row["target_object_id"]): row
        for row in rows
        if row["target_object_id"] is not None
    }


def _order_outcome_rows_by_link(
    *,
    link_ids,
    content_type,
    period,
) -> dict:
    converted_events = AnalyticsEvent.objects.filter(
        target_content_type=content_type,
        target_object_id__in=link_ids,
        event_type=(
            BOOKING_QUICK_LINK_CONVERTED_EVENT
        ),
        order_id__isnull=False,
        occurred_at__lte=period["end_at"],
    )

    if period["start_at"] is not None:
        converted_events = converted_events.filter(
            occurred_at__gte=period["start_at"]
        )

    converted_order_ids = (
        converted_events
        .order_by()
        .values("order_id")
    )

    rows = (
        Order.objects.filter(
            booking_quick_link_id__in=link_ids,
            pk__in=Subquery(
                converted_order_ids
            ),
        )
        .values("booking_quick_link_id")
        .annotate(
            completed_count=Count(
                "id",
                distinct=True,
                filter=(
                    Q(status="completed")
                    | Q(
                        service_completed_at__isnull=False
                    )
                ),
            ),
            cancelled_count=Count(
                "id",
                distinct=True,
                filter=Q(status="cancelled"),
            ),
            no_show_count=Count(
                "id",
                distinct=True,
                filter=Q(status="no_show"),
            ),
        )
        .order_by()
    )

    return {
        int(row["booking_quick_link_id"]): row
        for row in rows
        if row["booking_quick_link_id"]
        is not None
    }


def _row_last_activity(row):
    return (
        row.get("last_activity_at")
        or row["quick_link"].created_at
        or _MIN_AWARE_DATETIME
    )


def _performance_key(row):
    return (
        int(row["converted_count"]),
        float(row["conversion_rate"]),
        int(row["unique_visitors"]),
        int(row["total_opens"]),
        _row_last_activity(row),
        int(row["id"]),
    )


def _sort_booking_quick_link_rows(
    rows,
    *,
    sort_key,
):
    if sort_key == "unique_visitors":
        key = lambda row: (
            int(row["unique_visitors"]),
            int(row["converted_count"]),
            _row_last_activity(row),
            int(row["id"]),
        )
    elif sort_key == "conversions":
        key = lambda row: (
            int(row["converted_count"]),
            float(row["conversion_rate"]),
            int(row["unique_visitors"]),
            _row_last_activity(row),
            int(row["id"]),
        )
    elif sort_key == "conversion_rate":
        key = lambda row: (
            float(row["conversion_rate"]),
            int(row["converted_count"]),
            int(row["unique_visitors"]),
            _row_last_activity(row),
            int(row["id"]),
        )
    elif sort_key == "last_activity":
        key = lambda row: (
            _row_last_activity(row),
            int(row["converted_count"]),
            int(row["id"]),
        )
    else:
        key = lambda row: (
            row["quick_link"].created_at
            or _MIN_AWARE_DATETIME,
            int(row["id"]),
        )

    return sorted(
        rows,
        key=key,
        reverse=True,
    )


def build_booking_quick_link_stats(
    *,
    links_queryset,
    period="30",
    sort="newest",
    now=None,
) -> dict:
    """
    آمار لینک‌ها را تنها با Queryهای گروهی تولید می‌کند.

    Scope دسترسی باید پیش از فراخوانی این تابع داخل
    links_queryset اعمال شده باشد.
    """
    applied_period = resolve_booking_quick_link_period(
        period,
        now=now,
    )

    applied_sort = normalize_booking_quick_link_sort(
        sort
    )

    links = list(
        links_queryset.select_related(
            "salon",
            "service",
            "stylist__user",
            "creator",
        )
    )

    if not links:
        return {
            "period": applied_period,
            "sort": applied_sort,
            "summary": {
                "total_links": 0,
                "active_links": 0,
                "total_opens": 0,
                "unique_visitors": 0,
                "started_count": 0,
                "converted_count": 0,
                "conversion_rate": 0.0,
                "completed_count": 0,
                "cancelled_count": 0,
                "no_show_count": 0,
                "best_link": None,
            },
            "links": [],
        }

    link_ids = [
        int(link.pk)
        for link in links
    ]

    content_type = ContentType.objects.get_for_model(
        BookingQuickLink,
        for_concrete_model=False,
    )

    event_rows = _event_rows_by_link(
        link_ids=link_ids,
        content_type=content_type,
        period=applied_period,
    )

    outcome_rows = _order_outcome_rows_by_link(
        link_ids=link_ids,
        content_type=content_type,
        period=applied_period,
    )

    result_rows = []

    for quick_link in links:
        analytics = event_rows.get(
            quick_link.pk,
            {},
        )

        outcomes = outcome_rows.get(
            quick_link.pk,
            {},
        )

        total_opens = int(
            analytics.get("total_opens") or 0
        )

        unique_visitors = int(
            analytics.get(
                "unique_visitors"
            )
            or 0
        )

        started_count = int(
            analytics.get("started_count") or 0
        )

        converted_count = int(
            analytics.get(
                "converted_count"
            )
            or 0
        )

        conversion_rate = (
            calculate_booking_quick_link_conversion_rate(
                converted_count=converted_count,
                unique_visitors=unique_visitors,
            )
        )

        result_rows.append(
            {
                "id": quick_link.pk,
                "quick_link": quick_link,
                "total_opens": total_opens,
                "unique_visitors": (
                    unique_visitors
                ),
                "started_count": started_count,
                "converted_count": (
                    converted_count
                ),
                "conversion_rate": (
                    conversion_rate
                ),
                "completed_count": int(
                    outcomes.get(
                        "completed_count"
                    )
                    or 0
                ),
                "cancelled_count": int(
                    outcomes.get(
                        "cancelled_count"
                    )
                    or 0
                ),
                "no_show_count": int(
                    outcomes.get(
                        "no_show_count"
                    )
                    or 0
                ),
                "last_opened_at": (
                    analytics.get(
                        "last_opened_at"
                    )
                ),
                "last_started_at": (
                    analytics.get(
                        "last_started_at"
                    )
                ),
                "last_converted_at": (
                    analytics.get(
                        "last_converted_at"
                    )
                ),
                "last_activity_at": (
                    analytics.get(
                        "last_activity_at"
                    )
                ),
            }
        )

    total_opens = sum(
        row["total_opens"]
        for row in result_rows
    )

    unique_visitors = sum(
        row["unique_visitors"]
        for row in result_rows
    )

    started_count = sum(
        row["started_count"]
        for row in result_rows
    )

    converted_count = sum(
        row["converted_count"]
        for row in result_rows
    )

    completed_count = sum(
        row["completed_count"]
        for row in result_rows
    )

    cancelled_count = sum(
        row["cancelled_count"]
        for row in result_rows
    )

    no_show_count = sum(
        row["no_show_count"]
        for row in result_rows
    )

    active_links = sum(
        1
        for row in result_rows
        if row["quick_link"].can_open
    )

    has_activity = any(
        (
            row["total_opens"]
            or row["started_count"]
            or row["converted_count"]
        )
        for row in result_rows
    )

    best_link = (
        max(
            result_rows,
            key=_performance_key,
        )
        if has_activity
        else None
    )

    sorted_rows = _sort_booking_quick_link_rows(
        result_rows,
        sort_key=applied_sort,
    )

    return {
        "period": applied_period,
        "sort": applied_sort,
        "summary": {
            "total_links": len(result_rows),
            "active_links": active_links,
            "total_opens": total_opens,
            "unique_visitors": (
                unique_visitors
            ),
            "started_count": started_count,
            "converted_count": (
                converted_count
            ),
            "conversion_rate": (
                calculate_booking_quick_link_conversion_rate(
                    converted_count=converted_count,
                    unique_visitors=unique_visitors,
                )
            ),
            "completed_count": (
                completed_count
            ),
            "cancelled_count": (
                cancelled_count
            ),
            "no_show_count": no_show_count,
            "best_link": best_link,
        },
        "links": sorted_rows,
    }
