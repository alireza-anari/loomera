import ast
import re

from django import template

register = template.Library()


@register.filter
def clean_ui_message(value):
    """Normalize message-framework text for display without changing backend logic.

    Django ValidationError stringification can produce a Python-list-looking string,
    e.g. ``['زمان انتخاب‌شده دیگر آزاد نیست.']``.  This filter only unwraps a
    literal list/tuple of strings and normalizes whitespace; arbitrary content is
    returned as text and remains auto-escaped by the template engine.
    """

    text = str(value or "").strip()
    if not text:
        return ""

    if (text.startswith("[") and text.endswith("]")) or (
        text.startswith("(") and text.endswith(")")
    ):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, (list, tuple)) and parsed and all(
            isinstance(item, str) for item in parsed
        ):
            text = "، ".join(item.strip() for item in parsed if item.strip())

    return re.sub(r"\s+", " ", text).strip()
