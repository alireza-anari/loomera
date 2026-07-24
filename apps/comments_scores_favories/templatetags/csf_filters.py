from django import template

register = template.Library()


@register.filter
def range_filter(value):
    """Generate a range of numbers up to the given value."""
    return range(1, value + 1)


@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value
