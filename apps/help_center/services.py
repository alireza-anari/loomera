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

from .ai import AIProviderError, get_ai_provider
from .content import resolve_page_context
from .models import HelpConversation, HelpFeedback, HelpMessage
from .retrieval import retrieve_help_chunks


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

    role_prompts = {
        "manager": [
            "چطور متخصص را برای رزرو آماده کنم؟",
            "چرا متخصص در رزرو نمایش داده نمی‌شود؟",
            "چطور برنامه کاری تیم را تنظیم کنم؟",
        ],
        "stylist": [
            "چطور برنامه کاری ثبت کنم؟",
            "چطور درخواست مرخصی بدهم؟",
            "نوبت‌های من را از کجا ببینم؟",
        ],
        "customer": [
            "چطور نوبت رزرو کنم؟",
            "چطور زمان نوبتم را تغییر بدهم؟",
            "پرداخت یا کیف پول چطور کار می‌کند؟",
        ],
        "guest": [
            "چطور در لومرا رزرو کنم؟",
            "چطور مجموعه و متخصص مناسب پیدا کنم؟",
        ],
    }

    prompts = list(resolved.get("quick_prompts") or [])
    if not prompts:
        prompts = role_prompts.get(role, role_prompts["guest"])

    return {
        "page_key": resolved.get("page_key", ""),
        "title": "آنلاین · پاسخ براساس راهنمای لومرا",
        "summary": (
            "هر سؤالی درباره کار با لومرا داری بپرس. جواب رو از راهنماهای رسمی پیدا می‌کنم "
            "و منبعش رو هم کنارش می‌ذارم."
        ),
        "quick_prompts": prompts[:4],
        "article_url": (
            reverse("help_center:article", kwargs={"slug": article["slug"]})
            if article
            else reverse("help_center:home")
        ),
        "context_article_title": article.get("title", "") if article else "",
    }



def _unique_hits(hits):
    result = []
    seen = set()
    for hit in hits:
        if hit.article_id in seen:
            continue
        seen.add(hit.article_id)
        result.append(hit)
    return result


def _evidence_groups(hits, *, max_sources: int = 4, max_chunks_per_source: int = 2):
    """Group multiple relevant chunks under one stable article/source number."""
    groups = []
    by_article = {}
    for hit in hits:
        group = by_article.get(hit.article_id)
        if group is None:
            if len(groups) >= max_sources:
                continue
            group = {
                "article_id": hit.article_id,
                "article_key": hit.article_key,
                "slug": hit.slug,
                "title": hit.title,
                "article_type": hit.article_type,
                "score": hit.score,
                "chunks": [],
            }
            by_article[hit.article_id] = group
            groups.append(group)
        if len(group["chunks"]) < max_chunks_per_source:
            group["chunks"].append(
                {
                    "heading": hit.heading,
                    "content": hit.content,
                    "score": hit.score,
                }
            )
    return groups


def _local_answer(groups, *, provider_unavailable: bool = False) -> str:
    if not groups:
        return (
            "برای این مورد توی راهنماهای فعلی لومرا جواب مطمئنی پیدا نکردم. "
            "اگر موضوع به حساب، رزرو، پرداخت یا کار مجموعه مربوطه، "
            "می‌تونی همین گفتگو رو برای پشتیبانی بفرستی تا دقیق‌تر بررسی بشه."
        )

    primary = groups[0]
    prefix = (
        "الان بخش هوشمند پاسخ‌گویی موقتاً در دسترس نیست، "
        "ولی این راهنمای مرتبط رو برات پیدا کردم:\n\n"
        if provider_unavailable
        else ""
    )
    chunks = primary.get("chunks") or []
    text = "\n\n".join(
        item["content"].strip()
        for item in chunks
        if item.get("content", "").strip()
    )
    if len(text) > 1000:
        text = text[:1000].rstrip() + "…"
    return f"{prefix}{text}\n\nمنبع: {primary['title']}"


def _source_payload(groups) -> list[dict]:
    sources = []
    for group in groups[:4]:
        headings = [
            item.get("heading", "").strip()
            for item in group.get("chunks", [])
            if item.get("heading", "").strip()
        ]
        sources.append(
            {
                "key": group["article_key"],
                "title": group["title"],
                "heading": " · ".join(dict.fromkeys(headings))[:240],
                "url": reverse("help_center:article", kwargs={"slug": group["slug"]}),
            }
        )
    return sources


_CITATION_RE = re.compile(r"\[(\d{1,2})\]")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _clean_ai_answer(answer: str, source_count: int) -> str:
    """Keep the answer UI-safe and remove citation numbers that do not exist."""
    value = str(answer or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = _BOLD_RE.sub(r"\1", value)

    def replace_citation(match):
        number = int(match.group(1))
        return match.group(0) if 1 <= number <= source_count else ""

    value = _CITATION_RE.sub(replace_citation, value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def answer_help_question(*, question: str, page_path: str, role: str, history=None, route_name: str = "") -> dict:
    cleaned_question = redact_sensitive(question).strip()
    resolved = resolve_page_context(page_path, public_role(role), route_name)
    page_key = resolved.get("page_key", "")

    hits = retrieve_help_chunks(
        cleaned_question,
        role=public_role(role),
        page_key=page_key,
        limit=8,
    )
    evidence = _evidence_groups(hits, max_sources=4, max_chunks_per_source=2)
    sources = _source_payload(evidence)

    # No relevant documentation means no model call. The model is not allowed to
    # fill product gaps from general knowledge.
    if not evidence:
        return {
            "answer": _local_answer([]),
            "sources": [],
            "page_key": page_key,
            "ai": False,
            "model_name": "",
            "provider": "",
            "redacted_question": cleaned_question,
        }

    provider = get_ai_provider()
    answer = ""
    used_ai = False
    model_name = ""

    blocks = []
    for idx, group in enumerate(evidence, 1):
        sections = []
        for chunk in group["chunks"]:
            sections.append(
                f"بخش: {chunk['heading'] or 'راهنما'}\n"
                f"{chunk['content']}"
            )
        blocks.append(
            f"[منبع {idx}]\n"
            f"عنوان مقاله: {group['title']}\n"
            f"نوع مقاله: {group['article_type']}\n"
            + "\n\n".join(sections)
        )

    system = """تو «دستیار پشتیبانی لومرا» هستی. مثل یک عضو باتجربه و خوش‌برخورد تیم پشتیبانی جواب بده، اما هرگز وانمود نکن انسان هستی یا به حساب کاربر دسترسی زنده داری. پاسخ محصولی تو باید کاملاً grounded در منابع رسمی همین درخواست باشد.

قواعد غیرقابل‌چشم‌پوشی:
1) درباره قابلیت، دکمه، نام صفحه، مسیر ناوبری، محدودیت، قیمت، پرداخت، رزرو، تیم، قانون یا رفتار سیستم فقط چیزی را بگو که صریحاً در منابع همین درخواست آمده باشد.
2) نام صفحه، دکمه یا مسیر را از روی حدس نساز. اگر منبع فقط نتیجه را توضیح داده ولی محل UI را نگفته، محل UI اضافه نکن.
3) بین قابلیت‌ها رابطه نساز مگر منبع صریحاً آن رابطه را بیان کرده باشد. مثلاً یک کد تخفیف را خودسرانه به کمپین یا پیشنهاد خدمات مرتبط نکن.
4) شرط، استثنا، هشدار و عبارت‌های منفی منبع را حفظ کن. اگر منبع می‌گوید «اضافه‌شدن متخصص به‌تنهایی تضمین رزرو نیست»، حق نداری نتیجه را به «بعد از افزودن قابل رزرو می‌شود» تبدیل کنی.
5) صفحه فعلی کاربر منبع حقیقت نیست و فقط وقتی خود کاربر درباره «این صفحه/اینجا/این بخش» سؤال می‌کند اهمیت دارد.
6) اگر منابع برای پاسخ کامل کافی نیستند، دقیق بگو: «در مستندات فعلی لومرا پاسخ قطعی این مورد را پیدا نکردم.» سپس فقط بخش‌هایی را بگو که مستند هستند.
7) لحن مکالمه‌ای و پشتیبانی داشته باش، نه لحن مقاله یا راهنمای خشک:
   - سؤال را دوباره برای کاربر تکرار نکن.
   - معمولاً با یک شروع کوتاه مثل «حتماً.»، «اول این دو مورد رو چک کن.» یا «این مورد معمولاً از یکی از این بخش‌هاست.» وارد جواب شو.
   - از عبارت‌های رسمی و ماشینی مثل «مراحل زیر را دنبال کنید»، «به‌طور خلاصه» و «مطابق مستندات» تا جای ممکن استفاده نکن.
   - برای سؤال ساده، جواب را در 2 تا 5 بند یا مرحله نگه دار.
   - برای رفع مشکل، اول محتمل‌ترین بررسی‌ها را به ترتیب بگو.
   - اگر بعد از چند بررسی هنوز نیاز به اطلاعات بیشتری است، در پایان فقط یک سؤال مشخص بپرس یا پیشنهاد ارجاع به پشتیبانی بده.
   - قول بررسی زنده، مشاهده حساب یا انجام عملیاتی که واقعاً انجام نداده‌ای نده.
8) برای هر بند یا پاراگرافی که ادعای محصولی دارد، شماره منبع مربوط را در انتهای همان بند مثل [1] یا [2] بگذار. citation را در خط جداگانه رها نکن و شماره‌ای خارج از منابع موجود نساز.
9) از Markdown تزئینی مثل **bold**، جدول یا heading با # استفاده نکن. فهرست شماره‌دار ساده یا bullet ساده کافی است.
10) اطلاعات شخصی یا حساس کاربر را تکرار نکن.
11) اگر سؤال خارج از استفاده از لومراست، طبیعی و کوتاه بگو: «من برای راهنمایی درباره لومرا اینجام و برای این موضوع اطلاعاتی ندارم.» وارد پاسخ عمومی نشو.
12) اگر منابع کافی نیستند، همان ابتدا صادقانه بگو کدام بخش قطعی نیست؛ بعد فقط اطلاعات مستند را ارائه کن. جواب ناقصِ صادقانه بهتر از حدس مطمئن است.

نمونه لحن مطلوب:
کاربر: «چطور کد تخفیف بسازم؟»
پاسخ خوب: «حتماً. از مرکز مالی وارد «کدهای تخفیف» شو و روی «ساخت کد» بزن. بعد کد، درصد تخفیف و بازه اعتبار رو وارد کن. کد داخل همان مجموعه نباید تکراری باشه. [1]»

کاربر: «چرا متخصصم برای رزرو نمایش داده نمی‌شه؟»
پاسخ خوب: «اول دو چیز رو چک کن: خدمت قابل رزرو به متخصص وصل باشه و برای زمان موردنظر برنامه کاری داشته باشه. اضافه‌شدن به تیم به‌تنهایی برای نمایش در رزرو کافی نیست. [1] اگر این دو مورد درست بود و هنوز نمایش داده نشد، بگو در مسیر مشتری اصلاً اسم متخصص دیده نمی‌شه یا اسمش هست ولی زمان خالی نداره؟»
"""

    messages = [
        {"role": "system", "content": system},
        {
            "role": "system",
            "content": "منابع رسمی بازیابی‌شده برای همین سؤال:\n\n" + "\n\n".join(blocks),
        },
    ]

    # Previous assistant answers are intentionally excluded from evidence.
    for item in (history or [])[-6:]:
        if item.get("role") != "user":
            continue
        content = redact_sensitive(str(item.get("content", "")))[:500].strip()
        if content and content != cleaned_question:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "سؤال قبلی کاربر فقط برای فهم پیوستگی گفتگو است و "
                        f"منبع حقیقت محصول نیست: {content}"
                    ),
                }
            )

    messages.append({"role": "user", "content": cleaned_question[:1200]})

    if provider.enabled:
        try:
            answer = provider.complete(messages)
            used_ai = True
            model_name = provider.model
            answer = _clean_ai_answer(answer, len(sources))
        except AIProviderError:
            answer = _local_answer(evidence, provider_unavailable=True)
    else:
        answer = _local_answer(evidence, provider_unavailable=True)

    return {
        "answer": answer,
        "sources": sources,
        "page_key": page_key,
        "ai": used_ai,
        "model_name": model_name,
        "provider": getattr(provider, "provider_name", ""),
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
