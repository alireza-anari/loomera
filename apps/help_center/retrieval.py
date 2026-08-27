from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass

from django.db import OperationalError, ProgrammingError
from django.db.models import Q

from .models import Audience, HelpArticleChunk


DB_ERRORS = (OperationalError, ProgrammingError)

ARABIC_PERSIAN_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)

STOP_WORDS = {
    "از", "به", "در", "با", "برای", "روی", "و", "یا", "که", "را", "این", "آن",
    "من", "ما", "شما", "یک", "چه", "چی", "چیه", "چطور", "چگونه", "می", "کنم",
    "کنیم", "کردم", "کرده", "باید", "است", "هست", "هستم", "میشه", "می‌شود", "لطفا",
    "لطفاً", "داره", "دارم", "داریم", "اگه", "اگر", "ولی", "هم", "همین", "تو", "توی",
}

# These are language aliases, not product facts. Product facts must come from docs.
CONCEPT_GROUPS = (
    ("متخصص", "استایلیست", "آرایشگر", "عضو تیم", "همکار"),
    ("رزرو", "نوبت", "وقت"),
    ("شیفت", "برنامه کاری", "برنامه کار"),
    ("ساعت کاری مجموعه", "ساعات کاری مجموعه", "ساعت سالن", "opening hours"),
    ("مجموعه", "سالن"),
    ("خدمت", "سرویس"),
    ("مرخصی", "عدم حضور", "تایم آف", "time off"),
    ("کد تخفیف", "کوپن", "coupon"),
    ("کیف پول", "wallet"),
    ("اعلان", "نوتیفیکیشن", "notification"),
    ("پرداخت", "درگاه", "تراکنش"),
    ("لغو", "کنسل"),
    ("دعوت", "دعوت همکاری", "invite"),
    ("همکاری", "عضویت", "membership"),
    ("برداشت", "دریافت درآمد", "واریز", "تسویه"),
    ("بله", "پیام رسان", "پیام‌رسان", "ربات بله", "bale"),
    ("رمز عبور", "پسورد", "password"),
    ("آدرس", "نشانی"),
    ("مالی", "درآمد", "سهم"),
    ("رسید", "فیش واریز"),
    ("موجودی", "مانده", "اعتبار"),
)

PAGE_INTENT_PHRASES = (
    "این صفحه",
    "همین صفحه",
    "اینجا",
    "این قسمت",
    "این بخش",
    "تو این صفحه",
    "در این صفحه",
    "با این صفحه",
)


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: int
    article_id: int
    article_key: str
    slug: str
    title: str
    article_type: str
    heading: str
    content: str
    score: float


def normalize_persian(value: str) -> str:
    text = str(value or "").translate(ARABIC_PERSIAN_TRANSLATION)
    text = text.replace("\u200c", " ").replace("ـ", " ").lower()
    text = re.sub(r"[^0-9a-zA-Z\u0600-\u06ff]+", " ", text)
    return " ".join(text.split())


def tokenize(value: str) -> list[str]:
    return [
        token
        for token in normalize_persian(value).split()
        if len(token) > 1 and token not in STOP_WORDS
    ]


def _expanded_terms(query: str) -> set[str]:
    normalized = normalize_persian(query)
    terms = set(tokenize(query))
    for group in CONCEPT_GROUPS:
        normalized_group = [normalize_persian(item) for item in group]
        if any(term and term in normalized for term in normalized_group):
            for item in group:
                terms.update(tokenize(item))
    return terms


def is_page_context_question(query: str) -> bool:
    normalized = normalize_persian(query)
    return any(normalize_persian(phrase) in normalized for phrase in PAGE_INTENT_PHRASES)


def allowed_audiences(role: str) -> tuple[str, ...]:
    """Return documentation audiences a role is allowed to retrieve.

    Managers and stylists frequently need to explain the customer journey, so
    they may retrieve public/customer docs in addition to their own operational
    docs. Customers never receive manager/stylist internal guides.
    """
    value = (role or "").strip().lower()
    if value == Audience.MANAGER:
        return (Audience.ALL, Audience.CUSTOMER, Audience.MANAGER)
    if value == Audience.STYLIST:
        return (Audience.ALL, Audience.CUSTOMER, Audience.STYLIST)
    if value == Audience.CUSTOMER:
        return (Audience.ALL, Audience.CUSTOMER)
    return (Audience.ALL,)


def _audience_q(role: str):
    return Q(article__audience__in=allowed_audiences(role))


def _field_score(query_norm: str, terms: set[str], text: str, *, exact_bonus: float, token_weight: float) -> float:
    normalized = normalize_persian(text)
    if not normalized:
        return 0.0
    score = exact_bonus if query_norm and query_norm in normalized else 0.0
    tokens = set(tokenize(normalized))
    overlap = terms & tokens
    score += len(overlap) * token_weight
    return score


def _alias_phrase_bonus(query_norm: str, aliases: str) -> float:
    """Reward curated user phrasings without treating them as answer evidence."""
    if not query_norm:
        return 0.0

    query_tokens = set(tokenize(query_norm))
    best = 0.0
    for raw in str(aliases or "").splitlines():
        alias = normalize_persian(raw)
        alias_tokens = tokenize(alias)
        if len(alias_tokens) < 2:
            continue

        if alias and alias in query_norm:
            best = max(best, min(12.0, 6.0 + len(alias_tokens) * 1.5))
            continue

        overlap = len(set(alias_tokens) & query_tokens)
        coverage = overlap / max(len(set(alias_tokens)), 1)
        if len(alias_tokens) >= 3 and coverage >= 0.75:
            best = max(best, 5.0 + coverage * 4.0)

    return best


def _score_chunk(
    chunk,
    query: str,
    *,
    role: str = "",
    page_key: str = "",
    use_page_context: bool = False,
) -> float:
    query_norm = normalize_persian(query)
    terms = _expanded_terms(query)
    if not terms and not query_norm:
        return 0.0

    article = chunk.article
    score = 0.0
    score += _field_score(query_norm, terms, article.title, exact_bonus=15.0, token_weight=5.2)
    score += _field_score(query_norm, terms, chunk.heading, exact_bonus=10.0, token_weight=4.2)
    score += _field_score(query_norm, terms, article.keywords, exact_bonus=8.0, token_weight=3.6)
    score += _field_score(query_norm, terms, article.aliases, exact_bonus=8.0, token_weight=3.6)
    score += _alias_phrase_bonus(query_norm, article.aliases)
    score += _field_score(query_norm, terms, chunk.content, exact_bonus=7.0, token_weight=2.0)

    searchable_tokens = set(tokenize(chunk.search_text))
    overlap_count = len(terms & searchable_tokens)
    if terms:
        coverage = overlap_count / max(len(terms), 1)
        score += coverage * 8.0
        # Require stronger evidence for long questions. One accidental token match
        # should not pull an unrelated document into RAG.
        if len(terms) >= 4 and coverage < 0.20:
            score *= 0.35

    if article.article_type == "troubleshooting" and any(
        token in query_norm for token in ("چرا", "مشکل", "نمیشه", "نمی شه", "نمی‌شود", "خطا", "نمایش نمیده", "کار نمیکنه")
    ):
        score += 2.0

    # Operational intent words are highly discriminative in product support.
    # Example: "درخواست مرخصی" should rank the request-review doc above the
    # direct manager time-off form, and "لینک رزرو" should prefer quick-link
    # docs over generic booking availability troubleshooting.
    intent_surface = normalize_persian(
        " ".join((article.title, article.keywords, article.aliases))
    )
    for intent in ("درخواست", "بررسی", "تایید", "رد", "لغو", "لینک", "گزارش", "رمز", "حذف", "تیکت", "اعلان", "حداقل", "حداکثر", "وصل", "قطع", "شارژ"):
        normalized_intent = normalize_persian(intent)
        if normalized_intent in query_norm and normalized_intent in intent_surface:
            score += 4.0

    # Managers/stylists may intentionally retrieve customer-journey docs.
    # Exact-role affinity is only a small tie-breaker when two docs are close.
    if role and article.audience == role:
        score += 3.0

    # Current page is NEVER a general retrieval boost. It is only used when the
    # user explicitly asks about "this page / here / this section".
    if use_page_context and page_key and article.key == page_key:
        score += 8.0

    # Slight preference for concise evidence instead of huge generic chunks.
    if len(chunk.content) > 1200:
        score -= 0.5
    return max(score, 0.0)


def retrieve_help_chunks(
    query: str,
    *,
    role: str,
    page_key: str = "",
    limit: int = 5,
    min_score: float = 6.0,
) -> list[RetrievalHit]:
    question = str(query or "").strip()
    if not question:
        return []

    use_page_context = is_page_context_question(question)
    try:
        qs = (
            HelpArticleChunk.objects.select_related("article", "article__category")
            .filter(article__is_published=True)
            .filter(_audience_q(role))
            .order_by("article_id", "position")
        )
        chunks = list(qs[:3000])
    except DB_ERRORS:
        return []

    scored = [
        (
            _score_chunk(
                chunk,
                question,
                role=role,
                page_key=page_key,
                use_page_context=use_page_context,
            ),
            chunk,
        )
        for chunk in chunks
    ]
    scored.sort(key=lambda item: (item[0], -item[1].position), reverse=True)

    results: list[RetrievalHit] = []
    per_article = defaultdict(int)
    for score, chunk in scored:
        if score < min_score:
            break
        if per_article[chunk.article_id] >= 2:
            continue
        results.append(
            RetrievalHit(
                chunk_id=chunk.pk,
                article_id=chunk.article_id,
                article_key=chunk.article.key,
                slug=chunk.article.slug,
                title=chunk.article.title,
                article_type=chunk.article.article_type,
                heading=chunk.heading,
                content=chunk.content,
                score=round(score, 3),
            )
        )
        per_article[chunk.article_id] += 1
        if len(results) >= max(1, limit):
            break
    return results


def unique_article_hits(hits: list[RetrievalHit], limit: int = 10) -> list[RetrievalHit]:
    result = []
    seen = set()
    for hit in hits:
        if hit.article_id in seen:
            continue
        seen.add(hit.article_id)
        result.append(hit)
        if len(result) >= limit:
            break
    return result
