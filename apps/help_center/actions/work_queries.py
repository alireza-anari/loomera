from __future__ import annotations

from datetime import date, datetime

from django.db.models import Q
from django.utils import timezone

from apps.orders.models import OrderDetail
from apps.salons.models import SalonMembership, SalonMembershipStatus
from apps.stylists.models import StylistSchedule

from .common import (
    date_label,
    normalize_text,
    parse_relative_date,
    parse_weekday_dates,
    serialize_time,
)

UPCOMING_ORDER_STATUSES = ("pending", "confirmed", "paid")


def is_manager_read_query_candidate(message: str) -> bool:
    text = normalize_text(message)
    if not text or "چطور" in text or "چگونه" in text:
        return False
    if "درخواست" in text and any(term in text for term in ("برنامه", "مرخصی", "همکاری")):
        return False
    if any(term in text for term in ("نوبت", "رزرو")) and any(
        term in text for term in ("امروز", "فردا", "پس فردا", "بعدی", "چند", "تعداد", "کیه", "چه ساعتی")
    ):
        return True
    if any(term in text for term in ("برنامه", "شیفت", "ساعت کاری", "کار میکنه", "کار می کنه")):
        return True
    if any(term in text for term in ("متخصص", "اعضا", "تیم")) and "فعال" in text:
        return True
    if any(term in text for term in ("سرویس", "خدمت", "خدمات")) and any(
        term in text for term in ("سالن", "مجموعه", "داریم", "لیست", "چه")
    ):
        return True
    return False


def is_stylist_read_query_candidate(message: str) -> bool:
    text = normalize_text(message)
    if not text or "چطور" in text or "چگونه" in text:
        return False
    if any(
        term in text
        for term in (
            "ثبت کن", "ثبت کنم", "بساز", "بسازم", "بذار", "بزار",
            "تغییر بده", "درخواست", "مرخصی", "برداشت"
        )
    ):
        return False
    if any(term in text for term in ("نوبت", "مشتری بعدی")) and any(
        term in text for term in (
            "امروز", "فردا", "پس فردا", "بعدی", "بعدیم",
            "چند", "تعداد", "کیه", "چه ساعتی", "نشون", "نشان"
        )
    ):
        return True
    if any(
        term in text
        for term in ("برنامه", "شیفت", "ساعت کاری", "تا چه ساعتی", "چه ساعتی کار", "کار دارم")
    ):
        return True
    return False


def _notice(answer: str, *, result: dict | None = None, suggestions=None) -> dict:
    payload = {
        "handled": True,
        "kind": "action_notice",
        "answer": answer,
        "action_state": None,
    }
    if result is not None:
        payload["result"] = result
    if suggestions:
        payload["suggestions"] = list(suggestions)
    return payload


def _local_now(value: datetime | None = None) -> datetime:
    value = value or timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value)


def _target_date(message: str, *, today: date) -> date:
    relative = parse_relative_date(message, today=today)
    if relative:
        return relative
    weekdays = parse_weekday_dates(message, today=today)
    return weekdays[0] if weekdays else today


def _day_word(target: date, *, today: date) -> str:
    if target == today:
        return "امروز"
    if target.toordinal() == today.toordinal() + 1:
        return "فردا"
    return date_label(target)


def _customer_name(item: OrderDetail) -> str:
    user = getattr(getattr(item.order, "customer", None), "user", None)
    if user is None:
        return "مشتری"
    try:
        return user.get_fullName().strip() or "مشتری"
    except Exception:
        return (
            f"{getattr(user, 'name', '')} {getattr(user, 'family', '')}".strip()
            or "مشتری"
        )


def _stylist_name(stylist) -> str:
    try:
        return stylist.get_fullName().strip() or "متخصص"
    except Exception:
        return str(stylist) or "متخصص"


def _appointment_payload(item: OrderDetail) -> dict:
    return {
        "id": item.pk,
        "date": item.date.isoformat() if item.date else "",
        "time": serialize_time(item.time),
        "end_time": serialize_time(item.end_time),
        "service": getattr(getattr(item, "service", None), "service_name", "خدمت"),
        "customer": _customer_name(item),
        "stylist": _stylist_name(item.stylist),
        "status": item.get_status_display_fa(),
    }


def _base_appointments(*, salon, stylist=None):
    queryset = (
        OrderDetail.objects.select_related(
            "order", "order__customer__user", "service", "stylist__user", "salon"
        )
        .filter(salon=salon)
        .exclude(order__status="cancelled")
        .exclude(confirmation_status=OrderDetail.ConfirmationStatus.REJECTED)
    )
    return queryset.filter(stylist=stylist) if stylist is not None else queryset


def _day_appointments(*, salon, target_date: date, stylist=None):
    return _base_appointments(salon=salon, stylist=stylist).filter(date=target_date).order_by("time", "pk")


def _next_appointment(*, salon, stylist=None, now: datetime | None = None):
    local_now = _local_now(now)
    today = local_now.date()
    return (
        _base_appointments(salon=salon, stylist=stylist)
        .filter(order__status__in=UPCOMING_ORDER_STATUSES)
        .filter(Q(date__gt=today) | Q(date=today, time__gt=local_now.time()))
        .order_by("date", "time", "pk")
        .first()
    )


def _active_stylists(salon):
    memberships = (
        SalonMembership.objects.select_related("stylist__user")
        .filter(
            salon=salon,
            status=SalonMembershipStatus.ACTIVE,
            stylist__isnull=False,
        )
        .order_by("stylist__user__name", "stylist__user__family", "pk")
    )
    return [item.stylist for item in memberships]


def _match_stylist(*, salon, message: str):
    text = normalize_text(message)
    scored = []
    for stylist in _active_stylists(salon):
        user = getattr(stylist, "user", None)
        aliases = {
            normalize_text(_stylist_name(stylist)),
            normalize_text(getattr(user, "name", "")),
            normalize_text(getattr(user, "family", "")),
            normalize_text(getattr(stylist, "display_name", "")),
        }
        aliases = {alias for alias in aliases if len(alias) >= 2}
        score = max((len(alias) for alias in aliases if alias in text), default=0)
        if score:
            scored.append((score, stylist))
    if not scored:
        return "none", []
    best = max(score for score, _ in scored)
    matches = [stylist for score, stylist in scored if score == best]
    return ("one", matches) if len(matches) == 1 else ("ambiguous", matches)


def _ambiguity(matches) -> dict:
    names = [_stylist_name(item) for item in matches]
    return _notice(
        "چند متخصص با این نام پیدا کردم. نام کامل رو بگو تا اشتباه انتخاب نکنم: "
        + "، ".join(names),
        result={"type": "ambiguity", "items": names},
        suggestions=names,
    )


def _schedule_rows(*, salon, stylist=None, target_date: date):
    queryset = StylistSchedule.objects.select_related("stylist__user", "service").filter(
        salon=salon, date=target_date
    )
    if stylist is not None:
        queryset = queryset.filter(stylist=stylist)
    rows = []
    for item in queryset.order_by("start_time", "end_time", "pk"):
        rows.append(
            {
                "id": item.pk,
                "stylist": _stylist_name(item.stylist),
                "start_time": serialize_time(item.start_time),
                "end_time": serialize_time(item.end_time),
                "service": getattr(getattr(item, "service", None), "service_name", "همه خدمات"),
            }
        )
    return rows


def _appointment_lines(items, *, include_stylist: bool) -> str:
    lines = []
    for item in items[:8]:
        row = _appointment_payload(item)
        parts = [row["time"] or "بدون ساعت", row["customer"], row["service"]]
        if include_stylist:
            parts.append(row["stylist"])
        lines.append(" · ".join(parts))
    return "\n".join(lines)


def run_manager_read_query(
    *, salon, message: str, today: date | None = None, now: datetime | None = None
) -> dict | None:
    if not is_manager_read_query_candidate(message):
        return None

    text = normalize_text(message)
    today = today or timezone.localdate()
    target = _target_date(message, today=today)
    day_word = _day_word(target, today=today)

    if any(term in text for term in ("متخصص", "اعضا", "تیم")) and "فعال" in text:
        names = [_stylist_name(item) for item in _active_stylists(salon)]
        answer = (
            f"{len(names)} متخصص فعال داری: " + "، ".join(names)
            if names
            else "فعلاً متخصص فعالی برای این مجموعه پیدا نکردم."
        )
        return _notice(answer, result={"type": "active_stylists", "count": len(names), "items": names})

    if any(term in text for term in ("سرویس", "خدمت", "خدمات")) and any(
        term in text for term in ("سالن", "مجموعه", "داریم", "لیست", "چه")
    ):
        services = list(
            salon.services.filter(is_active=True)
            .order_by("service_name")
            .values_list("service_name", flat=True)
        )
        answer = (
            f"{len(services)} خدمت فعال داری: " + "، ".join(services[:12])
            if services
            else "فعلاً خدمت فعالی برای این مجموعه پیدا نکردم."
        )
        return _notice(answer, result={"type": "services", "count": len(services), "items": services[:20]})

    if any(term in text for term in ("برنامه", "شیفت", "ساعت کاری", "کار میکنه", "کار می کنه")):
        match_kind, matches = _match_stylist(salon=salon, message=message)
        if match_kind == "ambiguous":
            return _ambiguity(matches)
        if match_kind == "one":
            stylist = matches[0]
            rows = _schedule_rows(salon=salon, stylist=stylist, target_date=target)
            name = _stylist_name(stylist)
            if not rows:
                return _notice(
                    f"برای {name} در {day_word} برنامه کاری ثبت‌شده‌ای پیدا نکردم.",
                    result={"type": "stylist_schedule", "date": target.isoformat(), "stylist": name, "items": []},
                )
            periods = [f"{row['start_time']} تا {row['end_time']}" for row in rows]
            return _notice(
                f"برنامه {name} برای {day_word}: " + "، ".join(periods),
                result={"type": "stylist_schedule", "date": target.isoformat(), "stylist": name, "items": rows},
            )
        if any(term in text for term in ("تیم", "متخصص ها", "متخصص‌های", "اعضا")):
            rows = _schedule_rows(salon=salon, target_date=target)
            if not rows:
                return _notice(
                    f"برای {day_word} برنامه کاری ثبت‌شده‌ای برای تیم پیدا نکردم.",
                    result={"type": "team_schedule", "date": target.isoformat(), "items": []},
                )
            lines = [f"{row['stylist']} · {row['start_time']} تا {row['end_time']}" for row in rows[:10]]
            return _notice(
                f"برنامه تیم برای {day_word}:\n" + "\n".join(lines),
                result={"type": "team_schedule", "date": target.isoformat(), "items": rows[:20]},
            )
        return _notice("متخصص موردنظر رو در اعضای فعال این مجموعه پیدا نکردم.")

    if any(term in text for term in ("نوبت", "رزرو")) and "بعدی" in text:
        match_kind, matches = _match_stylist(salon=salon, message=message)
        if match_kind == "ambiguous":
            return _ambiguity(matches)
        stylist = matches[0] if match_kind == "one" else None
        item = _next_appointment(salon=salon, stylist=stylist, now=now)
        if item is None:
            subject = _stylist_name(stylist) if stylist else "مجموعه"
            return _notice(
                f"نوبت بعدی فعالی برای {subject} پیدا نکردم.",
                result={"type": "next_appointment", "item": None},
            )
        row = _appointment_payload(item)
        subject = f" {_stylist_name(stylist)}" if stylist else ""
        return _notice(
            f"نوبت بعدی{subject}: {date_label(item.date)} ساعت {row['time']} · {row['customer']} · {row['service']}.",
            result={"type": "next_appointment", "item": row},
        )

    if any(term in text for term in ("نوبت", "رزرو")):
        match_kind, matches = _match_stylist(salon=salon, message=message)
        if match_kind == "ambiguous":
            return _ambiguity(matches)
        stylist = matches[0] if match_kind == "one" else None
        items = list(_day_appointments(salon=salon, target_date=target, stylist=stylist))
        if any(term in text for term in ("چند", "تعداد")):
            subject = f" برای {_stylist_name(stylist)}" if stylist else ""
            return _notice(
                f"{day_word}{subject} {len(items)} نوبت غیرلغوشده ثبت شده.",
                result={"type": "appointment_count", "date": target.isoformat(), "count": len(items)},
            )
        if not items:
            return _notice(
                f"برای {day_word} نوبتی پیدا نکردم.",
                result={"type": "appointments", "date": target.isoformat(), "items": []},
            )
        return _notice(
            f"نوبت‌های {day_word}:\n" + _appointment_lines(items, include_stylist=True),
            result={
                "type": "appointments",
                "date": target.isoformat(),
                "count": len(items),
                "items": [_appointment_payload(item) for item in items[:20]],
            },
        )

    return None


def run_stylist_read_query(
    *,
    salon,
    stylist,
    message: str,
    today: date | None = None,
    now: datetime | None = None,
    can_view_clients: bool = True,
) -> dict | None:
    if not is_stylist_read_query_candidate(message):
        return None

    text = normalize_text(message)
    today = today or timezone.localdate()
    target = _target_date(message, today=today)
    day_word = _day_word(target, today=today)
    appointment_query = any(
        term in text for term in ("نوبت", "مشتری", "مشتری بعدی")
    )
    if appointment_query and not can_view_clients:
        return _notice(
            "برای دیدن نوبت‌ها و اطلاعات مشتری‌ها در این مجموعه دسترسی لازم رو نداری.",
            result={
                "type": "permission_denied",
                "permission": "can_view_own_clients",
            },
        )

    if any(term in text for term in ("نوبت", "مشتری بعدی")) and (
        "بعدی" in text or "بعدیم" in text or "مشتری بعدی" in text
    ):
        item = _next_appointment(salon=salon, stylist=stylist, now=now)
        if item is None:
            return _notice("نوبت بعدی فعالی برات پیدا نکردم.", result={"type": "next_appointment", "item": None})
        row = _appointment_payload(item)
        return _notice(
            f"نوبت بعدیت {date_label(item.date)} ساعت {row['time']} با {row['customer']} برای {row['service']} هست.",
            result={"type": "next_appointment", "item": row},
        )

    if any(term in text for term in ("نوبت", "مشتری")):
        items = list(_day_appointments(salon=salon, target_date=target, stylist=stylist))
        if any(term in text for term in ("چند", "تعداد")):
            return _notice(
                f"{day_word} {len(items)} نوبت غیرلغوشده داری.",
                result={"type": "appointment_count", "date": target.isoformat(), "count": len(items)},
            )
        if not items:
            return _notice(
                f"برای {day_word} نوبتی برات پیدا نکردم.",
                result={"type": "appointments", "date": target.isoformat(), "items": []},
            )
        return _notice(
            f"نوبت‌های {day_word}:\n" + _appointment_lines(items, include_stylist=False),
            result={
                "type": "appointments",
                "date": target.isoformat(),
                "count": len(items),
                "items": [_appointment_payload(item) for item in items[:20]],
            },
        )

    if any(
        term in text
        for term in ("برنامه", "شیفت", "ساعت کاری", "تا چه ساعتی", "چه ساعتی کار", "کار دارم")
    ):
        rows = _schedule_rows(salon=salon, stylist=stylist, target_date=target)
        if not rows:
            return _notice(
                f"برای {day_word} برنامه کاری ثبت‌شده‌ای برات پیدا نکردم.",
                result={"type": "stylist_schedule", "date": target.isoformat(), "items": []},
            )
        if any(term in text for term in ("تا چه ساعتی", "چه ساعتی کار", "کار دارم")):
            latest = max(row["end_time"] for row in rows)
            return _notice(
                f"{day_word} طبق برنامه تا ساعت {latest} کار داری.",
                result={"type": "stylist_schedule_end", "date": target.isoformat(), "end_time": latest, "items": rows},
            )
        periods = [f"{row['start_time']} تا {row['end_time']}" for row in rows]
        return _notice(
            f"برنامه‌ات برای {day_word}: " + "، ".join(periods),
            result={"type": "stylist_schedule", "date": target.isoformat(), "items": rows},
        )

    return None

