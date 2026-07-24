from datetime import date, datetime

from django import template
from persiantools.jdatetime import JalaliDate

register = template.Library()

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

MONTH_NAMES = [
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


@register.filter(name="fa_digits")
def fa_digits(value):
    if value is None:
        return ""
    return str(value).translate(_PERSIAN_DIGITS)


@register.filter(name="article_jalali")
def article_jalali(value):
    if not value:
        return ""

    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value).date()

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            jdate = JalaliDate(value)
            return f"{jdate.year}/{jdate.month:02d}/{jdate.day:02d}".translate(
                _PERSIAN_DIGITS
            )

        return str(value).translate(_PERSIAN_DIGITS)
    except Exception:
        return str(value).translate(_PERSIAN_DIGITS)


@register.filter(name="article_jalali_long")
def article_jalali_long(value):
    if not value:
        return ""

    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value).date()

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            jdate = JalaliDate(value)
            month_name = MONTH_NAMES[jdate.month - 1]
            return f"{jdate.day} {month_name} {jdate.year}".translate(_PERSIAN_DIGITS)

        return str(value).translate(_PERSIAN_DIGITS)
    except Exception:
        return str(value).translate(_PERSIAN_DIGITS)


@register.filter(name="article_jalali_short")
def article_jalali_short(value):
    if not value:
        return ""

    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value).date()

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            jdate = JalaliDate(value)
            month_name = MONTH_NAMES[jdate.month - 1]
            return f"{jdate.day} {month_name}".translate(_PERSIAN_DIGITS)

        return str(value).translate(_PERSIAN_DIGITS)
    except Exception:
        return str(value).translate(_PERSIAN_DIGITS)


@register.filter(name="clean_public_content")
def clean_public_content(value):
    text = (value or "").strip()
    if not text:
        return ""
    marker = "\n\nگزینه‌های پیشنهادی برای مدیر:"
    if marker in text:
        text = text.split(marker, 1)[0].strip()
    prefixes = (
        "گزینه‌های پیشنهادی برای مدیر:",
        "برچسب‌های مرتبط:",
        "برچسب‌های جدید:",
        "خدمات مرتبط:",
        "گروه‌های خدمت:",
        "نمایش پیشنهادی:",
        "نوع دکمه استوری:",
        "متن دکمه:",
        "لینک دکمه:",
    )
    lines = []
    for line in text.splitlines():
        normalized = line.strip()
        if any(normalized.startswith(prefix) for prefix in prefixes):
            continue
        lines.append(line)
    return "\n".join(lines).strip()
