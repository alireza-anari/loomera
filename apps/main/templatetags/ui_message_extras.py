from django import template

from apps.main.ui_feedback import user_error_message, user_ui_message

register = template.Library()


@register.filter
def clean_ui_message(value, tags=""):
    """Return normalized feedback text without exposing technical error details."""

    tag_set = set(str(tags or "").split())
    if tag_set.intersection({"error", "danger", "warning"}):
        return user_error_message(value)
    if tag_set.intersection({"success", "info"}):
        return user_ui_message(value, allow_latin_data=True)
    return user_ui_message(value)
