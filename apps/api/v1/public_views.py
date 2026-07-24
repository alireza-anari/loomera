from __future__ import annotations

from django.conf import settings
from django.db.models import Avg, Count, Min, Q
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.accounts.models import Stylist
from apps.salons.models import Salon
from apps.services.models import Services
from apps.stylists.profile_services import (
    can_show_stylist_on_salon_profile,
    public_salon_membership_prefetch,
)

from .public_serializers import (
    serialize_public_salon_card,
    serialize_public_salon_detail,
    serialize_public_service,
    serialize_public_stylist,
)
from .responses import api_error, api_success


def _query_string_too_large(request) -> bool:
    max_chars = int(getattr(settings, "LOOMERA_API_PUBLIC_QUERY_MAX_CHARS", 256) or 256)
    query_string = request.META.get("QUERY_STRING") or ""
    return len(query_string) > max_chars


def _clean_limit(request, *, default: int = 20) -> int:
    max_limit = int(getattr(settings, "LOOMERA_API_PUBLIC_LIST_MAX_LIMIT", 50) or 50)
    raw_limit = str(request.GET.get("limit") or default).strip()

    if not raw_limit.isdigit():
        return default

    return max(1, min(int(raw_limit), max_limit))


def _clean_offset(request) -> int:
    raw_offset = str(request.GET.get("offset") or "0").strip()
    if not raw_offset.isdigit():
        return 0
    return max(0, int(raw_offset))


def _public_salon_queryset():
    return (
        Salon.objects.filter(is_active=True)
        .select_related("neighborhood")
        .annotate(
            api_avg_score=Avg("scoring_salon__score"),
            api_services_count=Count(
                "services",
                filter=Q(services__is_active=True),
                distinct=True,
            ),
            api_stylists_count=Count(
                "stylists",
                filter=Q(stylists__is_active=True),
                distinct=True,
            ),
        )
        .order_by("salon_name", "id")
    )


def _get_public_salon_by_slug(salon_slug: str):
    return _public_salon_queryset().filter(slug=salon_slug).first()


def _public_salon_services_queryset(salon):
    return (
        Services.objects.filter(
            is_active=True,
            services_of_salon=salon,
        )
        .prefetch_related("service_group")
        .annotate(api_min_price=Min("service_prices__price"))
        .distinct()
        .order_by("service_name", "id")
    )


def _public_platform_services_queryset():
    return (
        Services.objects.filter(
            is_active=True,
            is_platform_catalog=True,
        )
        .prefetch_related("service_group")
        .annotate(api_min_price=Min("service_prices__price"))
        .distinct()
        .order_by("service_name", "id")
    )


class PublicSalonListAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        if _query_string_too_large(request):
            return api_error(
                "query_too_large",
                "حجم فیلترهای API بیش از حد مجاز است.",
                status=400,
            )

        query = str(request.GET.get("q") or "").strip()
        limit = _clean_limit(request)
        offset = _clean_offset(request)

        salons = _public_salon_queryset()
        if query:
            salons = salons.filter(
                Q(salon_name__icontains=query)
                | Q(description__icontains=query)
                | Q(address__icontains=query)
                | Q(neighborhood__name__icontains=query)
            )

        total = salons.count()
        items = salons[offset : offset + limit]

        return api_success(
            [serialize_public_salon_card(salon, request=request) for salon in items],
            meta={
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_next": offset + limit < total,
                }
            },
        )


class PublicSalonDetailAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, salon_slug: str, *args, **kwargs):
        if _query_string_too_large(request):
            return api_error(
                "query_too_large",
                "حجم فیلترهای API بیش از حد مجاز است.",
                status=400,
            )

        salon = _get_public_salon_by_slug(salon_slug)
        if salon is None:
            return api_error(
                "salon_not_found",
                "سالن پیدا نشد.",
                status=404,
            )

        services_count = _public_salon_services_queryset(salon).count()
        stylists_count = _visible_stylists_for_salon(salon).count()

        return api_success(
            serialize_public_salon_detail(
                salon,
                request=request,
                services_count=services_count,
                stylists_count=stylists_count,
            )
        )


class PublicSalonServicesAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, salon_slug: str, *args, **kwargs):
        if _query_string_too_large(request):
            return api_error(
                "query_too_large",
                "حجم فیلترهای API بیش از حد مجاز است.",
                status=400,
            )

        salon = _get_public_salon_by_slug(salon_slug)
        if salon is None:
            return api_error(
                "salon_not_found",
                "سالن پیدا نشد.",
                status=404,
            )

        query = str(request.GET.get("q") or "").strip()
        limit = _clean_limit(request, default=30)
        offset = _clean_offset(request)

        services = _public_salon_services_queryset(salon)
        if query:
            services = services.filter(
                Q(service_name__icontains=query)
                | Q(summery_description__icontains=query)
                | Q(description__icontains=query)
            )

        total = services.count()
        items = services[offset : offset + limit]

        return api_success(
            [serialize_public_service(service, request=request) for service in items],
            meta={
                "salon": {
                    "id": salon.pk,
                    "slug": salon.slug,
                    "name": salon.salon_name,
                },
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_next": offset + limit < total,
                },
            },
        )


def _visible_stylists_for_salon(salon):
    return (
        salon.stylists.filter(is_active=True)
        .select_related("user")
        .prefetch_related(
            public_salon_membership_prefetch(salon=salon),
        )
        .distinct()
        .order_by(
            "display_name",
            "user__name",
            "user__family",
            "pk",
        )
    )


class PublicSalonStylistsAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, salon_slug: str, *args, **kwargs):
        if _query_string_too_large(request):
            return api_error(
                "query_too_large",
                "حجم فیلترهای API بیش از حد مجاز است.",
                status=400,
            )

        salon = _get_public_salon_by_slug(salon_slug)
        if salon is None:
            return api_error(
                "salon_not_found",
                "سالن پیدا نشد.",
                status=404,
            )

        visible_stylists = []
        for stylist in _visible_stylists_for_salon(salon):
            access = can_show_stylist_on_salon_profile(
                salon=salon,
                stylist=stylist,
                legacy_membership_confirmed=True,
            )
            if access.allowed:
                visible_stylists.append(stylist)

        total = len(visible_stylists)
        limit = _clean_limit(request, default=30)
        offset = _clean_offset(request)
        items = visible_stylists[offset : offset + limit]

        return api_success(
            [serialize_public_stylist(stylist, request=request) for stylist in items],
            meta={
                "salon": {
                    "id": salon.pk,
                    "slug": salon.slug,
                    "name": salon.salon_name,
                },
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_next": offset + limit < total,
                },
            },
        )


class PublicServiceCatalogAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        if _query_string_too_large(request):
            return api_error(
                "query_too_large",
                "حجم فیلترهای API بیش از حد مجاز است.",
                status=400,
            )

        query = str(request.GET.get("q") or "").strip()
        limit = _clean_limit(request, default=30)
        offset = _clean_offset(request)

        services = _public_platform_services_queryset()
        if query:
            services = services.filter(
                Q(service_name__icontains=query)
                | Q(summery_description__icontains=query)
                | Q(description__icontains=query)
            )

        total = services.count()
        items = services[offset : offset + limit]

        return api_success(
            [serialize_public_service(service, request=request) for service in items],
            meta={
                "pagination": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_next": offset + limit < total,
                }
            },
        )
