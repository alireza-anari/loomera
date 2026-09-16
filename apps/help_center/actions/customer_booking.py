from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import resolve_url
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Customer, Stylist
from apps.orders.booking_utils import (
    get_available_slots_for_service,
    get_upcoming_available_stylists_for_service,
    resolve_booking_sequence,
)
from apps.orders.forms import AppointmentCheckoutForm
from apps.salons.models import Salon
from apps.services.models import Services


PUBLIC_BOOKING_STYLIST_VISIBILITIES = (
    Stylist.PublicVisibility.PUBLIC,
    Stylist.PublicVisibility.SALON_ONLY,
)

PERIOD_WINDOWS = {
    "morning": (6 * 60, 11 * 60 + 59),
    "noon": (12 * 60, 15 * 60 + 59),
    "evening": (16 * 60, 18 * 60 + 59),
    "night": (19 * 60, 23 * 60 + 59),
}

PERIOD_LABELS = {
    "morning": "صبح",
    "noon": "ظهر",
    "evening": "عصر",
    "night": "شب",
}

BOOKING_SESSION_KEYS = ("salon_id", "stylist_selections", "datetime_selections")


def _positive_int(value) -> int | None:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    parsed = int(raw)
    return parsed if parsed > 0 else None


def _clear_booking_session(request) -> None:
    for key in BOOKING_SESSION_KEYS:
        request.session.pop(key, None)
    request.session.modified = True


def _customer_access(request) -> tuple[Customer | None, dict | None]:
    if not getattr(request.user, "is_authenticated", False):
        return None, {
            "handled": True,
            "kind": "booking_auth_required",
            "answer": "برای رزرو نهایی باید وارد حساب مشتریت بشی. بعد از ورود می‌تونی همین مسیر رو ادامه بدی.",
            "auth_required": True,
            "login_url": resolve_url(settings.LOGIN_URL),
        }

    customer = Customer.objects.filter(user=request.user).select_related("user").first()
    if customer is None:
        return None, {
            "handled": True,
            "kind": "booking_customer_required",
            "answer": "رزرو نوبت از این مسیر برای حساب مشتری انجام می‌شه. اگر حساب مشتری داری با همون حساب وارد شو.",
        }
    return customer, None


def _active_salon(salon_id) -> Salon:
    parsed = _positive_int(salon_id)
    if parsed is None:
        raise ValidationError("مجموعه انتخاب‌شده معتبر نیست.")
    salon = Salon.objects.filter(pk=parsed, is_active=True).first()
    if salon is None:
        raise ValidationError("این مجموعه فعال نیست یا دیگر در دسترس نیست.")
    return salon


def _salon_service(salon: Salon, catalog_service_id) -> Services:
    source_id = _positive_int(catalog_service_id)
    if source_id is None:
        raise ValidationError("خدمت انتخاب‌شده معتبر نیست.")

    # Discovery starts from the platform catalog. Public booking may use either
    # that exact catalog service or the salon-owned version linked to it.
    services = list(
        Services.objects.filter(
            services_of_salon=salon,
            is_active=True,
        )
        .filter(Q(is_platform_catalog=True) | Q(catalog_source__isnull=False))
        .filter(Q(pk=source_id) | Q(catalog_source_id=source_id))
        .order_by("is_platform_catalog", "pk")
        .distinct()
    )
    if not services:
        raise ValidationError("این خدمت در مجموعه انتخاب‌شده قابل رزرو نیست.")

    # Prefer the salon-owned version when it exists because its duration/base
    # price and stylist mapping are the salon's current product truth.
    custom = next((item for item in services if item.catalog_source_id == source_id), None)
    return custom or services[0]


def _eligible_stylist(salon: Salon, service: Services, stylist_user_id) -> Stylist:
    stylist_id = _positive_int(stylist_user_id)
    if stylist_id is None:
        raise ValidationError("متخصص انتخاب‌شده معتبر نیست.")
    stylist = (
        salon.stylists.filter(
            user_id=stylist_id,
            is_active=True,
            public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
            services_of_stylist=service,
        )
        .select_related("user")
        .distinct()
        .first()
    )
    if stylist is None:
        raise ValidationError("این متخصص برای خدمت انتخاب‌شده قابل رزرو نیست.")
    return stylist


def _fa_date_label(value: date) -> str:
    try:
        from khayyam import JalaliDate

        return JalaliDate(value).strftime("%Y/%m/%d")
    except Exception:
        return value.strftime("%Y/%m/%d")


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def _period_matches(time_value, period: str) -> bool:
    if not period or period not in PERIOD_WINDOWS:
        return True
    start, end = PERIOD_WINDOWS[period]
    minute = _minutes(time_value)
    return start <= minute <= end


def _requested_start_date(state: dict) -> date:
    raw = str(state.get("date") or "").strip()
    if raw:
        try:
            parsed = date.fromisoformat(raw)
            if parsed >= timezone.localdate():
                return parsed
        except ValueError:
            pass
    return timezone.localdate()


def _slot_rows(
    *,
    salon: Salon,
    stylist: Stylist,
    service: Services,
    state: dict,
    relax: bool = False,
    horizon_days: int = 14,
    max_slots: int = 18,
) -> list[dict]:
    today = timezone.localdate()
    requested_date_raw = str(state.get("date") or "").strip()
    requested_period = "" if relax else str(state.get("period") or "").strip()
    start_date = today if relax else _requested_start_date(state)

    # When the user explicitly asked for a date, keep the initial list on that
    # date only. The UI offers "nearest times" when it is empty.
    days = 1 if requested_date_raw and not relax else max(int(horizon_days or 1), 1)
    rows: list[dict] = []
    for offset in range(days):
        target = start_date + timedelta(days=offset)
        for start_time, end_time in get_available_slots_for_service(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=target,
        ):
            if not _period_matches(start_time, requested_period):
                continue
            rows.append(
                {
                    "date": target.isoformat(),
                    "date_label": _fa_date_label(target),
                    "time": start_time.strftime("%H:%M"),
                    "end_time": end_time.strftime("%H:%M"),
                }
            )
            if len(rows) >= max_slots:
                return rows
    return rows


def _provider_rows(*, salon: Salon, service: Services, start_date: date) -> list[dict]:
    available = get_upcoming_available_stylists_for_service(
        salon=salon,
        service=service,
        start_date=start_date,
        horizon_days=30,
    )
    eligible_ids = set(
        salon.stylists.filter(
            is_active=True,
            public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
            services_of_stylist=service,
        ).values_list("pk", flat=True)
    )
    rows = []
    for item in available:
        stylist = item.get("stylist")
        first_slot = item.get("first_slot") or {}
        if not stylist or stylist.pk not in eligible_ids:
            continue
        image_url = ""
        try:
            if stylist.profile_image:
                image_url = stylist.profile_image.url
        except Exception:
            image_url = ""
        rows.append(
            {
                "id": stylist.user_id,
                "name": stylist.get_fullName(),
                "price": int(item.get("price") or 0),
                "image_url": image_url,
                "next_date": first_slot.get("date").isoformat() if first_slot.get("date") else "",
                "next_date_label": _fa_date_label(first_slot.get("date")) if first_slot.get("date") else "",
                "next_time": first_slot.get("time").strftime("%H:%M") if first_slot.get("time") else "",
            }
        )
    return rows[:8]


def _base_state(*, salon: Salon, service: Services, catalog_service_id: int, discovery_state: dict) -> dict:
    return {
        "mode": "customer_booking",
        "salon_id": salon.pk,
        "salon_name": salon.salon_name,
        "catalog_service_id": catalog_service_id,
        "service_id": service.pk,
        "service_name": service.service_name,
        "stylist_id": None,
        "stylist_name": "",
        "date": str(discovery_state.get("date") or ""),
        "date_label": str(discovery_state.get("date_label") or ""),
        "period": str(discovery_state.get("period") or ""),
        "step": "stylist",
    }


def _validated_state(state: dict) -> tuple[Salon, Services, dict]:
    if not isinstance(state, dict) or state.get("mode") != "customer_booking":
        raise ValidationError("اطلاعات رزرو ناقص است. دوباره مجموعه را انتخاب کن.")
    salon = _active_salon(state.get("salon_id"))
    catalog_id = _positive_int(state.get("catalog_service_id"))
    if catalog_id is None:
        raise ValidationError("خدمت انتخاب‌شده معتبر نیست.")
    service = _salon_service(salon, catalog_id)
    clean = dict(state)
    clean.update(
        {
            "salon_id": salon.pk,
            "salon_name": salon.salon_name,
            "catalog_service_id": catalog_id,
            "service_id": service.pk,
            "service_name": service.service_name,
        }
    )
    return salon, service, clean


def _prepare_preview(request, *, salon: Salon, service: Services, stylist: Stylist, selected_date: str, selected_time: str, state: dict) -> dict:
    selection = {
        "serviceId": str(service.pk),
        "requestedStylistId": str(stylist.user_id),
        "requestedStylistName": stylist.get_fullName(),
        "stylistId": str(stylist.user_id),
        "stylistName": stylist.get_fullName(),
        "resolvedStylistId": str(stylist.user_id),
        "resolvedStylistName": stylist.get_fullName(),
    }
    key = f"{stylist.user_id}_{service.pk}"
    datetimes = {
        key: {
            "date": selected_date,
            "time": selected_time,
            "stylist_id": str(stylist.user_id),
            "stylist_name": stylist.get_fullName(),
        }
    }

    # Read-only validation first. No Order is created here.
    resolved = resolve_booking_sequence(
        salon=salon,
        stylist_selections=[selection],
        datetime_selections=datetimes,
    )
    if not resolved:
        raise ValidationError("این زمان قابل رزرو نیست.")

    request.session["salon_id"] = str(salon.pk)
    request.session["stylist_selections"] = [selection]
    request.session["datetime_selections"] = datetimes
    request.session.modified = True

    # Reuse checkout's read-only pricing snapshot. Final checkout rebuilds it
    # again and revalidates under locks before any database write.
    from apps.orders.views import _build_checkout_payload

    payload = _build_checkout_payload(request=request, coupon_code="")
    form = AppointmentCheckoutForm(
        requires_online_payment=payload["requires_online_payment"]
    )
    payment_methods = [
        {"value": value, "label": label}
        for value, label in form.fields["payment_method"].choices
    ]
    if not payment_methods:
        raise ValidationError("در حال حاضر روش پرداخت معتبری برای این رزرو فعال نیست.")

    item = payload["resolved_items"][0]
    next_state = dict(state)
    next_state.update(
        {
            "stylist_id": item.stylist.user_id,
            "stylist_name": item.stylist.get_fullName(),
            "selected_date": item.date_value.isoformat(),
            "selected_time": item.start_time.strftime("%H:%M"),
            "selected_end_time": item.end_time.strftime("%H:%M"),
            "step": "confirm",
        }
    )
    return {
        "handled": True,
        "kind": "booking_preview",
        "answer": "همه‌چیز آماده است. جزئیات رو بررسی کن و فقط اگر درسته رزرو رو تأیید کن.",
        "action_state": next_state,
        "preview": {
            "salon": salon.salon_name,
            "service": item.service.service_name,
            "stylist": item.stylist.get_fullName(),
            "date": item.date_value.isoformat(),
            "date_label": _fa_date_label(item.date_value),
            "time": item.start_time.strftime("%H:%M"),
            "end_time": item.end_time.strftime("%H:%M"),
            "price": int(item.price or 0),
            "subtotal": int(payload.get("subtotal") or 0),
            "discount_amount": int(payload.get("discount_amount") or 0),
            "total_amount": int(payload.get("total_amount") or 0),
            "requires_online_payment": bool(payload.get("requires_online_payment")),
        },
        "payment_methods": payment_methods,
        "checkout_url": reverse("orders:checkout"),
    }


def run_customer_booking_action(request, payload: dict) -> dict:
    _customer, access_error = _customer_access(request)
    if access_error:
        return access_error

    action = str(payload.get("action") or "").strip()
    state = payload.get("action_state") if isinstance(payload.get("action_state"), dict) else {}

    if action == "cancel":
        _clear_booking_session(request)
        return {
            "handled": True,
            "kind": "booking_cancelled",
            "answer": "باشه، فرایند رزرو رو کنار گذاشتم.",
            "action_state": None,
        }

    if action == "select_salon":
        salon = _active_salon(payload.get("salon_id"))
        catalog_service_id = _positive_int(payload.get("catalog_service_id"))
        if catalog_service_id is None:
            raise ValidationError("خدمت انتخاب‌شده معتبر نیست.")
        service = _salon_service(salon, catalog_service_id)
        discovery_state = payload.get("discovery_state") if isinstance(payload.get("discovery_state"), dict) else {}
        next_state = _base_state(
            salon=salon,
            service=service,
            catalog_service_id=catalog_service_id,
            discovery_state=discovery_state,
        )
        providers = _provider_rows(
            salon=salon,
            service=service,
            start_date=_requested_start_date(next_state),
        )
        if not providers:
            return {
                "handled": True,
                "kind": "booking_no_stylists",
                "answer": "برای این خدمت در این مجموعه فعلاً متخصصی با وقت قابل رزرو پیدا نکردم.",
                "action_state": next_state,
                "salon": {"id": salon.pk, "name": salon.salon_name},
                "service": {"id": service.pk, "name": service.service_name},
                "providers": [],
            }
        return {
            "handled": True,
            "kind": "booking_stylists",
            "answer": "این متخصص‌ها برای این خدمت وقت قابل رزرو دارند. یکی رو انتخاب کن.",
            "action_state": next_state,
            "salon": {"id": salon.pk, "name": salon.salon_name},
            "service": {"id": service.pk, "name": service.service_name},
            "providers": providers,
        }

    salon, service, clean_state = _validated_state(state)

    if action in {"select_stylist", "relax_slots"}:
        stylist = _eligible_stylist(salon, service, payload.get("stylist_id") or clean_state.get("stylist_id"))
        relax = action == "relax_slots" or bool(payload.get("relax"))
        slots = _slot_rows(
            salon=salon,
            stylist=stylist,
            service=service,
            state=clean_state,
            relax=relax,
        )
        next_state = dict(clean_state)
        next_state.update(
            {
                "stylist_id": stylist.user_id,
                "stylist_name": stylist.get_fullName(),
                "step": "slot",
            }
        )
        if not slots:
            period = PERIOD_LABELS.get(str(clean_state.get("period") or ""), "")
            requested_label = str(clean_state.get("date_label") or "").strip()
            scope = " ".join(part for part in (requested_label, period) if part)
            answer = f"برای {scope} وقت خالی پیدا نکردم." if scope else "برای این متخصص فعلاً وقت خالی پیدا نکردم."
            return {
                "handled": True,
                "kind": "booking_slots_empty",
                "answer": answer,
                "action_state": next_state,
                "slots": [],
                "relax_available": not relax and bool(clean_state.get("date") or clean_state.get("period")),
            }
        return {
            "handled": True,
            "kind": "booking_slots",
            "answer": "زمان‌های آزاد واقعی رو پیدا کردم. ساعت مناسب رو انتخاب کن.",
            "action_state": next_state,
            "slots": slots,
            "relaxed": relax,
        }

    if action == "select_slot":
        stylist = _eligible_stylist(salon, service, clean_state.get("stylist_id"))
        selected_date = str(payload.get("date") or "").strip()
        selected_time = str(payload.get("time") or "").strip()
        try:
            parsed_date = date.fromisoformat(selected_date)
            parsed_time = datetime.strptime(selected_time, "%H:%M").time()
        except ValueError as exc:
            raise ValidationError("تاریخ یا ساعت انتخاب‌شده معتبر نیست.") from exc
        if parsed_date < timezone.localdate():
            raise ValidationError("این زمان گذشته و قابل رزرو نیست.")

        available = get_available_slots_for_service(
            salon=salon,
            stylist=stylist,
            service=service,
            date_value=parsed_date,
        )
        if not any(start == parsed_time for start, _end in available):
            raise ValidationError("این زمان دیگه آزاد نیست. زمان‌های آزاد رو دوباره بررسی کن.")
        return _prepare_preview(
            request,
            salon=salon,
            service=service,
            stylist=stylist,
            selected_date=selected_date,
            selected_time=selected_time,
            state=clean_state,
        )

    raise ValidationError("عملیات رزرو معتبر نیست.")
