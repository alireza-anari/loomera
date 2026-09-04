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
    ("تغییر", "عوض", "ویرایش", "جابه جایی", "جابجایی"),
    ("پیگیری", "وضعیت", "چی شد", "چه شد"),
    ("شیفت", "برنامه کاری", "ساعت کاری", "برنامه کار"),
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


ROLE_REFERENCE_TOKENS = {
    Audience.MANAGER: {"مدیر"},
    Audience.STYLIST: {"متخصص", "استایلیست", "آرایشگر"},
    Audience.CUSTOMER: {"مشتری"},
}

SELF_REFERENCE_TOKENS = {
    "من",
    "خودم",
    "خودمون",
    "خودمان",
}

STATUS_INTENT_PHRASES = (
    "چی شد",
    "چه شد",
    "وضعیت",
    "پیگیری",
)


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: int
    article_id: int
    article_key: str
    slug: str
    title: str
    article_type: str
    audience: str
    steps: list
    source_refs: list
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


ROLE_ACTOR_CUES = (
    "چطور",
    "چگونه",
    "از کجا",
    "کجا",
    "میتونه",
    "می تونه",
    "میتواند",
    "می تواند",
    "باید",
    "خودش",
)


def mentions_audience_as_actor(query: str, audience: str) -> bool:
    """Return True when a role is explicitly the actor of the question.

    A bare mention such as ``متخصص رو چطور انتخاب کنم؟`` means the customer
    is choosing a specialist; it must not disable customer-role affinity.
    Cross-role mode is only relaxed when the user actually asks how another
    role acts, e.g. ``مدیر چطور ...`` or ``مشتری نوبت‌های خودش ...``.
    """
    normalized = normalize_persian(query)
    if not normalized:
        return False

    for raw_token in ROLE_REFERENCE_TOKENS.get(audience, set()):
        token = normalize_persian(raw_token)
        if not token:
            continue

        if normalized == token:
            return True

        if f"حساب {token}" in normalized or f"از حساب {token}" in normalized:
            return True

        cue_pattern = "|".join(re.escape(normalize_persian(cue)) for cue in ROLE_ACTOR_CUES)
        if re.search(rf"(?:^|\s){re.escape(token)}\s+(?:{cue_pattern})(?:\s|$)", normalized):
            return True

        # Third-person ownership makes the mentioned role the actor even when
        # the noun between the role and the verb is explicit, e.g.
        # «مشتری نوبت‌های خودش را از کجا می‌بیند؟».
        if normalized.startswith(f"{token} ") and any(
            pronoun in normalized for pronoun in ("خودش", "خودشان", "خودشون")
        ):
            return True

    return False


def _mentions_other_role(query_norm: str, requester_role: str) -> bool:
    role = (requester_role or "").strip().lower()
    return any(
        audience != role and mentions_audience_as_actor(query_norm, audience)
        for audience in ROLE_REFERENCE_TOKENS
    )


def _has_self_reference(query_norm: str) -> bool:
    query_tokens = set(normalize_persian(query_norm).split())
    return bool(query_tokens & SELF_REFERENCE_TOKENS)


def _has_status_intent(query_norm: str) -> bool:
    normalized = normalize_persian(query_norm)
    return any(
        normalize_persian(phrase) in normalized
        for phrase in STATUS_INTENT_PHRASES
    )


def _has_leave_intent(query_norm: str) -> bool:
    normalized = normalize_persian(query_norm)
    return any(
        normalize_persian(phrase) in normalized
        for phrase in ("مرخصی", "عدم حضور", "تایم آف", "time off")
    )


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


def retrieval_audiences(role: str, *, allow_cross_role: bool = False) -> tuple[str, ...]:
    if allow_cross_role:
        return (
            Audience.ALL,
            Audience.CUSTOMER,
            Audience.STYLIST,
            Audience.MANAGER,
        )
    return allowed_audiences(role)


def _audience_q(role: str, *, allow_cross_role: bool = False):
    return Q(article__audience__in=retrieval_audiences(role, allow_cross_role=allow_cross_role))


def _audience_role_bonus(requester_role: str, article_audience: str, *, allow_cross_role: bool = False) -> float:
    role = (requester_role or '').strip().lower()
    audience = (article_audience or '').strip().lower()

    if audience == Audience.ALL:
        return 1.2

    if not allow_cross_role:
        return 1.8 if audience == role else 0.0

    if audience == role:
        return 3.5

    # Guest/public questions should still prioritize customer-facing docs.
    if role in ('guest', Audience.CUSTOMER) and audience == Audience.CUSTOMER:
        return 2.0

    # Cross-role retrieval is allowed for the chat assistant so it can explain
    # how a feature works for another role, but the user's own role remains the
    # first preference.
    if role == Audience.MANAGER and audience == Audience.CUSTOMER:
        return 1.6
    if role == Audience.STYLIST and audience == Audience.CUSTOMER:
        return 1.4
    if role == Audience.CUSTOMER and audience in (Audience.MANAGER, Audience.STYLIST):
        return 0.5
    if role == Audience.STYLIST and audience == Audience.MANAGER:
        return 0.9
    if role == Audience.MANAGER and audience == Audience.STYLIST:
        return 0.9

    return 0.7


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
    allow_cross_role: bool = False,
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
    for intent in (
        "درخواست", "بررسی", "تایید", "رد", "لغو", "لینک", "گزارش",
        "رمز", "حذف", "تیکت", "اعلان", "حداقل", "حداکثر",
        "وصل", "قطع", "شارژ",
    ):
        normalized_intent = normalize_persian(intent)
        if normalized_intent in query_norm and normalized_intent in intent_surface:
            score += 4.0

    # "وصل کردن بله" must not rank the disconnect guide just because both
    # documents contain the word "اتصال".
    if "وصل" in query_norm:
        if any(token in intent_surface for token in ("وصل", "متصل")):
            score += 5.0
        if "قطع" in intent_surface or "لغو اتصال" in intent_surface:
            score -= 7.0

    if "قطع" in query_norm:
        if "قطع" in intent_surface or "لغو اتصال" in intent_surface:
            score += 5.0
        if "وصل" in intent_surface and "قطع" not in intent_surface:
            score -= 3.0

    # If the requested service is explicitly NOT in the catalog, this is a
    # service-request intent rather than "add an existing catalog service".
    if "کاتالوگ" in query_norm and any(
        phrase in query_norm
        for phrase in ("نیست", "وجود نداره", "وجود ندارد", "پیدا نمیشه", "پیدا نمی")
    ):
        if "درخواست" in intent_surface:
            score += 8.0
        if "از کاتالوگ" in intent_surface and "درخواست" not in intent_surface:
            score -= 4.0

    # Status/follow-up questions such as "نوبتم چی شد؟" should prefer
    # tracking/status documentation over a generic booking workflow.
    if _has_status_intent(query_norm):
        status_surface = normalize_persian(
            " ".join(
                (
                    article.title,
                    chunk.heading,
                    article.keywords,
                    article.aliases,
                    chunk.content,
                )
            )
        )
        if any(
            normalize_persian(term) in status_surface
            for term in ("پیگیری", "وضعیت")
        ):
            score += 12.0

    # For a stylist, a natural "ثبت مرخصی" question means creating the
    # stylist's leave request. Manager documentation uses very strong lexical
    # phrases such as "ثبت عدم حضور" and "مرخصی آرایشگر", which can
    # otherwise outrank the correct stylist workflow. Keep the rule narrow and
    # disable it when the manager is explicitly the actor of the question.
    if (
        role == Audience.STYLIST
        and _has_leave_intent(query_norm)
        and not mentions_audience_as_actor(query_norm, Audience.MANAGER)
    ):
        if (
            article.audience == Audience.STYLIST
            and "درخواست" in intent_surface
            and any(term in intent_surface for term in ("مرخصی", "عدم حضور"))
        ):
            score += 24.0
        elif (
            article.audience == Audience.MANAGER
            and any(term in intent_surface for term in ("مرخصی", "عدم حضور"))
        ):
            score -= 16.0

    # Exact-role affinity remains a tie-breaker in both modes. Natural
    # first-person questions need a stronger preference for the requester's own
    # role, unless the user explicitly asks how another role performs the task.
    if role and article.audience == role:
        score += 3.0

        if not _mentions_other_role(query_norm, role):
            score += 8.0

            if _has_self_reference(query_norm):
                score += 4.0

    # Cross-role documents stay searchable, but should not outrank the user's
    # own operational docs merely because the query mentions another role as
    # an object (for example, a customer choosing a specialist). A document
    # from another audience receives a strong penalty unless that audience is
    # explicitly the actor the user is asking about.
    if allow_cross_role:
        score += _audience_role_bonus(
            role,
            article.audience,
            allow_cross_role=True,
        )

        if role and article.audience not in {Audience.ALL, role}:
            if mentions_audience_as_actor(query_norm, article.audience):
                score += 6.0
            elif _mentions_other_role(query_norm, role):
                score -= 6.0
            else:
                score -= 12.0

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
    allow_cross_role: bool = False,
) -> list[RetrievalHit]:
    question = str(query or "").strip()
    if not question:
        return []

    use_page_context = is_page_context_question(question)
    try:
        qs = (
            HelpArticleChunk.objects.select_related("article", "article__category")
            .filter(article__is_published=True)
            .filter(_audience_q(role, allow_cross_role=allow_cross_role))
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
                allow_cross_role=allow_cross_role,
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
                audience=chunk.article.audience,
                steps=list(chunk.article.steps or []),
                source_refs=list(chunk.article.source_refs or []),
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
