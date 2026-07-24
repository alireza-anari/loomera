from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.conf import settings


@dataclass(frozen=True)
class MapViewport:
    city: str
    lat: float
    lng: float
    zoom: int


DEFAULT_CITY = "تهران"
DEFAULT_LAT = 35.699739
DEFAULT_LNG = 51.338097
DEFAULT_ZOOM = 12


def get_default_viewport() -> MapViewport:
    return MapViewport(
        city=getattr(settings, "MAP_DEFAULT_CITY", DEFAULT_CITY),
        lat=float(getattr(settings, "MAP_DEFAULT_LAT", DEFAULT_LAT)),
        lng=float(getattr(settings, "MAP_DEFAULT_LNG", DEFAULT_LNG)),
        zoom=int(getattr(settings, "MAP_DEFAULT_ZOOM", DEFAULT_ZOOM)),
    )


def is_map_enabled() -> bool:
    provider = (getattr(settings, "MAP_PROVIDER", "mapir") or "").strip().lower()
    enabled = bool(getattr(settings, "MAP_ENABLED", True))
    api_key = bool(getattr(settings, "MAPIR_API_KEY", ""))
    return enabled and provider == "mapir" and api_key


def get_tehran_bounds() -> dict[str, float]:
    return {
        "min_lat": float(getattr(settings, "MAP_TEHRAN_MIN_LAT", 35.55)),
        "max_lat": float(getattr(settings, "MAP_TEHRAN_MAX_LAT", 35.88)),
        "min_lng": float(getattr(settings, "MAP_TEHRAN_MIN_LNG", 51.10)),
        "max_lng": float(getattr(settings, "MAP_TEHRAN_MAX_LNG", 51.65)),
    }


def is_within_tehran(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    bounds = get_tehran_bounds()
    return (
        bounds["min_lat"] <= float(lat) <= bounds["max_lat"]
        and bounds["min_lng"] <= float(lng) <= bounds["max_lng"]
    )


def get_map_context() -> dict[str, object]:
    viewport = get_default_viewport()
    bounds = get_tehran_bounds()
    return {
        "map_enabled": is_map_enabled(),
        "map_provider": (getattr(settings, "MAP_PROVIDER", "mapir") or "mapir").strip().lower(),
        "map_default_city": viewport.city,
        "map_default_lat": viewport.lat,
        "map_default_lng": viewport.lng,
        "map_default_zoom": viewport.zoom,
        "map_tehran_bounds": bounds,
    }


def build_neshan_desktop_url(lat: float | None = None, lng: float | None = None, zoom: int | None = None) -> str:
    viewport = get_default_viewport()
    route_zoom = int(zoom or viewport.zoom or DEFAULT_ZOOM)
    if lat is None or lng is None:
        lat = viewport.lat
        lng = viewport.lng
    return f"https://neshan.org/maps/@{float(lat):.6f},{float(lng):.6f},{route_zoom}z,0p"


def dedupe_suggestions(items: Iterable[dict], limit: int = 8) -> list[dict]:
    seen: set[tuple] = set()
    output: list[dict] = []
    for item in items:
        key = (
            (item.get("title") or "").strip(),
            (item.get("address") or "").strip(),
            item.get("lat"),
            item.get("lng"),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output
