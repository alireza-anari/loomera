from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date as dt_date, datetime, time as dt_time, timedelta
from typing import Iterable

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.apps import apps
from django.core.exceptions import FieldError
from django.db.models import Avg, Count, Exists, Min, OuterRef, Prefetch, Q
from django.urls import reverse
from django.utils import timezone

from apps.discounts.utils import (
    active_discount_basket_prefetch,
    attach_active_service_discount_meta,
)
from apps.locations.models import Neighborhood
from apps.orders.models import OrderDetail
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services
from apps.stylists.models import StaffLeaveRequest, StylistSchedule

try:
    from persiantools.jdatetime import JalaliDate
except Exception:  # pragma: no cover - defensive import
    JalaliDate = None


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
BLOCKING_STATUSES = ["pending", "confirmed", "paid", "completed"]
PERIOD_WINDOWS = {
    "morning": (dt_time(6, 0), dt_time(11, 59)),
    "noon": (dt_time(12, 0), dt_time(15, 59)),
    "evening": (dt_time(16, 0), dt_time(18, 59)),
    "night": (dt_time(19, 0), dt_time(23, 59)),
}
PERIOD_ALIASES = {
    "صبح": "morning",
    "morning": "morning",
    "ظهر": "noon",
    "noon": "noon",
    "بعدازظهر": "noon",
    "عصر": "evening",
    "evening": "evening",
    "شب": "night",
    "night": "night",
}
PERIOD_LABELS = {
    "morning": "صبح",
    "noon": "ظهر",
    "evening": "عصر",
    "night": "شب",
}


@dataclass
class SearchFilters:
    query: str = ""
    location: str = ""
    latitude: float | None = None
    longitude: float | None = None
    search_date: dt_date | None = None
    date_input: str = ""
    period: str = ""
    exact_time: dt_time | None = None
    exact_time_input: str = ""
    group_id: int | None = None
    service_ids: list[int] | None = None
    sort: str = "recommended"
    q_type: str = ""
    q_id: int | None = None
    min_price: int | None = None
    max_price: int | None = None
    # Backward-compatible aliases used by the search template/view state.
    price_min: int | None = None
    price_max: int | None = None
    min_rating: float | None = None
    rating_min: float | None = None
    has_discount: bool = False
    discount_only: bool = False
    discounted: bool = False
    availability: str = ""
    available: str = ""
    available_today: bool = False
    available_this_week: bool = False
    availability_dates: list[dt_date] | None = None
    today_only: bool = False
    this_week_only: bool = False
    verified: bool = False
    verified_only: bool = False
    open_now: bool = False
    map_view: bool = False
    instant_booking: bool = False
    online_payment: bool = False

    def __getattr__(self, name: str):
        """Backward-compatible defaults for older/newer search views.

        SearchPageView and templates evolved through QA and may read optional
        filter-state attributes before the backend starts actively using them.
        Returning safe defaults here prevents AttributeError while keeping
        unsupported toggles inactive.
        """
        false_like = {
            "discounted",
            "verified",
            "verified_only",
            "has_discount",
            "discount_only",
            "available_today",
            "available_this_week",
            "today_only",
            "this_week_only",
            "open_now",
            "instant_booking",
            "online_payment",
            "map_view",
            "near_me",
            "has_map",
        }
        none_like = {
            "min_rating",
            "rating_min",
            "min_price",
            "max_price",
            "price_min",
            "price_max",
        }
        empty_like = {
            "availability",
            "available",
            "city",
            "area",
            "neighborhood",
            "category",
            "service",
            "filter_badge",
        }
        list_like = {"selected_services", "service_slugs", "group_ids"}
        if name in false_like:
            return False
        if name in none_like:
            return None
        if name in empty_like:
            return ""
        if name in list_like:
            return []
        raise AttributeError(
            f"{self.__class__.__name__!s} object has no attribute {name!r}"
        )

    @property
    def has_time_filter(self) -> bool:
        return bool(self.period or self.exact_time)

    @property
    def service_ids_value(self) -> list[int]:
        return [value for value in (self.service_ids or []) if value]

    @property
    def has_price_filter(self) -> bool:
        return self.min_price is not None or self.max_price is not None


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return str(value).translate(PERSIAN_DIGITS).strip()


def safe_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(normalize_text(str(value)))
    except (TypeError, ValueError):
        return None


def parse_price_value(*raw_values) -> int | None:
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        value = normalize_text(str(raw_value))
        value = (
            value.replace(",", "")
            .replace("٬", "")
            .replace("،", "")
            .replace("تومان", "")
            .strip()
        )
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            continue
        try:
            return max(int(digits), 0)
        except (TypeError, ValueError):
            continue
    return None


def parse_rating_value(*raw_values) -> float | None:
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        value = normalize_text(str(raw_value)).replace("٫", ".").replace("،", ".")
        try:
            rating = float(value)
        except (TypeError, ValueError):
            continue
        if rating <= 0:
            return None
        return min(rating, 5.0)
    return None


def parse_bool_value(*raw_values) -> bool:
    truthy = {
        "1",
        "true",
        "yes",
        "on",
        "y",
        "discount",
        "has_discount",
        "تخفیف",
        "تخفیف دار",
        "تخفیف‌دار",
    }
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        value = normalize_text(str(raw_value)).lower().strip()
        if value in truthy:
            return True
    return False


def normalize_availability_value(*raw_values) -> str:
    aliases = {
        "today": "today",
        "available_today": "today",
        "today_only": "today",
        "امروز": "today",
        "وقت آزاد امروز": "today",
        "this_week": "this_week",
        "week": "this_week",
        "available_this_week": "this_week",
        "this_week_only": "this_week",
        "هفته": "this_week",
        "این هفته": "this_week",
        "وقت آزاد این هفته": "this_week",
    }
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        value = normalize_text(str(raw_value)).lower().strip()
        if value in aliases:
            return aliases[value]
    return ""


def parse_date_value(raw_value: str | None) -> dt_date | None:
    value = normalize_text(raw_value)
    if not value:
        return None

    for separator in ("/", "-"):
        if separator in value:
            parts = value.split(separator)
            break
    else:
        return None

    if len(parts) != 3:
        return None

    try:
        year, month, day = map(int, parts)
    except ValueError:
        return None

    try:
        if year >= 1700:
            return dt_date(year, month, day)
        if JalaliDate is None:
            return None
        return JalaliDate(year, month, day).to_gregorian()
    except Exception:
        return None


def parse_time_value(raw_value: str | None) -> dt_time | None:
    value = normalize_text(raw_value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def normalize_period(raw_value: str | None) -> str:
    value = normalize_text(raw_value)
    if not value:
        return ""
    return PERIOD_ALIASES.get(value.lower(), PERIOD_ALIASES.get(value, ""))


def filters_from_querydict(querydict) -> SearchFilters:
    raw_services_value = querydict.get("services", "")
    service_ids: list[int] = []
    if isinstance(raw_services_value, (list, tuple)):
        raw_parts = raw_services_value
    else:
        raw_services_value = normalize_text(raw_services_value)
        raw_parts = raw_services_value.split(",") if raw_services_value else []

    for part in raw_parts:
        normalized = normalize_text(part)
        if normalized.isdigit():
            service_ids.append(int(normalized))

    group_id_raw = normalize_text(querydict.get("group", ""))
    group_id = int(group_id_raw) if group_id_raw.isdigit() else None

    raw_q_type = normalize_text(querydict.get("q_type", "")).lower()
    q_type = raw_q_type if raw_q_type in {"service", "salon", "stylist"} else ""

    q_id_raw = normalize_text(querydict.get("q_id", ""))
    q_id = int(q_id_raw) if q_id_raw.isdigit() else None

    min_price = parse_price_value(
        querydict.get("min_price"),
        querydict.get("price_min"),
        querydict.get("minPrice"),
        querydict.get("priceMin"),
        querydict.get("from_price"),
        querydict.get("price_from"),
    )
    max_price = parse_price_value(
        querydict.get("max_price"),
        querydict.get("price_max"),
        querydict.get("maxPrice"),
        querydict.get("priceMax"),
        querydict.get("to_price"),
        querydict.get("price_to"),
        querydict.get("budget"),
    )
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price

    min_rating = parse_rating_value(
        querydict.get("min_rating"),
        querydict.get("rating_min"),
        querydict.get("minRating"),
        querydict.get("rating"),
    )
    has_discount = parse_bool_value(
        querydict.get("has_discount"),
        querydict.get("discount_only"),
        querydict.get("discount"),
        querydict.get("discounted"),
    )
    availability = normalize_availability_value(
        querydict.get("availability"),
        querydict.get("available"),
        querydict.get("available_filter"),
        querydict.get("time_filter"),
        querydict.get("slot_filter"),
    )
    available_today = availability == "today" or parse_bool_value(
        querydict.get("available_today"),
        querydict.get("today_only"),
        querydict.get("today"),
    )
    available_this_week = availability == "this_week" or parse_bool_value(
        querydict.get("available_this_week"),
        querydict.get("this_week_only"),
        querydict.get("week_only"),
    )
    if available_today:
        availability = "today"
    elif available_this_week:
        availability = "this_week"

    requested_date = parse_date_value(querydict.get("date"))
    availability_dates = None
    if availability == "today" and requested_date is None:
        requested_date = timezone.localdate()
        availability_dates = [requested_date]
    elif availability == "this_week" and requested_date is None:
        today = timezone.localdate()
        availability_dates = [today + timedelta(days=offset) for offset in range(7)]

    verified = parse_bool_value(
        querydict.get("verified"),
        querydict.get("verified_only"),
        querydict.get("is_verified"),
        querydict.get("salon_verified"),
        querydict.get("trust_badge"),
    )

    return SearchFilters(
        query=normalize_text(querydict.get("q", "")),
        q_type=q_type,
        q_id=q_id,
        location=normalize_text(querydict.get("location", "")),
        latitude=safe_float(querydict.get("lat")),
        longitude=safe_float(querydict.get("lng")),
        search_date=requested_date,
        date_input=normalize_text(querydict.get("date", "")),
        period=normalize_period(querydict.get("period", "")),
        exact_time=parse_time_value(querydict.get("time", "")),
        exact_time_input=normalize_text(querydict.get("time", "")),
        group_id=group_id,
        service_ids=service_ids,
        sort=normalize_text(querydict.get("sort", "recommended")) or "recommended",
        min_price=min_price,
        max_price=max_price,
        price_min=min_price,
        price_max=max_price,
        min_rating=min_rating,
        rating_min=min_rating,
        has_discount=has_discount,
        discount_only=has_discount,
        discounted=has_discount,
        availability=availability,
        available=availability,
        available_today=available_today,
        available_this_week=available_this_week,
        availability_dates=availability_dates,
        today_only=available_today,
        this_week_only=available_this_week,
        verified=verified,
        verified_only=verified,
        open_now=parse_bool_value(querydict.get("open_now"), querydict.get("now")),
        map_view=parse_bool_value(querydict.get("map_view"), querydict.get("map")),
        instant_booking=parse_bool_value(
            querydict.get("instant_booking"), querydict.get("instant")
        ),
        online_payment=parse_bool_value(
            querydict.get("online_payment"), querydict.get("pay_online")
        ),
    )


def get_descendant_group_ids(group_id: int | None) -> list[int]:
    if not group_id:
        return []

    groups = GroupServices.objects.filter(is_active=True).values(
        "id", "group_parent_id"
    )
    children_map: dict[int | None, list[int]] = defaultdict(list)
    for item in groups:
        children_map[item["group_parent_id"]].append(item["id"])

    stack = [group_id]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(children_map.get(current, []))
    return list(seen)


def _format_hhmm(value: dt_time | None) -> str:
    return value.strftime("%H:%M") if value else ""


def _time_to_minutes(value: dt_time | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = parse_time_value(value)
        if parsed is None:
            return None
        value = parsed
    return value.hour * 60 + value.minute


def _minutes_to_hhmm(minutes: int) -> str:
    minutes = max(minutes, 0)
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours:02d}:{mins:02d}"


def _iter_start_times(
    schedule_start: dt_time,
    schedule_end: dt_time,
    duration_minutes: int,
    exact_minutes: int | None = None,
    window: tuple[dt_time, dt_time] | None = None,
) -> Iterable[int]:
    start_minutes = _time_to_minutes(schedule_start)
    end_minutes = _time_to_minutes(schedule_end)
    if start_minutes is None or end_minutes is None:
        return []

    if end_minutes <= start_minutes:
        end_minutes += 24 * 60

    latest_start = end_minutes - duration_minutes
    if latest_start < start_minutes:
        return []

    if exact_minutes is not None:
        requested = exact_minutes
        if requested < start_minutes:
            requested += 24 * 60
        if start_minutes <= requested <= latest_start:
            return [requested]
        return []

    window_start = start_minutes
    window_end = latest_start
    if window:
        raw_window_start = _time_to_minutes(window[0])
        raw_window_end = _time_to_minutes(window[1])
        if raw_window_start is not None and raw_window_end is not None:
            if raw_window_end <= raw_window_start:
                raw_window_end += 24 * 60
            window_start = max(window_start, raw_window_start)
            window_end = min(window_end, raw_window_end)
            if window_end < window_start:
                return []

    slots: list[int] = []
    current = window_start
    while current <= window_end:
        slots.append(current)
        current += 15
    return slots


def _range_overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and end_a > start_b


def _time_off_blocks(
    start_minutes: int, end_minutes: int, time_offs: list[StaffLeaveRequest]
) -> bool:
    for time_off in time_offs:
        if time_off.start_time is None or time_off.end_time is None:
            return True
        off_start = _time_to_minutes(time_off.start_time)
        off_end = _time_to_minutes(time_off.end_time)
        if off_start is None or off_end is None:
            return True
        if off_end <= off_start:
            off_end += 24 * 60
        if _range_overlaps(start_minutes, end_minutes, off_start, off_end):
            return True
    return False


def _booking_blocks(
    start_minutes: int,
    end_minutes: int,
    bookings: list[OrderDetail],
    default_duration: int,
) -> bool:
    for booking in bookings:
        booking_start = _time_to_minutes(booking.time)
        if booking_start is None:
            continue
        if booking.end_time:
            booking_end = _time_to_minutes(booking.end_time)
        else:
            booking_duration = (
                getattr(booking.service, "duration_minutes", default_duration)
                or default_duration
            )
            booking_end = booking_start + booking_duration
        if booking_end is None:
            continue
        if booking_end <= booking_start:
            booking_end += 24 * 60
        if _range_overlaps(start_minutes, end_minutes, booking_start, booking_end):
            return True
    return False


def _find_service_slot(
    service: Services,
    stylist_ids: set[int],
    schedules_by_salon: dict[int, dict[int, list[StylistSchedule]]],
    time_offs_by_salon_stylist: dict[tuple[int, int], list[StaffLeaveRequest]],
    bookings_by_salon_stylist: dict[tuple[int, int], list[OrderDetail]],
    salon_id: int,
    period: str,
    exact_time: dt_time | None,
) -> dict | None:
    duration = int(getattr(service, "duration_minutes", 60) or 60)
    exact_minutes = _time_to_minutes(exact_time) if exact_time else None
    window = PERIOD_WINDOWS.get(period) if period else None

    for stylist_id in stylist_ids:
        schedules = schedules_by_salon.get(salon_id, {}).get(stylist_id, [])
        if not schedules:
            continue

        stylist_time_offs = time_offs_by_salon_stylist.get((salon_id, stylist_id), [])
        stylist_bookings = bookings_by_salon_stylist.get((salon_id, stylist_id), [])

        for schedule in schedules:
            if schedule.service_id and schedule.service_id != service.id:
                continue

            start_times = _iter_start_times(
                schedule.start_time,
                schedule.end_time,
                duration,
                exact_minutes=exact_minutes,
                window=window,
            )
            for start_minutes in start_times:
                end_minutes = start_minutes + duration
                if _time_off_blocks(start_minutes, end_minutes, stylist_time_offs):
                    continue
                if _booking_blocks(
                    start_minutes, end_minutes, stylist_bookings, duration
                ):
                    continue

                return {
                    "service_id": service.id,
                    "service_name": service.service_name,
                    "stylist_id": stylist_id,
                    "slot": _minutes_to_hhmm(start_minutes),
                    "duration": duration,
                }
    return None


def _find_any_slot(
    salon_id: int,
    schedules_by_salon: dict[int, dict[int, list[StylistSchedule]]],
    time_offs_by_salon_stylist: dict[tuple[int, int], list[StaffLeaveRequest]],
    bookings_by_salon_stylist: dict[tuple[int, int], list[OrderDetail]],
    period: str,
    exact_time: dt_time | None,
) -> dict | None:
    exact_minutes = _time_to_minutes(exact_time) if exact_time else None
    window = PERIOD_WINDOWS.get(period) if period else None

    for stylist_id, schedules in schedules_by_salon.get(salon_id, {}).items():
        stylist_time_offs = time_offs_by_salon_stylist.get((salon_id, stylist_id), [])
        stylist_bookings = bookings_by_salon_stylist.get((salon_id, stylist_id), [])

        for schedule in schedules:
            duration = 30
            start_times = _iter_start_times(
                schedule.start_time,
                schedule.end_time,
                duration,
                exact_minutes=exact_minutes,
                window=window,
            )

            for start_minutes in start_times:
                end_minutes = start_minutes + duration

                if _time_off_blocks(start_minutes, end_minutes, stylist_time_offs):
                    continue

                if _booking_blocks(
                    start_minutes, end_minutes, stylist_bookings, duration
                ):
                    continue

                return {
                    "service_id": schedule.service_id,
                    "service_name": (
                        schedule.service.service_name
                        if schedule.service_id
                        else "نوبت آزاد"
                    ),
                    "stylist_id": stylist_id,
                    "slot": _minutes_to_hhmm(start_minutes),
                    "duration": duration,
                }

    return None


def _coerce_price(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return parse_price_value(value)


def _price_matches_filter(price: int | None, filters: SearchFilters) -> bool:
    if not filters.has_price_filter:
        return True
    if price is None:
        return False
    if filters.min_price is not None and price < filters.min_price:
        return False
    if filters.max_price is not None and price > filters.max_price:
        return False
    return True


VERIFIED_STATUS_VALUES = {
    "approved",
    "approve",
    "verified",
    "accepted",
    "confirmed",
    "APPROVED",
    "APPROVE",
    "VERIFIED",
    "ACCEPTED",
    "CONFIRMED",
    "تایید",
    "تایید شده",
    "تأیید",
    "تأیید شده",
    "تاییدشده",
    "تأییدشده",
}


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _approved_values_for_field(field) -> set:
    values = set(VERIFIED_STATUS_VALUES)
    for value, label in getattr(field, "choices", None) or []:
        haystack = f"{value} {label}".lower()
        if any(
            token in haystack
            for token in (
                "approved",
                "verified",
                "accepted",
                "confirmed",
                "تایید",
                "تأیید",
            )
        ):
            values.add(value)
    return values


def _verification_queryset_for_model(model):
    """Return a queryset of verified salon ids for a SalonVerification-like model.

    The verification model was added during QA in some project snapshots, so this
    helper discovers the model/field names dynamically instead of depending on a
    single import path or related_name. If no verification model exists, callers
    can safely fall back to direct Salon fields.
    """
    salon_field = None
    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        remote_model = getattr(getattr(field, "remote_field", None), "model", None)
        if remote_model is Salon:
            salon_field = field
            break
    if salon_field is None:
        return None

    verification_q = Q()
    for status_name in (
        "status",
        "verification_status",
        "state",
        "review_status",
        "approval_status",
    ):
        if _model_has_field(model, status_name):
            field = model._meta.get_field(status_name)
            verification_q |= Q(
                **{f"{status_name}__in": list(_approved_values_for_field(field))}
            )

    for bool_name in (
        "is_verified",
        "verified",
        "is_approved",
        "approved",
        "is_confirmed",
        "confirmed",
    ):
        if _model_has_field(model, bool_name):
            verification_q |= Q(**{bool_name: True})

    # Use timestamp fields only as a last-resort signal when there is no status/boolean field.
    if not verification_q:
        for date_name in ("verified_at", "approved_at", "confirmed_at"):
            if _model_has_field(model, date_name):
                verification_q |= Q(**{f"{date_name}__isnull": False})

    if not verification_q:
        return None

    try:
        return model.objects.filter(verification_q).values_list(
            f"{salon_field.name}_id", flat=True
        )
    except Exception:
        return None


def _apply_verified_filter(base_qs):
    """Filter search results to only verified salons when the toggle is active."""
    # Direct fields on Salon, if the current project snapshot has any of them.
    direct_candidates = [
        {"is_verified": True},
        {"verified": True},
        {"is_approved": True},
        {"approved": True},
        {"verification_status__in": list(VERIFIED_STATUS_VALUES)},
        {"status__in": list(VERIFIED_STATUS_VALUES)},
    ]
    for candidate in direct_candidates:
        try:
            return base_qs.filter(**candidate).distinct()
        except (FieldError, Exception):
            continue

    # Dynamically discover SalonVerification-like models regardless of app name.
    for model in apps.get_models():
        model_name = model.__name__.lower()
        if "verification" not in model_name and "verify" not in model_name:
            continue
        salon_ids = _verification_queryset_for_model(model)
        if salon_ids is None:
            continue
        return base_qs.filter(pk__in=salon_ids).distinct()

    # Safe fallback: no known verification source exists in this snapshot.
    # Keep the search page working, but do not silently mark every salon verified.
    return base_qs.none()


def build_search_summary(
    filters: SearchFilters, selected_services: list[Services], selected_group
) -> str:
    parts: list[str] = []
    if selected_services:
        if len(selected_services) == 1:
            parts.append(selected_services[0].service_name)
        else:
            parts.append(f"{len(selected_services)} خدمت")
    elif selected_group:
        parts.append(selected_group.group_title)
    elif filters.query:
        parts.append(filters.query)

    if filters.location:
        parts.append(filters.location)
    if filters.date_input:
        parts.append(filters.date_input)
    if filters.period:
        parts.append(PERIOD_LABELS.get(filters.period, filters.period))
    if filters.exact_time_input:
        parts.append(filters.exact_time_input)
    if filters.min_price is not None and filters.max_price is not None:
        parts.append(f"از {filters.min_price:,} تا {filters.max_price:,} تومان")
    elif filters.min_price is not None:
        parts.append(f"از {filters.min_price:,} تومان")
    elif filters.max_price is not None:
        parts.append(f"تا {filters.max_price:,} تومان")
    if filters.min_rating is not None:
        parts.append(f"امتیاز از {filters.min_rating:g}")
    if filters.has_discount or filters.discount_only:
        parts.append("تخفیف‌دار")
    if filters.verified or filters.verified_only:
        parts.append("سالن‌های تاییدشده")
    if filters.available_today or filters.today_only:
        parts.append("وقت آزاد امروز")
    elif filters.available_this_week or filters.this_week_only:
        parts.append("وقت آزاد این هفته")

    return " • ".join(parts) if parts else "جستجو سالن، خدمات یا منطقه..."


def search_salons(filters: SearchFilters) -> dict:
    group_ids = get_descendant_group_ids(filters.group_id)

    selected_group = None
    if filters.group_id:
        selected_group = GroupServices.objects.filter(
            pk=filters.group_id,
            is_active=True,
        ).first()

    service_ids_value = list(filters.service_ids_value)

    # اگر کاربر از پیشنهادها یک «خدمت» انتخاب کرده باشد،
    # همان خدمت هم وارد فیلتر سرویس‌ها می‌شود.
    if (
        filters.q_type == "service"
        and filters.q_id
        and filters.q_id not in service_ids_value
    ):
        service_ids_value.append(filters.q_id)

    selected_services_qs = Services.objects.filter(
        pk__in=service_ids_value,
        is_active=True,
    ).prefetch_related(
        "service_group",
        "stylists",
        "service_prices",
    )

    selected_services = list(selected_services_qs)

    group_services_qs = Services.objects.none()
    if group_ids:
        group_services_qs = (
            Services.objects.filter(
                is_active=True,
                service_group__id__in=group_ids,
            )
            .prefetch_related("service_group", "stylists", "service_prices")
            .distinct()
        )

    group_services = list(group_services_qs)
    group_service_ids = {service.id for service in group_services}
    selected_service_ids = {service.id for service in selected_services}

    base_qs = (
        Salon.objects.filter(is_active=True)
        .select_related("neighborhood")
        .prefetch_related(
            Prefetch(
                "services",
                queryset=Services.objects.filter(is_active=True)
                .prefetch_related("service_group", "stylists", "service_prices")
                .distinct(),
            ),
            active_discount_basket_prefetch(),
        )
        .annotate(
            avg_score=Avg("scoring_salon__score"),
            total_reviews=Count("scoring_salon__score", distinct=True),
            min_price=Min("services__service_prices__price"),
        )
    )

    if filters.min_rating is not None:
        base_qs = base_qs.filter(avg_score__gte=filters.min_rating)

    if filters.verified or filters.verified_only:
        base_qs = _apply_verified_filter(base_qs)

    # =====================================================================
    # فیلتر سختگیرانه AND
    # اگر q + group + location با هم ارسال شوند، همه باید همزمان برقرار باشند.
    # =====================================================================

    # 1) اگر گروه انتخاب شده ولی هیچ خدمت فعالی داخل آن گروه/زیرگروه‌هایش نیست،
    # هیچ سالنی نباید نمایش داده شود.
    if filters.group_id and not group_service_ids:
        base_qs = base_qs.none()

    # 2) اگر گروه انتخاب شده، سالن باید حداقل یک خدمت فعال از همان گروه داشته باشد.
    elif group_service_ids:
        base_qs = base_qs.filter(
            services__is_active=True,
            services__id__in=group_service_ids,
        )

    # 3) اگر خدمت مشخص انتخاب شده، همان خدمت باید داخل سالن وجود داشته باشد.
    if selected_services:
        # اگر هم گروه انتخاب شده و هم خدمت انتخاب شده،
        # خدمت انتخاب‌شده باید جزو همان گروه باشد؛ وگرنه نتیجه باید خالی شود.
        if group_service_ids and not selected_service_ids.issubset(group_service_ids):
            base_qs = base_qs.none()
        else:
            for service_id in selected_service_ids:
                base_qs = base_qs.filter(
                    services__id=service_id,
                    services__is_active=True,
                )

    # 4) اگر کاربر از پیشنهادها سالن انتخاب کرده باشد.
    # این فیلتر بعد از فیلتر گروه اعمال می‌شود؛
    # پس اگر سالن خدمت آن گروه را نداشته باشد، دیگر نمایش داده نمی‌شود.
    if filters.q_type == "salon" and filters.q_id:
        base_qs = base_qs.filter(pk=filters.q_id)

    # 5) اگر کاربر از پیشنهادها متخصص انتخاب کرده باشد.
    elif filters.q_type == "stylist" and filters.q_id:
        base_qs = base_qs.filter(
            stylists__pk=filters.q_id,
            stylists__is_active=True,
        )

    # 6) اگر کاربر از پیشنهادها خدمت انتخاب کرده باشد.
    elif filters.q_type == "service" and filters.q_id:
        if group_service_ids and filters.q_id not in group_service_ids:
            base_qs = base_qs.none()
        else:
            base_qs = base_qs.filter(
                services__pk=filters.q_id,
                services__is_active=True,
            )

    # 7) اگر کاربر فقط تایپ آزاد انجام داده باشد.
    elif filters.query:
        base_qs = base_qs.filter(
            Q(salon_name__icontains=filters.query)
            | Q(description__icontains=filters.query)
            | Q(
                services__service_name__icontains=filters.query,
                services__is_active=True,
            )
            | Q(stylists__user__name__icontains=filters.query, stylists__is_active=True)
            | Q(
                stylists__user__family__icontains=filters.query,
                stylists__is_active=True,
            )
            | Q(stylists__expert__icontains=filters.query, stylists__is_active=True)
        )

    # =====================================================================
    # فیلتر موقعیت مکانی
    # دقت: اینجا دیگر نام سالن را داخل location جستجو نمی‌کنیم.
    # =====================================================================

    location_label = filters.location
    should_apply_text_location = bool(filters.location)

    if (
        filters.latitude is not None
        and filters.longitude is not None
        and location_label in {"نزدیک من", "near me", "Near me"}
    ):
        should_apply_text_location = False

    if should_apply_text_location:
        neighborhood_ids = list(
            Neighborhood.objects.filter(name__icontains=filters.location).values_list(
                "id", flat=True
            )
        )

        location_q = Q(neighborhood__name__icontains=filters.location) | Q(
            address__icontains=filters.location
        )

        if neighborhood_ids:
            location_q |= Q(neighborhood_id__in=neighborhood_ids)

        base_qs = base_qs.filter(location_q)

    distance_supported = False

    if filters.latitude is not None and filters.longitude is not None:
        try:
            user_point = Point(filters.longitude, filters.latitude, srid=4326)
            base_qs = base_qs.annotate(distance=Distance("location", user_point))
            distance_supported = True

            if location_label in {"نزدیک من", "near me", "Near me"}:
                base_qs = base_qs.filter(location__distance_lte=(user_point, 10000))

        except Exception:
            distance_supported = False

    salons = list(base_qs.distinct())
    salons = attach_active_service_discount_meta(salons)

    if filters.has_discount or filters.discount_only:
        salons = [
            salon
            for salon in salons
            if getattr(salon, "has_active_service_discount", False)
        ]

    inferred_services: list[Services] = []

    if selected_services:
        inferred_services = selected_services

    elif group_services:
        inferred_services = group_services

    elif filters.query:
        inferred_services = list(
            Services.objects.filter(
                is_active=True,
                service_name__icontains=filters.query,
            )
            .prefetch_related("stylists", "service_prices")
            .distinct()[:20]
        )

    availability_dates = filters.availability_dates or (
        [filters.search_date] if filters.search_date else []
    )

    if availability_dates:
        salon_ids = [salon.id for salon in salons]

        stylist_ids: set[int] = set()
        service_to_stylists: dict[int, set[int]] = defaultdict(set)

        for service in inferred_services:
            ids = {
                stylist.pk
                for stylist in service.stylists.all()
                if getattr(stylist, "is_active", True)
            }
            if ids:
                service_to_stylists[service.id] = ids
                stylist_ids.update(ids)

        if filters.q_type == "stylist" and filters.q_id:
            requested_stylist_ids = {filters.q_id}
            if service_to_stylists:
                for service_id in list(service_to_stylists.keys()):
                    service_to_stylists[service_id] = (
                        service_to_stylists[service_id] & requested_stylist_ids
                    )
                stylist_ids = {
                    stylist_id
                    for ids in service_to_stylists.values()
                    for stylist_id in ids
                }
            else:
                stylist_ids = requested_stylist_ids

        # اگر خدمت یا متخصص مشخصی انتخاب نشده، متخصصان فعال سالن‌های کاندید را جمع می‌کنیم
        # تا availability عمومی فقط بر اساس برنامه کاری همان سالن محاسبه شود.
        if not stylist_ids:
            for salon in salons:
                try:
                    ids = {
                        stylist.pk
                        for stylist in salon.stylists.all()
                        if getattr(stylist, "is_active", True)
                    }
                except Exception:
                    ids = set()
                stylist_ids.update(ids)

        filtered_by_availability: dict[int, Salon] = {}

        for current_date in availability_dates:
            if not salon_ids:
                break

            schedules_qs = StylistSchedule.objects.filter(
                salon_id__in=salon_ids,
                date=current_date,
                stylist__is_active=True,
            ).filter(Q(service__isnull=True) | Q(service__is_active=True))

            if stylist_ids:
                schedules_qs = schedules_qs.filter(stylist_id__in=stylist_ids)

            schedules_qs = schedules_qs.select_related(
                "service",
                "stylist__user",
            ).order_by(
                "salon_id",
                "stylist_id",
                "start_time",
            )

            bookings_qs = (
                OrderDetail.objects.filter(
                    salon_id__in=salon_ids,
                    date=current_date,
                    stylist_id__isnull=False,
                    order__status__in=BLOCKING_STATUSES,
                )
                .select_related("service", "order")
                .order_by("salon_id", "stylist_id", "time")
            )

            if stylist_ids:
                bookings_qs = bookings_qs.filter(stylist_id__in=stylist_ids)

            time_offs_qs = StaffLeaveRequest.objects.filter(
                salon_id__in=salon_ids,
                date=current_date,
                stylist_id__isnull=False,
                status=StaffLeaveRequest.Status.APPROVED,
            )

            if stylist_ids:
                time_offs_qs = time_offs_qs.filter(stylist_id__in=stylist_ids)

            schedules_by_salon: dict[int, dict[int, list[StylistSchedule]]] = (
                defaultdict(lambda: defaultdict(list))
            )
            for schedule in schedules_qs:
                schedules_by_salon[schedule.salon_id][schedule.stylist_id].append(
                    schedule
                )

            bookings_by_salon_stylist: dict[tuple[int, int], list[OrderDetail]] = (
                defaultdict(list)
            )
            for booking in bookings_qs:
                bookings_by_salon_stylist[
                    (booking.salon_id, booking.stylist_id)
                ].append(booking)

            time_offs_by_salon_stylist: dict[
                tuple[int, int], list[StaffLeaveRequest]
            ] = defaultdict(list)
            for time_off in time_offs_qs:
                time_offs_by_salon_stylist[
                    (time_off.salon_id, time_off.stylist_id)
                ].append(time_off)

            for salon in salons:
                if salon.id in filtered_by_availability:
                    continue

                salon_services = [
                    service for service in salon.services.all() if service.is_active
                ]
                salon_service_ids = {service.id for service in salon_services}
                matched_slots: list[dict] = []

                if selected_services:
                    salon_is_valid = True

                    for service in selected_services:
                        if service.id not in salon_service_ids:
                            salon_is_valid = False
                            break

                        slot_info = _find_service_slot(
                            service,
                            service_to_stylists.get(service.id, set()),
                            schedules_by_salon,
                            time_offs_by_salon_stylist,
                            bookings_by_salon_stylist,
                            salon.id,
                            filters.period,
                            filters.exact_time,
                        )

                        if slot_info is None:
                            salon_is_valid = False
                            break

                        matched_slots.append(slot_info)

                    if not salon_is_valid:
                        continue

                elif group_services:
                    available_group_services = [
                        service
                        for service in salon_services
                        if service.id in group_service_ids
                    ]

                    for service in available_group_services:
                        slot_info = _find_service_slot(
                            service,
                            service_to_stylists.get(service.id, set()),
                            schedules_by_salon,
                            time_offs_by_salon_stylist,
                            bookings_by_salon_stylist,
                            salon.id,
                            filters.period,
                            filters.exact_time,
                        )

                        if slot_info is not None:
                            matched_slots.append(slot_info)
                            break

                    if not matched_slots:
                        continue

                elif inferred_services:
                    query_service_ids = {service.id for service in inferred_services}
                    available_query_services = [
                        service
                        for service in salon_services
                        if service.id in query_service_ids
                    ]

                    if available_query_services:
                        for service in available_query_services:
                            slot_info = _find_service_slot(
                                service,
                                service_to_stylists.get(service.id, set()),
                                schedules_by_salon,
                                time_offs_by_salon_stylist,
                                bookings_by_salon_stylist,
                                salon.id,
                                filters.period,
                                filters.exact_time,
                            )

                            if slot_info is not None:
                                matched_slots.append(slot_info)
                                break

                        if not matched_slots:
                            continue
                    else:
                        fallback_slot = _find_any_slot(
                            salon.id,
                            schedules_by_salon,
                            time_offs_by_salon_stylist,
                            bookings_by_salon_stylist,
                            filters.period,
                            filters.exact_time,
                        )

                        if fallback_slot is None:
                            continue

                        matched_slots.append(fallback_slot)

                else:
                    fallback_slot = _find_any_slot(
                        salon.id,
                        schedules_by_salon,
                        time_offs_by_salon_stylist,
                        bookings_by_salon_stylist,
                        filters.period,
                        filters.exact_time,
                    )

                    if fallback_slot is None:
                        continue

                    matched_slots.append(fallback_slot)

                first_slot = min((slot["slot"] for slot in matched_slots), default="")

                matched_service_names = []
                for slot in matched_slots:
                    service_name = slot.get("service_name")
                    if service_name and service_name not in matched_service_names:
                        matched_service_names.append(service_name)

                salon.search_matched_services = matched_service_names

                if first_slot:
                    if len(availability_dates) > 1:
                        date_label = current_date.strftime("%Y/%m/%d")
                        salon.search_available_label = (
                            f"اولین زمان آزاد {date_label} ساعت {first_slot}"
                        )
                    else:
                        salon.search_available_label = f"اولین زمان آزاد {first_slot}"
                else:
                    salon.search_available_label = "دارای وقت آزاد"

                filtered_by_availability[salon.id] = salon

        salons = [salon for salon in salons if salon.id in filtered_by_availability]

    price_filtered_salons: list[Salon] = []

    for salon in salons:
        salon.search_matched_services = getattr(salon, "search_matched_services", [])
        salon.search_available_label = getattr(salon, "search_available_label", "")
        salon.search_distance_km = None

        if distance_supported and getattr(salon, "distance", None) is not None:
            try:
                salon.search_distance_km = round(salon.distance.km, 1)
            except Exception:
                salon.search_distance_km = None

        elif getattr(salon, "zone", None):
            try:
                salon.search_distance_km = round(float(salon.zone), 1)
            except Exception:
                salon.search_distance_km = None

        relevant_prices: list[int] = []

        relevant_ids = {service.id for service in selected_services}

        if not relevant_ids and group_services:
            relevant_ids = {service.id for service in group_services}

        if not relevant_ids and inferred_services:
            relevant_ids = {service.id for service in inferred_services}

        try:
            salon_stylist_ids = {stylist.pk for stylist in salon.stylists.all()}
        except Exception:
            salon_stylist_ids = set()

        for service in salon.services.all():
            if relevant_ids and service.id not in relevant_ids:
                continue

            base_price = _coerce_price(getattr(service, "base_price", None))
            if base_price:
                relevant_prices.append(base_price)

            for price in service.service_prices.all():
                if (
                    salon_stylist_ids
                    and getattr(price, "stylist_id", None) not in salon_stylist_ids
                ):
                    continue
                parsed_price = _coerce_price(getattr(price, "price", None))
                if parsed_price:
                    relevant_prices.append(parsed_price)

        salon.search_primary_price = (
            min(relevant_prices)
            if relevant_prices
            else _coerce_price(getattr(salon, "min_price", None))
        )

        if filters.has_price_filter and not _price_matches_filter(
            salon.search_primary_price, filters
        ):
            continue

        salon.search_location_label = (
            salon.neighborhood.name if salon.neighborhood else (salon.address or "")
        )
        price_filtered_salons.append(salon)

    salons = price_filtered_salons

    if filters.sort == "price":
        salons.sort(
            key=lambda salon: (
                salon.search_primary_price is None,
                salon.search_primary_price or 0,
                -(salon.avg_score or 0),
            )
        )

    elif filters.sort == "nearest" and distance_supported:
        salons.sort(
            key=lambda salon: (
                salon.search_distance_km is None,
                salon.search_distance_km or 0,
                -(salon.avg_score or 0),
            )
        )

    elif filters.sort == "newest":
        salons.sort(key=lambda salon: salon.registere_date, reverse=True)

    else:
        salons.sort(
            key=lambda salon: (
                0 if getattr(salon, "search_available_label", "") else 1,
                -(salon.avg_score or 0),
                -(salon.total_reviews or 0),
                (
                    salon.search_distance_km
                    if salon.search_distance_km is not None
                    else 9999
                ),
                salon.registere_date,
            )
        )

    service_ids_csv = ",".join(str(service.id) for service in selected_services)

    return {
        "salons": salons,
        "selected_group": selected_group,
        "selected_services": selected_services,
        "group_services": group_services[:30],
        "summary": build_search_summary(filters, selected_services, selected_group),
        "service_ids_csv": service_ids_csv,
        "distance_supported": distance_supported,
    }


def serialize_salon_for_map(salon: Salon) -> dict:
    coords = [0, 0]
    if getattr(salon, "location", None):
        try:
            coords = [salon.location.x, salon.location.y]
        except Exception:
            coords = [0, 0]
    return {
        "id": salon.id,
        "salon_name": salon.salon_name,
        "address": salon.address or "",
        "neighborhood": salon.neighborhood.name if salon.neighborhood else "",
        "detail_url": reverse("salons:detail_salon", args=[salon.id]),
        "image_url": (
            salon.banner_image.url if getattr(salon, "banner_image", None) else ""
        ),
        "banner_image": (
            salon.banner_image.url if getattr(salon, "banner_image", None) else ""
        ),
        "coordinates": coords,
        "avg_score": round(salon.avg_score or 0, 1),
        "available_label": getattr(salon, "search_available_label", ""),
        "distance_km": getattr(salon, "search_distance_km", None),
    }
