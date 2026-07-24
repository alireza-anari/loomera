from __future__ import annotations

import json
from typing import Any

from django.conf import settings


def absolute_uri(request, path_or_url: str) -> str:
    if not path_or_url:
        return request.build_absolute_uri("/")
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return request.build_absolute_uri(path_or_url)


def image_absolute_uri(request, image_field) -> str:
    try:
        if image_field and getattr(image_field, "url", ""):
            return request.build_absolute_uri(image_field.url)
    except Exception:
        return ""
    return ""


def json_dumps(data: dict[str, Any] | list[dict[str, Any]]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def build_breadcrumb_schema(request, items: list[tuple[str, str]]) -> str:
    return json_dumps(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": name,
                    "item": absolute_uri(request, url),
                }
                for index, (name, url) in enumerate(items, start=1)
            ],
        }
    )


def build_salon_schema(request, salon, average_score=0, total_reviews=0, services=None) -> str:
    schema: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "BeautySalon",
        "name": salon.salon_name,
        "description": salon.effective_seo_description,
        "url": absolute_uri(request, salon.get_absolute_url()),
    }

    image_url = image_absolute_uri(request, salon.og_image) or image_absolute_uri(request, salon.banner_image)
    if image_url:
        schema["image"] = image_url

    if salon.address or salon.neighborhood_id or salon.zone:
        schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": salon.address or "",
            "addressLocality": salon.neighborhood.name if salon.neighborhood_id else "",
            "addressRegion": f"منطقه {salon.zone}" if salon.zone else "",
            "addressCountry": "IR",
        }

    if salon.phone_number:
        schema["telephone"] = str(salon.phone_number)

    if getattr(salon, "location", None):
        try:
            schema["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": salon.location.y,
                "longitude": salon.location.x,
            }
        except Exception:
            pass

    if average_score and total_reviews:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": str(average_score),
            "reviewCount": int(total_reviews),
            "bestRating": "5",
            "worstRating": "1",
        }

    if services:
        schema["makesOffer"] = [
            {
                "@type": "Offer",
                "itemOffered": {
                    "@type": "Service",
                    "name": service.service_name,
                },
            }
            for service in list(services)[:10]
        ]

    return json_dumps(schema)


def build_service_schema(request, service) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": service.service_name,
        "description": service.effective_seo_description,
        "url": absolute_uri(request, service.get_absolute_url()),
        "provider": {"@type": "Organization", "name": getattr(settings, "BRAND_DISPLAY_NAME", "Loomera")},
    }
    image_url = image_absolute_uri(request, service.service_image)
    if image_url:
        data["image"] = image_url
    return json_dumps(data)
