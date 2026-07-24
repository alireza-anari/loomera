from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.salons.models import Salon
from apps.services.models import ServicePrice, Services
from apps.stylists.models import StaffLeaveRequest, StylistSchedule

from .models import OrderDetail

BLOCKING_STATUSES = ["pending", "confirmed", "paid", "completed"]
DEFAULT_SLOT_STEP = 15
DEFAULT_CANCELLATION_HOURS = 24
POLICY_KEYWORDS = ("لغو", "کنسلی", "cancellation", "cancel")


@dataclass
class ResolvedSequenceItem:
    index: int
    key: str
    requested_stylist_id: str
    service: Services
    stylist: Stylist
    price: int
    date_value: date
    start_time: time
    end_time: time
    duration_minutes: int
    auto_resolved: bool = False

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.date_value, self.start_time)

    @property
    def end_datetime(self) -> datetime:
        return datetime.combine(self.date_value, self.end_time)


def parse_date_value(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValidationError("تاریخ انتخاب‌شده نامعتبر است.") from exc
    raise ValidationError("تاریخ انتخاب‌شده نامعتبر است.")


def parse_time_value(value) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
    raise ValidationError("زمان انتخاب‌شده نامعتبر است.")


def combine_date_time(date_value, time_value) -> datetime:
    return datetime.combine(parse_date_value(date_value), parse_time_value(time_value))


def minutes_between(start_time: time, end_time: time) -> int:
    start = start_time.hour * 60 + start_time.minute
    end = end_time.hour * 60 + end_time.minute
    return end - start


def interval_overlaps(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and end_a > start_b


def _slot_is_available_against_windows(
    *,
    date_value: date,
    start_time: time,
    duration_minutes: int,
    buffer_minutes: int,
    schedule_windows: list[tuple[time, time]],
    time_off_windows: list[tuple[time, time]],
    booking_windows: list[tuple[time, time]],
) -> bool:
    """Evaluate one slot using windows already loaded from the database."""

    start_dt = datetime.combine(date_value, start_time)
    occupied_end_dt = start_dt + timedelta(
        minutes=duration_minutes + int(buffer_minutes or 0)
    )
    occupied_end_time = occupied_end_dt.time()

    fits_schedule = any(
        start_time >= window_start and occupied_end_time <= window_end
        for window_start, window_end in schedule_windows
    )
    if not fits_schedule:
        return False

    if any(
        interval_overlaps(
            start_time,
            occupied_end_time,
            off_start,
            off_end,
        )
        for off_start, off_end in time_off_windows
    ):
        return False

    if any(
        interval_overlaps(
            start_time,
            occupied_end_time,
            booking_start,
            booking_end,
        )
        for booking_start, booking_end in booking_windows
    ):
        return False

    return True


def _ceil_to_step(minutes: int, step: int = DEFAULT_SLOT_STEP) -> int:
    return ((max(minutes, 0) + step - 1) // step) * step


def _minutes_to_time(value: int) -> time:
    value = max(value, 0)
    return time(value // 60, value % 60)


def _current_day_minute_floor(target_date: date) -> int | None:
    if target_date != timezone.localdate():
        return None
    now = timezone.localtime(timezone.now()).time()
    return now.hour * 60 + now.minute


def get_service_duration_minutes(service: Services) -> int:
    return int(getattr(service, "duration_minutes", 30) or 30)


def get_service_buffer_minutes(service: Services) -> int:
    return int(getattr(service, "buffer_minutes", 0) or 0)


def get_service_occupied_minutes(service: Services) -> int:
    return get_service_duration_minutes(service) + get_service_buffer_minutes(service)


def get_available_slots_for_service(
    *,
    salon: Salon,
    stylist: Stylist,
    service: Services,
    date_value: date,
    earliest_start_minutes: int | None = None,
    slot_step: int = DEFAULT_SLOT_STEP,
    exclude_order_detail_ids: Iterable[int] | None = None,
) -> list[tuple[time, time]]:
    """Return service slots with a fixed three-query availability budget.

    Schedule, approved leave and blocking booking windows are loaded once for
    the stylist/date. Candidate slots are then evaluated entirely in memory.

    This function does not reserve a slot. Callers performing a write must
    still revalidate availability inside their transaction boundary.
    """

    duration_minutes = get_service_duration_minutes(service)
    buffer_minutes = get_service_buffer_minutes(service)
    occupied_minutes = duration_minutes + buffer_minutes
    current_floor = _current_day_minute_floor(date_value)

    schedule_windows = _get_schedule_windows(
        stylist,
        salon,
        date_value,
        service,
    )
    if not schedule_windows:
        return []

    time_off_windows = _get_time_off_windows(
        stylist,
        salon,
        date_value,
    )
    booking_windows = _get_booking_windows(
        salon,
        stylist,
        date_value,
        exclude_order_detail_ids,
    )

    results: list[tuple[time, time]] = []

    for window_start, window_end in schedule_windows:
        start_minutes = window_start.hour * 60 + window_start.minute
        end_minutes = window_end.hour * 60 + window_end.minute

        earliest = start_minutes
        if earliest_start_minutes is not None:
            earliest = max(earliest, earliest_start_minutes)
        if current_floor is not None:
            earliest = max(earliest, current_floor + 1)

        slot_start = _ceil_to_step(earliest, slot_step)
        last_start = end_minutes - occupied_minutes

        while slot_start <= last_start:
            start_time = _minutes_to_time(slot_start)

            if _slot_is_available_against_windows(
                date_value=date_value,
                start_time=start_time,
                duration_minutes=duration_minutes,
                buffer_minutes=buffer_minutes,
                schedule_windows=schedule_windows,
                time_off_windows=time_off_windows,
                booking_windows=booking_windows,
            ):
                end_time = _minutes_to_time(slot_start + duration_minutes)
                results.append((start_time, end_time))

            slot_start += slot_step

    results.sort(
        key=lambda item: (
            item[0].hour,
            item[0].minute,
        )
    )
    return results


def find_first_available_slot(
    *,
    salon: Salon,
    stylist: Stylist,
    service: Services,
    start_date: date | None = None,
    horizon_days: int = 30,
    earliest_start_minutes_by_date: dict[date, int] | None = None,
    exclude_order_detail_ids: Iterable[int] | None = None,
) -> dict | None:
    cursor = start_date or timezone.localdate()
    earliest_start_minutes_by_date = earliest_start_minutes_by_date or {}

    for offset in range(max(horizon_days, 1)):
        target_date = cursor + timedelta(days=offset)
        slots = get_available_slots_for_service(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=target_date,
            earliest_start_minutes=earliest_start_minutes_by_date.get(target_date),
            exclude_order_detail_ids=exclude_order_detail_ids,
        )
        if not slots:
            continue
        start_time, end_time = slots[0]
        return {
            "date": target_date,
            "time": start_time,
            "end_time": end_time,
        }
    return None


def get_upcoming_available_stylists_for_service(
    *,
    salon: Salon,
    service: Services,
    start_date: date | None = None,
    horizon_days: int = 30,
) -> list[dict]:
    stylists = list(
        salon.stylists.filter(services_of_stylist=service, is_active=True)
        .select_related("user")
        .distinct()
        .order_by("user_id")
    )

    available = []
    for stylist in stylists:
        first_slot = find_first_available_slot(
            salon=salon,
            stylist=stylist,
            service=service,
            start_date=start_date,
            horizon_days=horizon_days,
        )
        if not first_slot:
            continue
        available.append(
            {
                "stylist": stylist,
                "first_slot": first_slot,
                "price": get_price_for_stylist_service(stylist, service),
            }
        )

    available.sort(
        key=lambda item: (
            item["first_slot"]["date"],
            item["first_slot"]["time"],
            item["stylist"].user_id,
        )
    )
    return available


def resolve_best_available_stylist_for_service(
    *,
    salon: Salon,
    service: Services,
    start_date: date | None = None,
    horizon_days: int = 30,
) -> dict | None:
    available = get_upcoming_available_stylists_for_service(
        salon=salon,
        service=service,
        start_date=start_date,
        horizon_days=horizon_days,
    )
    return available[0] if available else None


def get_candidate_stylists_for_service(
    *,
    salon: Salon,
    service: Services,
    requested_stylist_id: str | int | None,
    resolved_stylist_id: str | int | None = None,
) -> list[Stylist]:
    if resolved_stylist_id not in (None, "", "any"):
        resolved = Stylist.objects.filter(
            user_id=int(resolved_stylist_id),
            stylists_of_salon=salon,
            services_of_stylist=service,
            is_active=True,
        ).select_related("user")
        if resolved.exists():
            return list(resolved)

    if requested_stylist_id not in (None, "", "any"):
        return list(
            Stylist.objects.filter(
                user_id=int(resolved_stylist_id),
                stylists_of_salon=salon,
                services_of_stylist=service,
                is_active=True,
            ).select_related("user")[:1]
        )

    return list(
        salon.stylists.filter(
            services_of_stylist=service,
            is_active=True,
        )
        .select_related("user")
        .distinct()
        .order_by("user_id")
    )


def get_price_for_stylist_service(stylist: Stylist, service: Services) -> int:
    price = stylist.get_price_for_service(service)
    if price is not None:
        return int(price)

    fallback = ServicePrice.objects.filter(service=service).order_by("price").first()
    if fallback:
        return int(fallback.price)
    return int(getattr(service, "base_price", 0) or 0)


def _salon_day_key(date_value: date) -> int:
    # SalonOpeningHours uses 1=Saturday ... 7=Friday; Python weekday is Monday=0.
    return ((date_value.weekday() + 2) % 7) + 1


def _get_salon_opening_windows(
    salon: Salon, date_value: date
) -> list[tuple[time, time]]:
    windows = []
    for item in salon.opening_hours.filter(day_of_week=_salon_day_key(date_value)):
        if item.is_closed or not item.open_time or not item.close_time:
            continue
        if item.close_time <= item.open_time:
            continue
        windows.append((item.open_time, item.close_time))
    windows.sort(key=lambda item: item[0])
    return windows


def _get_schedule_windows(
    stylist: Stylist,
    salon: Salon,
    date_value: date,
    service: Services,
) -> list[tuple[time, time]]:
    day_schedules = list(
        StylistSchedule.objects.filter(
            stylist=stylist,
            salon=salon,
            date=date_value,
        )
        .select_related("service")
        .order_by("start_time")
    )

    service_windows = [
        (schedule.start_time, schedule.end_time)
        for schedule in day_schedules
        if schedule.start_time
        and schedule.end_time
        and (schedule.service_id is None or schedule.service_id == service.id)
    ]

    if service_windows:
        return service_windows

    # نکته مهم چندسالنی:
    # اگر برای متخصص در همین سالن و همین روز برنامه کاری ثبت نشده باشد،
    # نباید ساعت کاری عمومی سالن به عنوان ظرفیت متخصص استفاده شود.
    return []


def _get_time_off_windows(
    stylist: Stylist,
    salon: Salon,
    date_value: date,
) -> list[tuple[time, time]]:
    leave_requests = StaffLeaveRequest.objects.filter(
        stylist=stylist,
        salon=salon,
        date=date_value,
        status=StaffLeaveRequest.Status.APPROVED,
    )

    windows: list[tuple[time, time]] = []

    for item in leave_requests:
        start = item.start_time or time.min
        end = item.end_time or time(23, 59)
        windows.append((start, end))

    return windows


def _get_booking_windows(
    salon: Salon,
    stylist: Stylist,
    date_value: date,
    exclude_order_detail_ids: Iterable[int] | None = None,
) -> list[tuple[time, time]]:
    qs = OrderDetail.objects.filter(
        salon=salon,
        stylist=stylist,
        date=date_value,
        order__status__in=BLOCKING_STATUSES,
    ).filter(Q(order__is_finally=True) | Q(order__is_paid=True))
    if exclude_order_detail_ids:
        qs = qs.exclude(id__in=list(exclude_order_detail_ids))

    windows: list[tuple[time, time]] = []
    for booking in qs.only("time", "end_time", "occupied_until"):
        booking_end = booking.occupied_until or booking.end_time
        if booking.time and booking_end:
            windows.append((booking.time, booking_end))
    return windows


def slot_is_available(
    *,
    salon: Salon,
    stylist: Stylist,
    service: Services,
    date_value: date,
    start_time: time,
    duration_minutes: int,
    buffer_minutes: int = 0,
    exclude_order_detail_ids: Iterable[int] | None = None,
) -> bool:
    """Validate one slot after loading each availability window once."""

    schedule_windows = _get_schedule_windows(
        stylist,
        salon,
        date_value,
        service,
    )
    if not schedule_windows:
        return False

    return _slot_is_available_against_windows(
        date_value=date_value,
        start_time=start_time,
        duration_minutes=duration_minutes,
        buffer_minutes=buffer_minutes,
        schedule_windows=schedule_windows,
        time_off_windows=_get_time_off_windows(
            stylist,
            salon,
            date_value,
        ),
        booking_windows=_get_booking_windows(
            salon,
            stylist,
            date_value,
            exclude_order_detail_ids,
        ),
    )


def resolve_booking_sequence(
    *,
    salon: Salon,
    stylist_selections: list[dict],
    datetime_selections: dict,
    exclude_order_detail_ids: Iterable[int] | None = None,
) -> list[ResolvedSequenceItem]:
    if not stylist_selections:
        raise ValidationError("هیچ خدمتی برای رزرو انتخاب نشده است.")

    resolved_items: list[ResolvedSequenceItem] = []
    previous_date: date | None = None
    previous_end_dt: datetime | None = None

    for index, selection in enumerate(stylist_selections):
        service_id = int(selection.get("serviceId"))
        requested_stylist_id = str(
            selection.get("requestedStylistId") or selection.get("stylistId") or ""
        )
        current_stylist_id = selection.get("stylistId")
        resolved_stylist_id = selection.get("resolvedStylistId") or current_stylist_id

        service = Services.objects.get(
            pk=service_id,
            services_of_salon=salon,
            is_active=True,
        )
        duration_minutes = get_service_duration_minutes(service)
        buffer_minutes = get_service_buffer_minutes(service)

        selection_keys = [
            f"{requested_stylist_id}_{service_id}",
            (
                f"{current_stylist_id}_{service_id}"
                if current_stylist_id not in (None, "")
                else None
            ),
            (
                f"{resolved_stylist_id}_{service_id}"
                if resolved_stylist_id not in (None, "")
                else None
            ),
        ]
        selection_keys = [key for key in selection_keys if key]

        datetime_info = {}
        used_key = selection_keys[0]
        for key in selection_keys:
            if key in datetime_selections:
                datetime_info = datetime_selections.get(key) or {}
                used_key = key
                break

        selected_date = datetime_info.get("date")
        selected_time = datetime_info.get("time")

        if not selected_date or not selected_time:
            raise ValidationError("تاریخ یا زمان یکی از خدمات انتخاب نشده است.")

        date_value = parse_date_value(selected_date)
        start_time = parse_time_value(selected_time)

        start_dt = datetime.combine(date_value, start_time)
        if previous_date and date_value < previous_date:
            raise ValidationError(
                "ترتیب خدمات نمی‌تواند به روزهای قبل برگردد. برای هر خدمت باید همان روز یا روز بعد را انتخاب کنید."
            )
        if (
            previous_end_dt
            and previous_date == date_value
            and start_dt < previous_end_dt
        ):
            raise ValidationError(
                "زمان خدمات در یک روز باید به‌صورت ترتیبی و بدون هم‌پوشانی انتخاب شود."
            )

        candidate_stylists = get_candidate_stylists_for_service(
            salon=salon,
            service=service,
            requested_stylist_id=requested_stylist_id,
            resolved_stylist_id=resolved_stylist_id,
        )
        if not candidate_stylists:
            raise ValidationError(
                f"برای خدمت «{service.service_name}» آرایشگر معتبری یافت نشد."
            )

        selected_stylist: Stylist | None = None
        auto_resolved = False
        for candidate in candidate_stylists:
            if slot_is_available(
                salon=salon,
                stylist=candidate,
                service=service,
                date_value=date_value,
                start_time=start_time,
                duration_minutes=duration_minutes,
                buffer_minutes=buffer_minutes,
                exclude_order_detail_ids=exclude_order_detail_ids,
            ):
                selected_stylist = candidate
                auto_resolved = str(candidate.user_id) != str(resolved_stylist_id)
                break

        if selected_stylist is None:
            raise ValidationError(
                f"زمان انتخاب‌شده برای «{service.service_name}» دیگر آزاد نیست یا همین حالا توسط کاربر دیگری نهایی شده است. لطفاً یک زمان آزاد دیگر انتخاب کنید."
            )

        end_dt = start_dt + timedelta(minutes=duration_minutes)
        occupied_end_dt = start_dt + timedelta(
            minutes=duration_minutes + buffer_minutes
        )
        price = get_price_for_stylist_service(selected_stylist, service)

        resolved_items.append(
            ResolvedSequenceItem(
                index=index,
                key=used_key,
                requested_stylist_id=requested_stylist_id,
                service=service,
                stylist=selected_stylist,
                price=price,
                date_value=date_value,
                start_time=start_time,
                end_time=end_dt.time(),
                duration_minutes=duration_minutes,
                auto_resolved=auto_resolved,
            )
        )
        previous_date = date_value
        previous_end_dt = end_dt

    return resolved_items


def build_cancellation_policy(
    salon: Salon, *, can_cancel: bool, is_upcoming: bool
) -> dict[str, str]:
    text = None
    try:
        supplementary_items = salon.supplementary_info.filter(is_active=True)
        for item in supplementary_items:
            haystack = f"{item.title or ''} {item.description or ''}".lower()
            if any(keyword in haystack for keyword in POLICY_KEYWORDS):
                text = item.description or item.title
                if text:
                    break
    except Exception:
        text = None

    cancellation_hours = int(
        getattr(salon, "cancellation_window_hours", DEFAULT_CANCELLATION_HOURS)
        or DEFAULT_CANCELLATION_HOURS
    )
    refund_percent = int(getattr(salon, "cancellation_refund_percent", 100) or 0)
    policy_note = (getattr(salon, "cancellation_policy_note", "") or "").strip()

    if text:
        title = "سیاست لغو این سالن"
        description = text.strip()
    elif policy_note:
        title = "سیاست لغو این سالن"
        description = policy_note
    else:
        title = "سیاست لغو"
        description = f"لغو آنلاین تا {cancellation_hours} ساعت قبل از نوبت امکان‌پذیر است و در صورت پرداخت دیجیتال (آنلاین یا کیف پول)، {refund_percent}٪ مبلغ به کیف پول شما برمی‌گردد."

    if can_cancel:
        hint = f"در حال حاضر امکان لغو آنلاین برای شما فعال است. در صورت لغو این رزرو، {refund_percent}٪ مبلغ پرداخت دیجیتال به کیف پول شما برمی‌گردد."
    elif is_upcoming:
        hint = "برای این نوبت در حال حاضر امکان لغو آنلاین وجود ندارد و در صورت نیاز باید با سالن هماهنگ شود."
    else:
        hint = "برای نوبت‌های انجام‌شده یا گذشته، امکان لغو آنلاین در دسترس نیست."

    return {
        "title": title,
        "description": description,
        "hint": hint,
    }
