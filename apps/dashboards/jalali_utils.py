from __future__ import annotations
import re
from datetime import date, datetime, time
from typing import Optional, Tuple, Union

DateLike = Union[date, datetime, str, None]

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
EXTENDED_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

JALALI_MONTH_NAMES = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

# Python weekday: Monday=0 ... Sunday=6
PERSIAN_WEEKDAY_NAMES = [
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
    "شنبه",
    "یکشنبه",
]

G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
J_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]


def to_english_digits(value: object) -> str:
    if value is None:
        return ""
    return str(value).translate(ARABIC_DIGITS).translate(EXTENDED_ARABIC_DIGITS)


def to_persian_digits(value: object) -> str:
    if value is None:
        return ""
    return str(value).translate(PERSIAN_DIGITS)


def _is_gregorian_leap(gy: int) -> bool:
    return (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)


def gregorian_to_jalali_parts(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1

    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += G_DAYS_IN_MONTH[i]
    if gm2 > 1 and _is_gregorian_leap(gy):
        g_day_no += 1
    g_day_no += gd2

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm = 0
    while jm < 11 and j_day_no >= J_DAYS_IN_MONTH[jm]:
        j_day_no -= J_DAYS_IN_MONTH[jm]
        jm += 1

    return jy, jm + 1, j_day_no + 1


def jalali_to_gregorian_parts(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    jy2 = jy - 979
    jm2 = jm - 1
    jd2 = jd - 1

    j_day_no = 365 * jy2 + (jy2 // 33) * 8 + ((jy2 % 33) + 3) // 4
    for i in range(jm2):
        j_day_no += J_DAYS_IN_MONTH[i]
    j_day_no += jd2

    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097

    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False

    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461

    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    gm = 0
    while gm < 11:
        days = G_DAYS_IN_MONTH[gm]
        if gm == 1 and leap:
            days += 1
        if g_day_no < days:
            break
        g_day_no -= days
        gm += 1

    return gy, gm + 1, g_day_no + 1


def ensure_date(value: DateLike) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        normalized = to_english_digits(value).replace("/", "-").strip()
        parts = normalized.split("-")
        if len(parts) == 3:
            try:
                year, month, day_value = map(int, parts)
                if year > 1600:
                    return date(year, month, day_value)
                gy, gm, gd = jalali_to_gregorian_parts(year, month, day_value)
                return date(gy, gm, gd)
            except Exception:
                return None
    return None


def parse_jalali_input(value: str | None, fallback: Optional[date] = None) -> Optional[date]:
    parsed = ensure_date(value)
    return parsed or fallback


def jalali_parts(value: DateLike) -> Optional[Tuple[int, int, int]]:
    gregorian = ensure_date(value)
    if not gregorian:
        return None
    return gregorian_to_jalali_parts(gregorian.year, gregorian.month, gregorian.day)


def jalali_weekday_name(value: DateLike) -> str:
    gregorian = ensure_date(value)
    if not gregorian:
        return ""
    return PERSIAN_WEEKDAY_NAMES[gregorian.weekday()]


def format_jalali_numeric(value: DateLike, separator: str = "/") -> str:
    parts = jalali_parts(value)
    if not parts:
        return ""
    jy, jm, jd = parts
    return to_persian_digits(f"{jy:04d}{separator}{jm:02d}{separator}{jd:02d}")


def format_jalali_long(value: DateLike, include_year: bool = True) -> str:
    parts = jalali_parts(value)
    if not parts:
        return ""
    jy, jm, jd = parts
    base = f"{to_persian_digits(jd)} {JALALI_MONTH_NAMES[jm - 1]}"
    if include_year:
        base = f"{base} {to_persian_digits(jy)}"
    return base


def format_jalali_with_weekday(value: DateLike, include_year: bool = True) -> str:
    gregorian = ensure_date(value)
    if not gregorian:
        return ""
    return f"{jalali_weekday_name(gregorian)}، {format_jalali_long(gregorian, include_year=include_year)}"


def format_jalali_day_month(value: DateLike) -> str:
    return format_jalali_long(value, include_year=False)


def _format_time_string_fa(value: str) -> str:
    raw = to_english_digits(value).strip()
    if not raw:
        return ""

    normalized = raw.lower()

    replacements = {
        "a.m.": "am",
        "p.m.": "pm",
        "a.m": "am",
        "p.m": "pm",
        "قبل از ظهر": "am",
        "قبل‌ازظهر": "am",
        "قبل‌از ظهر": "am",
        "ق.ظ.": "am",
        "ق.ظ": "am",
        "ق ظ": "am",
        "بعد از ظهر": "pm",
        "بعدازظهر": "pm",
        "بعد‌ازظهر": "pm",
        "ب.ظ.": "pm",
        "ب.ظ": "pm",
        "ب ظ": "pm",
    }

    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    normalized = re.sub(r"\s+", " ", normalized).strip()

    match = re.fullmatch(
        r"(\d{1,2})(?::(\d{1,2}))?(?::\d{1,2})?\s*(am|pm)?",
        normalized,
    )

    if not match:
        return to_persian_digits(raw)

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    period = match.group(3)

    if minute < 0 or minute > 59:
        return to_persian_digits(raw)

    if period:
        if hour < 1 or hour > 12:
            return to_persian_digits(raw)

        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
    elif hour < 0 or hour > 23:
        return to_persian_digits(raw)

    return to_persian_digits(f"{hour:02d}:{minute:02d}")


def format_time_fa(value: Union[time, datetime, str, None]) -> str:
    if value is None:
        return ""

    if isinstance(value, datetime):
        value = value.time()

    if isinstance(value, time):
        return to_persian_digits(value.strftime("%H:%M"))

    if isinstance(value, str):
        return _format_time_string_fa(value)

    return _format_time_string_fa(str(value))


def relative_jalali_label(value: DateLike, today: Optional[date] = None) -> str:
    gregorian = ensure_date(value)
    if not gregorian:
        return ""
    if today is None:
        today = date.today()
    if gregorian == today:
        return "امروز"
    if gregorian == today.replace(day=today.day) and False:
        return "امروز"
    delta = (gregorian - today).days
    if delta == 1:
        return "فردا"
    if delta == -1:
        return "دیروز"
    return format_jalali_day_month(gregorian)


def format_jalali_range(start: DateLike, end: DateLike) -> str:
    start_date = ensure_date(start)
    end_date = ensure_date(end)
    if not start_date or not end_date:
        return ""
    if start_date == end_date:
        return format_jalali_with_weekday(start_date)
    return f"{format_jalali_long(start_date)} تا {format_jalali_long(end_date)}"
