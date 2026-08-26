from __future__ import annotations

import json

from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.notifications import notify_support_ticket_created
from apps.main.models import SupportTicket
from apps.main.support_services import initialize_support_ticket

from .content import (
    get_article_by_slug,
    get_categories,
    get_featured_articles,
    get_legal_document,
    get_legal_documents,
    legacy_legal_url,
    related_articles,
    search_articles,
)
from .models import HelpConversation
from .services import (
    answer_help_question,
    consume_handoff_limit,
    consume_rate_limit,
    context_for_request,
    detect_user_role,
    get_or_create_conversation,
    get_owned_conversation,
    persist_exchange,
    public_role,
    save_feedback,
    transcript_for_support,
)


def _role(request) -> str:
    return detect_user_role(request.user)


def help_home(request):
    role = public_role(_role(request))
    return render(
        request,
        "help_center/home.html",
        {
            "categories": get_categories(role),
            "featured_articles": get_featured_articles(role, limit=8),
            "legal_documents": get_legal_documents(),
            "help_role": role,
        },
    )


def help_search(request):
    query = (request.GET.get("q") or "").strip()[:200]
    role = public_role(_role(request))
    results = search_articles(query, role=role, limit=20) if query else []
    return render(
        request,
        "help_center/search.html",
        {"query": query, "results": results},
    )


def help_article(request, slug):
    article = get_article_by_slug(slug)
    if not article:
        raise Http404
    return render(
        request,
        "help_center/article.html",
        {
            "article": article,
            "related_articles": related_articles(article),
        },
    )


def legal_index(request):
    return render(
        request,
        "help_center/legal_index.html",
        {"legal_documents": get_legal_documents()},
    )


def legal_detail(request, slug):
    doc = get_legal_document(slug)
    if not doc:
        fallback = next((item for item in get_legal_documents() if item["slug"] == slug), None)
        if fallback and fallback.get("legacy_url_name"):
            try:
                return redirect(fallback["legacy_url_name"])
            except NoReverseMatch:
                pass
        raise Http404

    if not doc.content.strip():
        url = legacy_legal_url(doc)
        if url:
            return redirect(url)

    return render(request, "help_center/legal_detail.html", {"document": doc})


@require_GET
def context_api(request):
    path = (request.GET.get("path") or "/")[:500]
    role = _role(request)
    route_name = (request.GET.get("route") or "")[:220]
    payload = context_for_request(path, role, route_name)
    payload["role"] = role
    return JsonResponse(payload)


@require_POST
def chat_api(request):
    if len(request.body or b"") > 16 * 1024:
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

    role = _role(request)
    path = str(payload.get("path") or "/")[:500]
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    route_name = str(payload.get("route_name") or "")[:220]
    result = answer_help_question(
        question=question,
        page_path=path,
        role=role,
        history=history,
        route_name=route_name,
    )

    conversation = get_or_create_conversation(
        request,
        conversation_id=payload.get("conversation_id"),
        page_path=path,
        page_key=result["page_key"],
        route_name=route_name,
    )
    assistant_message = persist_exchange(
        conversation,
        question=result["redacted_question"],
        answer=result["answer"],
        used_ai=result["ai"],
        model_name=result["model_name"],
        sources=result["sources"],
    )

    result.pop("redacted_question", None)
    result["remaining"] = remaining
    result["conversation_id"] = str(conversation.public_id) if conversation else None
    result["assistant_message_id"] = str(assistant_message.public_id) if assistant_message else None
    return JsonResponse(result)


@require_POST
def feedback_api(request):
    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    ok = save_feedback(
        request,
        message_public_id=payload.get("message_id"),
        rating=str(payload.get("rating") or ""),
        note=str(payload.get("note") or ""),
    )
    if not ok:
        return JsonResponse({"error": "امکان ثبت بازخورد وجود ندارد."}, status=400)
    return JsonResponse({"ok": True})


@require_POST
def support_handoff_api(request):
    support_url = reverse("support")

    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "error": "برای انتقال مستقیم گفتگو به تیکت وارد حساب شو؛ یا فرم پشتیبانی را باز کن.",
                "support_url": support_url,
                "requires_login": True,
            },
            status=401,
        )

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "درخواست نامعتبر است."}, status=400)

    conversation = get_owned_conversation(request, payload.get("conversation_id"))
    if not conversation:
        return JsonResponse(
            {"error": "گفتگویی برای انتقال پیدا نشد.", "support_url": support_url},
            status=400,
        )

    if conversation.support_ticket_id:
        return JsonResponse(
            {
                "ok": True,
                "ticket_id": conversation.support_ticket_id,
                "ticket_url": reverse(
                    "main:support_ticket_detail",
                    kwargs={"pk": conversation.support_ticket_id},
                ),
            }
        )

    if not consume_handoff_limit(request):
        return JsonResponse(
            {"error": "تعداد ارجاع‌های این بازه زیاد است. کمی بعد دوباره تلاش کن."},
            status=429,
        )

    email = (request.user.email or "").strip()
    if not email:
        return JsonResponse(
            {
                "error": "برای ثبت مستقیم تیکت، ایمیل حساب کامل نیست. فرم پشتیبانی را باز کن.",
                "support_url": support_url,
            },
            status=409,
        )

    requester_role = {
        "manager": "salon_manager",
        "stylist": "stylist",
        "customer": "customer",
    }.get(detect_user_role(request.user), "customer")

    with transaction.atomic():
        conversation = HelpConversation.objects.select_for_update().get(pk=conversation.pk)
        if conversation.support_ticket_id:
            ticket = conversation.support_ticket
        else:
            ticket = SupportTicket.objects.create(
                user=request.user,
                email=email,
                full_name=request.user.get_fullName(),
                mobile=request.user.mobile_number,
                issue_type="other",
                support_reason="help_assistant",
                subject=f"پیگیری دستیار لومرا · {conversation.page_key or 'راهنما'}",
                description=transcript_for_support(conversation),
                category="other",
                requester_role=requester_role,
                metadata={
                    "source": "help_assistant",
                    "help_conversation_id": str(conversation.public_id),
                    "page_key": conversation.page_key,
                    "page_path": conversation.page_path,
                },
            )
            initialize_support_ticket(
                ticket,
                actor=request.user,
                attachment_file=None,
                request=request,
            )
            conversation.support_ticket = ticket
            conversation.status = HelpConversation.Status.ESCALATED
            conversation.save(update_fields=["support_ticket", "status", "updated_at"])

            transaction.on_commit(
                lambda: notify_support_ticket_created(
                    user=request.user,
                    ticket=ticket,
                    action_url=reverse(
                        "main:support_ticket_detail",
                        kwargs={"pk": ticket.pk},
                    ),
                )
            )

    return JsonResponse(
        {
            "ok": True,
            "ticket_id": ticket.pk,
            "ticket_url": reverse("main:support_ticket_detail", kwargs={"pk": ticket.pk}),
        }
    )
