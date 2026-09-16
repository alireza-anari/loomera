from __future__ import annotations

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe


register = template.Library()
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _inline(value: str) -> str:
    safe = escape(value or "")
    return BOLD_RE.sub(r"<strong>\1</strong>", safe)


@register.filter(name="render_help_markdown")
def render_help_markdown(value):
    """Render the tiny Markdown subset used by reviewed Loomera docs.

    Everything is HTML-escaped first. Supported syntax is intentionally limited
    to headings, paragraphs, ordered/unordered lists and **bold** text so Admin
    content cannot inject arbitrary HTML.
    """
    lines = str(value or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    paragraph = []
    list_type = None

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            text = " ".join(part.strip() for part in paragraph if part.strip())
            if text:
                output.append(f"<p>{_inline(text)}</p>")
            paragraph = []

    def close_list():
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = None

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue

        if line.startswith("### "):
            flush_paragraph(); close_list()
            output.append(f"<h3>{_inline(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph(); close_list()
            output.append(f"<h2>{_inline(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph(); close_list()
            output.append(f"<h2>{_inline(line[2:])}</h2>")
            continue

        ordered = re.match(r"^\d+[.)]\s+(.+)$", line)
        unordered = re.match(r"^[-*]\s+(.+)$", line)
        if ordered or unordered:
            flush_paragraph()
            wanted = "ol" if ordered else "ul"
            if list_type != wanted:
                close_list()
                output.append(f"<{wanted}>")
                list_type = wanted
            output.append(f"<li>{_inline((ordered or unordered).group(1))}</li>")
            continue

        close_list()
        paragraph.append(line)

    flush_paragraph()
    close_list()
    return mark_safe("".join(output))
