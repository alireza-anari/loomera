from __future__ import annotations

import re

from django.db import OperationalError, ProgrammingError
from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from . import knowledge
from .models import Audience, HelpArticle, HelpCategory, HelpLegalDocument, HelpPageContext


DB_ERRORS = (OperationalError, ProgrammingError)


def _role_value(role: str) -> str:
    value = (role or "").strip().lower()
    return value if value in {"customer", "manager", "stylist"} else "all"


def _audience_q(role: str):
    role = _role_value(role)
    if role == "all":
        return Q(audience=Audience.ALL)
    return Q(audience=Audience.ALL) | Q(audience=role)


def _fallback_article_dict(article):
    return {
        "key": article.key,
        "slug": article.slug,
        "title": article.title,
        "role": article.role,
        "category": article.category,
        "summary": article.summary,
        "body": "",
        "steps": [{"title": title, "body": body} for title, body in article.steps],
        "tips": list(article.tips),
        "keywords": " ".join(article.keywords),
        "updated_at": None,
        "source": "fallback",
    }


def article_to_dict(article: HelpArticle) -> dict:
    steps = []
    for item in article.steps or []:
        if isinstance(item, dict):
            steps.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "body": str(item.get("body") or "").strip(),
                }
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            steps.append({"title": str(item[0]), "body": str(item[1])})

    return {
        "key": article.key,
        "slug": article.slug,
        "title": article.title,
        "role": article.audience,
        "category": article.category.slug,
        "summary": article.summary,
        "body": article.body,
        "steps": steps,
        "tips": [str(item) for item in (article.tips or []) if str(item).strip()],
        "keywords": article.keywords,
        "updated_at": article.updated_at,
        "source": "database",
    }


def get_categories(role: str) -> list[dict]:
    try:
        rows = list(
            HelpCategory.objects.filter(is_published=True)
            .filter(_audience_q(role))
            .order_by("sort_order", "title")
        )
        if rows:
            return [
                {
                    "slug": row.slug,
                    "title": row.title,
                    "description": row.description,
                    "icon": row.icon,
                    "audience": row.audience,
                }
                for row in rows
            ]
    except DB_ERRORS:
        pass

    return [
        {
            "slug": slug,
            "title": data["title"],
            "description": data["description"],
            "icon": data["icon"],
            "audience": "all",
        }
        for slug, data in knowledge.CATEGORIES.items()
    ]


def get_featured_articles(role: str, limit: int = 8) -> list[dict]:
    try:
        rows = list(
            HelpArticle.objects.select_related("category")
            .filter(is_published=True)
            .filter(_audience_q(role))
            .order_by("category__sort_order", "sort_order", "title")[:limit]
        )
        if rows:
            return [article_to_dict(row) for row in rows]
    except DB_ERRORS:
        pass

    role_value = _role_value(role)
    items = [item for item in knowledge.ARTICLES if item.role in {"all", role_value}][:limit]
    return [_fallback_article_dict(item) for item in items]


def get_article_by_slug(slug: str) -> dict | None:
    try:
        row = (
            HelpArticle.objects.select_related("category")
            .filter(slug=slug, is_published=True)
            .first()
        )
        if row:
            return article_to_dict(row)
    except DB_ERRORS:
        pass

    fallback = knowledge.ARTICLE_BY_SLUG.get(slug)
    return _fallback_article_dict(fallback) if fallback else None


def get_article_by_key(key: str) -> dict | None:
    try:
        row = (
            HelpArticle.objects.select_related("category")
            .filter(key=key, is_published=True)
            .first()
        )
        if row:
            return article_to_dict(row)
    except DB_ERRORS:
        pass

    fallback = knowledge.ARTICLE_BY_KEY.get(key)
    return _fallback_article_dict(fallback) if fallback else None


def _normalize(value: str) -> str:
    value = (value or "").lower().replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return " ".join(re.sub(r"[^\w\u0600-\u06ff]+", " ", value).split())


def _tokens(value: str) -> set[str]:
    stop = {
        "را", "به", "از", "در", "با", "برای", "که", "این", "آن", "من",
        "چطور", "چگونه", "یک", "و", "یا", "روی", "میخوام", "میخواهم", "می", "کنم",
    }
    return {token for token in _normalize(value).split() if len(token) > 1 and token not in stop}


def _score(query: str, article: dict, page_key: str = "") -> float:
    q = _normalize(query)
    q_tokens = _tokens(query)
    text = _normalize(
        " ".join(
            [
                article.get("title", ""),
                article.get("summary", ""),
                article.get("body", ""),
                article.get("keywords", ""),
                " ".join(
                    f'{step.get("title","")} {step.get("body","")}'
                    for step in article.get("steps", [])
                ),
                " ".join(article.get("tips", [])),
            ]
        )
    )
    text_tokens = _tokens(text)

    score = 0.0
    if article.get("key") == page_key:
        score += 8.0
    if q and q in text:
        score += 8.0
    score += len(q_tokens & text_tokens) * 2.4

    title = _normalize(article.get("title", ""))
    keywords = _normalize(article.get("keywords", ""))
    for token in q_tokens:
        if token in title:
            score += 1.5
        if token in keywords:
            score += 1.2
    return score


def search_articles(query: str, *, role: str = "", page_key: str = "", limit: int = 10) -> list[dict]:
    candidates = []
    try:
        qs = (
            HelpArticle.objects.select_related("category")
            .filter(is_published=True)
            .filter(_audience_q(role))
        )
        candidates = [article_to_dict(row) for row in qs[:500]]
    except DB_ERRORS:
        candidates = []

    if not candidates:
        role_value = _role_value(role)
        candidates = [
            _fallback_article_dict(item)
            for item in knowledge.ARTICLES
            if item.role in {"all", role_value}
        ]

    ranked = sorted(
        ((_score(query, item, page_key), item) for item in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    useful = [item for score, item in ranked if score > 0]
    if not useful and page_key:
        current = get_article_by_key(page_key)
        if current:
            useful = [current]
    return useful[:limit]


def resolve_page_context(path: str, role: str, route_name: str = "") -> dict:
    clean_path = (path or "/").split("?", 1)[0]
    role_value = _role_value(role)
    route_name = (route_name or "").strip()

    if route_name:
        try:
            context = (
                HelpPageContext.objects.select_related("article", "article__category")
                .filter(is_active=True, article__is_published=True, route_name=route_name)
                .filter(Q(role=Audience.ALL) | Q(role=role_value))
                .order_by("-priority", "id")
                .first()
            )
            if context:
                article = article_to_dict(context.article)
                prompts = [str(item).strip() for item in (context.quick_prompts or []) if str(item).strip()]
                if not prompts:
                    prompts = [step["title"] for step in article["steps"][:3]]
                return {
                    "page_key": context.page_key or article["key"],
                    "article": article,
                    "quick_prompts": prompts[:4],
                    "route_name": route_name,
                }
        except DB_ERRORS:
            pass

    try:
        contexts = (
            HelpPageContext.objects.select_related("article", "article__category")
            .filter(is_active=True, article__is_published=True)
            .filter(Q(role=Audience.ALL) | Q(role=role_value))
            .order_by("-priority", "id")
        )
        for context in contexts:
            try:
                if context.path_pattern and re.search(context.path_pattern, clean_path):
                    article = article_to_dict(context.article)
                    prompts = [
                        str(item).strip()
                        for item in (context.quick_prompts or [])
                        if str(item).strip()
                    ]
                    if not prompts:
                        prompts = [step["title"] for step in article["steps"][:3]]
                    return {
                        "page_key": context.page_key or article["key"],
                        "article": article,
                        "quick_prompts": prompts[:4],
                    }
            except re.error:
                continue
    except DB_ERRORS:
        pass

    key = knowledge.resolve_page_key(clean_path, role_value)
    article = get_article_by_key(key)
    prompts = [step["title"] for step in (article or {}).get("steps", [])[:3]]
    return {"page_key": key, "article": article, "quick_prompts": prompts, "route_name": route_name}


def related_articles(article: dict, limit: int = 4) -> list[dict]:
    role = article.get("role", "all")
    category = article.get("category", "")
    try:
        qs = (
            HelpArticle.objects.select_related("category")
            .filter(is_published=True)
            .exclude(key=article.get("key"))
            .filter(Q(category__slug=category) | Q(audience=role))
            .order_by("category__sort_order", "sort_order", "title")[:limit]
        )
        rows = [article_to_dict(row) for row in qs]
        if rows:
            return rows
    except DB_ERRORS:
        pass

    items = []
    for fallback in knowledge.ARTICLES:
        if fallback.key == article.get("key"):
            continue
        if fallback.category == category or fallback.role == role:
            items.append(_fallback_article_dict(fallback))
        if len(items) >= limit:
            break
    return items


def get_legal_documents() -> list[dict]:
    try:
        docs = list(
            HelpLegalDocument.objects.filter(
                status=HelpLegalDocument.Status.PUBLISHED,
                is_current=True,
            ).order_by("title")
        )
        if docs:
            return [
                {
                    "slug": doc.slug,
                    "title": doc.title,
                    "version": doc.version,
                    "summary": doc.summary,
                    "effective_at": doc.effective_at,
                    "updated_at": doc.updated_at,
                    "legacy_url_name": doc.legacy_url_name,
                }
                for doc in docs
            ]
    except DB_ERRORS:
        pass

    return [
        {"slug": "privacy", "title": "حریم خصوصی", "version": "legacy", "summary": "", "legacy_url_name": "accounts:privacy_policy"},
        {"slug": "terms", "title": "شرایط استفاده", "version": "legacy", "summary": "", "legacy_url_name": "accounts:terms_of_use"},
        {"slug": "messaging-privacy", "title": "حریم خصوصی پیام‌رسان‌ها", "version": "legacy", "summary": "", "legacy_url_name": "messaging:privacy"},
    ]


def get_legal_document(slug: str):
    try:
        return (
            HelpLegalDocument.objects.filter(
                slug=slug,
                status=HelpLegalDocument.Status.PUBLISHED,
                is_current=True,
            )
            .order_by("-published_at", "-id")
            .first()
        )
    except DB_ERRORS:
        return None


def legacy_legal_url(doc) -> str:
    if not doc or not getattr(doc, "legacy_url_name", ""):
        return ""
    try:
        return reverse(doc.legacy_url_name)
    except NoReverseMatch:
        return ""
