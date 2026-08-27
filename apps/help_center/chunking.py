from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import transaction

from .models import HelpArticle, HelpArticleChunk


HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
MAX_CHUNK_CHARS = 1400


@dataclass(frozen=True)
class ChunkSpec:
    heading: str
    content: str


def _clean(value: str) -> str:
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _split_long_text(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    text = _clean(text)
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > limit:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[.!؟])\s+", paragraph)
            segment = ""
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                candidate = f"{segment} {sentence}".strip()
                if segment and len(candidate) > limit:
                    chunks.append(segment)
                    segment = sentence
                else:
                    segment = candidate
            if segment:
                chunks.append(segment)
            continue

        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > limit:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def article_chunk_specs(article: HelpArticle) -> list[ChunkSpec]:
    sections: list[tuple[str, str]] = []

    if _clean(article.summary):
        sections.append(("خلاصه", article.summary))

    body = _clean(article.body)
    if body:
        current_heading = "راهنما"
        current_lines: list[str] = []
        for line in body.splitlines():
            match = HEADING_RE.match(line)
            if match:
                if current_lines:
                    sections.append((current_heading, "\n".join(current_lines)))
                current_heading = _clean(match.group(1)) or "راهنما"
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_heading, "\n".join(current_lines)))

    for index, step in enumerate(article.steps or [], start=1):
        if isinstance(step, dict):
            title = _clean(step.get("title")) or f"مرحله {index}"
            content = _clean(step.get("body"))
        elif isinstance(step, (list, tuple)) and len(step) >= 2:
            title = _clean(step[0]) or f"مرحله {index}"
            content = _clean(step[1])
        else:
            continue
        if content:
            sections.append((title, content))

    tips = [_clean(item) for item in (article.tips or []) if _clean(item)]
    if tips:
        sections.append(("نکته‌های مهم", "\n".join(f"- {item}" for item in tips)))

    result: list[ChunkSpec] = []
    seen: set[tuple[str, str]] = set()
    for heading, content in sections:
        for part in _split_long_text(content):
            key = (_clean(heading), _clean(part))
            if not key[1] or key in seen:
                continue
            seen.add(key)
            result.append(ChunkSpec(heading=key[0], content=key[1]))
    return result


def build_search_text(article: HelpArticle, *, heading: str, content: str) -> str:
    pieces = [
        article.title,
        article.summary,
        article.keywords,
        article.aliases,
        article.category.title if article.category_id else "",
        article.get_article_type_display(),
        heading,
        content,
    ]
    return _clean("\n".join(str(piece or "") for piece in pieces))


@transaction.atomic
def rebuild_article_chunks(article: HelpArticle) -> int:
    HelpArticleChunk.objects.filter(article=article).delete()
    if not article.is_published:
        return 0

    specs = article_chunk_specs(article)
    rows = [
        HelpArticleChunk(
            article=article,
            position=index,
            heading=spec.heading[:240],
            content=spec.content,
            search_text=build_search_text(
                article,
                heading=spec.heading,
                content=spec.content,
            ),
        )
        for index, spec in enumerate(specs, start=1)
    ]
    if rows:
        HelpArticleChunk.objects.bulk_create(rows)
    return len(rows)
