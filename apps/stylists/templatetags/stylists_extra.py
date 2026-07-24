from django import template

register = template.Library()


@register.filter
def get_price_for_service(stylist, service):
    return stylist.get_price_for_service(service)


@register.filter
def make_range(arg):
    return range(1, arg + 1)


@register.filter
def filter_active_comments(comments):
    return comments.filter(is_active=True)



@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value
