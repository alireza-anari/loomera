from django import template


register = template.Library()


@register.filter
def services_by_group(salon, group):
    return salon.services.filter(service_group=group)


@register.filter
def make_range(arg):
    return range(1, arg + 1)


@register.filter
def round_value(value):
    return round(value, 2)


@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value


@register.filter
def dict_lookup(d, key):
    """
    از این فیلتر برای گرفتن مقدار کلید عددی یا رشته‌ای از دیکشنری استفاده می‌کنیم.
    مثلاً {{ star_counts|dict_lookup:3 }} مقدار star_counts[3] را برمی‌گرداند.
    """
    if not isinstance(d, dict):
        return ""
    return d.get(key, 0)


@register.filter
def to_percent(value, total):
    """
    برای تبدیل مقدار value به درصدی از total، مثلاً (value / total * 100).
    اگر total صفر بود، برمی‌گرداند 0.
    """
    try:
        v = float(value)
        t = float(total)
        if t == 0:
            return 0
        return (v / t) * 100
    except (ValueError, TypeError):
        return 0


@register.filter(name="get_item")
def get_item(dictionary, key):
    """فیلتر پیشرفته برای دسترسی به دیکشنری با پشتیبانی از کلیدهای عددی و رشته‌ای"""
    try:
        if isinstance(key, str) and key.isdigit():
            key = int(key)
        return dictionary.get(key, [])
    except (AttributeError, TypeError):
        return []


@register.filter(name="add_class")
def add_class(field, css_class):
    """
    افزودن کلاس‌های CSS به فیلد فرم Django
    مثال استفاده:
        {{ form.field|add_class:"w-full bg-gray-50" }}
    """
    return field.as_widget(
        attrs={
            **field.field.widget.attrs,
            "class": (field.field.widget.attrs.get("class", "") + " " + css_class).strip(),
        }
    )
