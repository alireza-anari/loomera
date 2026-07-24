from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent

from .models import BookingQuickLink
from .quick_links import MAX_AGE_SECONDS


def _locked_link(*, links_queryset, link_id):
    try:
        link_id = int(link_id)
    except (TypeError, ValueError):
        raise ValidationError("شناسه لینک رزرو معتبر نیست.")

    quick_link = (
        links_queryset.select_for_update()
        .filter(pk=link_id)
        .first()
    )

    if quick_link is None:
        raise ValidationError(
            "لینک انتخاب‌شده پیدا نشد یا متعلق به این حساب نیست."
        )

    return quick_link


def _clean_text(field_name, value, label):
    value = str(value or "").strip()
    field = BookingQuickLink._meta.get_field(field_name)

    if field.max_length and len(value) > field.max_length:
        raise ValidationError(f"{label} از طول مجاز بیشتر است.")

    return value


def _clean_placement(value):
    value = str(
        value or BookingQuickLink.Placement.OTHER
    ).strip()

    valid = {
        choice_value
        for choice_value, _label
        in BookingQuickLink.Placement.choices
    }

    if value not in valid:
        raise ValidationError(
            "محل استفاده انتخاب‌شده برای لینک معتبر نیست."
        )

    return value


def _fresh_expiry():
    return timezone.now() + timedelta(seconds=MAX_AGE_SECONDS)


@transaction.atomic
def update_booking_quick_link_metadata(
    *,
    links_queryset,
    link_id,
    title="",
    placement=BookingQuickLink.Placement.OTHER,
    campaign_name="",
    internal_note="",
    is_permanent=False,
):
    quick_link = _locked_link(
        links_queryset=links_queryset,
        link_id=link_id,
    )

    title = _clean_text("title", title, "عنوان لینک")
    campaign_name = _clean_text(
        "campaign_name",
        campaign_name,
        "نام کمپین",
    )
    internal_note = _clean_text(
        "internal_note",
        internal_note,
        "یادداشت داخلی",
    )
    placement = _clean_placement(placement)
    is_permanent = bool(is_permanent)

    if is_permanent:
        expires_at = None
    elif (
        quick_link.is_permanent
        or quick_link.expires_at is None
        or quick_link.expires_at <= timezone.now()
    ):
        expires_at = _fresh_expiry()
    else:
        expires_at = quick_link.expires_at

    quick_link.title = title
    quick_link.placement = placement
    quick_link.campaign_name = campaign_name
    quick_link.internal_note = internal_note
    quick_link.is_permanent = is_permanent
    quick_link.expires_at = expires_at

    quick_link.save(
        update_fields=[
            "title",
            "placement",
            "campaign_name",
            "internal_note",
            "is_permanent",
            "expires_at",
            "updated_at",
        ]
    )

    return quick_link, "مشخصات لینک رزرو ذخیره شد."


@transaction.atomic
def clone_booking_quick_link(*, links_queryset, link_id, creator):
    source = _locked_link(
        links_queryset=links_queryset,
        link_id=link_id,
    )

    max_length = BookingQuickLink._meta.get_field(
        "title"
    ).max_length
    title = f"کپی {source.title or source.get_mode_display()}"

    if max_length:
        title = title[:max_length]

    cloned = BookingQuickLink.objects.create(
        creator=creator,
        salon=source.salon,
        service=source.service,
        stylist=source.stylist,
        title=title,
        mode=source.mode,
        payload=deepcopy(
            source.payload
            if isinstance(source.payload, dict)
            else {}
        ),
        placement=source.placement,
        campaign_name=source.campaign_name,
        internal_note=source.internal_note,
        is_permanent=source.is_permanent,
        is_active=True,
        expires_at=(
            None
            if source.is_permanent
            else _fresh_expiry()
        ),
    )

    return cloned, "یک نسخه مستقل از لینک ساخته شد."


def _has_history(quick_link):
    if any(
        (
            int(quick_link.opens_count or 0) > 0,
            int(quick_link.bookings_count or 0) > 0,
            bool(quick_link.last_opened_at),
            bool(quick_link.last_converted_at),
            bool(quick_link.used_at),
            bool(quick_link.used_order_id),
        )
    ):
        return True

    if quick_link.attributed_orders.exists():
        return True

    content_type = ContentType.objects.get_for_model(
        BookingQuickLink,
        for_concrete_model=False,
    )

    return AnalyticsEvent.objects.filter(
        target_content_type=content_type,
        target_object_id=quick_link.pk,
    ).exists()


@transaction.atomic
def change_booking_quick_link_status(
    *,
    links_queryset,
    link_id,
    action,
):
    quick_link = _locked_link(
        links_queryset=links_queryset,
        link_id=link_id,
    )
    action = str(action or "").strip().lower()

    if action == "disable":
        if quick_link.archived_at:
            raise ValidationError(
                "لینک بایگانی‌شده قابل تغییر وضعیت نیست."
            )
        quick_link.mark_disabled()
        return quick_link, "لینک رزرو غیرفعال شد."

    if action == "enable":
        if quick_link.archived_at:
            raise ValidationError(
                "لینک بایگانی‌شده را نمی‌توان دوباره فعال کرد."
            )
        quick_link.mark_enabled()
        return quick_link, "لینک رزرو دوباره فعال شد."

    if action == "archive":
        if not quick_link.archived_at:
            quick_link.mark_archived()
        return quick_link, "لینک رزرو بایگانی شد و سابقه آن حفظ شد."

    if action == "delete":
        if _has_history(quick_link):
            if not quick_link.archived_at:
                quick_link.mark_archived()
            return (
                quick_link,
                "این لینک سابقه فعالیت دارد؛ به‌جای حذف، بایگانی شد.",
            )

        quick_link.delete()
        return None, "لینک بدون سابقه برای همیشه حذف شد."

    raise ValidationError("عملیات مدیریت لینک رزرو معتبر نیست.")
