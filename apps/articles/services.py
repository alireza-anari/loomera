from __future__ import annotations

from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.comments_scores_favories.models import Favorits

from .models import Article, SalonStory, SalonStoryItem, SalonStoryView

PUBLIC_STORY_ITEMS_ATTR = "_public_active_story_items"


def get_customer_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None

    for attr in ("customer_profile", "customer"):
        customer = getattr(user, attr, None)
        if customer is not None:
            return customer

    try:
        from apps.accounts.models import Customer

        return Customer.objects.filter(user=user).first()
    except Exception:
        return None


def published_articles_queryset():
    return (
        Article.objects.published()
        .filter(visibility=Article.Visibility.PUBLIC)
        .select_related(
            "category", "author_user", "author_stylist__user", "author_salon"
        )
        .prefetch_related("tags", "related_services", "related_service_groups", "faqs")
    )


def published_stories_queryset():
    """Return live stories with their public active items prefetched.

    The dedicated ``to_attr`` is important because filtering a related manager
    after a normal prefetch would execute one extra query per story.
    """

    now = timezone.now()

    return (
        SalonStory.objects.filter(
            status=SalonStory.Status.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=now,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
        .select_related(
            "salon",
            "stylist__user",
            "related_article",
            "related_service",
            "related_service_group",
        )
        .prefetch_related(
            Prefetch(
                "items",
                queryset=SalonStoryItem.objects.filter(
                    is_active=True,
                ).order_by(
                    "sort_order",
                    "id",
                ),
                to_attr=PUBLIC_STORY_ITEMS_ATTR,
            )
        )
    )


def favorite_salon_story_queryset(user):
    customer = get_customer_for_user(user)
    if customer is None:
        return SalonStory.objects.none()

    favorite_salon_ids = Favorits.objects.filter(
        favorite_user=customer,
        salon__isnull=False,
    ).values_list("salon_id", flat=True)

    return published_stories_queryset().filter(
        salon_id__in=favorite_salon_ids,
        visibility__in=[
            SalonStory.Visibility.FAVORITES_ONLY,
            SalonStory.Visibility.PUBLIC,
        ],
    )


PUBLIC_CONTENT_META_MARKER = "\n\nگزینه‌های پیشنهادی برای مدیر:"
PUBLIC_CONTENT_META_PREFIXES = (
    "گزینه‌های پیشنهادی برای مدیر:",
    "برچسب‌های مرتبط:",
    "برچسب‌های جدید:",
    "خدمات مرتبط:",
    "گروه‌های خدمت:",
    "نمایش پیشنهادی:",
    "نوع دکمه استوری:",
    "متن دکمه:",
    "لینک دکمه:",
)


def strip_internal_content_notes(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if PUBLIC_CONTENT_META_MARKER in text:
        text = text.split(PUBLIC_CONTENT_META_MARKER, 1)[0].strip()
    cleaned = []
    for line in text.splitlines():
        normalized = line.strip()
        if any(
            normalized.startswith(prefix) for prefix in PUBLIC_CONTENT_META_PREFIXES
        ):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def user_can_access_story(user, story):
    if not story.is_live:
        return False

    if story.visibility in {
        SalonStory.Visibility.PUBLIC,
        SalonStory.Visibility.SALON_PAGE_ONLY,
    }:
        return True

    if story.visibility == SalonStory.Visibility.FAVORITES_ONLY:
        customer = get_customer_for_user(user)
        if customer is None:
            return False

        return Favorits.objects.filter(
            favorite_user=customer,
            salon_id=story.salon_id,
        ).exists()

    return False


def mark_story_viewed(user, story, last_item_seen=None, completed=False):
    if not getattr(user, "is_authenticated", False):
        return None

    view, _ = SalonStoryView.objects.update_or_create(
        user=user,
        story=story,
        defaults={"last_item_seen": last_item_seen},
    )

    if completed and not view.completed_at:
        view.completed_at = timezone.now()
        view.save(update_fields=["completed_at", "viewed_at"])

    return view


def _active_story_items(story) -> list[SalonStoryItem]:
    """Return active story items without querying when properly prefetched."""

    prefetched_items = getattr(
        story,
        PUBLIC_STORY_ITEMS_ATTR,
        None,
    )

    if prefetched_items is not None:
        return list(prefetched_items)

    # Backward compatibility for callers that provide an unprepared Story.
    return list(
        story.items.filter(
            is_active=True,
        ).order_by(
            "sort_order",
            "id",
        )
    )


def build_story_payload(stories, user=None, request=None):
    viewed_story_ids = set()

    if getattr(user, "is_authenticated", False):
        viewed_story_ids = set(
            SalonStoryView.objects.filter(
                user=user,
                story__in=stories,
                completed_at__isnull=False,
            ).values_list("story_id", flat=True)
        )

    payload = []

    for story in stories:
        items = []
        active_items = _active_story_items(story)

        for item in active_items:
            media_url = ""

            if item.media_type == item.MediaType.VIDEO and item.video:
                media_url = item.video.url
            elif item.image:
                media_url = item.image.url

            if request and media_url:
                media_url = request.build_absolute_uri(media_url)

            items.append(
                {
                    "id": item.id,
                    "mediaType": item.media_type,
                    "mediaUrl": media_url,
                    "caption": strip_internal_content_notes(item.caption),
                    "buttonLabel": item.button_label,
                    "buttonUrl": item.button_url,
                    "duration": item.duration_seconds or 5,
                }
            )

        cta_url = story.get_cta_url()
        if request and cta_url and cta_url.startswith("/"):
            cta_url = request.build_absolute_uri(cta_url)

        cover_url = ""

        if story.cover_image:
            cover_url = story.cover_image.url
        else:
            first_image_item = next(
                (item for item in active_items if item.image),
                None,
            )
            if first_image_item is not None:
                cover_url = first_image_item.image.url

        if request and cover_url:
            cover_url = request.build_absolute_uri(cover_url)

        payload.append(
            {
                "id": story.id,
                "title": story.title,
                "summary": strip_internal_content_notes(story.summary),
                "salonName": story.salon.salon_name if story.salon_id else "",
                "stylistName": story.stylist.get_fullName() if story.stylist_id else "",
                "coverUrl": cover_url,
                "ctaLabel": story.cta_label or "مشاهده",
                "ctaUrl": cta_url,
                "viewUrl": (
                    request.build_absolute_uri(f"/magazine/stories/{story.id}/view/")
                    if request
                    else f"/magazine/stories/{story.id}/view/"
                ),
                "clickUrl": (
                    request.build_absolute_uri(f"/magazine/stories/{story.id}/click/")
                    if request
                    else f"/magazine/stories/{story.id}/click/"
                ),
                "reportUrl": (
                    request.build_absolute_uri(f"/magazine/report/story/{story.id}/")
                    if request
                    else f"/magazine/report/story/{story.id}/"
                ),
                "isViewed": story.id in viewed_story_ids,
                "items": items,
            }
        )

    return payload


def accessible_stories_queryset(user):
    """
    استوری‌هایی که کاربر اجازه دیدن آن‌ها را دارد:
    - همه کاربران: استوری‌های عمومی
    - کاربر لاگین‌شده: استوری‌های عمومی + استوری سالن‌های مورد علاقه خودش
    """
    base_public = published_stories_queryset().filter(
        visibility=SalonStory.Visibility.PUBLIC,
    )

    customer = get_customer_for_user(user)
    if customer is None:
        return base_public.distinct()

    favorite_salon_ids = Favorits.objects.filter(
        favorite_user=customer,
        salon__isnull=False,
    ).values_list("salon_id", flat=True)

    favorites_only = published_stories_queryset().filter(
        salon_id__in=favorite_salon_ids,
        visibility=SalonStory.Visibility.FAVORITES_ONLY,
    )

    return (base_public | favorites_only).distinct()


def merge_story_querysets(*querysets):
    story_ids = []
    seen = set()

    for queryset in querysets:
        for story in queryset:
            if story.id not in seen:
                seen.add(story.id)
                story_ids.append(story.id)

    if not story_ids:
        return SalonStory.objects.none()

    preserved_order = {story_id: index for index, story_id in enumerate(story_ids)}
    stories = list(published_stories_queryset().filter(id__in=story_ids))
    stories.sort(key=lambda story: preserved_order.get(story.id, 9999))
    return stories


# -----------------------------------------------------------------------------
# Content moderation and staff submissions

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import ContentModerationEvent, ContentReport, StaffContentSubmission


def _get_status(obj):
    if hasattr(obj, "status"):
        return getattr(obj, "status") or ""
    if hasattr(obj, "review_status"):
        return getattr(obj, "review_status") or ""
    return ""


def _set_status(obj, value):
    if hasattr(obj, "status"):
        setattr(obj, "status", value)
    elif hasattr(obj, "review_status"):
        setattr(obj, "review_status", value)


def create_moderation_event(
    target, event_type, actor=None, old_status="", new_status="", note="", metadata=None
):
    return ContentModerationEvent.objects.create(
        target_content_type=ContentType.objects.get_for_model(
            target, for_concrete_model=False
        ),
        target_object_id=target.pk,
        event_type=event_type,
        actor=actor,
        old_status=old_status or "",
        new_status=new_status or "",
        note=note or "",
        metadata=metadata or {},
    )


def submit_staff_content(submission, actor=None, terms_version="content-v1"):
    old_status = submission.status
    submission.status = StaffContentSubmission.Status.PENDING_REVIEW
    submission.professional_confirmed_responsibility = True
    submission.professional_confirmed_at = timezone.now()
    submission.review_note = submission.review_note or "ارسال‌شده برای بررسی مدیر سالن."
    submission.save(
        update_fields=[
            "status",
            "professional_confirmed_responsibility",
            "professional_confirmed_at",
            "review_note",
            "updated_at",
        ]
    )
    create_moderation_event(
        submission,
        "staff_submission_sent",
        actor=actor,
        old_status=old_status,
        new_status=submission.status,
        metadata={"terms_version": terms_version},
    )
    return submission


@transaction.atomic
def approve_staff_submission(submission, actor, note=""):
    old_status = submission.status
    submission.status = StaffContentSubmission.Status.APPROVED
    submission.manager_approved_responsibility = True
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.review_note = note or "تأیید شده توسط مدیر سالن."
    submission.save(
        update_fields=[
            "status",
            "manager_approved_responsibility",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    create_moderation_event(
        submission,
        "staff_submission_approved",
        actor=actor,
        old_status=old_status,
        new_status=submission.status,
        note=note,
    )
    return submission


@transaction.atomic
def reject_staff_submission(submission, actor, note=""):
    old_status = submission.status
    submission.status = StaffContentSubmission.Status.REJECTED
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.review_note = note or "رد شده توسط مدیر سالن."
    submission.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    create_moderation_event(
        submission,
        "staff_submission_rejected",
        actor=actor,
        old_status=old_status,
        new_status=submission.status,
        note=note,
    )
    return submission


@transaction.atomic
def request_staff_submission_revision(submission, actor, note=""):
    old_status = submission.status
    submission.status = StaffContentSubmission.Status.NEEDS_REVISION
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.review_note = note or "نیازمند اصلاح توسط آرایشگر."
    submission.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
            "updated_at",
        ]
    )
    create_moderation_event(
        submission,
        "staff_submission_needs_revision",
        actor=actor,
        old_status=old_status,
        new_status=submission.status,
        note=note,
    )
    return submission


@transaction.atomic
def approve_content_object(
    target, actor, note="", publish=False, terms_version="content-v1"
):
    old_status = _get_status(target)
    new_status = "published" if publish else "approved"
    _set_status(target, new_status)
    fields = []
    if hasattr(target, "status"):
        fields.append("status")
    if hasattr(target, "review_status"):
        fields.append("review_status")
    if hasattr(target, "reviewed_by"):
        target.reviewed_by = actor
        fields.append("reviewed_by")
    if hasattr(target, "reviewed_at"):
        target.reviewed_at = timezone.now()
        fields.append("reviewed_at")
    if hasattr(target, "manager_approved_responsibility"):
        target.manager_approved_responsibility = True
        fields.append("manager_approved_responsibility")
    if hasattr(target, "manager_approved_by"):
        target.manager_approved_by = actor
        fields.append("manager_approved_by")
    if hasattr(target, "manager_approved_at"):
        target.manager_approved_at = timezone.now()
        fields.append("manager_approved_at")
    if hasattr(target, "manager_terms_version"):
        target.manager_terms_version = terms_version
        fields.append("manager_terms_version")
    if hasattr(target, "moderation_note"):
        target.moderation_note = note or target.moderation_note
        fields.append("moderation_note")
    if hasattr(target, "published_at") and publish and not target.published_at:
        target.published_at = timezone.now()
        fields.append("published_at")
    if hasattr(target, "updated_at"):
        fields.append("updated_at")
    target.save(update_fields=list(dict.fromkeys(fields)) if fields else None)
    create_moderation_event(
        target,
        "content_published" if publish else "content_approved",
        actor=actor,
        old_status=old_status,
        new_status=_get_status(target),
        note=note,
        metadata={"terms_version": terms_version},
    )
    return target


@transaction.atomic
def reject_content_object(target, actor, note=""):
    old_status = _get_status(target)
    _set_status(target, "rejected")
    fields = []
    if hasattr(target, "status"):
        fields.append("status")
    if hasattr(target, "review_status"):
        fields.append("review_status")
    if hasattr(target, "reviewed_by"):
        target.reviewed_by = actor
        fields.append("reviewed_by")
    if hasattr(target, "reviewed_at"):
        target.reviewed_at = timezone.now()
        fields.append("reviewed_at")
    if hasattr(target, "rejection_reason"):
        target.rejection_reason = note or "رد شده در بررسی محتوا."
        fields.append("rejection_reason")
    if hasattr(target, "moderation_note"):
        target.moderation_note = note or target.moderation_note
        fields.append("moderation_note")
    if hasattr(target, "updated_at"):
        fields.append("updated_at")
    target.save(update_fields=list(dict.fromkeys(fields)) if fields else None)
    create_moderation_event(
        target,
        "content_rejected",
        actor=actor,
        old_status=old_status,
        new_status=_get_status(target),
        note=note,
    )
    return target


@transaction.atomic
def suspend_content_object(target, actor=None, note=""):
    old_status = _get_status(target)
    _set_status(target, "suspended")
    fields = []
    if hasattr(target, "status"):
        fields.append("status")
    if hasattr(target, "review_status"):
        fields.append("review_status")
    if hasattr(target, "removed_by"):
        target.removed_by = actor
        fields.append("removed_by")
    if hasattr(target, "removed_at"):
        target.removed_at = timezone.now()
        fields.append("removed_at")
    if hasattr(target, "moderation_note"):
        target.moderation_note = note or target.moderation_note
        fields.append("moderation_note")
    if hasattr(target, "updated_at"):
        fields.append("updated_at")
    target.save(update_fields=list(dict.fromkeys(fields)) if fields else None)
    create_moderation_event(
        target,
        "content_suspended",
        actor=actor,
        old_status=old_status,
        new_status=_get_status(target),
        note=note,
    )
    return target


@transaction.atomic
def report_content_object(target, reported_by=None, reason="other", description=""):
    report = ContentReport.objects.create(
        target_content_type=ContentType.objects.get_for_model(
            target, for_concrete_model=False
        ),
        target_object_id=target.pk,
        reported_by=(
            reported_by if getattr(reported_by, "is_authenticated", False) else None
        ),
        reason=reason,
        description=description or "",
    )
    if hasattr(target, "report_count"):
        target.report_count = (target.report_count or 0) + 1
        target.save(update_fields=["report_count"])
    old_status = _get_status(target)
    if hasattr(target, "status") and old_status == "published":
        target.status = "reported"
        target.save(update_fields=["status"])
    create_moderation_event(
        target,
        "content_reported",
        actor=reported_by if getattr(reported_by, "is_authenticated", False) else None,
        old_status=old_status,
        new_status=_get_status(target),
        note=description,
        metadata={"reason": reason, "report_id": report.pk},
    )
    return report
