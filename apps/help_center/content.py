from __future__ import annotations

import re

from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Q
from django.urls import NoReverseMatch, reverse

from .models import ArticleType, Audience, HelpArticle, HelpCategory, HelpLegalDocument, HelpPageContext
from .retrieval import allowed_audiences, retrieve_help_chunks, unique_article_hits


DB_ERRORS = (OperationalError, ProgrammingError)


def _role_value(role: str) -> str:
    value = (role or "").strip().lower()
    return value if value in {"customer", "manager", "stylist"} else "all"


def _audience_q(role: str):
    role = _role_value(role)
    if role == "all":
        return Q(audience=Audience.ALL)
    return Q(audience=Audience.ALL) | Q(audience=role)


def _article_action_links(items) -> list[dict]:
    links = []
    seen_urls = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        route_name = str(item.get("route_name") or item.get("url_name") or "").strip()
        if not route_name:
            continue
        try:
            url = reverse(route_name)
        except NoReverseMatch:
            continue
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        label = str(item.get("link_label") or item.get("title") or "باز کردن").strip()
        links.append({"label": label[:100], "url": url})
    return links


def article_to_dict(article: HelpArticle) -> dict:
    raw_steps = article.steps or []
    steps = []
    for item in raw_steps:
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
        "category_title": article.category.title,
        "article_type": article.article_type,
        "article_type_label": article.get_article_type_display(),
        "summary": article.summary,
        "body": article.body,
        "steps": steps,
        "action_links": _article_action_links(raw_steps),
        "tips": [str(item) for item in (article.tips or []) if str(item).strip()],
        "keywords": article.keywords,
        "aliases": article.aliases,
        "is_featured": article.is_featured,
        "updated_at": article.updated_at,
        "source": "database",
    }



def get_categories(role: str) -> list[dict]:
    role_value = _role_value(role)
    try:
        rows = list(
            HelpCategory.objects.filter(is_published=True)
            .filter(_audience_q(role_value))
            .order_by("sort_order", "title")
        )
        counts = {
            row["category_id"]: row["total"]
            for row in (
                HelpArticle.objects.filter(
                    is_published=True,
                    audience__in=allowed_audiences(role_value),
                    category_id__in=[item.id for item in rows],
                )
                .values("category_id")
                .annotate(total=Count("id"))
            )
        }
    except DB_ERRORS:
        return []

    return [
        {
            "slug": row.slug,
            "title": row.title,
            "description": row.description,
            "icon": row.icon,
            "audience": row.audience,
            "article_count": counts.get(row.id, 0),
        }
        for row in rows
        if counts.get(row.id, 0) > 0
    ]


def get_category(slug: str, *, role: str = "") -> dict | None:
    role_value = _role_value(role)
    try:
        row = (
            HelpCategory.objects.filter(slug=slug, is_published=True)
            .filter(_audience_q(role_value))
            .first()
        )
        if not row:
            return None
        count = HelpArticle.objects.filter(
            category=row,
            is_published=True,
            audience__in=allowed_audiences(role_value),
        ).count()
        return {
            "slug": row.slug,
            "title": row.title,
            "description": row.description,
            "icon": row.icon,
            "audience": row.audience,
            "article_count": count,
        }
    except DB_ERRORS:
        return None


def get_article_type_options() -> list[dict]:
    return [{"value": value, "label": label} for value, label in ArticleType.choices]


def list_articles(*, role: str = "", category_slug: str = "", article_type: str = "", limit: int = 100) -> list[dict]:
    try:
        qs = HelpArticle.objects.select_related("category").filter(
            is_published=True,
            audience__in=allowed_audiences(_role_value(role)),
        )
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        if article_type in ArticleType.values:
            qs = qs.filter(article_type=article_type)
        qs = qs.order_by("-is_featured", "sort_order", "title")[:limit]
        return [article_to_dict(row) for row in qs]
    except DB_ERRORS:
        return []


def get_troubleshooting_articles(role: str, limit: int = 6) -> list[dict]:
    return list_articles(role=role, article_type=ArticleType.TROUBLESHOOTING, limit=limit)


def get_recent_articles(role: str, limit: int = 6) -> list[dict]:
    try:
        qs = HelpArticle.objects.select_related("category").filter(
            is_published=True,
            audience__in=allowed_audiences(_role_value(role)),
        ).order_by("-updated_at", "-id")[:limit]
        return [article_to_dict(row) for row in qs]
    except DB_ERRORS:
        return []


def get_featured_articles(role: str, limit: int = 8) -> list[dict]:
    try:
        qs = (
            HelpArticle.objects.select_related("category")
            .filter(is_published=True)
            .filter(_audience_q(role))
            .order_by("-is_featured", "category__sort_order", "sort_order", "title")[:limit]
        )
        return [article_to_dict(row) for row in qs]
    except DB_ERRORS:
        return []


def get_article_by_slug(slug: str, *, role: str = "") -> dict | None:
    try:
        row = (
            HelpArticle.objects.select_related("category")
            .filter(
                slug=slug,
                is_published=True,
                audience__in=allowed_audiences(_role_value(role)),
            )
            .first()
        )
        return article_to_dict(row) if row else None
    except DB_ERRORS:
        return None


def get_article_by_key(key: str) -> dict | None:
    if not key:
        return None
    try:
        row = (
            HelpArticle.objects.select_related("category")
            .filter(key=key, is_published=True)
            .first()
        )
        return article_to_dict(row) if row else None
    except DB_ERRORS:
        return None



def search_articles(
    query: str,
    *,
    role: str = "",
    page_key: str = "",
    category_slug: str = "",
    article_type: str = "",
    limit: int = 10,
) -> list[dict]:
    if not str(query or "").strip():
        return list_articles(
            role=role,
            category_slug=category_slug,
            article_type=article_type,
            limit=limit,
        )

    hits = unique_article_hits(
        retrieve_help_chunks(
            query,
            role=_role_value(role),
            page_key=page_key,
            limit=max(limit * 6, 30),
        ),
        limit=max(limit * 4, 20),
    )
    if not hits:
        return []

    article_ids = [hit.article_id for hit in hits]
    try:
        rows = HelpArticle.objects.select_related("category").in_bulk(article_ids)
    except DB_ERRORS:
        return []

    results = []
    for hit in hits:
        row = rows.get(hit.article_id)
        if not row:
            continue
        if category_slug and row.category.slug != category_slug:
            continue
        if article_type in ArticleType.values and row.article_type != article_type:
            continue
        results.append(article_to_dict(row))
        if len(results) >= limit:
            break
    return results


def resolve_page_context(path: str, role: str, route_name: str = "") -> dict:
    clean_path = (path or "/").split("?", 1)[0]
    role_value = _role_value(role)
    route_name = (route_name or "").strip()

    if route_name:
        try:
            context = (
                HelpPageContext.objects.select_related("article", "article__category")
                .filter(
                    is_active=True,
                    article__is_published=True,
                    route_name=route_name,
                )
                .filter(Q(role=Audience.ALL) | Q(role=role_value))
                .order_by("-priority", "id")
                .first()
            )
            if context:
                article = article_to_dict(context.article)
                prompts = [
                    str(item).strip()
                    for item in (context.quick_prompts or [])
                    if str(item).strip()
                ]
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
            .exclude(path_pattern="")
            .order_by("-priority", "id")
        )
        for context in contexts:
            try:
                if re.search(context.path_pattern, clean_path):
                    article = article_to_dict(context.article)
                    prompts = [
                        str(item).strip()
                        for item in (context.quick_prompts or [])
                        if str(item).strip()
                    ]
                    return {
                        "page_key": context.page_key or article["key"],
                        "article": article,
                        "quick_prompts": prompts[:4],
                        "route_name": route_name,
                    }
            except re.error:
                continue
    except DB_ERRORS:
        pass

    # Important: unknown pages stay unknown. We do not force a manager/customer
    # dashboard article as a fallback because that poisoned unrelated questions.
    return {
        "page_key": "",
        "article": None,
        "quick_prompts": [],
        "route_name": route_name,
    }


def related_articles(article: dict, limit: int = 4) -> list[dict]:
    role = article.get("role", "all")
    category = article.get("category", "")
    try:
        qs = (
            HelpArticle.objects.select_related("category")
            .filter(is_published=True)
            .exclude(key=article.get("key"))
            .filter(_audience_q(role))
            .filter(category__slug=category)
            .order_by("-is_featured", "sort_order", "title")[:limit]
        )
        return [article_to_dict(row) for row in qs]
    except DB_ERRORS:
        return []


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
        {
            "slug": "privacy",
            "title": "حریم خصوصی",
            "version": "legacy",
            "summary": "",
            "legacy_url_name": "accounts:privacy_policy",
        },
        {
            "slug": "terms",
            "title": "شرایط استفاده",
            "version": "legacy",
            "summary": "",
            "legacy_url_name": "accounts:terms_of_use",
        },
        {
            "slug": "messaging-privacy",
            "title": "حریم خصوصی پیام‌رسان‌ها",
            "version": "legacy",
            "summary": "",
            "legacy_url_name": "messaging:privacy",
        },
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
