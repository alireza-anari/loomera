from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, TemplateView, View

from .models import (
    Article,
    ArticleCategory,
    ArticleTag,
    ArticleView,
    SalonStory,
    SalonStoryItem,
)
from .services import (
    accessible_stories_queryset,
    build_story_payload,
    strip_internal_content_notes,
    favorite_salon_story_queryset,
    mark_story_viewed,
    merge_story_querysets,
    published_articles_queryset,
    published_stories_queryset,
    user_can_access_story,
)
from apps.services.models import GroupServices
from apps.main.ui_feedback import safe_form_errors


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def hash_ip(ip):
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:64]


class StoryTrackPayloadTooLarge(Exception):
    """Raised when story tracking payload exceeds the configured limit."""


class StoryTrackPayloadInvalid(Exception):
    """Raised when story tracking payload contains invalid values."""


def _story_track_post_max_bytes():
    return max(
        int(getattr(settings, "ARTICLE_STORY_TRACK_POST_MAX_BYTES", 2 * 1024) or 1),
        1,
    )


def _story_track_payload_too_large(request):
    content_length = request.META.get("CONTENT_LENGTH")
    if not content_length:
        return False

    try:
        return int(content_length) > _story_track_post_max_bytes()
    except ValueError:
        return True


def _story_track_item_id(raw_item_id):
    item_id = str(raw_item_id or "").strip()
    if not item_id:
        return None

    if not item_id.isdigit():
        raise StoryTrackPayloadInvalid

    return int(item_id)


def _story_track_completed(raw_completed):
    completed = str(raw_completed or "").strip().lower()

    if completed in {"", "0", "false", "no", "off"}:
        return False

    if completed in {"1", "true", "yes", "on"}:
        return True

    raise StoryTrackPayloadInvalid


def paginate_queryset(request, queryset, per_page=12):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def _magazine_story_id_from_value(value):
    story_id = str(value or "").strip()
    if not story_id:
        return None

    if not story_id.isdigit():
        raise Http404("استوری موردنظر معتبر نیست.")

    story_id = int(story_id)
    if story_id <= 0:
        raise Http404("استوری موردنظر معتبر نیست.")

    return story_id


def _magazine_requested_story_id(request):
    return _magazine_story_id_from_value(
        request.GET.get("story") or request.GET.get("story_id")
    )


class MagazineHomeView(TemplateView):
    template_name = "articles/magazine_home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        articles = published_articles_queryset()

        favorite_stories = list(favorite_salon_story_queryset(self.request.user)[:15])

        all_stories_preview = list(
            accessible_stories_queryset(self.request.user)
            .exclude(id__in=[story.id for story in favorite_stories])
            .order_by("-published_at")[:14]
        )

        requested_story_id = _magazine_requested_story_id(self.request)
        if requested_story_id is not None:
            requested_story = (
                accessible_stories_queryset(self.request.user)
                .filter(pk=requested_story_id)
                .first()
            )
            if requested_story and requested_story.id not in {
                story.id for story in favorite_stories + all_stories_preview
            }:
                all_stories_preview.insert(0, requested_story)

        magazine_story_payload = build_story_payload(
            merge_story_querysets(favorite_stories, all_stories_preview),
            user=self.request.user,
            request=self.request,
        )

        featured_articles = articles.filter(is_featured=True)[:5]
        latest_articles = articles[:12]
        educational_articles = articles.filter(is_educational=True)[:8]
        expert_articles = articles.filter(
            Q(author_stylist__isnull=False) | Q(author_salon__isnull=False)
        )[:8]

        context.update(
            {
                "page_title": "مجله لومرا",
                "page_description": "آموزش‌ها، راهنماها، تجربه متخصصان و محتوای تازه مجموعه‌های زیبایی در لومرا.",
                "favorite_stories": favorite_stories,
                "favorite_stories_payload": build_story_payload(
                    favorite_stories,
                    user=self.request.user,
                    request=self.request,
                ),
                "featured_articles": featured_articles,
                "latest_articles": latest_articles,
                "educational_articles": educational_articles,
                "expert_articles": expert_articles,
                "categories": ArticleCategory.objects.filter(
                    is_active=True, parent__isnull=True
                )[:12],
                "popular_tags": ArticleTag.objects.filter(
                    is_active=True,
                    articles__status=Article.Status.PUBLISHED,
                )
                .distinct()
                .order_by("title")[:20],
                "all_stories_preview": all_stories_preview,
                "magazine_stories_payload": magazine_story_payload,
            }
        )

        return context


class ArticleDetailView(DetailView):
    template_name = "articles/article_detail.html"
    model = Article
    context_object_name = "article"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        # Published noindex articles should still be viewable when linked directly;
        # robots handling belongs to the template/meta layer.
        return published_articles_queryset()

    def get_object(self, queryset=None):
        article = super().get_object(queryset)
        self.record_article_view(article)
        return article

    def record_article_view(self, article):
        request = self.request

        if not request.session.session_key:
            request.session.save()

        session_key = request.session.session_key or ""
        ip_hash = hash_ip(get_client_ip(request))
        user = request.user if request.user.is_authenticated else None

        recently_viewed = ArticleView.objects.filter(
            article=article,
            session_key=session_key,
            viewed_at__gte=timezone.now() - timezone.timedelta(hours=6),
        ).exists()

        if not recently_viewed:
            ArticleView.objects.create(
                article=article,
                user=user,
                session_key=session_key,
                ip_hash=ip_hash,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            )
            Article.objects.filter(pk=article.pk).update(view_count=F("view_count") + 1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = self.object

        related_articles = (
            published_articles_queryset()
            .exclude(pk=article.pk)
            .filter(
                Q(category=article.category)
                | Q(tags__in=article.tags.all())
                | Q(related_service_groups__in=article.related_service_groups.all())
            )
            .distinct()[:6]
        )

        article_schema = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": article.title,
            "description": article.effective_seo_description,
            "datePublished": (
                article.published_at.isoformat() if article.published_at else ""
            ),
            "dateModified": (
                article.updated_at.isoformat() if article.updated_at else ""
            ),
            "author": {
                "@type": "Person",
                "name": article.author_display_name,
            },
            "publisher": {
                "@type": "Organization",
                "name": "Loomera",
            },
            "mainEntityOfPage": self.request.build_absolute_uri(
                article.get_absolute_url()
            ),
        }

        if article.cover_image:
            article_schema["image"] = self.request.build_absolute_uri(
                article.cover_image.url
            )

        breadcrumb_schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "name": "مجله لومرا",
                    "item": self.request.build_absolute_uri("/magazine/"),
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": article.title,
                    "item": self.request.build_absolute_uri(article.get_absolute_url()),
                },
            ],
        }

        active_faqs = [faq for faq in article.faqs.all() if faq.is_active]
        faq_schema_json = ""
        if active_faqs:
            faq_schema_json = json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "FAQPage",
                    "mainEntity": [
                        {
                            "@type": "Question",
                            "name": faq.question,
                            "acceptedAnswer": {
                                "@type": "Answer",
                                "text": faq.answer,
                            },
                        }
                        for faq in active_faqs
                    ],
                },
                ensure_ascii=False,
            )

        context.update(
            {
                "related_articles": related_articles,
                "article_schema_json": json.dumps(article_schema, ensure_ascii=False),
                "breadcrumb_schema_json": json.dumps(
                    breadcrumb_schema, ensure_ascii=False
                ),
                "faq_schema_json": faq_schema_json,
                "public_article_content": strip_internal_content_notes(article.content),
                "public_article_summary": strip_internal_content_notes(article.summary),
                "canonical_url": article.canonical_url
                or self.request.build_absolute_uri(article.get_absolute_url()),
            }
        )

        return context


class ArticleCategoryView(ListView):
    template_name = "articles/article_list.html"
    context_object_name = "articles"
    paginate_by = 12

    def dispatch(self, request, *args, **kwargs):
        self.category = get_object_or_404(
            ArticleCategory,
            slug=kwargs.get("slug"),
            is_active=True,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return published_articles_queryset().filter(category=self.category)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "list_title": self.category.title,
                "list_description": self.category.description
                or "مقالات و آموزش‌های مرتبط با این دسته‌بندی.",
                "taxonomy_type": "category",
                "taxonomy_object": self.category,
            }
        )
        return context


class ArticleTagView(ListView):
    template_name = "articles/article_list.html"
    context_object_name = "articles"
    paginate_by = 12

    def dispatch(self, request, *args, **kwargs):
        self.tag = get_object_or_404(
            ArticleTag,
            slug=kwargs.get("slug"),
            is_active=True,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return published_articles_queryset().filter(tags=self.tag)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "list_title": self.tag.title,
                "list_description": self.tag.description
                or "مطالب مرتبط با این موضوع در مجله لومرا.",
                "taxonomy_type": "tag",
                "taxonomy_object": self.tag,
            }
        )
        return context


@method_decorator(require_POST, name="dispatch")
class StoryViewTrackView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if _story_track_payload_too_large(request):
            return JsonResponse(
                {"ok": False, "error": "payload_too_large"},
                status=413,
            )

        story = get_object_or_404(SalonStory, pk=pk)

        if not user_can_access_story(request.user, story):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

        try:
            item_id = _story_track_item_id(request.POST.get("item_id"))
            completed = _story_track_completed(request.POST.get("completed"))
        except StoryTrackPayloadInvalid:
            return JsonResponse(
                {"ok": False, "error": "invalid_payload"},
                status=400,
            )

        item = None
        if item_id is not None:
            item = SalonStoryItem.objects.filter(
                story=story,
                pk=item_id,
                is_active=True,
            ).first()

        mark_story_viewed(request.user, story, last_item_seen=item, completed=completed)

        SalonStory.objects.filter(pk=story.pk).update(view_count=F("view_count") + 1)

        return JsonResponse({"ok": True})


@method_decorator(require_POST, name="dispatch")
class StoryClickTrackView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if _story_track_payload_too_large(request):
            return JsonResponse(
                {"ok": False, "error": "payload_too_large"},
                status=413,
            )

        story = get_object_or_404(SalonStory, pk=pk)

        if not user_can_access_story(request.user, story):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

        SalonStory.objects.filter(pk=story.pk).update(click_count=F("click_count") + 1)

        return JsonResponse({"ok": True})


STORY_EXPLORE_SORT_OPTIONS = {"newest", "popular", "ending"}
STORY_EXPLORE_SCOPE_OPTIONS = {"all", "favorites"}


def _story_explore_text_max_chars():
    return max(
        int(getattr(settings, "ARTICLE_STORY_EXPLORE_TEXT_MAX_CHARS", 80) or 1),
        1,
    )


def _clean_story_explore_text_param(value):
    text = str(value or "").strip()
    return text[: _story_explore_text_max_chars()]


def _story_explore_sort(value):
    sort = str(value or "newest").strip()
    if sort not in STORY_EXPLORE_SORT_OPTIONS:
        return "newest"
    return sort


def _story_explore_scope(value):
    scope = str(value or "all").strip()
    if scope not in STORY_EXPLORE_SCOPE_OPTIONS:
        return "all"
    return scope


def _story_explore_service_group_id(value):
    service_group = str(value or "").strip()
    if not service_group:
        return None

    if not service_group.isdigit():
        raise Http404("فیلتر استوری معتبر نیست.")

    return int(service_group)


class StoryExploreView(TemplateView):
    template_name = "articles/story_explore.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        request = self.request
        stories = accessible_stories_queryset(request.user)

        q = _clean_story_explore_text_param(request.GET.get("q"))
        sort = _story_explore_sort(request.GET.get("sort"))
        topic = _clean_story_explore_text_param(request.GET.get("topic"))
        service_group_id = _story_explore_service_group_id(
            request.GET.get("service_group")
        )
        scope = _story_explore_scope(request.GET.get("scope"))

        if scope == "favorites":
            stories = favorite_salon_story_queryset(request.user)

        if q:
            stories = stories.filter(
                Q(title__icontains=q)
                | Q(summary__icontains=q)
                | Q(salon__salon_name__icontains=q)
                | Q(stylist__user__name__icontains=q)
                | Q(stylist__user__family__icontains=q)
            )

        if topic:
            stories = stories.filter(related_article__category__slug=topic)

        if service_group_id is not None:
            stories = stories.filter(related_service_group_id=service_group_id)

        if sort == "popular":
            stories = stories.order_by("-view_count", "-published_at")
        elif sort == "ending":
            stories = stories.order_by("expires_at", "-published_at")
        else:
            stories = stories.order_by("-published_at")

        page_obj = paginate_queryset(request, stories, per_page=18)
        story_list = list(page_obj.object_list)

        context.update(
            {
                "page_title": "همه استوری‌های مجموعه‌ها",
                "stories": story_list,
                "page_obj": page_obj,
                "is_paginated": page_obj.has_other_pages(),
                "stories_payload": build_story_payload(
                    story_list,
                    user=request.user,
                    request=request,
                ),
                "categories": ArticleCategory.objects.filter(is_active=True)[:20],
                "service_groups": GroupServices.objects.filter(is_active=True)[:20],
                "current_q": q,
                "current_sort": sort,
                "current_topic": topic,
                "current_service_group": str(service_group_id or ""),
                "current_scope": scope,
            }
        )

        return context


from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from apps.accounts.models import WorkSamples
from .forms import ContentReportForm
from .services import report_content_object


class ContentReportPayloadTooLarge(Exception):
    """Raised when content report payload exceeds the configured limit."""


class ContentReportPayloadInvalid(Exception):
    """Raised when content report payload contains invalid values."""


def _content_report_post_max_bytes():
    return max(
        int(getattr(settings, "ARTICLE_CONTENT_REPORT_POST_MAX_BYTES", 8 * 1024) or 1),
        1,
    )


def _content_report_description_max_chars():
    return max(
        int(
            getattr(
                settings,
                "ARTICLE_CONTENT_REPORT_DESCRIPTION_MAX_CHARS",
                1000,
            )
            or 1
        ),
        1,
    )


def _content_report_payload_too_large(request):
    content_length = request.META.get("CONTENT_LENGTH")
    if not content_length:
        return False

    try:
        return int(content_length) > _content_report_post_max_bytes()
    except ValueError:
        return True


def _validate_content_report_description(description):
    if len(str(description or "").strip()) > _content_report_description_max_chars():
        raise ContentReportPayloadInvalid


def _get_reportable_content_object(request, model_name, object_id):
    if model_name == "article":
        return get_object_or_404(
            published_articles_queryset(),
            pk=object_id,
        )

    if model_name == "story":
        return get_object_or_404(
            accessible_stories_queryset(request.user),
            pk=object_id,
        )

    if model_name == "work_sample":
        return get_object_or_404(
            WorkSamples.objects.filter(
                is_active=True,
                is_public=True,
                review_status="published",
            ),
            pk=object_id,
        )

    return None


@method_decorator(require_POST, name="dispatch")
class ContentReportCreateView(LoginRequiredMixin, View):
    """Report public content without exposing moderation internals."""

    def post(self, request, model_name, object_id):
        if _content_report_payload_too_large(request):
            return JsonResponse(
                {"ok": False, "error": "payload_too_large"},
                status=413,
            )

        target = _get_reportable_content_object(request, model_name, object_id)
        if target is None:
            return JsonResponse(
                {"ok": False, "error": "invalid_content_type"},
                status=400,
            )

        form = ContentReportForm(request.POST)
        if not form.is_valid():
            return JsonResponse(
                {"ok": False, "error": "invalid_form", "errors": safe_form_errors(form)},
                status=400,
            )

        description = form.cleaned_data.get("description") or ""
        try:
            _validate_content_report_description(description)
        except ContentReportPayloadInvalid:
            return JsonResponse(
                {"ok": False, "error": "description_too_long"},
                status=400,
            )

        report_content_object(
            target,
            reported_by=request.user,
            reason=form.cleaned_data["reason"],
            description=description,
        )
        return JsonResponse({"ok": True, "message": "گزارش محتوا ثبت شد."})
