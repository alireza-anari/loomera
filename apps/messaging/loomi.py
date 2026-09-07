from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.db import OperationalError, ProgrammingError, transaction, connection, DatabaseError

from .links import absolute_site_url
from .models import MessagingConversationContext

logger = logging.getLogger(__name__)

DB_ERRORS = (OperationalError, ProgrammingError)
_SUPPORTED_SCOPE_TYPES = {"salon", "stylist"}
_START_RE = re.compile(
    r"^loomi[_:-](?P<scope>s|salon|p|stylist)[_:-](?P<object_id>[1-9][0-9]{0,9})$",
    re.IGNORECASE,
)

_AVAILABILITY_PHRASES = {
    "وقت دارید", "وقت دارین", "وقت خالی", "وقت آزاد", "نوبت آزاد",
    "نوبت خالی", "زمان آزاد", "زمان خالی", "ساعت آزاد", "ساعت خالی",
    "تایم آزاد", "تایم خالی", "چه ساعتی", "چه ساعت", "چه زمانی",
    "چه وقت", "خالی دارید", "خالی دارین", "موجودی وقت",
}
_BOOKING_ACTION_PHRASES = {
    "رزرو", "رزرو کن", "نوبت میخوام", "نوبت می خواهم", "نوبت می‌خوام",
    "وقت میخوام", "وقت می خواهم", "وقت می‌خوام", "نوبت بگیر", "وقت بگیر",
}
_BOOKING_NOUNS = {"وقت", "نوبت", "زمان", "ساعت", "تایم", "رزرو"}
_DATE_HINT_WORDS = {"امروز", "فردا", "پس فردا", "پس‌فردا", "این هفته", "هفته"}
_CANCELLATION_WORDS = {"لغو", "کنسل", "کنسلی", "استرداد", "بازگشت وجه"}
_GREETING_WORDS = {"سلام", "درود", "سلام لومی", "سلام وقت بخیر", "hello", "hi"}
_LOOMI_SERVICE_CALLBACK_PREFIX = "loomi:service:"
_LOOMI_SERVICE_CALLBACK_RE = re.compile(
    r"^loomi:service:(?P<service_id>[1-9][0-9]{0,9}):(?P<offset>[0-9]{1,2}):(?P<horizon>[1-9][0-9]?)$"
)
_SERVICE_WORDS = {"خدمت", "خدمات", "سرویس", "سرویس‌ها", "کارها", "چه کارهایی"}
_PRICE_WORDS = {"قیمت", "هزینه", "چقدر", "چنده", "تعرفه"}
_CONTACT_WORDS = {"آدرس", "کجاست", "کجا", "تلفن", "شماره", "تماس", "لوکیشن"}
_IDENTITY_WORDS = {"کی هستی", "تو کی هستی", "لومی", "راهنما"}


def _safe_loomi(function):
    """Keep optional assistant failures outside the webhook transaction."""
    @wraps(function)
    def wrapped(**kwargs):
        try:
            if not loomi_messaging_enabled(kwargs.get("provider")):
                return None
            with transaction.atomic():
                result = function(**kwargs)
                if connection.needs_rollback:
                    raise DatabaseError("Loomi database operation failed")
                if result:
                    result["text"] = result["text"][:3500]
                return result
        except Exception:
            logger.exception("Loomi %s failed; returning to bot menu", function.__name__)
            return None
    return wrapped


@dataclass(frozen=True)
class ParsedLoomiStart:
    scope_type: str
    object_id: int


def _normalize(text: str) -> str:
    value = str(text or "").strip().lower()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = re.sub(r"[\u200c\s]+", " ", value)
    return value


def _contains_any(text: str, words: set[str]) -> bool:
    return any(_normalize(word) in text for word in words)


def _is_greeting(normalized: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", _normalize(normalized)).strip()
    return cleaned in {_normalize(item) for item in _GREETING_WORDS}


def _is_booking_or_availability_question(normalized: str) -> bool:
    """Recognize booking intent without treating every date/nobat word as booking.

    Cancellation/refund questions are deliberately excluded so they can continue
    to the product/help flow. Date words only count when paired with an actual
    booking noun.
    """
    value = _normalize(normalized)
    if _contains_any(value, _CANCELLATION_WORDS):
        return False
    if _contains_any(value, _AVAILABILITY_PHRASES | _BOOKING_ACTION_PHRASES):
        return True
    cleaned = re.sub(r"[^\w\s]", "", value).strip()
    if cleaned in {_normalize(item) for item in _BOOKING_NOUNS}:
        return True
    return _contains_any(value, _DATE_HINT_WORDS) and _contains_any(value, _BOOKING_NOUNS)


def parse_loomi_start_payload(payload: str) -> ParsedLoomiStart | None:
    """Parse compact provider deep-link payloads without trusting object existence."""
    match = _START_RE.fullmatch(str(payload or "").strip())
    if not match:
        return None
    if int(match.group("object_id")) > 2147483647:
        return None
    raw_scope = match.group("scope").lower()
    scope_type = "salon" if raw_scope in {"s", "salon"} else "stylist"
    if scope_type not in _SUPPORTED_SCOPE_TYPES:
        return None
    return ParsedLoomiStart(scope_type=scope_type, object_id=int(match.group("object_id")))


def loomi_messaging_enabled(provider) -> bool:
    if not bool(getattr(settings, "LOOMI_MESSAGING_ENABLED", False)):
        return False
    provider_key = str(getattr(provider, "key", provider) or "").strip().lower()
    allowed = {
        str(item or "").strip().lower()
        for item in getattr(
            settings,
            "LOOMI_MESSAGING_ALLOWED_PROVIDERS",
            ["telegram", "bale"],
        )
        if str(item or "").strip()
    }
    return provider_key in allowed


def _consume_rate_limit(identity, provider) -> bool:
    linked = bool(getattr(identity, "user_id", None))
    limit = int(
        getattr(
            settings,
            "LOOMI_MESSAGING_USER_LIMIT" if linked else "LOOMI_MESSAGING_GUEST_LIMIT",
            30 if linked else 10,
        )
        or (30 if linked else 10)
    )
    window = max(int(getattr(settings, "LOOMI_MESSAGING_RATE_WINDOW_SECONDS", 3600) or 3600), 60)
    provider_key = str(getattr(provider, "key", provider) or "unknown").strip().lower()
    key = f"loomera:loomi-msg:{provider_key}:{getattr(identity, 'pk', 'guest')}"
    try:
        if cache.add(key, 1, timeout=window):
            return True
        try:
            return cache.incr(key) <= limit
        except ValueError:
            return cache.add(key, 1, timeout=window)
    except Exception:
        logger.exception("Loomi rate limiter unavailable")
        raise


def _public_stylist_salons(stylist):
    from apps.salons.models import Salon
    from apps.stylists.profile_services import can_show_stylist_on_salon_profile
    from django.db.models import Q

    candidates = Salon.objects.filter(is_active=True).filter(
        Q(stylists=stylist) | Q(memberships__stylist=stylist)
    ).distinct().order_by("salon_name", "id")
    return [salon for salon in candidates
            if can_show_stylist_on_salon_profile(salon=salon, stylist=stylist).allowed]


def _resolve_target(scope_type: str, object_id: int):
    if scope_type == "salon":
        from apps.salons.models import Salon

        return Salon.objects.filter(pk=object_id, is_active=True).first()

    if scope_type == "stylist":
        from apps.accounts.models import Stylist

        queryset = Stylist.objects.filter(pk=object_id, is_active=True)
        target = queryset.first()
        if not target:
            return None
        visibility = str(getattr(target, "public_visibility", "") or "")
        allowed = {
            getattr(Stylist.PublicVisibility, "SALON_ONLY", "salon_only"),
            getattr(Stylist.PublicVisibility, "PUBLIC", "public"),
        }
        if visibility not in allowed:
            return None
        if visibility == Stylist.PublicVisibility.SALON_ONLY and not _public_stylist_salons(target):
            return None
        return target

    return None


def _target_label(scope_type: str, target) -> str:
    if scope_type == "salon":
        return str(getattr(target, "salon_name", "") or str(target)).strip()
    return str(
        getattr(target, "professional_display_name", "")
        or getattr(target, "get_fullName", lambda: "")()
        or str(target)
    ).strip()


def _context_target(context: MessagingConversationContext):
    try:
        return _resolve_target(context.scope_type, int(context.scope_object_id or 0))
    except (TypeError, ValueError):
        return None


def _booking_url(scope_type: str, target, base_url: str) -> str:
    try:
        if scope_type == "salon":
            return absolute_site_url(base_url, target.get_absolute_url())
        salons = _public_stylist_salons(target)
        if salons:
            return absolute_site_url(base_url, salons[0].get_absolute_url())
    except Exception:
        logger.exception("Failed to build Loomi booking URL")
    return absolute_site_url(base_url, "/") if base_url else ""


def _booking_markup(scope_type: str, target, base_url: str) -> dict | None:
    url = _booking_url(scope_type, target, base_url)
    if not url or not url.startswith(("http://", "https://")):
        return None
    return {
        "inline_keyboard": [
            [{"text": "رزرو در Loomera", "url": url}],
        ]
    }


def _welcome_text(scope_type: str, target) -> str:
    label = _target_label(scope_type, target)
    kind = "مجموعه" if scope_type == "salon" else "متخصص"
    return (
        f"سلام، من لومی هستم؛ دستیار هوشمند {kind} «{label}» در Loomera.\n\n"
        "می‌تونی درباره خدمات، قیمت‌ها، اطلاعات مجموعه و زمان‌های آزاد ازم بپرسی. "
        "برای رزرو نهایی هم مسیر امن Loomera رو بهت می‌دم."
    )


@_safe_loomi
def try_apply_loomi_start_context(*, identity, provider, payload: str, base_url: str = "") -> dict | None:
    """Handle only Loomi deep links; return None for existing connect/unknown payloads."""
    if not loomi_messaging_enabled(provider):
        return None
    parsed = parse_loomi_start_payload(payload)
    if not parsed:
        if str(payload or "").lower().startswith("loomi"):
            MessagingConversationContext.objects.filter(identity=identity).delete()
            return {"text": "این لینک لومی معتبر نیست. لطفاً لینک را از صفحه مجموعه یا متخصص باز کن.", "reply_markup": None}
        return None

    try:
        target = _resolve_target(parsed.scope_type, parsed.object_id)
        if not target:
            MessagingConversationContext.objects.filter(identity=identity).delete()
            return {
                "text": "این لینک لومی معتبر نیست یا این پروفایل در حال حاضر فعال نیست.",
                "reply_markup": None,
            }
        context, _ = MessagingConversationContext.objects.update_or_create(
            identity=identity,
            defaults={
                "scope_type": parsed.scope_type,
                "scope_object_id": parsed.object_id,
                "source": "provider_start",
                "start_payload": str(payload or "")[:128],
                "metadata": {"target_label": _target_label(parsed.scope_type, target)},
            },
        )
        return {
            "text": _welcome_text(context.scope_type, target),
            "reply_markup": _booking_markup(context.scope_type, target, base_url),
        }
    except DB_ERRORS:
        logger.exception("Loomi context storage is not ready")
        return None
    except Exception:
        logger.exception("Failed to apply Loomi start context")
        return None


def _format_price(value) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,} تومان" if amount > 0 else "قیمت ثبت نشده"


def _salon_service_price(service, salon) -> str:
    try:
        from apps.accounts.models import Stylist
        from apps.stylists.profile_services import can_show_stylist_on_salon_profile
        from django.db.models import Q
        candidates = Stylist.objects.filter(is_active=True, services_of_stylist=service).filter(
            Q(stylists_of_salon=salon) | Q(salon_memberships__salon=salon)
        ).distinct()
        active_stylists = [stylist.pk for stylist in candidates
                           if can_show_stylist_on_salon_profile(salon=salon, stylist=stylist).allowed]
        overrides = dict(service.service_prices.filter(stylist_id__in=active_stylists)
                         .values_list("stylist_id", "price"))
        prices = [overrides.get(pk, service.base_price) for pk in active_stylists]
        prices = [price for price in prices if price and price > 0]
    except Exception:
        logger.exception("Failed to read Loomi salon service prices")
        raise
    if not prices:
        base = int(getattr(service, "base_price", 0) or 0)
        return _format_price(base)
    low, high = min(prices), max(prices)
    if low == high:
        return _format_price(low)
    return f"از {_format_price(low)} تا {_format_price(high)}"


def _stylist_service_price(service, stylist) -> str:
    return _format_price(stylist.get_price_for_service(service))


def _scope_services(scope_type: str, target):
    if scope_type == "salon":
        return target.services.filter(is_active=True).order_by("service_name", "id")
    return target.services_of_stylist.filter(
        is_active=True, services_of_salon__in=_public_stylist_salons(target),
    ).distinct().order_by("service_name", "id")


def _matching_services(scope_type: str, target, normalized_question: str):
    matches = []
    for service in _scope_services(scope_type, target)[:80]:
        name = _normalize(getattr(service, "service_name", ""))
        if name and (name in normalized_question or normalized_question in name):
            matches.append(service)
    return matches[:5]


def _render_service_line(scope_type: str, target, service) -> str:
    price = (
        _salon_service_price(service, target)
        if scope_type == "salon"
        else _stylist_service_price(service, target)
    )
    duration = int(getattr(service, "duration_minutes", 0) or 0)
    duration_text = f"، حدود {duration} دقیقه" if duration > 0 else ""
    return f"• {service.service_name}: {price}{duration_text}"


def _service_answer(scope_type: str, target, question: str) -> str | None:
    normalized = _normalize(question)
    matches = _matching_services(scope_type, target, normalized)
    wants_prices = _contains_any(normalized, _PRICE_WORDS)
    wants_services = _contains_any(normalized, _SERVICE_WORDS)

    if matches:
        lines = [_render_service_line(scope_type, target, service) for service in matches]
        return "اطلاعات ثبت‌شده در Loomera:\n" + "\n".join(lines)

    if wants_prices or wants_services:
        services = list(_scope_services(scope_type, target)[:8])
        if not services:
            return "فعلاً خدمت فعالی برای این پروفایل در Loomera ثبت نشده."
        lines = [_render_service_line(scope_type, target, service) for service in services]
        suffix = "\n\nاگر اسم خدمت مدنظرت رو بگی، دقیق‌تر بررسی می‌کنم." if len(services) >= 2 else ""
        return "خدمات فعال ثبت‌شده:\n" + "\n".join(lines) + suffix

    return None


def _contact_answer(scope_type: str, target) -> str:
    if scope_type == "stylist":
        salons = _public_stylist_salons(target)[:5]
        if salons:
            names = "، ".join(str(item.salon_name) for item in salons)
            return f"این متخصص در مجموعه‌های فعال زیر حضور دارد: {names}. برای آدرس دقیق، صفحه همان مجموعه را باز کن."
        return "برای این متخصص در حال حاضر مجموعه فعالی با آدرس عمومی پیدا نکردم."

    lines = [f"مجموعه: {target.salon_name}"]
    address = str(getattr(target, "address", "") or "").strip()
    if address:
        lines.append(f"آدرس: {address}")
    phone = (
        str(getattr(target, "mobile_phone", "") or "").strip()
        or str(getattr(target, "landline_phone", "") or "").strip()
        or str(getattr(target, "phone_number", "") or "").strip()
    )
    if phone:
        lines.append(f"تماس: {phone}")
    if len(lines) == 1:
        lines.append("آدرس یا شماره تماس عمومی هنوز ثبت نشده.")
    return "\n".join(lines)




def _availability_window(normalized_question: str):
    """Resolve a small, deterministic date window for availability previews."""
    from django.utils import timezone

    today = timezone.localdate()
    normalized = _normalize(normalized_question)
    if "پس فردا" in normalized or "پس‌فردا" in normalized:
        return today + timedelta(days=2), 1, 2
    if "فردا" in normalized:
        return today + timedelta(days=1), 1, 1
    if "امروز" in normalized:
        return today, 1, 0
    if "هفته" in normalized:
        return today, 7, 0
    # A generic "وقت دارید؟" should still be useful even when today is full.
    return today, 7, 0


def _availability_callback_data(service_id: int, *, offset: int, horizon: int) -> str:
    return f"{_LOOMI_SERVICE_CALLBACK_PREFIX}{int(service_id)}:{int(offset)}:{int(horizon)}"


def _parse_availability_callback(callback_data: str):
    match = _LOOMI_SERVICE_CALLBACK_RE.fullmatch(str(callback_data or "").strip())
    if not match:
        return None
    service_id = int(match.group("service_id"))
    offset = int(match.group("offset"))
    horizon = int(match.group("horizon"))
    if offset > 14 or horizon > 7:
        return None
    return service_id, offset, horizon


def _bookable_scope_services(scope_type: str, target):
    """Return services that can enter the existing public booking flow."""
    from django.db.models import Q

    public_filter = Q(is_platform_catalog=True) | Q(catalog_source__isnull=False)
    if scope_type == "salon":
        return (
            target.services.filter(is_active=True)
            .filter(public_filter)
            .distinct()
            .order_by("service_name", "id")
        )

    booking_salons = [
        salon
        for salon in _public_stylist_salons(target)
        if salon.stylists.filter(pk=target.pk).exists()
    ]
    return (
        target.services_of_stylist.filter(
            is_active=True,
            services_of_salon__in=booking_salons,
        )
        .filter(public_filter)
        .distinct()
        .order_by("service_name", "id")
    )


def _visible_salon_stylists_for_service(salon, service):
    from apps.stylists.profile_services import can_show_stylist_on_salon_profile

    candidates = list(
        salon.stylists.filter(
            is_active=True,
            services_of_stylist=service,
        )
        .select_related("user")
        .distinct()
        .order_by("user_id")
    )
    return [
        stylist
        for stylist in candidates
        if can_show_stylist_on_salon_profile(
            salon=salon,
            stylist=stylist,
            legacy_membership_confirmed=True,
        ).allowed
    ]


def _slot_booking_url(*, salon, service, stylist, date_value, start_time, base_url: str) -> str:
    """Build a signed read-to-write handoff into the existing booking flow.

    This creates no Order and reserves no slot. The booking flow revalidates the
    service/stylist/time before confirmation.
    """
    from django.urls import reverse
    from apps.orders.quick_links import sign_booking_payload

    payload = {
        "mode": "service_stylist_time",
        "salon_id": int(salon.pk),
        "service_ids": [int(service.pk)],
        "stylist_user_id": int(stylist.user_id),
        "date": date_value.isoformat(),
        "time": start_time.strftime("%H:%M"),
    }
    token = sign_booking_payload(payload)
    path = reverse("orders:quick_booking_entry", kwargs={"token": token})
    return absolute_site_url(base_url, path)


def _collect_availability_slots(
    *,
    scope_type: str,
    target,
    service,
    start_date,
    horizon_days: int,
    max_slots: int = 5,
):
    """Read real slots from the existing booking engine without reserving them.

    A cheap schedule prefilter avoids calling the three-query availability helper
    for stylist/date pairs that cannot possibly have capacity. The booking helper
    remains the single source of truth for leaves, existing bookings and slot math.
    """
    from django.db.models import Q
    from apps.orders.booking_utils import get_available_slots_for_service
    from apps.stylists.models import StylistSchedule

    horizon_days = max(1, min(int(horizon_days or 1), 7))
    max_slots = max(1, min(int(max_slots or 5), 8))
    end_date = start_date + timedelta(days=horizon_days - 1)

    pair_map = {}
    if scope_type == "salon":
        for stylist in _visible_salon_stylists_for_service(target, service):
            pair_map[(target.pk, stylist.pk)] = (target, stylist)
    else:
        for salon in _public_stylist_salons(target):
            if not salon.stylists.filter(pk=target.pk).exists():
                continue
            if not salon.services.filter(pk=service.pk, is_active=True).exists():
                continue
            pair_map[(salon.pk, target.pk)] = (salon, target)

    if not pair_map:
        return []

    salon_ids = {key[0] for key in pair_map}
    stylist_ids = {key[1] for key in pair_map}
    scheduled_keys = set(
        StylistSchedule.objects.filter(
            salon_id__in=salon_ids,
            stylist_id__in=stylist_ids,
            date__range=(start_date, end_date),
        )
        .filter(Q(service_id=service.pk) | Q(service__isnull=True))
        .values_list("salon_id", "stylist_id", "date")
        .distinct()
    )
    if not scheduled_keys:
        return []

    candidates = []
    seen = set()
    for day_offset in range(horizon_days):
        day = start_date + timedelta(days=day_offset)
        day_pairs = [
            pair
            for key, pair in pair_map.items()
            if (key[0], key[1], day) in scheduled_keys
        ]
        for salon, stylist in day_pairs:
            for start_time, end_time in get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=day,
            ):
                key = (salon.pk, stylist.pk, day.isoformat(), start_time.strftime("%H:%M"))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "salon": salon,
                        "stylist": stylist,
                        "service": service,
                        "date": day,
                        "time": start_time,
                        "end_time": end_time,
                    }
                )

        candidates.sort(
            key=lambda item: (
                item["date"],
                item["time"],
                int(getattr(item["stylist"], "user_id", 0) or 0),
            )
        )
        if len(candidates) >= max_slots:
            return candidates[:max_slots]

    return candidates[:max_slots]


def _availability_slot_text(slot, *, scope_type: str) -> str:
    from django.utils import timezone
    from apps.dashboards.jalali_utils import (
        format_jalali_with_weekday,
        format_time_fa,
        relative_jalali_label,
    )

    day = slot["date"]
    relative = relative_jalali_label(day, today=timezone.localdate())
    if relative not in {"امروز", "فردا"}:
        relative = format_jalali_with_weekday(day, include_year=False)
    time_label = format_time_fa(slot["time"])
    suffix = ""
    if scope_type == "salon":
        stylist_label = _target_label("stylist", slot["stylist"])
        if stylist_label:
            suffix = f" — {stylist_label}"
    else:
        salon_label = str(getattr(slot["salon"], "salon_name", "") or "").strip()
        if salon_label:
            suffix = f" — {salon_label}"
    return f"{relative}، {time_label}{suffix}"


def _availability_answer(
    scope_type: str,
    target,
    question: str,
    base_url: str,
    *,
    selected_service_id: int | None = None,
    start_date=None,
    horizon_days: int | None = None,
) -> dict | None:
    """Preview real availability and hand final reservation to the website."""
    from django.utils import timezone

    services = list(_bookable_scope_services(scope_type, target)[:80])
    if not services:
        return {
            "text": "فعلاً خدمت قابل رزرو آنلاینی برای بررسی زمان آزاد پیدا نکردم.",
            "reply_markup": _booking_markup(scope_type, target, base_url),
        }

    normalized = _normalize(question)
    if start_date is None or horizon_days is None:
        start_date, horizon_days, offset = _availability_window(normalized)
    else:
        offset = max((start_date - timezone.localdate()).days, 0)
        horizon_days = max(1, min(int(horizon_days), 7))

    selected = None
    if selected_service_id:
        selected = next((item for item in services if item.pk == int(selected_service_id)), None)
        if selected is None:
            return {
                "text": "این خدمت برای این پروفایل قابل رزرو نیست. لطفاً دوباره خدمت را انتخاب کن.",
                "reply_markup": None,
            }
    else:
        mentioned = [
            service
            for service in services
            if _normalize(getattr(service, "service_name", "")) in normalized
        ]
        if mentioned:
            selected = mentioned[0]

    if selected is None and len(services) > 1:
        rows = [
            [
                {
                    "text": str(service.service_name),
                    "callback_data": _availability_callback_data(
                        service.pk,
                        offset=offset,
                        horizon=horizon_days,
                    ),
                }
            ]
            for service in services[:10]
        ]
        if len(services) > 10:
            url = _booking_url(scope_type, target, base_url)
            if url.startswith(("https://", "http://")):
                rows.append([{"text": "مشاهده همه خدمات در Loomera", "url": url}])
        return {
            "text": "برای بررسی زمان‌های آزاد، اول خدمت موردنظرت رو انتخاب کن یا اسم خدمت رو بنویس:",
            "reply_markup": {"inline_keyboard": rows},
        }

    service = selected or services[0]
    slots = _collect_availability_slots(
        scope_type=scope_type,
        target=target,
        service=service,
        start_date=start_date,
        horizon_days=horizon_days,
        max_slots=5,
    )

    if not slots:
        if horizon_days == 1:
            when = "امروز" if offset == 0 else "فردا" if offset == 1 else "این روز"
            text = f"برای {when} زمان آزادی برای «{service.service_name}» پیدا نکردم. می‌تونی زمان‌های دیگر رو در مسیر رزرو Loomera بررسی کنی."
        else:
            text = f"در چند روز آینده زمان آزادی برای «{service.service_name}» پیدا نکردم. می‌تونی مسیر رزرو Loomera رو برای زمان‌های دیگر بررسی کنی."
        return {
            "text": text,
            "reply_markup": _booking_markup(scope_type, target, base_url),
        }

    lines = [_availability_slot_text(slot, scope_type=scope_type) for slot in slots]
    rows = []
    for slot, line in zip(slots, lines):
        url = _slot_booking_url(
            salon=slot["salon"],
            service=slot["service"],
            stylist=slot["stylist"],
            date_value=slot["date"],
            start_time=slot["time"],
            base_url=base_url,
        )
        if url.startswith(("https://", "http://")):
            rows.append([{"text": line[:60], "url": url}])

    reply_markup = {"inline_keyboard": rows} if rows else _booking_markup(scope_type, target, base_url)
    return {
        "text": (
            f"زمان‌های آزاد واقعی برای «{service.service_name}»:\n\n"
            + "\n".join(f"• {line}" for line in lines)
            + "\n\nزمان موردنظرت رو انتخاب کن؛ رزرو نهایی داخل Loomera انجام می‌شه."
        ),
        "reply_markup": reply_markup,
    }


@_safe_loomi
def try_handle_loomi_callback(*, identity, provider, callback_data: str, base_url: str = "") -> dict | None:
    """Handle Loomi-only callbacks after existing menu/action callbacks."""
    parsed = _parse_availability_callback(callback_data)
    if not parsed:
        return None

    service_id, offset, horizon = parsed
    context = _current_context(identity)
    if not context:
        return {
            "text": "این انتخاب به گفت‌وگوی فعالی وصل نیست. لطفاً دوباره لینک لومی سالن یا متخصص رو باز کن.",
            "reply_markup": None,
        }
    target = _context_target(context)
    if not target:
        return {
            "text": "این پروفایل دیگر در دسترس نیست. لطفاً لینک یک مجموعه یا متخصص فعال رو باز کن.",
            "reply_markup": None,
        }

    from django.utils import timezone

    return _availability_answer(
        context.scope_type,
        target,
        "",
        base_url,
        selected_service_id=service_id,
        start_date=timezone.localdate() + timedelta(days=offset),
        horizon_days=horizon,
    )

def _scoped_read_only_reply(*, context, target, question: str, base_url: str) -> dict | None:
    normalized = _normalize(question)

    if _is_greeting(normalized):
        return {
            "text": _welcome_text(context.scope_type, target),
            "reply_markup": _booking_markup(context.scope_type, target, base_url),
        }

    # Product/account lifecycle questions belong to the Help Center even when
    # a public salon/stylist context is active. In particular, cancellation
    # must never be mistaken for a request to find a new slot.
    if _contains_any(normalized, _CANCELLATION_WORDS | {
        "پرداخت", "حساب", "ثبت نام", "ورود", "قوانین", "پشتیبانی",
    }):
        return None

    if _is_booking_or_availability_question(normalized):
        return _availability_answer(context.scope_type, target, question, base_url)

    if _contains_any(normalized, _CONTACT_WORDS):
        return {"text": _contact_answer(context.scope_type, target), "reply_markup": None}

    service_text = _service_answer(context.scope_type, target, question)
    if service_text:
        return {"text": service_text, "reply_markup": None}

    if _contains_any(normalized, _IDENTITY_WORDS):
        return {
            "text": _welcome_text(context.scope_type, target),
            "reply_markup": _booking_markup(context.scope_type, target, base_url),
        }

    return None


def clear_loomi_context(*, identity) -> bool:
    """Clear only the public Loomi conversation scope for one provider identity."""
    deleted, _ = MessagingConversationContext.objects.filter(identity=identity).delete()
    return bool(deleted)


def _current_context(identity) -> MessagingConversationContext | None:
    context = MessagingConversationContext.objects.filter(identity=identity).first()
    if not context:
        return None

    ttl_seconds = max(
        int(getattr(settings, "LOOMI_MESSAGING_CONTEXT_TTL_SECONDS", 86400) or 86400),
        0,
    )
    if ttl_seconds:
        from django.utils import timezone

        if context.updated_at < timezone.now() - timedelta(seconds=ttl_seconds):
            context.delete()
            return None
    return context


def _is_general_help_question(normalized: str) -> bool:
    return _contains_any(normalized, _CANCELLATION_WORDS | {
        "حساب", "ثبت نام", "ورود", "پرداخت", "قوانین", "پشتیبانی",
        "لومرا چیه", "لومرا چیست", "loomera چیست", "loomera چیه",
    })


def _unscoped_reply(normalized: str, base_url: str, *, connected: bool = False) -> dict | None:
    """Guide public discovery back into the existing customer search flow."""
    from django.urls import reverse
    greeting = _is_greeting(normalized)
    booking = _is_booking_or_availability_question(normalized)
    public_question = _contains_any(normalized, _SERVICE_WORDS | _PRICE_WORDS | _CONTACT_WORDS | {
        "سالن", "متخصص", "آرایشگر", "مجموعه", "انجام میدی", "انجام می دهید",
    })
    if not (greeting or booking or public_question):
        return None
    if greeting:
        text = "سلام 🌱\nمن لومی، دستیار هوشمند لومرا هستم. می‌تونم برای پیدا کردن سالن، خدمات، قیمت‌ها و مسیر رزرو کمکت کنم."
    elif booking:
        text = "برای بررسی زمان‌های آزاد، اول سالن یا متخصص موردنظرت رو انتخاب کن. رزرو از مسیر سایت انجام می‌شود."
    else:
        text = "برای اینکه اطلاعات دقیق خدمات، قیمت یا آدرس رو بگم، باید بدونم درباره کدوم سالن یا متخصص می‌پرسی. از جستجوی سالن‌ها شروع کن یا لینک لومیِ مجموعه یا متخصص رو باز کن."
    rows = [[{"text": "جستجوی سالن‌ها", "callback_data": "menu:customer_search"}]]
    url = absolute_site_url(base_url, reverse("search:search_page"))
    if url.startswith(("https://", "http://")):
        rows.append([{"text": "مشاهده سالن‌ها", "url": url}])
    rows.append([{"text": "منوی اصلی", "callback_data": "menu:main" if connected else "menu:guest"}])
    return {"text": text, "reply_markup": {"inline_keyboard": rows}}


@_safe_loomi
def answer_loomi_message(*, identity, provider, text: str, base_url: str = "") -> dict | None:
    """
    AI fallback for otherwise-unknown messages.

    Existing deterministic bot commands run before this function. Scoped salon/
    stylist data is answered deterministically from the database. The shared
    Help Center RAG is used only for Loomera product/help questions.
    """
    if not loomi_messaging_enabled(provider):
        return None
    question = str(text or "").strip()
    if not question or question.startswith(("/", "menu:", "action:")):
        return None

    max_chars = max(int(getattr(settings, "LOOMI_MESSAGING_MAX_QUESTION_CHARS", 1200) or 1200), 100)
    if len(question) > max_chars:
        return {
            "text": f"پیامت خیلی طولانیه. لطفاً سؤال رو در حداکثر {max_chars} کاراکتر بفرست.",
            "reply_markup": None,
        }

    if not _consume_rate_limit(identity, provider):
        return {
            "text": "تعداد پیام‌های لومی در این بازه به سقف رسیده. کمی بعد دوباره امتحان کن یا از منوی ربات استفاده کن.",
            "reply_markup": None,
        }

    context = _current_context(identity)
    from apps.help_center.services import answer_help_question, detect_user_role
    from .services import identity_has_active_connection
    user = getattr(identity, "user", None) if identity_has_active_connection(identity) else None
    if user is not None and not user.is_active:
        user = None
    role = detect_user_role(user)
    normalized = _normalize(question)
    general_help = not context and _is_general_help_question(normalized)
    if not general_help and role in {"manager", "stylist"} and _contains_any(normalized, {
        "برنامه", "تقویم", "شیفت", "مرخصی", "گزارش", "درآمد", "مدیریت", "همکاری", "نوبت", "امروز", "فردا",
    }):
        from apps.bale_bot.menus import menu_for_role
        _, markup = menu_for_role(base_url, user, role)
        return {
            "text": "برای بررسی برنامه و نوبت‌ها، تقویم را باز کن. تغییر شیفت، مرخصی و سایر کارها از گزینه‌های زیر و داشبورد انجام می‌شود؛ اطلاعات نهایی را همان‌جا بررسی کن.",
            "reply_markup": markup,
        }
    target = None
    if context:
        target = _context_target(context)
        if target:
            scoped = _scoped_read_only_reply(
                context=context,
                target=target,
                question=question,
                base_url=base_url,
            )
            if scoped:
                return scoped
        else:
            return {"text": "این پروفایل دیگر در دسترس نیست. لطفاً لینک یک مجموعه یا متخصص فعال را باز کن.", "reply_markup": None}

    try:
        if not context and not general_help:
            reply = _unscoped_reply(normalized, base_url, connected=user is not None)
            if reply:
                return reply
        if context and target and not _contains_any(
            normalized,
            {"لومرا", "loomera", "حساب", "داشبورد", "پشتیبانی", "پرداخت", "ثبت نام", "ورود"} | _CANCELLATION_WORDS,
        ):
            label = _target_label(context.scope_type, target)
            target_hint = f" «{label}»" if label else ""
            return {
                "text": (
                    f"درباره{target_hint} اطلاعات عمومی ثبت‌شده رو می‌تونم دقیق بررسی کنم: "
                    "خدمات و قیمت‌ها، آدرس و تماس، و زمان‌های آزاد. "
                    "اسم خدمت یا چیزی که می‌خوای بدونی رو کوتاه بفرست تا بررسی کنم."
                ),
                "reply_markup": _booking_markup(context.scope_type, target, base_url),
            }
        result = answer_help_question(
            question=question,
            page_path="/",
            role=role,
            history=[],
            route_name="",
        )
        answer = str((result or {}).get("answer") or "").strip()
        if not answer:
            return None
        return {"text": answer[:3500], "reply_markup": None}
    except Exception:
        # Fail open to the pre-existing deterministic unknown-message menu.
        logger.exception("Loomi messaging fallback failed")
        return None
