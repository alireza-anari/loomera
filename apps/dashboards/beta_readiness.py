from __future__ import annotations

from django.db.models import Count, Exists, F, OuterRef, Q
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.dashboards.readiness import (
    PUBLIC_BOOKING_STYLIST_VISIBILITIES,
    build_salon_readiness_checklist,
)
from apps.salons.models import SalonOpeningHours, SalonsGallery
from apps.services.models import Services
from apps.stylists.models import StylistSchedule

CRITICAL_BETA_READINESS_KEYS = {
    "profile",
    "location",
    "services",
    "team",
    "stylist_services",
    "schedule",
    "bookable_path",
    "opening_hours",
    "public_active",
}


def _bookable_path_state(readiness):
    if "has_bookable_path" in readiness:
        return bool(readiness["has_bookable_path"])

    for item in readiness.get("items", []):
        if item.get("key") == "bookable_path":
            return bool(item.get("is_done"))

    return False


BETA_READINESS_ANNOTATION_MAP = {
    "active_services_count": "_beta_active_services_count",
    "priced_services_count": "_beta_priced_services_count",
    "active_stylists_count": "_beta_active_stylists_count",
    "has_stylist_service_link": "_beta_has_stylist_service_link",
    "schedule_exists": "_beta_schedule_exists",
    "has_bookable_path": "_beta_has_bookable_path",
    "has_gallery": "_beta_has_gallery",
    "has_opening_hours": "_beta_has_opening_hours",
}


def with_beta_readiness_annotations(queryset):
    """Attach all database-backed readiness facts to a Salon queryset.

    The annotations allow readiness serialization for multiple salons without
    running a separate set of queries for every salon.
    """

    today = timezone.localdate()

    stylist_service_link_exists = Services.objects.filter(
        services_of_salon__pk=OuterRef("pk"),
        is_active=True,
        stylists__is_active=True,
        stylists__stylists_of_salon__pk=OuterRef("pk"),
    )

    future_schedule_exists = StylistSchedule.objects.filter(
        salon_id=OuterRef("pk"),
        date__gte=today,
        stylist__is_active=True,
        stylist__public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
    )

    bookable_path_exists = StylistSchedule.objects.filter(
        salon_id=OuterRef("pk"),
        date__gte=today,
        stylist__is_active=True,
        stylist__public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
        stylist__services_of_stylist__is_active=True,
        stylist__services_of_stylist__base_price__gt=0,
        stylist__services_of_stylist__duration_minutes__gt=0,
        stylist__services_of_stylist__services_of_salon__pk=OuterRef("pk"),
    ).filter(
        Q(service__isnull=True) | Q(service_id=F("stylist__services_of_stylist__id"))
    )

    return queryset.annotate(
        _beta_active_services_count=Count(
            "services",
            filter=Q(services__is_active=True),
            distinct=True,
        ),
        _beta_priced_services_count=Count(
            "services",
            filter=Q(
                services__is_active=True,
                services__base_price__gt=0,
                services__duration_minutes__gt=0,
            ),
            distinct=True,
        ),
        _beta_active_stylists_count=Count(
            "stylists",
            filter=Q(stylists__is_active=True),
            distinct=True,
        ),
        _beta_has_stylist_service_link=Exists(stylist_service_link_exists),
        _beta_schedule_exists=Exists(future_schedule_exists),
        _beta_has_bookable_path=Exists(bookable_path_exists),
        _beta_has_gallery=Exists(SalonsGallery.objects.filter(salon_id=OuterRef("pk"))),
        _beta_has_opening_hours=Exists(
            SalonOpeningHours.objects.filter(
                salon_id=OuterRef("pk"),
                is_closed=False,
                open_time__isnull=False,
                close_time__isnull=False,
            )
        ),
    )


def _readiness_facts_from_salon(salon):
    """Return readiness facts only when the queryset supplied all annotations."""

    if not all(
        hasattr(salon, annotation_name)
        for annotation_name in BETA_READINESS_ANNOTATION_MAP.values()
    ):
        return None

    return {
        fact_name: getattr(salon, annotation_name)
        for fact_name, annotation_name in BETA_READINESS_ANNOTATION_MAP.items()
    }


def serialize_beta_salon_readiness(salon):
    """Return a sanitized, read-only beta readiness summary for one salon."""

    readiness = build_salon_readiness_checklist(
        salon,
        facts=_readiness_facts_from_salon(salon),
    )

    missing_items = []

    for item in readiness.get("missing_items", []):
        key = str(item.get("key") or "")

        missing_items.append(
            {
                "key": key,
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
                "action_label": str(item.get("action_label") or ""),
                "action_url": str(item.get("action_url") or ""),
                "weight": int(item.get("weight") or 0),
                "is_critical": (key in CRITICAL_BETA_READINESS_KEYS),
            }
        )

    missing_keys = [item["key"] for item in missing_items if item["key"]]

    critical_missing_keys = [
        key for key in missing_keys if key in CRITICAL_BETA_READINESS_KEYS
    ]

    critical_missing_items = [item for item in missing_items if item["is_critical"]]

    has_bookable_path = _bookable_path_state(readiness)
    checklist_ready = bool(readiness.get("is_ready"))

    beta_ready = checklist_ready and has_bookable_path and not critical_missing_keys

    primary_blocker = None

    if critical_missing_items:
        primary_blocker = critical_missing_items[0]
    elif missing_items:
        primary_blocker = missing_items[0]

    return {
        "salon_id": salon.pk,
        "salon_name": str(salon.salon_name or ""),
        "slug": str(salon.slug or ""),
        "is_active": bool(salon.is_active),
        "verification_status": str(salon.verification_status or ""),
        "readiness_percent": int(readiness.get("percent") or 0),
        "readiness_percent_label": str(readiness.get("percent_label") or "۰٪"),
        "completed_count": int(readiness.get("completed_count") or 0),
        "total_count": int(readiness.get("total_count") or 0),
        "missing_count": len(missing_items),
        "has_bookable_path": has_bookable_path,
        "checklist_ready": checklist_ready,
        "beta_ready": beta_ready,
        "status_label": ("آماده بتا" if beta_ready else "نیازمند تکمیل"),
        "status_tone": ("success" if beta_ready else "warning"),
        "critical_missing_keys": critical_missing_keys,
        "critical_missing_count": len(critical_missing_items),
        "missing_items": missing_items,
        "primary_blocker": primary_blocker,
        "summary": str(readiness.get("summary") or ""),
    }


def summarize_beta_salon_readiness(salons):
    total = len(salons)

    ready = sum(1 for salon in salons if salon["beta_ready"])

    incomplete = total - ready

    without_bookable_path = sum(1 for salon in salons if not salon["has_bookable_path"])

    return {
        "total": total,
        "ready": ready,
        "incomplete": incomplete,
        "without_bookable_path": without_bookable_path,
        "all_ready": bool(total) and incomplete == 0,
    }
