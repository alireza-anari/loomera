# custom_tags.py
from django import template

register = template.Library()


@register.filter
def range_filter(value):
    """Generate a range of numbers up to the given value."""
    return range(1, value + 1)


@register.inclusion_tag("services/partials/service_card.html")
def render_service_card(service):
    stylist_prices = {}
    for stylist in service.stylists.all():
        stylist_prices[stylist] = stylist.get_price_for_service(service)

    return {"service": service, "stylist_prices": stylist_prices}


@register.filter
def make_range(arg):
    return range(1, arg + 1)


@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value


