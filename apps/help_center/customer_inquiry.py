from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.booking_utils import get_upcoming_available_stylists_for_service
from apps.orders.quick_links import sign_booking_payload
from apps.salons.models import SalonMembership, SalonMembershipStatus

from .actions.common import normalize_text


PRIVATE_OPERATION_TERMS = (
    "نوبت من", "نوبتم", "رزرو من", "رزروم", "لغو کن", "لغوش کن",
    "جابجا", "جابه جا", "جابه‌جا", "تغییر نوبت", "شماره مشتری",
    "شماره تماس مشتری",
)
AVAILABILITY_TERMS = (
    "وقت خالی", "زمان خالی", "وقت آزاد", "زمان آزاد", "اولین وقت",
    "اولین زمان", "کی وقت دارید", "کی وقت دارین", "فردا وقت", "امروز وقت",
)
PRICE_TERMS = ("قیمت", "هزینه", "چنده", "چقدر")
SERVICE_TERMS = ("خدمت", "خدمات", "سرویس", "انجام میدید", "انجام می دین", "دارید", "دارین")
STYLIST_TERMS = ("متخصص", "آرایشگر", "استایلیست", "چه کسی", "کی انجام")
BOOKING_TERMS = ("رزرو", "وقت بگیر", "نوبت بگیر", "لینک رزرو")
ADDRESS_TERMS = ("آدرس", "کجاست", "کجا هستید", "کجا هستین")
HOURS_TERMS = ("ساعت کاری", "چه ساعتی باز", "کی باز", "چه روزهایی باز")


@dataclass(frozen=True)
class CustomerInquiryResult:
    disposition: str
    answer: str
    facts: dict[str, Any]
    requires_human: bool = False


def _public_base_url() -> str:
    return str(
        getattr(settings, "PUBLIC_BASE_URL", "")
        or getattr(settings, "SITE_URL", "")
        or ""
    ).strip().rstrip("/")


def _absolute_url(path: str) -> str:
    base = _public_base_url()
    return f"{base}{path}" if base else path


def _active_membership_stylist_ids(salon) -> set[int]:
    return set(
        SalonMembership.objects.filter(
            salon=salon,
            status=SalonMembershipStatus.ACTIVE,
            stylist__isnull=False,
            stylist__is_active=True,
        ).values_list("stylist_id", flat=True)
    )


def scoped_services(*, salon, stylist=None):
    qs = (
        salon.services.filter(is_active=True)
        .prefetch_related("service_prices", "stylists__user")
        .order_by("service_name", "pk")
        .distinct()
    )
    if stylist is not None:
        qs = qs.filter(stylists=stylist)
    return qs


def _match_service(*, salon, stylist, message: str):
    text = normalize_text(message)
    best = None
    best_score = 0
    for service in scoped_services(salon=salon, stylist=stylist):
        name = normalize_text(service.service_name)
        if not name:
            continue
        score = 0
        if name in text:
            score = len(name) + 100
        else:
            tokens = [token for token in name.split() if len(token) >= 2]
            matched = sum(1 for token in tokens if token in text)
            if tokens and matched:
                score = matched * 10
                if matched == len(tokens):
                    score += 30
        if score > best_score:
            best = service
            best_score = score
    return best


def _stylist_name(stylist) -> str:
    return (
        getattr(stylist, "professional_display_name", "")
        or stylist.get_fullName()
        or "متخصص"
    ).strip()


def _service_price_fact(*, service, salon, stylist=None):
    if stylist is not None:
        value = stylist.get_price_for_service(service)
        return {
            "kind": "single",
            "price": int(value) if value else None,
            "stylist": _stylist_name(stylist),
        }

    active_ids = _active_membership_stylist_ids(salon)
    values = []
    for price_obj in service.service_prices.all():
        if price_obj.stylist_id in active_ids and price_obj.price:
            values.append(int(price_obj.price))
    if not values and service.base_price:
        values.append(int(service.base_price))
    if not values:
        return {"kind": "unknown", "min": None, "max": None}
    return {"kind": "range", "min": min(values), "max": max(values)}


def _format_price(price_fact) -> str:
    if price_fact["kind"] == "single":
        price = price_fact.get("price")
        if not price:
            return "قیمت این خدمت هنوز به‌صورت قطعی ثبت نشده."
        return f"قیمت این خدمت {price:,} تومان است."
    minimum = price_fact.get("min")
    maximum = price_fact.get("max")
    if minimum is None:
        return "قیمت این خدمت هنوز به‌صورت قطعی ثبت نشده."
    if minimum == maximum:
        return f"قیمت این خدمت {minimum:,} تومان است."
    return f"قیمت این خدمت از {minimum:,} تا {maximum:,} تومان است."


def _format_date(value) -> str:
    try:
        from apps.dashboards.jalali_utils import format_jalali_numeric
        return format_jalali_numeric(value)
    except Exception:
        return value.isoformat()


def _availability_fact(*, salon, service, stylist=None):
    items = get_upcoming_available_stylists_for_service(
        salon=salon,
        service=service,
        start_date=timezone.localdate(),
        horizon_days=30,
    )
    if stylist is not None:
        items = [
            item for item in items
            if item.get("stylist") and item["stylist"].pk == stylist.pk
        ]
    else:
        active_ids = _active_membership_stylist_ids(salon)
        items = [
            item for item in items
            if item.get("stylist") and item["stylist"].pk in active_ids
        ]
    if not items:
        return None
    item = items[0]
    slot = item["first_slot"]
    available_stylist = item["stylist"]
    return {
        "stylist_id": available_stylist.pk,
        "stylist_user_id": available_stylist.user_id,
        "stylist": _stylist_name(available_stylist),
        "date": slot["date"].isoformat(),
        "date_label": _format_date(slot["date"]),
        "time": slot["time"].strftime("%H:%M"),
        "end_time": slot["end_time"].strftime("%H:%M"),
        "price": int(item.get("price") or 0) or None,
    }


def _booking_url(*, salon, service=None, stylist=None):
    if service is not None and stylist is not None:
        mode = "service_stylist"
    elif service is not None:
        mode = "service"
    elif stylist is not None:
        mode = "stylist"
    else:
        mode = "salon"
    payload = {
        "mode": mode,
        "salon_id": salon.pk,
        "service_ids": [service.pk] if service is not None else [],
        "stylist_user_id": stylist.user_id if stylist is not None else None,
        "date": "",
        "time": "",
        "summary": {"source": "instagram_lumi"},
    }
    token = sign_booking_payload(payload)
    path = reverse("orders:quick_booking_entry", kwargs={"token": token})
    return _absolute_url(path)


def _salon_hours(salon):
    rows = list(salon.opening_hours.all().order_by("day_of_week", "pk"))
    result = []
    for row in rows:
        if row.is_closed:
            value = "تعطیل"
        elif row.open_time and row.close_time:
            value = f"{row.open_time.strftime('%H:%M')} تا {row.close_time.strftime('%H:%M')}"
        else:
            value = "ثبت نشده"
        result.append({"day": row.get_day_of_week_display(), "hours": value})
    return result


def answer_business_customer_inquiry(*, salon, stylist=None, message: str):
    # Context is injected by the channel adapter and is never selected by Lumi.
    # This function reads public business data only.
    text = normalize_text(message)
    if not text:
        return CustomerInquiryResult(
            "out_of_scope",
            "اگر درباره خدمات، قیمت، زمان خالی یا رزرو سؤال داری می‌تونم کمکت کنم.",
            {},
        )

    if any(term in text for term in PRIVATE_OPERATION_TERMS):
        return CustomerInquiryResult(
            "out_of_scope",
            "از دایرکت می‌تونم درباره خدمات، قیمت‌ها، متخصص‌ها، زمان‌های خالی و رزرو راهنماییت کنم.",
            {"reason": "private_operation_not_supported"},
        )

    service = _match_service(salon=salon, stylist=stylist, message=message)
    wants_availability = any(term in text for term in AVAILABILITY_TERMS)
    wants_price = any(term in text for term in PRICE_TERMS)
    wants_booking = any(term in text for term in BOOKING_TERMS)

    if wants_availability:
        if service is None:
            return CustomerInquiryResult(
                "clarification",
                "برای کدوم خدمت زمان خالی می‌خوای؟",
                {"reason": "service_required_for_availability"},
            )
        availability = _availability_fact(salon=salon, service=service, stylist=stylist)
        if availability is None:
            subject = _stylist_name(stylist) if stylist is not None else salon.salon_name
            return CustomerInquiryResult(
                "answer",
                f"فعلاً در ۳۰ روز آینده برای {service.service_name} زمان خالی ثبت‌شده‌ای برای {subject} پیدا نکردم.",
                {"service_id": service.pk, "service": service.service_name, "availability": None},
            )
        booking_url = _booking_url(
            salon=salon,
            service=service,
            stylist=stylist if stylist is not None else None,
        )
        answer = (
            f"اولین زمان خالی برای {service.service_name} با "
            f"{availability['stylist']}، {availability['date_label']} "
            f"ساعت {availability['time']} است.\nبرای رزرو: {booking_url}"
        )
        return CustomerInquiryResult(
            "answer",
            answer,
            {
                "service_id": service.pk,
                "service": service.service_name,
                "availability": availability,
                "booking_url": booking_url,
            },
        )

    if service is not None and wants_price:
        price_fact = _service_price_fact(service=service, salon=salon, stylist=stylist)
        return CustomerInquiryResult(
            "answer",
            f"{service.service_name}: {_format_price(price_fact)}",
            {"service_id": service.pk, "service": service.service_name, "price": price_fact},
        )

    if service is not None and (wants_booking or any(term in text for term in SERVICE_TERMS)):
        price_fact = _service_price_fact(service=service, salon=salon, stylist=stylist)
        booking_url = _booking_url(salon=salon, service=service, stylist=stylist)
        summary = (service.summery_description or service.description or "").strip()
        parts = [f"بله، {service.service_name} ارائه می‌شه."]
        if summary:
            parts.append(summary[:350])
        parts.append(_format_price(price_fact))
        if wants_booking:
            parts.append(f"برای رزرو: {booking_url}")
        return CustomerInquiryResult(
            "answer",
            "\n".join(parts),
            {
                "service_id": service.pk,
                "service": service.service_name,
                "price": price_fact,
                "booking_url": booking_url if wants_booking else "",
            },
        )

    if any(term in text for term in ADDRESS_TERMS):
        address = str(salon.address or "").strip()
        if not address:
            return CustomerInquiryResult(
                "human_handoff",
                "آدرس دقیق برای این مجموعه در Loomera ثبت نشده؛ بهتره همکاران سالن راهنماییت کنن.",
                {"address": ""},
                True,
            )
        return CustomerInquiryResult(
            "answer",
            f"آدرس {salon.salon_name}: {address}",
            {"address": address},
        )

    if any(term in text for term in HOURS_TERMS):
        hours = _salon_hours(salon)
        if not hours:
            return CustomerInquiryResult(
                "human_handoff",
                "ساعت کاری دقیق در Loomera ثبت نشده؛ بهتره همکاران سالن راهنماییت کنن.",
                {"hours": []},
                True,
            )
        lines = [f"{item['day']}: {item['hours']}" for item in hours]
        return CustomerInquiryResult("answer", "ساعت کاری:\n" + "\n".join(lines), {"hours": hours})

    if any(term in text for term in STYLIST_TERMS):
        if stylist is not None:
            return CustomerInquiryResult(
                "answer",
                f"این حساب مربوط به {_stylist_name(stylist)} در {salon.salon_name} است.",
                {"stylist_id": stylist.pk, "stylist": _stylist_name(stylist)},
            )
        active_ids = _active_membership_stylist_ids(salon)
        names = [
            _stylist_name(item)
            for item in salon.stylists.filter(pk__in=active_ids, is_active=True)
            .select_related("user")
            .order_by("user__name", "user__family", "pk")
        ]
        if not names:
            return CustomerInquiryResult(
                "human_handoff",
                "فعلاً متخصص فعالی برای معرفی در Loomera ثبت نشده.",
                {"stylists": []},
                True,
            )
        return CustomerInquiryResult(
            "answer",
            "متخصص‌های فعال این مجموعه: " + "، ".join(names[:12]),
            {"stylists": names[:20]},
        )

    if any(term in text for term in SERVICE_TERMS):
        services = list(
            scoped_services(salon=salon, stylist=stylist)
            .values_list("service_name", flat=True)[:20]
        )
        if not services:
            return CustomerInquiryResult(
                "human_handoff",
                "فعلاً خدمت فعالی برای این حساب در Loomera ثبت نشده.",
                {"services": []},
                True,
            )
        return CustomerInquiryResult(
            "answer",
            "خدمات فعال: " + "، ".join(services[:12]),
            {"services": services},
        )

    if wants_booking:
        booking_url = _booking_url(salon=salon, stylist=stylist)
        return CustomerInquiryResult(
            "answer",
            f"برای دیدن خدمات و رزرو از این لینک استفاده کن:\n{booking_url}",
            {"booking_url": booking_url},
        )

    return CustomerInquiryResult(
        "out_of_scope",
        "من دستیار این مجموعه‌ام و می‌تونم درباره خدمات، قیمت‌ها، متخصص‌ها، زمان‌های خالی و رزرو کمکت کنم.",
        {"reason": "outside_business_inquiry_scope"},
    )
