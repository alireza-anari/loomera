from __future__ import annotations

import json

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .knowledge import ARTICLE_BY_SLUG, ARTICLES, CATEGORIES, search_articles
from .services import (
    answer_help_question,
    consume_rate_limit,
    context_for_request,
    detect_user_role,
)


def _role_for_page(request) -> str:
    role = detect_user_role(request.user)
    return "customer" if role == "guest" else role


def help_home(request):
    role = _role_for_page(request)
    featured = [a for a in ARTICLES if a.role in {"all", role}][:8]
    return render(
        request,
        "help_center/home.html",
        {
            "categories": CATEGORIES,
            "featured_articles": featured,
            "help_role": role,
        },
    )


def help_search(request):
    query = (request.GET.get("q") or "").strip()[:200]
    role = _role_for_page(request)
    results = search_articles(query, role=role, limit=20) if query else []
    return render(
        request,
        "help_center/search.html",
        {
            "query": query,
            "results": results,
        },
    )


def help_article(request, slug):
    article = ARTICLE_BY_SLUG.get(slug)
    if not article:
        raise Http404
    related = [
        a
        for a in ARTICLES
        if a.slug != article.slug
        and (a.category == article.category or a.role == article.role)
    ][:4]
    return render(
        request,
        "help_center/article.html",
        {
            "article": article,
            "related_articles": related,
        },
    )


@require_GET
def context_api(request):
    path = (request.GET.get("path") or request.path or "/")[:500]
    role = _role_for_page(request)
    payload = context_for_request(path, role)
    payload["role"] = role
    return JsonResponse(payload)


@require_POST
def chat_api(request):
    if len(request.body or b"") > 12 * 1024:
        return JsonResponse({"error": "پیام بیش از حد بزرگ است."}, status=413)

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    question = str(payload.get("message") or "").strip()
    if not question:
        return JsonResponse({"error": "پیام خالی است."}, status=400)
    if len(question) > 1200:
        return JsonResponse({"error": "پیام را کوتاه‌تر بنویس."}, status=400)

    allowed, remaining = consume_rate_limit(request)
    if not allowed:
        return JsonResponse(
            {
                "error": "تعداد پیام‌های این بازه به حد مجاز رسیده است. کمی بعد دوباره امتحان کن.",
                "rate_limited": True,
            },
            status=429,
        )

    role = _role_for_page(request)
    path = str(payload.get("path") or "/")[:500]
    raw_history = payload.get("history") or []
    history = raw_history if isinstance(raw_history, list) else []

    result = answer_help_question(
        question=question,
        page_path=path,
        role=role,
        history=history,
    )
    result["remaining"] = remaining
    return JsonResponse(result)
