from __future__ import annotations

import logging
import re
from dataclasses import dataclass
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

_BOOKING_WORDS = {
    "رزرو",
    "نوبت",
    "وقت",
    "وقت آزاد",
    "زمان آزاد",
    "ساعت آزاد",
    "خالی",
    "امروز",
    "فردا",
}
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
        "می‌تونی درباره خدمات، قیمت‌ها و اطلاعات مجموعه ازم بپرسی. "
        "برای رزرو هم مسیر امن Loomera رو بهت می‌دم."
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


def _scoped_read_only_reply(*, context, target, question: str, base_url: str) -> dict | None:
    normalized = _normalize(question)

    if _contains_any(normalized, _BOOKING_WORDS):
        label = _target_label(context.scope_type, target)
        return {
            "text": (
                f"برای اینکه زمان نادرست بهت نگم، وقت‌های آزاد «{label}» رو فعلاً فقط از مسیر رزرو خود Loomera بررسی کن. "
                "من اینجا اطلاعات خدمات و قیمت‌های ثبت‌شده رو هم می‌تونم برات بررسی کنم."
            ),
            "reply_markup": _booking_markup(context.scope_type, target, base_url),
        }

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


def _current_context(identity) -> MessagingConversationContext | None:
    return MessagingConversationContext.objects.filter(identity=identity).first()


def _is_general_help_question(normalized: str) -> bool:
    return _contains_any(normalized, {
        "حساب", "ثبت نام", "ورود", "لغو", "پرداخت", "قوانین", "پشتیبانی",
        "لومرا چیه", "لومرا چیست", "loomera چیست", "loomera چیه",
    })


def _unscoped_reply(normalized: str, base_url: str, *, connected: bool = False) -> dict | None:
    """Guide public discovery back into the existing customer search flow."""
    from django.urls import reverse
    greeting = re.sub(r"[^\w\s]", "", normalized).strip() in {
        "سلام", "درود", "سلام لومی", "سلام وقت بخیر", "hello", "hi",
    }
    booking = _contains_any(normalized, _BOOKING_WORDS | {"زمان", "موجودی وقت"})
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
        if context and not _contains_any(normalized, {"لومرا", "loomera", "حساب", "داشبورد", "پشتیبانی", "پرداخت", "ثبت نام", "ورود", "لغو"}):
            return {"text": "برای این سؤال اطلاعات تأییدشده‌ای ندارم. می‌تونی درباره خدمات، قیمت، آدرس یا مسیر رزرو بپرسی.", "reply_markup": None}
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
