# orders/templatetags/jalali_filters.py

"""
Custom Template Filters برای تبدیل تاریخ میلادی به شمسی

استفاده:
    {% load jalali_filters %}

    {{ appointment.date|jalali }}
    {{ appointment.date|jalali_long }}
    {{ appointment.date|jalali_with_weekday }}
"""

from django import template
from datetime import date, datetime
from persiantools.jdatetime import JalaliDate
from apps.dashboards.jalali_utils import format_time_fa, to_persian_digits

register = template.Library()


@register.filter(name="jalali")
def jalali(value):
    """
    تبدیل تاریخ به فرمت شمسی کوتاه

    مثال:
        2026-02-22 → 1404/12/03

    استفاده:
        {{ appointment.date|jalali }}
    """
    if not value:
        return ""

    try:
        # اگه string هست، تبدیل به date
        if isinstance(value, str):
            try:
                # فرض: فرمت YYYY-MM-DD
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:                # اگه نتونست parse کنه، همون string رو برگردون
                return value

        # اگه datetime هست، فقط date رو بگیر
        if isinstance(value, datetime):
            value = value.date()

        # تبدیل به شمسی
        if isinstance(value, date):
            jdate = JalaliDate(value)
            return to_persian_digits(f"{jdate.year}/{jdate.month:02d}/{jdate.day:02d}")

        return str(value)

    except Exception as e:
        # در صورت خطا، مقدار اصلی رو برگردون
        return str(value)


@register.filter(name="jalali_long")
def jalali_long(value):
    """
    تبدیل تاریخ به فرمت شمسی بلند با نام ماه

    مثال:
        2026-02-22 → 3 اسفند 1404

    استفاده:
        {{ appointment.date|jalali_long }}
    """
    if not value:
        return ""

    try:
        # تبدیل به date object
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:                return value

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            jdate = JalaliDate(value)

            # نام ماه‌ها
            month_names = [
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

            month_name = month_names[jdate.month - 1]

            return to_persian_digits(f"{jdate.day} {month_name} {jdate.year}")

        return str(value)

    except Exception as e:
        return str(value)


@register.filter(name="jalali_with_weekday")
def jalali_with_weekday(value):
    """
    تبدیل تاریخ به فرمت شمسی با روز هفته

    مثال:
        2026-02-22 → یکشنبه، 3 اسفند 1404

    استفاده:
        {{ appointment.date|jalali_with_weekday }}
    """
    if not value:
        return ""

    try:
        # تبدیل به date object
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:                return value

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            jdate = JalaliDate(value)

            # نام ماه‌ها
            month_names = [
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

            # نام روزهای هفته
            weekday_names = [
                "شنبه",
                "یکشنبه",
                "دوشنبه",
                "سه‌شنبه",
                "چهارشنبه",
                "پنج‌شنبه",
                "جمعه",
            ]

            # گرفتن روز هفته (0=شنبه، 6=جمعه)
            gregorian_date = jdate.to_gregorian()
            # در Python: 0=دوشنبه، 6=یکشنبه
            # تبدیل به: 0=شنبه، 6=جمعه
            weekday = (gregorian_date.weekday() + 2) % 7

            weekday_name = weekday_names[weekday]
            month_name = month_names[jdate.month - 1]

            return to_persian_digits(
                f"{weekday_name}، {jdate.day} {month_name} {jdate.year}"
            )

        return str(value)

    except Exception as e:
        return str(value)


@register.filter(name="jalali_short")
def jalali_short(value):
    """
    تبدیل تاریخ به فرمت شمسی خیلی کوتاه (بدون سال)

    مثال:
        2026-02-22 → 3 اسفند

    استفاده:
        {{ appointment.date|jalali_short }}
    """
    if not value:
        return ""

    try:
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:                return value

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            jdate = JalaliDate(value)

            month_names = [
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

            month_name = month_names[jdate.month - 1]

            return to_persian_digits(f"{jdate.day} {month_name}")

        return str(value)

    except Exception as e:
        return str(value)


@register.filter(name="time_ago")
def time_ago(value):
    """
    نمایش زمان به صورت نسبی (مثل "2 ساعت پیش")

    مثال:
        امروز → "امروز"
        دیروز → "دیروز"
        2 روز پیش → "2 روز پیش"
        1 هفته پیش → "1 هفته پیش"

    استفاده:
        {{ appointment.date|time_ago }}
    """
    if not value:
        return ""

    try:
        # تبدیل به date object
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:                return value

        if isinstance(value, datetime):
            value = value.date()

        if isinstance(value, date):
            today = date.today()
            delta = today - value

            if delta.days == 0:
                return "امروز"
            elif delta.days == 1:
                return "دیروز"
            elif delta.days == -1:
                return "فردا"
            elif delta.days < 0:
                # آینده
                days = abs(delta.days)
                if days < 7:
                    return f"{days} روز دیگر"
                elif days < 30:
                    weeks = days // 7
                    return f"{weeks} هفته دیگر"
                elif days < 365:
                    months = days // 30
                    return f"{months} ماه دیگر"
                else:
                    years = days // 365
                    return f"{years} سال دیگر"
            else:
                # گذشته
                if delta.days < 7:
                    return f"{delta.days} روز پیش"
                elif delta.days < 30:
                    weeks = delta.days // 7
                    return f"{weeks} هفته پیش"
                elif delta.days < 365:
                    months = delta.days // 30
                    return f"{months} ماه پیش"
                else:
                    years = delta.days // 365
                    return f"{years} سال پیش"

        return str(value)

    except Exception as e:
        return str(value)


@register.filter(name="persian_time")
def persian_time(value):
    """
    نمایش ساعت به فرمت فارسی و ۲۴ ساعته.

    مثال:
        2:30 p.m. → ۱۴:۳۰
        09:00     → ۰۹:۰۰
        14:30     → ۱۴:۳۰
    """
    if not value:
        return ""

    try:
        return format_time_fa(value)
    except Exception:
        return to_persian_digits(value)
