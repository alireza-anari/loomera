from django import template

from apps.dashboards.jalali_utils import (
    format_jalali_day_month,
    format_jalali_long,
    format_jalali_numeric,
    format_jalali_with_weekday,
    format_time_fa,
)

register = template.Library()


@register.filter
def jalali_date(value, date_format="short"):
    format_key = (date_format or "short").lower()
    if format_key in {"short", "%y/%m/%d", "numeric"}:
        return format_jalali_numeric(value)
    if format_key in {"weekday", "with_weekday"}:
        return format_jalali_with_weekday(value)
    if format_key in {"day_month", "compact"}:
        return format_jalali_day_month(value)
    return format_jalali_long(value)


@register.filter
def jalali_weekday(value):
    return format_jalali_with_weekday(value)


@register.filter
def jalali_short(value):
    return format_jalali_numeric(value)


@register.filter
def jalali_day_month(value):
    return format_jalali_day_month(value)


@register.filter
def fa_time(value):
    return format_time_fa(value)


@register.filter
def jalali_datetime(value):
    date_part = format_jalali_numeric(value)
    time_part = format_time_fa(value)
    if date_part and time_part:
        return f"{date_part} • {time_part}"
    return date_part or time_part


@register.filter
def fa_digits(value):
    from apps.dashboards.jalali_utils import to_persian_digits

    return to_persian_digits(value)


@register.filter
def intdiv(value, arg):
    try:
        return int(value) // int(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return ""


@register.filter
def modulo(value, arg):
    try:
        return int(value) % int(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return ""


@register.filter
def startswith(text, starts):
    if isinstance(text, str):
        return text.startswith(starts)
    return False
