from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.accounts.models import Stylist
from apps.orders.booking_utils import (
    DEFAULT_SLOT_STEP,
    get_available_slots_for_service,
    get_price_for_stylist_service,
    get_service_buffer_minutes,
    get_service_duration_minutes,
)
from apps.services.models import Services
from apps.stylists.profile_services import can_show_stylist_on_salon_profile

from .public_views import _get_public_salon_by_slug, _query_string_too_large
from .responses import api_error, api_success


def _clean_positive_int(value):
    raw_value = str(value or "").strip()
    if not raw_value.isdigit():
        return None
    parsed = int(raw_value)
    if parsed <= 0:
        return None
    return parsed


def _parse_api_date(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _date_allowed(date_value) -> bool:
    today = timezone.localdate()
    max_days = int(
        getattr(settings, "LOOMERA_API_AVAILABILITY_MAX_DAYS_AHEAD", 45) or 45
    )
    return today <= date_value <= today + timedelta(days=max_days)


def _clean_days(value, *, default: int = 7) -> int:
    max_days = int(getattr(settings, "LOOMERA_API_NEXT_AVAILABLE_MAX_DAYS", 14) or 14)
    raw_value = str(value or default).strip()

    if not raw_value.isdigit():
        return default

    parsed = int(raw_value)
    if parsed <= 0:
        return default

    return max(1, min(parsed, max_days))


def _serialize_next_available_slot(
    *, date_value, stylist, service, start_time, end_time
):
    return {
        "date": date_value.isoformat(),
        "start_time": start_time.strftime("%H:%M"),
        "end_time": end_time.strftime("%H:%M"),
        "stylist": {
            "id": stylist.pk,
            "display_name": stylist.professional_display_name,
            "expert": stylist.expert or "",
        },
        "price": int(get_price_for_stylist_service(stylist, service) or 0),
    }


def _find_next_available_slots(*, salon, service, stylists, start_date, days):
    results = []

    for day_offset in range(days):
        date_value = start_date + timedelta(days=day_offset)
        if not _date_allowed(date_value):
            break

        for stylist in stylists:
            slots = get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=date_value,
            )
            if not slots:
                continue

            start_time, end_time = slots[0]
            results.append(
                {
                    "date": date_value,
                    "start_time": start_time,
                    "end_time": end_time,
                    "stylist": stylist,
                }
            )

    results.sort(
        key=lambda item: (
            item["date"],
            item["start_time"],
            item["stylist"].pk,
        )
    )
    return results


def _public_service_for_salon(salon, service_id):
    parsed_service_id = _clean_positive_int(service_id)
    if parsed_service_id is None:
        return None

    return (
        Services.objects.filter(
            pk=parsed_service_id,
            is_active=True,
            services_of_salon=salon,
        )
        .prefetch_related("service_group")
        .first()
    )


def _visible_eligible_stylists(salon, service, *, stylist_id=None):
    stylists = (
        salon.stylists.filter(
            is_active=True,
            services_of_stylist=service,
        )
        .select_related("user")
        .distinct()
        .order_by("display_name", "user__name", "user__family", "pk")
    )

    parsed_stylist_id = None
    if stylist_id not in (None, "", "any"):
        parsed_stylist_id = _clean_positive_int(stylist_id)
        if parsed_stylist_id is None:
            return []
        stylists = stylists.filter(pk=parsed_stylist_id)

    visible = []
    for stylist in stylists:
        access = can_show_stylist_on_salon_profile(salon=salon, stylist=stylist)
        if access.allowed:
            visible.append(stylist)

    return visible


def _serialize_slot(start_time, end_time):
    return {
        "start_time": start_time.strftime("%H:%M"),
        "end_time": end_time.strftime("%H:%M"),
    }


def _serialize_availability_stylist(*, stylist, service, slots):
    return {
        "id": stylist.pk,
        "display_name": stylist.professional_display_name,
        "expert": stylist.expert or "",
        "price": int(get_price_for_stylist_service(stylist, service) or 0),
        "has_available_slots": bool(slots),
        "slots": [_serialize_slot(start, end) for start, end in slots],
    }


class PublicSalonAvailabilityAPIView(APIView):
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

        service = _public_service_for_salon(salon, request.GET.get("service_id"))
        if service is None:
            return api_error(
                "service_not_found",
                "خدمت پیدا نشد.",
                status=404,
            )

        date_value = _parse_api_date(request.GET.get("date"))
        if date_value is None:
            return api_error(
                "invalid_date",
                "تاریخ باید با فرمت YYYY-MM-DD ارسال شود.",
                status=400,
            )

        if not _date_allowed(date_value):
            return api_error(
                "date_out_of_range",
                "تاریخ انتخاب‌شده در بازه مجاز رزرو نیست.",
                status=400,
            )

        stylists = _visible_eligible_stylists(
            salon,
            service,
            stylist_id=request.GET.get("stylist_id"),
        )

        if request.GET.get("stylist_id") not in (None, "", "any") and not stylists:
            return api_error(
                "stylist_not_found",
                "متخصص پیدا نشد.",
                status=404,
            )

        max_slots = int(
            getattr(settings, "LOOMERA_API_AVAILABILITY_MAX_SLOTS_PER_STYLIST", 40)
            or 40
        )

        stylist_payload = []
        total_slots = 0

        for stylist in stylists:
            slots = get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=date_value,
            )
            slots = slots[:max_slots]
            total_slots += len(slots)
            stylist_payload.append(
                _serialize_availability_stylist(
                    stylist=stylist,
                    service=service,
                    slots=slots,
                )
            )

        return api_success(
            {
                "salon": {
                    "id": salon.pk,
                    "slug": salon.slug,
                    "name": salon.salon_name,
                },
                "service": {
                    "id": service.pk,
                    "slug": service.slug,
                    "name": service.service_name,
                    "duration_minutes": int(get_service_duration_minutes(service)),
                    "buffer_minutes": int(get_service_buffer_minutes(service)),
                },
                "date": date_value.isoformat(),
                "slot_step_minutes": DEFAULT_SLOT_STEP,
                "stylists": stylist_payload,
                "summary": {
                    "total_stylists": len(stylist_payload),
                    "total_slots": total_slots,
                },
            }
        )


class PublicSalonNextAvailableAPIView(APIView):
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

        service = _public_service_for_salon(salon, request.GET.get("service_id"))
        if service is None:
            return api_error(
                "service_not_found",
                "خدمت پیدا نشد.",
                status=404,
            )

        start_date = _parse_api_date(request.GET.get("date")) or timezone.localdate()
        if not _date_allowed(start_date):
            return api_error(
                "date_out_of_range",
                "تاریخ شروع در بازه مجاز رزرو نیست.",
                status=400,
            )

        days = _clean_days(request.GET.get("days"))

        stylists = _visible_eligible_stylists(
            salon,
            service,
            stylist_id=request.GET.get("stylist_id"),
        )

        if request.GET.get("stylist_id") not in (None, "", "any") and not stylists:
            return api_error(
                "stylist_not_found",
                "متخصص پیدا نشد.",
                status=404,
            )

        next_slots = _find_next_available_slots(
            salon=salon,
            service=service,
            stylists=stylists,
            start_date=start_date,
            days=days,
        )

        next_available = None
        if next_slots:
            first = next_slots[0]
            next_available = _serialize_next_available_slot(
                date_value=first["date"],
                stylist=first["stylist"],
                service=service,
                start_time=first["start_time"],
                end_time=first["end_time"],
            )

        per_stylist = []
        by_stylist_id = {}
        for item in next_slots:
            stylist_id = item["stylist"].pk
            if stylist_id not in by_stylist_id:
                by_stylist_id[stylist_id] = item

        for stylist in stylists:
            item = by_stylist_id.get(stylist.pk)
            per_stylist.append(
                {
                    "id": stylist.pk,
                    "display_name": stylist.professional_display_name,
                    "expert": stylist.expert or "",
                    "next_available": (
                        _serialize_next_available_slot(
                            date_value=item["date"],
                            stylist=stylist,
                            service=service,
                            start_time=item["start_time"],
                            end_time=item["end_time"],
                        )
                        if item
                        else None
                    ),
                }
            )

        return api_success(
            {
                "salon": {
                    "id": salon.pk,
                    "slug": salon.slug,
                    "name": salon.salon_name,
                },
                "service": {
                    "id": service.pk,
                    "slug": service.slug,
                    "name": service.service_name,
                    "duration_minutes": int(get_service_duration_minutes(service)),
                    "buffer_minutes": int(get_service_buffer_minutes(service)),
                },
                "search": {
                    "start_date": start_date.isoformat(),
                    "days": days,
                    "stylist_id": request.GET.get("stylist_id") or None,
                },
                "next_available": next_available,
                "stylists": per_stylist,
                "summary": {
                    "total_stylists": len(stylists),
                    "has_available_slot": bool(next_available),
                },
            }
        )
