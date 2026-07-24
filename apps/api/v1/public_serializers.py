from __future__ import annotations

from typing import Any


def _safe_media_url(file_field, *, request=None) -> str:
    if not file_field:
        return ""

    try:
        url = file_field.url or ""
    except Exception:
        return ""

    if request is not None and url.startswith("/"):
        return request.build_absolute_uri(url)

    return url


def _short_text(value: str | None, *, max_length: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}…"


def serialize_service_group(group) -> dict[str, Any]:
    return {
        "id": group.pk,
        "slug": group.slug,
        "title": group.group_title,
    }


def serialize_public_service(service, *, request=None) -> dict[str, Any]:
    min_price = getattr(service, "api_min_price", None)
    price_from = min_price if min_price is not None else service.base_price

    return {
        "id": service.pk,
        "slug": service.slug,
        "name": service.service_name,
        "summary": _short_text(service.summery_description, max_length=220),
        "duration_minutes": int(service.duration_minutes or 0),
        "buffer_minutes": int(service.buffer_minutes or 0),
        "base_price": int(service.base_price or 0),
        "price_from": int(price_from or 0),
        "image_url": _safe_media_url(service.service_image, request=request),
        "groups": [
            serialize_service_group(group)
            for group in service.service_group.all()
            if getattr(group, "is_active", False)
        ],
    }


def serialize_public_salon_card(salon, *, request=None) -> dict[str, Any]:
    neighborhood = getattr(salon, "neighborhood", None)

    return {
        "id": salon.pk,
        "slug": salon.slug,
        "name": salon.salon_name,
        "summary": _short_text(salon.description, max_length=220),
        "address": str(salon.address or "").strip(),
        "zone": salon.zone,
        "neighborhood": (
            {
                "id": neighborhood.pk,
                "name": str(neighborhood),
            }
            if neighborhood
            else None
        ),
        "banner_image_url": _safe_media_url(salon.banner_image, request=request),
        "rating": {
            "average": getattr(salon, "api_avg_score", None),
        },
        "counts": {
            "services": int(getattr(salon, "api_services_count", 0) or 0),
            "stylists": int(getattr(salon, "api_stylists_count", 0) or 0),
        },
    }


def serialize_public_salon_detail(
    salon,
    *,
    request=None,
    services_count: int = 0,
    stylists_count: int = 0,
) -> dict[str, Any]:
    data = serialize_public_salon_card(salon, request=request)
    data.update(
        {
            "description": str(salon.description or "").strip(),
            "seo": {
                "title": salon.effective_seo_title,
                "description": salon.effective_seo_description,
            },
            "counts": {
                "services": int(services_count or 0),
                "stylists": int(stylists_count or 0),
            },
        }
    )
    return data


def serialize_public_stylist(stylist, *, request=None) -> dict[str, Any]:
    return {
        "id": stylist.pk,
        "display_name": stylist.professional_display_name,
        "expert": stylist.expert or "",
        "headline": stylist.resume_headline or stylist.expert or "",
        "is_verified_professional": bool(stylist.is_verified_professional),
        "profile_image_url": _safe_media_url(stylist.profile_image, request=request),
    }
