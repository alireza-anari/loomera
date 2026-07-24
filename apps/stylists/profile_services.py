from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Avg, Count, Prefetch, Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Stylist, WorkSamples
from apps.comments_scores_favories.models import Comments, Scoring
from apps.orders.models import Order, OrderDetail
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services

PUBLIC_WORK_STATUSES = {"published", "approved"}
COMPLETED_LIFECYCLE = getattr(
    OrderDetail.ServiceLifecycleStatus, "COMPLETED", "completed"
)

PUBLIC_WORK_SAMPLE_ALLOWED_CLIENT_CONSENT_STATUSES = {
    "",
    "not_required",
    "approved",
    "granted",
    "obtained",
    "consented",
}


def _public_work_sample_client_consent_filter():
    return Q(contains_identifiable_client=False) | Q(
        client_consent_status__in=PUBLIC_WORK_SAMPLE_ALLOWED_CLIENT_CONSENT_STATUSES
    )


def _public_work_sample_salon_scope_filter(salon):
    return (
        Q(salon=salon)
        | Q(salon__isnull=True, appointment__isnull=True)
        | Q(salon__isnull=True, appointment__salon=salon)
    )


@dataclass(frozen=True)
class StylistProfileAccess:
    allowed: bool
    reason: str = ""
    membership: SalonMembership | None = None


PUBLIC_SALON_MEMBERSHIPS_ATTR = "_public_salon_memberships"


def public_salon_membership_prefetch(*, salon: Salon) -> Prefetch:
    """Prefetch only memberships relevant to one public salon context."""

    return Prefetch(
        "salon_memberships",
        queryset=SalonMembership.objects.filter(salon=salon).select_related(
            "salon",
            "stylist__user",
        ),
        to_attr=PUBLIC_SALON_MEMBERSHIPS_ATTR,
    )


def get_salon_membership(*, salon: Salon, stylist: Stylist) -> SalonMembership | None:
    """Return the salon membership without querying when it was prefetched."""

    prefetched_memberships = getattr(
        stylist,
        PUBLIC_SALON_MEMBERSHIPS_ATTR,
        None,
    )

    if prefetched_memberships is not None:
        for membership in prefetched_memberships:
            if membership.salon_id == salon.pk:
                return membership
        return None

    return (
        SalonMembership.objects.filter(
            salon=salon,
            stylist=stylist,
        )
        .select_related(
            "salon",
            "stylist__user",
        )
        .first()
    )


def can_show_stylist_on_salon_profile(
    *,
    salon: Salon,
    stylist: Stylist,
    legacy_membership_confirmed: bool = False,
) -> StylistProfileAccess:
    if not stylist or not salon:
        return StylistProfileAccess(False, "not_found")

    if not getattr(stylist, "is_active", False):
        return StylistProfileAccess(False, "stylist_inactive")

    if not getattr(stylist, "is_visible_on_salon_pages", False):
        return StylistProfileAccess(False, "profile_hidden")

    membership = get_salon_membership(salon=salon, stylist=stylist)
    if membership:
        if membership.status != SalonMembershipStatus.ACTIVE:
            return StylistProfileAccess(False, "membership_not_active", membership)
        if not membership.show_on_salon_profile:
            return StylistProfileAccess(False, "membership_hidden", membership)
        return StylistProfileAccess(True, membership=membership)

    # Callers loading stylists directly through salon.stylists have already
    # confirmed the legacy ManyToMany relation and do not need another query.
    if legacy_membership_confirmed:
        return StylistProfileAccess(True, reason="legacy_membership")

    # Backward compatibility for callers without a prepared salon context.
    if salon.stylists.filter(pk=stylist.pk, is_active=True).exists():
        return StylistProfileAccess(True, reason="legacy_membership")

    return StylistProfileAccess(False, "not_member")


def get_stylist_services_for_salon(*, salon: Salon, stylist: Stylist):
    return (
        Services.objects.filter(
            is_active=True, services_of_salon=salon, stylists=stylist
        )
        .prefetch_related("service_group", "service_prices")
        .annotate(avg_score=Avg("scoring_services__score"))
        .distinct()
        .order_by("service_name", "id")
    )


def get_public_work_samples(
    *, stylist: Stylist, salon: Salon | None = None, limit: int | None = None
):
    qs = (
        WorkSamples.objects.filter(
            stylist=stylist,
            is_active=True,
            is_public=True,
            review_status__in=PUBLIC_WORK_STATUSES,
        )
        .filter(_public_work_sample_client_consent_filter())
        .select_related("service", "salon", "appointment")
        .order_by("-is_verified_work", "-id")
    )

    if salon is not None:
        qs = qs.filter(_public_work_sample_salon_scope_filter(salon))

    return qs[:limit] if limit else qs


def get_stylist_reviews(
    *, stylist: Stylist, salon: Salon | None = None, limit: int | None = None
):
    qs = (
        Comments.objects.filter(stylist=stylist, is_active=True)
        .select_related("comment_user__user", "service", "salon", "scoring")
        .order_by("-register_date", "-id")
    )
    if salon is not None:
        qs = qs.filter(salon=salon)
    return qs[:limit] if limit else qs


def get_stylist_rating_summary(
    *, stylist: Stylist, salon: Salon | None = None
) -> dict[str, Any]:
    scores_qs = Scoring.objects.filter(
        stylist=stylist, score__gt=0, comment__is_active=True
    )
    if salon is not None:
        scores_qs = scores_qs.filter(salon=salon)

    aggregate = scores_qs.aggregate(average=Avg("score"), count=Count("id"))
    average = (
        round(float(aggregate.get("average") or 0), 1)
        if aggregate.get("average")
        else 0
    )
    count = int(aggregate.get("count") or 0)
    return {"average": average, "count": count}


def get_completed_appointment_count(
    *, stylist: Stylist, salon: Salon | None = None
) -> int:
    qs = OrderDetail.objects.filter(
        stylist=stylist,
    ).filter(Q(lifecycle_status=COMPLETED_LIFECYCLE) | Q(order__status="completed"))
    if salon is not None:
        qs = qs.filter(salon=salon)
    return qs.distinct().count()


def build_resume_snapshot(
    stylist: Stylist, *, salon: Salon | None = None
) -> dict[str, Any]:
    salon_rating = (
        get_stylist_rating_summary(stylist=stylist, salon=salon) if salon else None
    )
    overall_rating = get_stylist_rating_summary(stylist=stylist)
    services = []
    if salon:
        services = [
            service.service_name
            for service in get_stylist_services_for_salon(salon=salon, stylist=stylist)[
                :20
            ]
        ]

    samples = []
    for sample in get_public_work_samples(stylist=stylist, salon=salon, limit=8):
        image_url = ""
        try:
            image_url = sample.sample_image.url if sample.sample_image else ""
        except Exception:
            image_url = ""
        samples.append(
            {
                "id": sample.id,
                "service": sample.service.service_name if sample.service else "",
                "is_verified_work": bool(sample.is_verified_work),
                "image_url": image_url,
            }
        )

    return {
        "generated_at": timezone.now().isoformat(),
        "stylist_id": stylist.pk,
        "display_name": stylist.professional_display_name,
        "headline": stylist.resume_headline or stylist.expert or "",
        "summary": stylist.resume_summary or stylist.description or "",
        "expert": stylist.expert or "",
        "started_working_year": stylist.started_working_year,
        "public_visibility": stylist.public_visibility,
        "overall_rating": overall_rating,
        "salon_rating": salon_rating,
        "completed_appointments": {
            "overall": get_completed_appointment_count(stylist=stylist),
            "in_salon": (
                get_completed_appointment_count(stylist=stylist, salon=salon)
                if salon
                else None
            ),
        },
        "services": services,
        "portfolio_samples": samples,
    }


def build_salon_stylist_profile_context(
    *, salon: Salon, stylist: Stylist, request=None
) -> dict[str, Any]:
    access = can_show_stylist_on_salon_profile(salon=salon, stylist=stylist)
    services = list(get_stylist_services_for_salon(salon=salon, stylist=stylist))
    portfolio = list(get_public_work_samples(stylist=stylist, salon=salon, limit=24))
    verified_portfolio = [
        sample
        for sample in portfolio
        if sample.is_verified_work or sample.appointment_id
    ]
    reviews = list(get_stylist_reviews(stylist=stylist, salon=salon, limit=12))
    rating_in_salon = get_stylist_rating_summary(stylist=stylist, salon=salon)
    overall_rating = get_stylist_rating_summary(stylist=stylist)
    completed_in_salon = get_completed_appointment_count(stylist=stylist, salon=salon)
    completed_overall = get_completed_appointment_count(stylist=stylist)

    service_cards = []
    for service in services:
        service_cards.append(
            {
                "service": service,
                "booking_url": f"{reverse('orders:select_stylists')}?salon_id={salon.id}&selected_services={service.id}",
            }
        )

    return {
        "salon": salon,
        "stylist": stylist,
        "membership": access.membership,
        "services": services,
        "service_cards": service_cards,
        "portfolio_items": portfolio,
        "verified_portfolio_items": verified_portfolio,
        "reviews": reviews,
        "rating_in_salon": rating_in_salon,
        "overall_rating": overall_rating,
        "completed_in_salon": completed_in_salon,
        "completed_overall": completed_overall,
        "resume_snapshot": build_resume_snapshot(stylist, salon=salon),
        "book_with_stylist_url": reverse("salons:detail_salon", args=[salon.id])
        + "#services",
        "hide_navbar": True,
    }
