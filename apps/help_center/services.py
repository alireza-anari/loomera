from __future__ import annotations

import hashlib
import re
import secrets
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.db import OperationalError, ProgrammingError, transaction
from django.urls import reverse
from django.utils import timezone

from .ai import AIProviderError, GroqProvider
from .content import resolve_page_context, search_articles
from .models import HelpConversation, HelpFeedback, HelpMessage


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
IR_MOBILE_RE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")
CARD_RE = re.compile(r"(?<!\d)(?:\d[\s-]?){15}\d(?!\d)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{10,}(?!\d)")
DB_ERRORS = (OperationalError, ProgrammingError)


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

    for attr, role in (
        ("salon_manager_profile", "manager"),
        ("stylist", "stylist"),
        ("customer_profile", "customer"),
    ):
        try:
            if getattr(user, attr, None) is not None:
                return role
        except Exception:
            continue
    return "customer"


def public_role(role: str) -> str:
    return "customer" if role == "guest" else role


def _identity_key(request) -> str:
    if getattr(request.user, "is_authenticated", False):
        return f"user:{request.user.pk}"
    raw_ip = request.META.get("REMOTE_ADDR", "") or "unknown"
    digest = hashlib.sha256(raw_ip.encode("utf-8")).hexdigest()[:20]
    return f"guest:{digest}"


def consume_rate_limit(request) -> tuple[bool, int]:
    authenticated = getattr(request.user, "is_authenticated", False)
    limit = int(
        getattr(
            settings,
            "HELP_CHAT_USER_LIMIT" if authenticated else "HELP_CHAT_GUEST_LIMIT",
            30 if authenticated else 10,
        ) or (30 if authenticated else 10)
    )
    window = int(getattr(settings, "HELP_CHAT_RATE_WINDOW_SECONDS", 3600) or 3600)
    key = f"loomera:help-chat:{_identity_key(request)}"
    try:
        count = int(cache.get(key, 0) or 0)
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
        return True, max(0, limit - count)
    except Exception:
        return True, limit


def consume_handoff_limit(request) -> bool:
    limit = max(int(getattr(settings, "HELP_SUPPORT_HANDOFF_LIMIT", 3) or 3), 1)
    window = max(int(getattr(settings, "HELP_SUPPORT_HANDOFF_WINDOW_SECONDS", 3600) or 3600), 60)
    key = f"loomera:help-handoff:{_identity_key(request)}"
    try:
        count = int(cache.get(key, 0) or 0)
        if count >= limit:
            return False
        if count == 0:
            cache.set(key, 1, timeout=window)
        else:
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=window)
        return True
    except Exception:
        return True


def _session_hash(request) -> str:
    token = request.session.get("loomera_help_session")
    if not token:
        token = secrets.token_urlsafe(24)
        request.session["loomera_help_session"] = token
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def get_owned_conversation(request, public_id) -> Optional[HelpConversation]:
    if not public_id:
        return None
    try:
        conversation = HelpConversation.objects.select_related("user", "support_ticket").filter(
            public_id=public_id
        ).first()
    except DB_ERRORS:
        return None

    if not conversation:
        return None

    session_hash = _session_hash(request)
    if request.user.is_authenticated:
        if conversation.user_id == request.user.pk:
            return conversation
        if conversation.user_id is None and conversation.session_key_hash == session_hash:
            conversation.user = request.user
            conversation.role = detect_user_role(request.user)
            conversation.save(update_fields=["user", "role", "updated_at"])
            return conversation
        return None

    if conversation.user_id is not None:
        return None
    return conversation if conversation.session_key_hash == session_hash else None


def get_or_create_conversation(request, *, conversation_id=None, page_path: str, page_key: str, route_name: str = ""):
    existing = get_owned_conversation(request, conversation_id)
    if existing:
        dirty = []
        if page_key and existing.page_key != page_key:
            existing.page_key = page_key
            dirty.append("page_key")
        if page_path and existing.page_path != page_path:
            existing.page_path = page_path[:500]
            dirty.append("page_path")
        if route_name and existing.page_route_name != route_name:
            existing.page_route_name = route_name[:220]
            dirty.append("page_route_name")
        if dirty:
            dirty.append("updated_at")
            existing.save(update_fields=dirty)
        return existing

    try:
        return HelpConversation.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key_hash=_session_hash(request),
            role=detect_user_role(request.user),
            page_key=page_key[:140],
            page_path=page_path[:500],
            page_route_name=(route_name or "")[:220],
            status=HelpConversation.Status.ACTIVE,
        )
    except DB_ERRORS:
        return None


def context_for_request(path: str, role: str, route_name: str = "") -> dict:
    resolved = resolve_page_context(path, public_role(role), route_name)
    article = resolved.get("article")
    if not article:
        return {
            "page_key": resolved.get("page_key", ""),
            "title": "دستیار لومرا",
            "summary": "درباره استفاده از لومرا از من بپرس.",
            "quick_prompts": [
                "در این صفحه چه کارهایی می‌توانم انجام بدهم؟",
                "اگر به مشکل خوردم از کجا شروع کنم؟",
            ],
            "article_url": reverse("help_center:home"),
        }

    return {
        "page_key": resolved["page_key"],
        "title": article["title"],
        "summary": article["summary"],
        "quick_prompts": resolved.get("quick_prompts", [])[:4],
        "article_url": reverse("help_center:article", kwargs={"slug": article["slug"]}),
    }


def _local_answer(docs: list[dict]) -> str:
    if not docs:
        return (
            "در مستندات فعلی لومرا پاسخ قطعی این مورد را ندارم. "
            "می‌توانی در مرکز راهنما جستجو کنی یا گفتگو را به پشتیبانی بفرستی."
        )
    primary = docs[0]
    lines = [primary["summary"]]
    if primary.get("steps"):
        lines.append("")
        for index, step in enumerate(primary["steps"][:3], 1):
            lines.append(f'{index}. {step["title"]}: {step["body"]}')
    return "\n".join(lines)


def answer_help_question(*, question: str, page_path: str, role: str, history=None, route_name: str = "") -> dict:
    cleaned_question = redact_sensitive(question).strip()
    resolved = resolve_page_context(page_path, public_role(role), route_name)
    page_key = resolved.get("page_key", "")
    docs = search_articles(
        cleaned_question,
        page_key=page_key,
        role=public_role(role),
        limit=4,
    )

    provider = GroqProvider()
    answer = ""
    used_ai = False
    model_name = ""

    if provider.enabled:
        blocks = []
        for idx, doc in enumerate(docs, 1):
            steps = "\n".join(
                f'- {step["title"]}: {step["body"]}'
                for step in doc.get("steps", [])
            )
            tips = "\n".join(f"- {tip}" for tip in doc.get("tips", []))
            blocks.append(
                f"""سند {idx}: {doc["title"]}
خلاصه: {doc["summary"]}
توضیح تکمیلی: {doc.get("body") or "- ندارد"}
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
        if blocks:
            messages.append(
                {"role": "system", "content": "مستندات مرتبط لومرا:\n\n" + "\n\n".join(blocks)}
            )

        for item in (history or [])[-6:]:
            history_role = item.get("role")
            content = redact_sensitive(str(item.get("content", "")))[:600].strip()
            if history_role in {"user", "assistant"} and content:
                messages.append({"role": history_role, "content": content})

        messages.append({"role": "user", "content": cleaned_question[:1200]})
        try:
            answer = provider.complete(messages)
            used_ai = True
            model_name = provider.model
        except AIProviderError:
            answer = _local_answer(docs)
    else:
        answer = _local_answer(docs)

    sources = [
        {
            "key": doc["key"],
            "title": doc["title"],
            "url": reverse("help_center:article", kwargs={"slug": doc["slug"]}),
        }
        for doc in docs[:3]
    ]
    return {
        "answer": answer,
        "sources": sources,
        "page_key": page_key,
        "ai": used_ai,
        "model_name": model_name,
        "redacted_question": cleaned_question,
    }


def persist_exchange(conversation, *, question, answer, used_ai, model_name, sources):
    if not conversation:
        return None
    try:
        with transaction.atomic():
            HelpMessage.objects.create(
                conversation=conversation,
                role=HelpMessage.Role.USER,
                content=redact_sensitive(question),
                used_ai=False,
            )
            assistant = HelpMessage.objects.create(
                conversation=conversation,
                role=HelpMessage.Role.ASSISTANT,
                content=answer,
                used_ai=used_ai,
                model_name=model_name,
                sources=sources,
            )
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=["last_message_at", "updated_at"])
            return assistant
    except DB_ERRORS:
        return None


def save_feedback(request, *, message_public_id, rating: str, note: str = "") -> bool:
    if rating not in {HelpFeedback.Rating.HELPFUL, HelpFeedback.Rating.NOT_HELPFUL}:
        return False
    try:
        message = HelpMessage.objects.select_related("conversation").filter(
            public_id=message_public_id,
            role=HelpMessage.Role.ASSISTANT,
        ).first()
    except DB_ERRORS:
        return False
    if not message:
        return False

    owned = get_owned_conversation(request, message.conversation.public_id)
    if not owned or owned.pk != message.conversation_id:
        return False

    HelpFeedback.objects.update_or_create(
        message=message,
        defaults={
            "user": request.user if request.user.is_authenticated else None,
            "rating": rating,
            "note": redact_sensitive(note)[:500],
        },
    )
    return True


def transcript_for_support(conversation: HelpConversation, limit: int = 12) -> str:
    messages = list(conversation.messages.order_by("-created_at", "-id")[:limit])
    messages.reverse()
    lines = [
        "این درخواست از دستیار راهنمای لومرا ایجاد شده است.",
        f"صفحه: {conversation.page_path or '-'}",
        f"کلید راهنما: {conversation.page_key or '-'}",
        f"Route: {conversation.page_route_name or '-'}",
        "",
        "گفتگوی اخیر:",
    ]
    for item in messages:
        label = "کاربر" if item.role == HelpMessage.Role.USER else "دستیار"
        lines.append(f"{label}: {redact_sensitive(item.content)[:1500]}")
    return "\n".join(lines)[:12000]
