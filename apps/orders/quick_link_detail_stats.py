from __future__ import annotations

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Max, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent

from .models import BookingQuickLink, Order
from .quick_link_stats import (
    calculate_booking_quick_link_conversion_rate,
    resolve_booking_quick_link_period,
)
from .quick_links import (
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
)


DETAIL_EVENT_TYPES = (
    BOOKING_QUICK_LINK_OPENED_EVENT,
    BOOKING_QUICK_LINK_STARTED_EVENT,
    BOOKING_QUICK_LINK_CONVERTED_EVENT,
)


def _percentage(*, value, maximum) -> float:
    value = max(int(value or 0), 0)
    maximum = max(int(maximum or 0), 0)

    if value == 0 or maximum == 0:
        return 0.0

    return round(
        min((value / maximum) * 100, 100.0),
        2,
    )


def _funnel_rate(*, value, previous) -> float:
    value = max(int(value or 0), 0)
    previous = max(int(previous or 0), 0)

    if previous == 0:
        return 0.0

    return round(
        min((value / previous) * 100, 100.0),
        2,
    )


def _period_events_queryset(
    *,
    quick_link,
    content_type,
    period,
):
    queryset = AnalyticsEvent.objects.filter(
        target_content_type=content_type,
        target_object_id=quick_link.pk,
        event_type__in=DETAIL_EVENT_TYPES,
        occurred_at__lte=period["end_at"],
    )

    if period["start_at"] is not None:
        queryset = queryset.filter(
            occurred_at__gte=period["start_at"]
        )

    return queryset


def _daily_rows(
    *,
    quick_link,
    events,
    period,
) -> list[dict]:
    grouped_rows = list(
        events.annotate(
            day=TruncDate("occurred_at")
        )
        .values("day")
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
        )
        .order_by("day")
    )

    values_by_day = {
        row["day"]: row
        for row in grouped_rows
        if row.get("day") is not None
    }

    end_date = timezone.localtime(
        period["end_at"]
    ).date()

    if period["start_at"] is not None:
        start_date = timezone.localtime(
            period["start_at"]
        ).date()
    elif grouped_rows:
        start_date = grouped_rows[0]["day"]
    else:
        start_date = timezone.localtime(
            quick_link.created_at
        ).date()

    if start_date > end_date:
        start_date = end_date

    rows = []
    cursor = start_date

    while cursor <= end_date:
        raw = values_by_day.get(cursor, {})

        rows.append(
            {
                "date": cursor,
                "total_opens": int(
                    raw.get("total_opens") or 0
                ),
                "unique_visitors": int(
                    raw.get("unique_visitors") or 0
                ),
                "started_count": int(
                    raw.get("started_count") or 0
                ),
                "converted_count": int(
                    raw.get("converted_count") or 0
                ),
            }
        )

        cursor += timedelta(days=1)

    maximum = max(
        [
            value
            for row in rows
            for value in (
                row["total_opens"],
                row["unique_visitors"],
                row["started_count"],
                row["converted_count"],
            )
        ]
        or [0]
    )

    for row in rows:
        row.update(
            {
                "open_height": _percentage(
                    value=row["total_opens"],
                    maximum=maximum,
                ),
                "unique_height": _percentage(
                    value=row["unique_visitors"],
                    maximum=maximum,
                ),
                "started_height": _percentage(
                    value=row["started_count"],
                    maximum=maximum,
                ),
                "converted_height": _percentage(
                    value=row["converted_count"],
                    maximum=maximum,
                ),
            }
        )

    return rows


def build_booking_quick_link_detail_stats(
    *,
    quick_link: BookingQuickLink,
    period="30",
    now=None,
) -> dict:
    if not quick_link or not getattr(
        quick_link,
        "pk",
        None,
    ):
        raise ValueError(
            "برای محاسبه جزئیات، لینک ذخیره‌شده لازم است."
        )

    applied_period = resolve_booking_quick_link_period(
        period,
        now=now,
    )

    content_type = ContentType.objects.get_for_model(
        BookingQuickLink,
        for_concrete_model=False,
    )

    events = _period_events_queryset(
        quick_link=quick_link,
        content_type=content_type,
        period=applied_period,
    )

    metrics = events.aggregate(
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

    total_opens = int(
        metrics.get("total_opens") or 0
    )
    unique_visitors = int(
        metrics.get("unique_visitors") or 0
    )
    started_count = int(
        metrics.get("started_count") or 0
    )
    converted_count = int(
        metrics.get("converted_count") or 0
    )

    converted_order_ids = (
        events.filter(
            event_type=(
                BOOKING_QUICK_LINK_CONVERTED_EVENT
            ),
            order_id__isnull=False,
        )
        .order_by()
        .values("order_id")
    )

    outcomes = Order.objects.filter(
        booking_quick_link=quick_link,
        pk__in=Subquery(converted_order_ids),
    ).aggregate(
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

    daily = _daily_rows(
        quick_link=quick_link,
        events=events,
        period=applied_period,
    )

    conversion_rate = (
        calculate_booking_quick_link_conversion_rate(
            converted_count=converted_count,
            unique_visitors=unique_visitors,
        )
    )

    funnel = [
        {
            "key": "unique",
            "label": "بازدیدکننده یکتا",
            "value": unique_visitors,
            "rate": 100.0 if unique_visitors else 0.0,
            "width": 100.0 if unique_visitors else 0.0,
        },
        {
            "key": "started",
            "label": "شروع رزرو",
            "value": started_count,
            "rate": _funnel_rate(
                value=started_count,
                previous=unique_visitors,
            ),
            "width": _percentage(
                value=started_count,
                maximum=unique_visitors,
            ),
        },
        {
            "key": "converted",
            "label": "رزرو موفق",
            "value": converted_count,
            "rate": _funnel_rate(
                value=converted_count,
                previous=started_count,
            ),
            "width": _percentage(
                value=converted_count,
                maximum=unique_visitors,
            ),
        },
    ]

    return {
        "period": applied_period,
        "metrics": {
            "total_opens": total_opens,
            "unique_visitors": unique_visitors,
            "started_count": started_count,
            "converted_count": converted_count,
            "conversion_rate": conversion_rate,
            "start_rate": _funnel_rate(
                value=started_count,
                previous=unique_visitors,
            ),
            "converted_from_start_rate": (
                _funnel_rate(
                    value=converted_count,
                    previous=started_count,
                )
            ),
            "completed_count": int(
                outcomes.get("completed_count") or 0
            ),
            "cancelled_count": int(
                outcomes.get("cancelled_count") or 0
            ),
            "no_show_count": int(
                outcomes.get("no_show_count") or 0
            ),
            "last_opened_at": metrics.get(
                "last_opened_at"
            ),
            "last_started_at": metrics.get(
                "last_started_at"
            ),
            "last_converted_at": metrics.get(
                "last_converted_at"
            ),
            "last_activity_at": metrics.get(
                "last_activity_at"
            ),
        },
        "funnel": funnel,
        "daily": daily,
        "has_activity": any(
            (
                total_opens,
                started_count,
                converted_count,
            )
        ),
    }
