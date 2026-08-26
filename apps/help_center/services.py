from __future__ import annotations

import hashlib
import os
import re

from django.core.cache import cache
from django.urls import reverse

from .ai import AIProviderError, GroqProvider
from .knowledge import ARTICLE_BY_KEY, HelpArticle, resolve_page_key, search_articles


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
IR_MOBILE_RE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")
CARD_RE = re.compile(r"(?<!\d)(?:\d[\s-]?){15}\d(?!\d)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{10,}(?!\d)")


def redact_sensitive(text: str) -> str:
    value = str(text or "")
    value = EMAIL_RE.sub("[ایمیل حذف شد]", value)
    value = IR_MOBILE_RE.sub("[شماره موبایل حذف شد]", value)
    value = CARD_RE.sub("[شماره کارت حذف شد]", value)
    value = LONG_NUMBER_RE.sub("[عدد حساس حذف شد]", value)
    return value


def detect_user_role(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return "guest"

    # Related objects are intentionally checked without exposing any personal data.
    for attr, role in (
        ("salon_manager_profile", "manager"),
        ("stylist", "stylist"),
        ("customer_profile", "customer"),
    ):
        try:
            if getattr(user, attr, None) is not None:
                return role
        except Exception:
            pass
    return "customer"


def _identity_key(request) -> str:
    if getattr(request.user, "is_authenticated", False):
        return f"user:{request.user.pk}"
    raw_ip = request.META.get("REMOTE_ADDR", "") or "unknown"
    digest = hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()[:20]
    return f"guest:{digest}"


def consume_rate_limit(request) -> tuple[bool, int]:
    authenticated = getattr(request.user, "is_authenticated", False)
    limit = int(
        os.getenv(
            "HELP_CHAT_USER_LIMIT" if authenticated else "HELP_CHAT_GUEST_LIMIT",
            "30" if authenticated else "10",
        )
    )
    window = int(os.getenv("HELP_CHAT_RATE_WINDOW_SECONDS", "3600"))
    key = f"loomera:help-chat:{_identity_key(request)}"
    try:
        count = cache.get(key, 0)
        if count >= limit:
            return False, 0
        if count == 0:
            cache.set(key, 1, timeout=window)
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=window)
                count = 1
        return True, max(0, limit - int(count))
    except Exception:
        # Rate limiting should not break the help center if cache is temporarily unavailable.
        return True, limit


def article_public_dict(article: HelpArticle) -> dict:
    return {
        "key": article.key,
        "title": article.title,
        "summary": article.summary,
        "url": reverse("help_center:article", kwargs={"slug": article.slug}),
        "steps": [{"title": t, "body": b} for t, b in article.steps],
        "tips": list(article.tips),
    }


def context_for_request(path: str, role: str) -> dict:
    key = resolve_page_key(path, role)
    article = ARTICLE_BY_KEY.get(key)
    if not article:
        return {
            "page_key": key,
            "title": "دستیار لومرا",
            "summary": "درباره استفاده از لومرا از من بپرس.",
            "quick_prompts": [
                "در این صفحه چه کارهایی می‌توانم انجام بدهم؟",
                "اگر به مشکل خوردم از کجا شروع کنم؟",
            ],
            "article_url": reverse("help_center:home"),
        }

    quick = [title for title, _ in article.steps[:3]]
    return {
        "page_key": key,
        "title": article.title,
        "summary": article.summary,
        "quick_prompts": quick,
        "article_url": reverse("help_center:article", kwargs={"slug": article.slug}),
    }


def _local_answer(question: str, docs: list[HelpArticle]) -> str:
    if not docs:
        return (
            "برای این سؤال هنوز راهنمای مستند کافی در مرکز راهنمای لومرا ندارم. "
            "می‌توانی از «مرکز راهنما» جستجو کنی یا درخواست پشتیبانی بفرستی."
        )

    primary = docs[0]
    lines = [primary.summary]
    if primary.steps:
        lines.append("")
        for index, (title, body) in enumerate(primary.steps[:3], 1):
            lines.append(f"{index}. {title}: {body}")
    return "\n".join(lines)


def answer_help_question(
    *,
    question: str,
    page_path: str,
    role: str,
    history: list[dict] | None = None,
) -> dict:
    cleaned_question = redact_sensitive(question).strip()
    page_key = resolve_page_key(page_path, role)
    docs = search_articles(
        cleaned_question,
        page_key=page_key,
        role=role,
        limit=4,
    )

    provider = GroqProvider()
    answer = ""
    used_ai = False

    if provider.enabled:
        doc_blocks = []
        for idx, doc in enumerate(docs, 1):
            steps = "\n".join(f"- {title}: {body}" for title, body in doc.steps)
            tips = "\n".join(f"- {tip}" for tip in doc.tips)
            doc_blocks.append(
                f"""سند {idx}: {doc.title}
خلاصه: {doc.summary}
مراحل:
{steps or "- ندارد"}
نکته‌ها:
{tips or "- ندارد"}"""
            )

        system = """تو «دستیار راهنمای لومرا» هستی.
فقط درباره استفاده از محصول Loomera و فقط بر اساس مستندات ارائه‌شده پاسخ بده.
اگر مستندات برای پاسخ قطعی کافی نیستند، صریح بگو «در مستندات فعلی لومرا پاسخ قطعی این مورد را ندارم» و کاربر را به مرکز راهنما یا پشتیبانی هدایت کن.
هیچ دکمه، مسیر، قابلیت، قیمت، قانون یا رفتار محصولی را که در متن مستندات نیست اختراع نکن.
پاسخ‌ها فارسی، کوتاه، کاربردی و مرحله‌ای باشند.
هرگز اطلاعات شخصی، شماره تماس، ایمیل، شماره کارت یا داده حساس کاربر را تکرار نکن.
اگر سؤال خارج از استفاده از لومراست، کوتاه بگو که فقط درباره لومرا راهنمایی می‌کنی."""

        messages = [{"role": "system", "content": system}]
        if doc_blocks:
            messages.append(
                {
                    "role": "system",
                    "content": "مستندات مرتبط لومرا:\n\n" + "\n\n".join(doc_blocks),
                }
            )

        for item in (history or [])[-6:]:
            role_name = item.get("role")
            content = redact_sensitive(str(item.get("content", "")))[:600].strip()
            if role_name in {"user", "assistant"} and content:
                messages.append({"role": role_name, "content": content})

        messages.append({"role": "user", "content": cleaned_question[:1200]})
        try:
            answer = provider.complete(messages)
            used_ai = True
        except AIProviderError:
            answer = _local_answer(cleaned_question, docs)
    else:
        answer = _local_answer(cleaned_question, docs)

    sources = [
        {
            "title": doc.title,
            "url": reverse("help_center:article", kwargs={"slug": doc.slug}),
        }
        for doc in docs[:3]
    ]
    return {
        "answer": answer,
        "sources": sources,
        "page_key": page_key,
        "ai": used_ai,
    }
