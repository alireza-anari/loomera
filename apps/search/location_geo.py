import json
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET


_PERSIAN_DIGITS_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
)


def _normalize_location_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return " ".join(text.replace("ي", "ی").replace("ك", "ک").split())


def _walk_reverse_payload_values(payload, wanted_keys):
    wanted = {str(key).lower() for key in wanted_keys}
    seen = set()

    def walk(value):
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in wanted:
                    normalized = _normalize_location_text(item)
                    if normalized:
                        yield normalized
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    yield from walk(payload)


def _first_reverse_value(payload, keys):
    for key in keys:
        for value in _walk_reverse_payload_values(payload, [key]):
            return value
    return ""


def _extract_reverse_geocode_city(payload):
    return _first_reverse_value(
        payload,
        [
            "city",
            "city_name",
            "town",
            "municipality",
            "شهر",
            "locality",
            "county",
        ],
    )


def _extract_reverse_geocode_neighborhood(payload):
    city = _extract_reverse_geocode_city(payload).casefold()
    priority_groups = [
        ["neighbourhood", "neighborhood", "neighborhood_name", "neighbourhood_name", "محله"],
        ["mahale", "quarter", "suburb"],
        ["locality"],
    ]
    for keys in priority_groups:
        for key in keys:
            for value in _walk_reverse_payload_values(payload, [key]):
                if city and value.casefold() == city:
                    continue
                return value
    return ""


def _extract_reverse_geocode_zone(payload):
    city = _extract_reverse_geocode_city(payload).casefold()
    keys = [
        "municipal_zone",
        "municipality_zone",
        "city_district",
        "district",
        "zone",
        "منطقه",
        "region",
    ]

    for key in keys:
        for value in _walk_reverse_payload_values(payload, [key]):
            normalized = _normalize_location_text(value)
            compact = normalized.casefold()
            if city and compact == city:
                continue

            translated = normalized.translate(_PERSIAN_DIGITS_TRANSLATION)
            digits = "".join(ch for ch in translated if ch.isdigit())
            if digits:
                try:
                    number = int(digits)
                except ValueError:
                    continue
                if 1 <= number <= 99:
                    label = normalized if any(ch for ch in normalized if not ch.isdigit() and not ch.isspace()) else f"منطقه {number}"
                    return number, label
                continue

            # `region` is commonly a province/city-level value. Only accept it
            # as a district when its text explicitly looks like a sub-city area.
            if key == "region" and not any(
                token in normalized.casefold()
                for token in ("منطقه", "ناحیه", "بخش", "district", "zone")
            ):
                continue

            if normalized and not normalized.startswith("استان "):
                return "", normalized

    return "", ""


def _extract_coordinates(item):
    if not isinstance(item, dict):
        return None
    geom = item.get("geom") or item.get("geometry") or {}
    coordinates = geom.get("coordinates") if isinstance(geom, dict) else None
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        return None
    try:
        lon = float(coordinates[0])
        lat = float(coordinates[1])
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _city_result_label(item, fallback=""):
    if not isinstance(item, dict):
        return _normalize_location_text(fallback)
    for key in ("city", "title", "name", "text"):
        value = _normalize_location_text(item.get(key))
        if value:
            return value
    address = item.get("address_compound") or item.get("addressComponents") or {}
    if isinstance(address, dict):
        for key in ("city", "town", "municipality"):
            value = _normalize_location_text(address.get(key))
            if value:
                return value
    return _normalize_location_text(fallback)


def _perform_mapir_json_post(url, *, payload, headers, timeout, retries, max_response_bytes):
    # Import lazily to avoid a module-import cycle: views re-exports these
    # helpers after defining its hardened Map.ir transport primitives.
    from apps.search import views as legacy

    legacy._validate_mapir_upstream_url(url)
    max_response_bytes = max(1, int(max_response_bytes))
    attempts = max(1, int(retries) + 1)
    last_error = None
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(attempts):
        try:
            request = Request(url, data=body, headers=headers, method="POST")
            with urlopen(request, timeout=timeout) as response:
                response_body = response.read(max_response_bytes + 1)
                if len(response_body) > max_response_bytes:
                    raise legacy.MapirUpstreamResponseTooLarge(
                        "Map.ir upstream response is too large."
                    )
                return response_body, response.headers.get_content_type()
        except HTTPError as exc:
            last_error = exc
            if exc.code in {400, 401, 403, 404}:
                break
        except URLError as exc:
            last_error = exc

        if attempt < attempts - 1:
            sleep(0.2 * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise URLError("Map.ir search request failed")


@require_GET
def city_search_proxy(request):
    query = (request.GET.get("q") or "").strip()
    max_chars = max(int(getattr(settings, "CITY_SEARCH_QUERY_MAX_CHARS", 80) or 1), 1)
    if len(query) > max_chars:
        return JsonResponse({"ok": False, "results": [], "error": "query_too_long"}, status=400)
    if len(query) < 2:
        return JsonResponse({"ok": True, "results": []})

    api_key = getattr(settings, "MAPIR_API_KEY", "")
    if not api_key:
        return JsonResponse({"ok": False, "results": [], "message": "سرویس جستجوی شهر فعلاً تنظیم نشده است."}, status=503)

    base_url = getattr(settings, "MAPIR_SEARCH_BASE_URL", "https://map.ir/search/v2").rstrip("?")
    try:
        body, _ = _perform_mapir_json_post(
            base_url,
            payload={"text": f"{query} ایران"},
            headers={
                "x-api-key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": getattr(settings, "LOOMERA_USER_AGENT", "Loomera/1.0"),
            },
            timeout=getattr(settings, "MAPIR_REVERSE_TIMEOUT_SECONDS", 15),
            retries=getattr(settings, "MAPIR_UPSTREAM_RETRY_COUNT", 1),
            max_response_bytes=getattr(settings, "MAPIR_MAX_REVERSE_RESPONSE_BYTES", 256 * 1024),
        )
        payload = json.loads(body.decode("utf-8"))
        raw_results = payload.get("value") if isinstance(payload, dict) else []
        if not isinstance(raw_results, list):
            raw_results = []

        results = []
        seen = set()
        for item in raw_results:
            coords = _extract_coordinates(item)
            if coords is None:
                continue
            label = _city_result_label(item, fallback=query)
            if not label:
                continue
            lat, lon = coords
            key = (label.casefold(), round(lat, 5), round(lon, 5))
            if key in seen:
                continue
            seen.add(key)
            province = _normalize_location_text(item.get("province") if isinstance(item, dict) else "")
            results.append(
                {
                    "city": label,
                    "label": label,
                    "province": province,
                    "lat": lat,
                    "lon": lon,
                }
            )
            if len(results) >= 8:
                break

        return JsonResponse({"ok": True, "results": results}, json_dumps_params={"ensure_ascii": False})
    except (HTTPError, URLError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "results": [], "message": "جستجوی شهر در دسترس نیست."}, status=502)
    except Exception as exc:
        from apps.search import views as legacy
        if isinstance(exc, legacy.MapirUpstreamSecurityError):
            return JsonResponse({"ok": False, "results": [], "message": "تنظیمات سرویس نقشه معتبر نیست."}, status=503)
        if isinstance(exc, legacy.MapirUpstreamResponseTooLarge):
            return JsonResponse({"ok": False, "results": [], "message": "پاسخ سرویس نقشه بیش از حد بزرگ است."}, status=502)
        raise


@require_GET
def reverse_geocode_proxy(request):
    from apps.search import views as legacy

    api_key = getattr(settings, "MAPIR_API_KEY", "")
    if not api_key:
        return JsonResponse({"ok": False, "message": "سرویس آدرس‌یابی فعلاً تنظیم نشده است."}, status=503)

    try:
        lat = float(request.GET.get("lat"))
        lon = float(request.GET.get("lon"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "مختصات معتبر نیست."}, status=400, json_dumps_params={"ensure_ascii": False})
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JsonResponse({"ok": False, "message": "مختصات معتبر نیست."}, status=400, json_dumps_params={"ensure_ascii": False})

    base_url = getattr(settings, "MAPIR_REVERSE_BASE_URL", "https://map.ir/reverse/no").rstrip("?")
    upstream_url = f"{base_url}?lat={lat}&lon={lon}"

    try:
        body, _ = legacy._perform_upstream_request(
            upstream_url,
            headers={
                "x-api-key": api_key,
                "Accept": "application/json",
                "User-Agent": getattr(settings, "LOOMERA_USER_AGENT", "Loomera/1.0"),
            },
            timeout=getattr(settings, "MAPIR_REVERSE_TIMEOUT_SECONDS", 15),
            retries=getattr(settings, "MAPIR_UPSTREAM_RETRY_COUNT", 1),
            max_response_bytes=getattr(settings, "MAPIR_MAX_REVERSE_RESPONSE_BYTES", 256 * 1024),
        )
        payload = json.loads(body.decode("utf-8"))
        city = _extract_reverse_geocode_city(payload)
        zone, zone_label = _extract_reverse_geocode_zone(payload)
        neighborhood = _extract_reverse_geocode_neighborhood(payload)
        address = legacy._extract_reverse_geocode_address(payload)
        plaque = legacy._extract_reverse_geocode_plaque(payload)
        return JsonResponse(
            {
                "ok": True,
                "city": city,
                "address": address,
                "zone": zone,
                "zone_label": zone_label,
                "neighborhood": neighborhood,
                "plaque": plaque,
            },
            json_dumps_params={"ensure_ascii": False},
        )
    except (HTTPError, URLError):
        return JsonResponse({"ok": False, "message": "سرویس آدرس‌یابی در دسترس نیست."}, status=502, json_dumps_params={"ensure_ascii": False})
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "message": "پاسخ سرویس آدرس‌یابی قابل پردازش نیست."}, status=502, json_dumps_params={"ensure_ascii": False})
    except legacy.MapirUpstreamSecurityError:
        return JsonResponse({"ok": False, "message": "تنظیمات سرویس آدرس‌یابی معتبر نیست."}, status=503, json_dumps_params={"ensure_ascii": False})
    except legacy.MapirUpstreamResponseTooLarge:
        return JsonResponse({"ok": False, "message": "پاسخ سرویس آدرس‌یابی بیش از حد بزرگ است."}, status=502, json_dumps_params={"ensure_ascii": False})
