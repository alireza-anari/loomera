from __future__ import annotations

import hashlib
import re
import secrets
from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.urls import Resolver404, resolve
from django.utils import timezone

PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

CONFIRMATION_SALT = "loomera.help-center.lumi-action.v1"
CONFIRMATION_MAX_AGE = 15 * 60

WEEKDAY_MAP = {
    "شنبه": 5,
    "یکشنبه": 6,
    "یک شنبه": 6,
    "دوشنبه": 0,
    "دو شنبه": 0,
    "سه شنبه": 1,
    "سه‌شنبه": 1,
    "چهارشنبه": 2,
    "پنجشنبه": 3,
    "پنج شنبه": 3,
    "پنج‌شنبه": 3,
    "جمعه": 4,
}

WEEKDAY_ORDER = [5, 6, 0, 1, 2, 3, 4]
WEEKDAY_LABELS = {
    5: "شنبه",
    6: "یکشنبه",
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنج‌شنبه",
    4: "جمعه",
}


def normalize_text(value: str) -> str:
    text = str(value or "").translate(PERSIAN_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    text = text.replace("\u200c", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def user_roles(user) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return {"guest"}
    roles: set[str] = set()
    if hasattr(user, "salon_manager_profile"):
        roles.add("manager")
    if hasattr(user, "stylist"):
        roles.add("stylist")
    if hasattr(user, "customer_profile"):
        roles.add("customer")
    if getattr(user, "is_admin", False) or getattr(user, "is_superuser", False):
        roles.add("admin")
    return roles or {"user"}


def resolve_current_path(path: str):
    raw = str(path or "").strip()
    if not raw:
        return None
    try:
        clean = urlsplit(raw).path or "/"
        return resolve(clean)
    except (Resolver404, ValueError):
        return None


def issue_confirmation(*, user, action: str, data: dict, ttl_seconds: int | None = None) -> str:
    if not getattr(user, "is_authenticated", False):
        raise ValidationError("برای انجام این عملیات باید وارد حساب کاربری شوی.")
    payload = {
        "uid": int(user.pk),
        "action": str(action),
        "data": dict(data or {}),
        "nonce": secrets.token_urlsafe(12),
        "issued_at": timezone.now().isoformat(),
        "ttl": int(ttl_seconds or CONFIRMATION_MAX_AGE),
    }
    return signing.dumps(payload, salt=CONFIRMATION_SALT, compress=True)


def read_confirmation(*, user, token: str, consume: bool = False) -> dict:
    max_age = int(getattr(settings, "HELP_ACTION_CONFIRM_TTL_SECONDS", CONFIRMATION_MAX_AGE) or CONFIRMATION_MAX_AGE)
    try:
        payload = signing.loads(
            str(token or ""),
            salt=CONFIRMATION_SALT,
            max_age=max_age,
        )
    except signing.SignatureExpired as exc:
        raise ValidationError("زمان تأیید این عملیات تمام شده. دوباره از لومی بخواه تا پیش‌نمایش را بسازد.") from exc
    except signing.BadSignature as exc:
        raise ValidationError("تأیید این عملیات معتبر نیست. دوباره تلاش کن.") from exc

    if not isinstance(payload, dict) or int(payload.get("uid") or 0) != int(getattr(user, "pk", 0) or 0):
        raise ValidationError("این تأیید برای حساب فعلی معتبر نیست.")

    if consume:
        digest = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
        key = f"loomera:lumi-action-confirm:{digest}"
        try:
            first = cache.add(key, "1", timeout=max_age)
        except Exception as exc:
            # Confirmation replay protection is part of the write-safety
            # boundary. If the cache is unavailable, fail closed rather than
            # allowing the same signed write token to be replayed.
            raise ValidationError(
                "سامانه تأیید عملیات موقتاً در دسترس نیست. دوباره تلاش کن."
            ) from exc
        if not first:
            raise ValidationError("این عملیات قبلاً تأیید شده یا در حال انجام است.")
    return payload


def parse_clock(raw: str, marker: str = "") -> time | None:
    value = str(raw or "").strip().translate(PERSIAN_DIGITS)
    match = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if minute > 59:
        return None
    marker = normalize_text(marker)
    if marker in {"عصر", "شب", "بعدازظهر", "بعد از ظهر"} and 1 <= hour <= 11:
        hour += 12
    if marker in {"ظهر"} and 1 <= hour <= 5:
        hour += 12
    if marker in {"صبح"} and hour == 12:
        hour = 0
    if hour > 23:
        return None
    return time(hour, minute)


def parse_time_range(text: str) -> tuple[time | None, time | None]:
    value = normalize_text(text)
    patterns = (
        r"(?:از\s+)?(\d{1,2}(?::\d{1,2})?)\s*(صبح|ظهر|بعدازظهر|بعد از ظهر|عصر|شب)?\s*(?:تا|الی|-)\s*(\d{1,2}(?::\d{1,2})?)\s*(صبح|ظهر|بعدازظهر|بعد از ظهر|عصر|شب)?",
        r"ساعت\s*(\d{1,2}(?::\d{1,2})?)\s*(صبح|ظهر|بعدازظهر|بعد از ظهر|عصر|شب)?\s*(?:تا|الی|-)\s*(\d{1,2}(?::\d{1,2})?)\s*(صبح|ظهر|بعدازظهر|بعد از ظهر|عصر|شب)?",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if not match:
            continue
        start = parse_clock(match.group(1), match.group(2) or "")
        end = parse_clock(match.group(3), match.group(4) or "")
        if start and end and end <= start and not (match.group(4) or ""):
            # Conversational Persian often says "۹ تا ۵" for 09:00–17:00.
            if end.hour <= 11 and start.hour <= 12:
                end = time(end.hour + 12, end.minute)
        return start, end
    return None, None


def parse_relative_date(text: str, *, today: date | None = None) -> date | None:
    today = today or timezone.localdate()
    value = normalize_text(text)
    if "پس فردا" in value or "پس‌فردا" in str(text or ""):
        return today + timedelta(days=2)
    if "فردا" in value:
        return today + timedelta(days=1)
    if "امروز" in value:
        return today
    return None


def _next_weekday(target_weekday: int, *, start: date) -> date:
    delta = (target_weekday - start.weekday()) % 7
    return start + timedelta(days=delta)


def parse_weekday_dates(text: str, *, today: date | None = None) -> list[date]:
    today = today or timezone.localdate()
    value = normalize_text(text)

    # Range: شنبه تا چهارشنبه
    found_labels = []
    for label, weekday in WEEKDAY_MAP.items():
        if label in value:
            found_labels.append((value.index(label), label, weekday))
    found_labels.sort()

    if "تا" in value and len(found_labels) >= 2:
        start_weekday = found_labels[0][2]
        end_weekday = found_labels[1][2]
        start_index = WEEKDAY_ORDER.index(start_weekday)
        end_index = WEEKDAY_ORDER.index(end_weekday)
        if end_index < start_index:
            sequence = WEEKDAY_ORDER[start_index:] + WEEKDAY_ORDER[: end_index + 1]
        else:
            sequence = WEEKDAY_ORDER[start_index : end_index + 1]
        first_date = _next_weekday(sequence[0], start=today)
        dates = [first_date]
        for _ in sequence[1:]:
            dates.append(dates[-1] + timedelta(days=1))
        return dates

    # Explicit individual weekday names.
    unique = []
    seen = set()
    for _pos, _label, weekday in found_labels:
        if weekday in seen:
            continue
        seen.add(weekday)
        unique.append(weekday)
    if unique:
        rows = [_next_weekday(day, start=today) for day in unique]
        return sorted(rows)
    return []


def parse_dates(text: str, *, allow_weekday_range: bool = False) -> list[date]:
    relative = parse_relative_date(text)
    if relative:
        return [relative]
    if allow_weekday_range:
        return parse_weekday_dates(text)
    weekdays = parse_weekday_dates(text)
    return weekdays[:1]


def date_label(value: date) -> str:
    try:
        from khayyam import JalaliDate

        jalali = JalaliDate(value).strftime("%Y/%m/%d")
        return f"{WEEKDAY_LABELS.get(value.weekday(), '')} {jalali}".strip()
    except Exception:
        return f"{WEEKDAY_LABELS.get(value.weekday(), '')} {value.isoformat()}".strip()


def serialize_time(value: time | None) -> str:
    return value.strftime("%H:%M") if value else ""


def parse_iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise ValidationError("تاریخ عملیات معتبر نیست.") from exc
    if parsed < timezone.localdate():
        raise ValidationError("تاریخ انتخاب‌شده در گذشته است.")
    return parsed


def parse_hhmm(value: str, *, required: bool = True) -> time | None:
    raw = str(value or "").strip()
    if not raw and not required:
        return None
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise ValidationError("ساعت انتخاب‌شده معتبر نیست.") from exc
