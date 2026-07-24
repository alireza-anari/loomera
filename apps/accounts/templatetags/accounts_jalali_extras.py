from django import template
from khayyam import JalaliDate

register = template.Library()


@register.filter
def jalali_date(date, date_format="%B"):
    """
    تبدیل تاریخ میلادی به تاریخ شمسی با فرمت دلخواه.
    به طور پیش‌فرض فرمت %B به معنی نمایش نام کامل ماه (فارسی) است.
    """
    try:
        j_date = JalaliDate(date)
        return j_date.strftime(date_format)
    except Exception:
        return date


@register.filter
def make_range(arg):
    return range(1, arg + 1)
