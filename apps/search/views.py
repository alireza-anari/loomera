import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Avg, Count, Min, Q

from apps.accounts.models import Customer, Stylist
from apps.orders.models import OrderDetail
from apps.locations.models import Neighborhood
from apps.services.models import Services
from apps.salons.models import Salon
from apps.search.utils import (
    filters_from_querydict,
    search_salons,
    serialize_salon_for_map,
)
import math
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from django.conf import settings
from django.http import HttpResponse
from time import sleep
from django.views.decorators.http import require_GET

import logging

logger = logging.getLogger(__name__)


def _positive_int_setting(name, default):
    return max(int(getattr(settings, name, default) or 1), 1)


def _limited_query(raw_query, *, setting_name, default):
    query = (raw_query or "").strip()
    max_chars = _positive_int_setting(setting_name, default)

    if len(query) > max_chars:
        return None

    return query


class SearchJsonBodyTooLarge(Exception):
    """Raised when a public search JSON payload exceeds the configured limit."""


class SearchJsonBodyInvalid(Exception):
    """Raised when a public search JSON payload is not a JSON object."""


def _search_json_body_max_bytes():
    return max(int(getattr(settings, "SEARCH_JSON_BODY_MAX_BYTES", 16 * 1024) or 1), 1)


def _load_limited_search_json_object(request):
    max_bytes = _search_json_body_max_bytes()

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise SearchJsonBodyTooLarge
        except ValueError:
            raise SearchJsonBodyInvalid

    raw_body = request.body or b"{}"
    if len(raw_body) > max_bytes:
        raise SearchJsonBodyTooLarge

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SearchJsonBodyInvalid

    if not isinstance(payload, dict):
        raise SearchJsonBodyInvalid

    return payload


def _public_search_json_error(exc):
    if isinstance(exc, SearchJsonBodyTooLarge):
        return JsonResponse({"error": "payload_too_large"}, status=413)

    return JsonResponse(
        {"error": "داده‌های ارسالی به صورت JSON معتبر نیست."},
        status=400,
        json_dumps_params={"ensure_ascii": False},
    )


# ------------------------------------------------------------------------------------
class MapirUpstreamSecurityError(Exception):
    """Raised when Map.ir upstream configuration is unsafe."""


class MapirUpstreamResponseTooLarge(Exception):
    """Raised when Map.ir upstream response exceeds the configured size limit."""


def _normalize_allowed_mapir_hosts():
    hosts = getattr(settings, "MAPIR_ALLOWED_HOSTS", {"map.ir"})
    if isinstance(hosts, str):
        hosts = hosts.split(",")

    normalized = {str(host).strip().lower() for host in hosts if str(host).strip()}
    return normalized or {"map.ir"}


def _validate_mapir_upstream_url(url):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    allowed_hosts = _normalize_allowed_mapir_hosts()

    if parsed.scheme != "https":
        raise MapirUpstreamSecurityError("Map.ir upstream URL must use https.")

    if hostname not in allowed_hosts:
        raise MapirUpstreamSecurityError("Map.ir upstream host is not allowed.")


# --------------------------------------------------------------------------------------
@require_GET
def salon_search(request):
    query = _limited_query(
        request.GET.get("q"),
        setting_name="SALON_SEARCH_QUERY_MAX_CHARS",
        default=80,
    )

    if query is None:
        return JsonResponse({"error": "query_too_long"}, status=400)

    salons = (
        Salon.objects.filter(is_active=True)
        .filter(
            Q(salon_name__icontains=query)
            | Q(address__icontains=query)
            | Q(neighborhood__name__icontains=query)
            | Q(
                services__service_name__icontains=query,
                services__is_active=True,
                services__is_platform_catalog=True,
            )
        )
        .distinct()[:20]
    )

    serialized_salons = []
    for salon in salons:
        coords = [0, 0]
        if salon.location:
            coords = [salon.location.x, salon.location.y]
        serialized_salons.append(
            {
                "id": salon.pk,
                "salon_name": salon.salon_name,
                "address": salon.address,
                "banner_image": salon.banner_image.url if salon.banner_image else "",
                "neighborhood": salon.neighborhood.name if salon.neighborhood else None,
                "location": {
                    "type": "Point",
                    "coordinates": coords,
                },
            }
        )

    return JsonResponse({"salons": serialized_salons})


# --------------------------------------------------------------------------------------
class SearchPageView(View):
    def get(self, request, *args, **kwargs):
        filters = filters_from_querydict(request.GET)
        search_data = search_salons(filters)

        initial_state = {
            "q": filters.query,
            "q_type": filters.q_type,
            "q_id": filters.q_id or "",
            "location": filters.location,
            "date": filters.date_input,
            "period": filters.period,
            "time": filters.exact_time_input,
            "group": str(filters.group_id or ""),
            "services": [
                str(service.id) for service in search_data["selected_services"]
            ],
            "sort": filters.sort,
            "lat": filters.latitude or "",
            "lng": filters.longitude or "",
            "min_price": getattr(filters, "min_price", None) or "",
            "max_price": getattr(filters, "max_price", None) or "",
            "min_rating": getattr(filters, "min_rating", None) or "",
            "discounted": bool(
                getattr(filters, "discounted", False)
                or getattr(filters, "has_discount", False)
            ),
            "verified": bool(
                getattr(filters, "verified", False)
                or getattr(filters, "verified_only", False)
            ),
            "availability": getattr(filters, "availability", "")
            or (
                "today"
                if getattr(filters, "available_today", False)
                else (
                    "this_week"
                    if getattr(filters, "available_this_week", False)
                    else ""
                )
            ),
        }

        context = {
            "salons": search_data["salons"],
            "search_summary": search_data["summary"],
            "search_state_json": json.dumps(initial_state, ensure_ascii=False),
            "selected_group": search_data["selected_group"],
            "selected_services": search_data["selected_services"],
            "group_services": search_data["group_services"],
            "service_ids_csv": search_data["service_ids_csv"],
            # "hide_navbar": True,
            "map_provider_enabled": getattr(settings, "MAP_PROVIDER_ENABLED", False),
        }

        return render(request, "pages/search.html", context)


# --------------------------------------------------------------------------------------
def search_results_api(request):
    filters = filters_from_querydict(request.GET)
    search_data = search_salons(filters)

    html = render_to_string(
        "search/search_results.html",
        {
            "salons": search_data["salons"],
            "selected_services": search_data["selected_services"],
            "selected_group": search_data["selected_group"],
            "summary": search_data["summary"],
        },
        request=request,
    )

    return JsonResponse(
        {
            "html": html,
            "count": len(search_data["salons"]),
            "summary": search_data["summary"],
            "salons": [
                serialize_salon_for_map(salon) for salon in search_data["salons"]
            ],
        },
        json_dumps_params={"ensure_ascii": False},
    )


# --------------------------------------------------------------------------------------
def salon_list(request):
    salons = (
        Salon.objects.filter(is_active=True)
        .select_related("neighborhood")
        .only("id", "salon_name", "address", "location", "neighborhood__name")
    )
    data = []
    for salon in salons:
        coords = [0, 0]
        if salon.location:
            coords = [salon.location.x, salon.location.y]
        data.append(
            {
                "id": salon.id,
                "salon_name": salon.salon_name,
                "address": salon.address or "",
                "neighborhood": salon.neighborhood.name if salon.neighborhood else "",
                "location": {"coordinates": coords},
            }
        )
    return JsonResponse(data, safe=False, json_dumps_params={"ensure_ascii": False})


# -------------------------------------------------------------------------------------------------
class FilterSalonView(View):
    """
    این endpoint قدیمی برای سازگاری نگه داشته شده و اکنون به موتور جستجوی جدید
    متصل است تا خروجی deterministic و واقعی‌تری بدهد.
    """

    def post(self, request, *args, **kwargs):
        try:
            data = _load_limited_search_json_object(request)
        except (SearchJsonBodyTooLarge, SearchJsonBodyInvalid) as exc:
            return _public_search_json_error(exc)

        params = {
            "location": data.get("location") or data.get("type") or "",
            "lat": data.get("latitude") or "",
            "lng": data.get("longitude") or "",
            "sort": data.get("sort") or "recommended",
            "q": data.get("q") or "",
            "date": data.get("date") or "",
            "period": data.get("period") or "",
            "time": data.get("time") or "",
            "services": data.get("services") or "",
            "group": data.get("group") or "",
        }
        filters = filters_from_querydict(params)
        search_data = search_salons(filters)
        salons_data = [
            serialize_salon_for_map(salon) for salon in search_data["salons"]
        ]
        return JsonResponse(
            {"salons": salons_data}, json_dumps_params={"ensure_ascii": False}
        )


# -----------------------------------------------------------------------------------------------------------------------------------------------
@csrf_exempt
def loomera_search(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        data = _load_limited_search_json_object(request)
    except SearchJsonBodyTooLarge:
        return JsonResponse({"error": "payload_too_large"}, status=413)
    except SearchJsonBodyInvalid:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    params = {
        "q": data.get("query") or data.get("q") or "",
        "location": data.get("location") or "",
        "date": data.get("date") or "",
        "period": data.get("period") or "",
        "time": data.get("time") or "",
        "group": data.get("service_group") or data.get("group") or "",
        "services": data.get("services") or "",
        "lat": data.get("lat") or data.get("latitude") or "",
        "lng": data.get("lng") or data.get("longitude") or "",
        "sort": data.get("sort") or "recommended",
    }
    filters = filters_from_querydict(params)
    search_data = search_salons(filters)
    salons_data = [serialize_salon_for_map(salon) for salon in search_data["salons"]]
    return JsonResponse(
        {"salons": salons_data}, json_dumps_params={"ensure_ascii": False}
    )


# Backward-compatible alias for external clients that still call the legacy endpoint.
salonify_search = loomera_search


# ---------------------------------------------------------------------------------------
def _manager_customer_search_forbidden():
    return JsonResponse({"error": "access_denied"}, status=403)


def _get_manager_owned_salon_from_request(request):
    salon_manager = getattr(request.user, "salon_manager_profile", None)
    if salon_manager is None:
        return None

    salons = Salon.objects.filter(salon_manager=salon_manager)
    requested_salon_id = (
        request.GET.get("salon_id") or request.POST.get("salon_id") or ""
    ).strip()

    if requested_salon_id:
        if not requested_salon_id.isdigit():
            return None
        salons = salons.filter(pk=int(requested_salon_id))

    return salons.order_by("pk").first()


@login_required
def customers_search(request):
    query = request.GET.get("q", "")
    salon = _get_manager_owned_salon_from_request(request)
    if salon is None:
        return _manager_customer_search_forbidden()

    # Find customers who have ordered from this salon
    customer_ids = (
        OrderDetail.objects.filter(salon=salon)
        .values_list("order__customer", flat=True)
        .distinct()
    )

    # Filter these customers based on the search query
    customers = (
        Customer.objects.filter(Q(user_id__in=customer_ids) | Q(added_by_salon=salon))
        .filter(
            Q(user__name__icontains=query)
            | Q(user__family__icontains=query)
            | Q(user__mobile_number__icontains=query)
            | Q(user__email__icontains=query)
        )
        .distinct()
    )

    serialized_customers = []
    for customer in customers:
        customer_data = {
            "id": customer.user.pk,
            "name": customer.get_fullName(),
            "phone_number": customer.user.mobile_number,
            "email": customer.user.email,
        }

        # Add profile image URL if it exists
        if customer.profile_image:
            customer_data["profile_image"] = customer.profile_image.url

        serialized_customers.append(customer_data)

    return JsonResponse({"customers": serialized_customers})


# ----------------------------------------------------------------------------------------
class FilterCustomersView(LoginRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        """Handle POST requests for filter submission"""
        salon = _get_manager_owned_salon_from_request(request)
        if salon is None:
            return HttpResponseForbidden("access_denied")

        sort_by = request.POST.get("sort_by", "newest")
        client_group = request.POST.get("client_group", "all")
        gender = request.POST.get("gender", "all")

        request.session["customer_filters"] = {
            "sort_by": sort_by,
            "client_group": client_group,
            "gender": gender,
        }

        customers = Customer.objects.filter(added_by_salon=salon).distinct()

        if sort_by == "newest":
            customers = customers.order_by("-user__register_date")
        elif sort_by == "oldest":
            customers = customers.order_by("user__register_date")
        elif sort_by == "name_asc":
            customers = customers.order_by("user__name", "user__family")
        elif sort_by == "name_desc":
            customers = customers.order_by("-user__name", "-user__family")

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            customers_data = []
            for customer in customers:
                profile_image_url = (
                    customer.profile_image.url if customer.profile_image else None
                )
                customers_data.append(
                    {
                        "id": customer.user.pk,
                        "name": customer.get_fullName(),
                        "phone_number": customer.user.mobile_number,
                        "email": customer.user.email or "بدون ایمیل",
                        "profile_image": profile_image_url,
                    }
                )

            return JsonResponse({"customers": customers_data})

        return redirect("dashboards:salons_customers_page")


# ---------------------------------------------------------------------------
class AjaxSearchView(View):

    def get(self, request):
        query = request.GET.get("q", "").strip()
        category_id = request.GET.get("category", "").strip()

        salons = Salon.objects.filter(is_active=True)

        if query:
            salons = salons.filter(
                Q(salon_name__icontains=query)
                | Q(address__icontains=query)
                | Q(description__icontains=query)
                | Q(services__service_name__icontains=query)
            )

        if category_id:
            salons = salons.filter(services__service_group__id=category_id)

        salons = (
            salons.annotate(
                avg_score=Avg("scoring_salon__score"),
                min_price=Min("services__service_prices__price"),
                total_reviews=Count("scoring_salon__score", distinct=True),
            )
            .select_related("neighborhood")
            .prefetch_related("services")
            .distinct()
        )

        count = salons.count()
        html = render_to_string(
            "search/search_results.html", {"salons": salons}, request=request
        )

        return JsonResponse(
            {
                "html": html,
                "count": count,
                "query": query,
                "category": category_id,
            }
        )


# ----------------------------------------------------------------------------------
def _xyz_to_bbox_3857(z: int, x: int, y: int) -> str:
    tile_size = 256
    initial_resolution = 2 * math.pi * 6378137 / tile_size
    origin_shift = 2 * math.pi * 6378137 / 2.0

    resolution = initial_resolution / (2**z)

    minx = x * tile_size * resolution - origin_shift
    maxx = (x + 1) * tile_size * resolution - origin_shift
    maxy = origin_shift - y * tile_size * resolution
    miny = origin_shift - (y + 1) * tile_size * resolution

    return f"{minx},{miny},{maxx},{maxy}"


def _perform_upstream_request(url, *, headers, timeout, retries, max_response_bytes):
    _validate_mapir_upstream_url(url)

    max_response_bytes = max(1, int(max_response_bytes))
    attempts = max(1, int(retries) + 1)
    last_error = None

    for attempt in range(attempts):
        try:
            upstream_request = Request(url, headers=headers)
            with urlopen(upstream_request, timeout=timeout) as upstream_response:
                body = upstream_response.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise MapirUpstreamResponseTooLarge(
                        "Map.ir upstream response is too large."
                    )
                content_type = upstream_response.headers.get_content_type()
                return body, content_type
        except HTTPError as exc:
            last_error = exc
            if exc.code in {401, 403, 404}:
                break
        except URLError as exc:
            last_error = exc

        if attempt < attempts - 1:
            sleep(0.2 * (attempt + 1))

    raise last_error


def map_tile_proxy(request, z, x, y):
    api_key = getattr(settings, "MAPIR_API_KEY", "")

    if not api_key:
        return HttpResponse(
            "سرویس نقشه فعلاً تنظیم نشده است.".encode("utf-8"),
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    if not (0 <= z <= 22 and 0 <= x < 2**z and 0 <= y < 2**z):
        return HttpResponse(
            b"Invalid tile coordinates",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    bbox = _xyz_to_bbox_3857(z, x, y)

    params = {
        "service": "WMS",
        "request": "GetMap",
        "layers": getattr(settings, "MAPIR_WMS_LAYER", "Shiveh:Shiveh"),
        "styles": "",
        "format": "image/png",
        "transparent": "false",
        "version": "1.1.1",
        "width": "256",
        "height": "256",
        "srs": "EPSG:3857",
        "bbox": bbox,
    }

    base_url = getattr(settings, "MAPIR_WMS_BASE_URL", "https://map.ir/shiveh").rstrip(
        "?"
    )
    upstream_url = f"{base_url}?{urlencode(params)}"

    try:
        body, content_type = _perform_upstream_request(
            upstream_url,
            headers={
                "x-api-key": api_key,
                "User-Agent": getattr(settings, "LOOMERA_USER_AGENT", "Loomera/1.0"),
                "Accept": "image/png,image/*;q=0.9,*/*;q=0.8",
            },
            timeout=getattr(settings, "MAPIR_TILE_TIMEOUT_SECONDS", 15),
            retries=getattr(settings, "MAPIR_UPSTREAM_RETRY_COUNT", 1),
            max_response_bytes=getattr(
                settings, "MAPIR_MAX_TILE_RESPONSE_BYTES", 1024 * 1024
            ),
        )

        response = HttpResponse(body, content_type=content_type or "image/png")
        response["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=120"
        return response

    except HTTPError:
        return HttpResponse(
            b"Tile provider unavailable",
            status=502,
            content_type="text/plain; charset=utf-8",
        )
    except URLError:
        return HttpResponse(
            b"Tile provider unavailable",
            status=502,
            content_type="text/plain; charset=utf-8",
        )
    except MapirUpstreamSecurityError:
        return HttpResponse(
            b"Tile provider is not configured safely",
            status=503,
            content_type="text/plain; charset=utf-8",
        )
    except MapirUpstreamResponseTooLarge:
        return HttpResponse(
            b"Tile provider response is too large",
            status=502,
            content_type="text/plain; charset=utf-8",
        )


def _dedupe_address_parts(parts):
    cleaned = []
    seen = set()
    for value in parts:
        text = _normalize_location_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _is_generic_address_part(text):
    normalized = _normalize_location_text(text)
    if not normalized:
        return True

    compact = normalized.replace(" ", "")
    if compact in {"ایران", "تهران", "استانتهران", "شهرتهران", "شهرستانتهران"}:
        return True
    if "منطقه" in normalized and len(normalized) <= 18:
        return True
    if normalized.startswith(("منطقه ", "ناحیه ")):
        return True
    return False


def _strip_generic_address_prefix(address, *, compound=None, extra_blocked_values=None):
    parts = re.split(r"\s*[،,]\s*", str(address or ""))
    if not parts:
        return ""

    blocked_values = {
        "ایران",
        "تهران",
        "استان تهران",
        "شهر تهران",
        "شهرستان تهران",
    }
    for value in extra_blocked_values or []:
        normalized = _normalize_location_text(value)
        if normalized:
            blocked_values.add(normalized)
    if isinstance(compound, dict):
        for key in [
            "country",
            "country_name",
            "province",
            "state",
            "county",
            "city",
            "town",
            "district",
            "region",
            "municipal_zone",
            "municipality_zone",
            "city_district",
            "neighbourhood",
            "neighborhood",
            "suburb",
            "quarter",
            "locality",
            "استان",
            "شهر",
            "شهرستان",
            "بخش",
            "ناحیه",
            "منطقه",
            "محله",
        ]:
            value = compound.get(key)
            if isinstance(value, str) and value.strip():
                blocked_values.add(_normalize_location_text(value))

    result = []
    blocked_compact = {value.replace(" ", "") for value in blocked_values if value}
    for part in parts:
        text = _normalize_location_text(part)
        compact = text.replace(" ", "")
        if not text:
            continue
        if compact in blocked_compact:
            continue
        if _is_generic_address_part(text):
            continue
        if any(
            blocked and blocked in compact
            for blocked in blocked_compact
            if len(blocked) >= 4
        ):
            continue
        result.append(text)

    if result:
        return "، ".join(_dedupe_address_parts(result))

    return _normalize_location_text(address)


def _extract_reverse_geocode_address(payload):
    if not isinstance(payload, dict):
        return ""

    compound = payload.get("address_compound") or payload.get("addressComponents") or {}
    extra_blocked_values = []
    neighborhood = _extract_reverse_geocode_neighborhood(payload)
    if neighborhood:
        extra_blocked_values.append(neighborhood)
    zone_number, zone_label = _extract_reverse_geocode_zone(payload)
    if zone_number:
        extra_blocked_values.extend([str(zone_number), f"منطقه {zone_number}"])
    if zone_label:
        extra_blocked_values.append(zone_label)
    plaque = _extract_reverse_geocode_plaque(payload)
    if plaque:
        extra_blocked_values.append(plaque)

    if isinstance(compound, dict):
        detail_parts = []
        for key in [
            "road",
            "street",
            "street_name",
            "primary",
            "secondary",
            "last",
            "alley",
        ]:
            value = compound.get(key)
            if isinstance(value, str) and value.strip():
                detail_parts.append(value.strip())

        detail_parts = _dedupe_address_parts(detail_parts)
        if detail_parts:
            return "، ".join(detail_parts)

        compound_candidates = [
            compound.get("address"),
            compound.get("formatted_address"),
            compound.get("postal_address"),
        ]
        for candidate in compound_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return _strip_generic_address_prefix(
                    candidate,
                    compound=compound,
                    extra_blocked_values=extra_blocked_values,
                )

    direct_candidates = [
        payload.get("address"),
        payload.get("formatted_address"),
        payload.get("postal_address"),
    ]
    for candidate in direct_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return _strip_generic_address_prefix(
                candidate,
                compound=compound if isinstance(compound, dict) else None,
                extra_blocked_values=extra_blocked_values,
            )

    return ""


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
    wanted = {key.lower() for key in wanted_keys}
    seen = set()

    def walk(value):
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key).lower()
                if key_text in wanted:
                    normalized = _normalize_location_text(item)
                    if normalized:
                        yield normalized
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    yield from walk(payload)



def _extract_reverse_geocode_plaque(payload):
    if not isinstance(payload, dict):
        return ""
    for value in _walk_reverse_payload_values(
        payload,
        ["plaque", "house_number", "houseNumber", "building_number"],
    ):
        return value
    return ""


def _extract_reverse_geocode_neighborhood(payload):
    for value in _walk_reverse_payload_values(
        payload,
        [
            "neighbourhood",
            "neighborhood",
            "neighborhood_name",
            "neighbourhood_name",
            "mahale",
            "محله",
            "suburb",
            "quarter",
            "locality",
        ],
    ):
        return value
    return ""


def _extract_reverse_geocode_zone(payload):
    keys = [
        "municipal_zone",
        "municipality_zone",
        "city_district",
        "district",
        "zone",
        "منطقه",
        "region",
    ]
    for value in _walk_reverse_payload_values(payload, keys):
        translated = value.translate(_PERSIAN_DIGITS_TRANSLATION)
        digits = "".join(ch for ch in translated if ch.isdigit())
        if not digits:
            # Some providers return the city name (for example تهران) in
            # district/region fields. That must not be saved as the zone.
            continue
        try:
            number = int(digits)
        except ValueError:
            continue
        if 1 <= number <= 99:
            return number, f"منطقه {number}"
    return "", ""


def reverse_geocode_proxy(request):
    api_key = getattr(settings, "MAPIR_API_KEY", "")

    if not api_key:
        return JsonResponse(
            {"ok": False, "message": "سرویس آدرس‌یابی فعلاً تنظیم نشده است."},
            status=503,
        )

    lat_raw = request.GET.get("lat")
    lon_raw = request.GET.get("lon")

    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "message": "مختصات معتبر نیست."},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JsonResponse(
            {"ok": False, "message": "مختصات معتبر نیست."},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    base_url = getattr(
        settings, "MAPIR_REVERSE_BASE_URL", "https://map.ir/reverse/no"
    ).rstrip("?")
    upstream_url = f"{base_url}?lat={lat}&lon={lon}"

    try:
        body, _ = _perform_upstream_request(
            upstream_url,
            headers={
                "x-api-key": api_key,
                "Accept": "application/json",
                "User-Agent": getattr(settings, "LOOMERA_USER_AGENT", "Loomera/1.0"),
            },
            timeout=getattr(settings, "MAPIR_REVERSE_TIMEOUT_SECONDS", 15),
            retries=getattr(settings, "MAPIR_UPSTREAM_RETRY_COUNT", 1),
            max_response_bytes=getattr(
                settings, "MAPIR_MAX_REVERSE_RESPONSE_BYTES", 256 * 1024
            ),
        )
        payload = json.loads(body.decode("utf-8"))
        address = _extract_reverse_geocode_address(payload)
        zone, zone_label = _extract_reverse_geocode_zone(payload)
        neighborhood = _extract_reverse_geocode_neighborhood(payload)
        plaque = _extract_reverse_geocode_plaque(payload)

        return JsonResponse(
            {
                "ok": True,
                "address": address,
                "zone": zone,
                "zone_label": zone_label,
                "neighborhood": neighborhood,
                "plaque": plaque,
            },
            json_dumps_params={"ensure_ascii": False},
        )

    except HTTPError:
        return JsonResponse(
            {
                "ok": False,
                "message": "سرویس آدرس‌یابی فعلاً در دسترس نیست.",
            },
            status=502,
            json_dumps_params={"ensure_ascii": False},
        )

    except URLError:
        return JsonResponse(
            {
                "ok": False,
                "message": "سرویس آدرس‌یابی در دسترس نیست.",
            },
            status=502,
            json_dumps_params={"ensure_ascii": False},
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {
                "ok": False,
                "message": "پاسخ سرویس آدرس‌یابی قابل پردازش نیست.",
            },
            status=502,
            json_dumps_params={"ensure_ascii": False},
        )
    except MapirUpstreamSecurityError:
        return JsonResponse(
            {
                "ok": False,
                "message": "تنظیمات سرویس آدرس‌یابی معتبر نیست.",
            },
            status=503,
            json_dumps_params={"ensure_ascii": False},
        )

    except MapirUpstreamResponseTooLarge:
        return JsonResponse(
            {
                "ok": False,
                "message": "پاسخ سرویس آدرس‌یابی بیش از حد بزرگ است.",
            },
            status=502,
            json_dumps_params={"ensure_ascii": False},
        )


@require_GET
def search_suggestions(request):
    query = _limited_query(
        request.GET.get("q"),
        setting_name="SEARCH_SUGGESTIONS_QUERY_MAX_CHARS",
        default=80,
    )

    if query is None:
        return JsonResponse({"error": "query_too_long"}, status=400)

    if not query:
        return JsonResponse(
            {
                "results": [],
                "services": [],
                "salons": [],
                "stylists": [],
            },
            json_dumps_params={"ensure_ascii": False},
        )

    services_qs = (
        Services.objects.filter(
            is_active=True,
            is_platform_catalog=True,
            service_group__is_active=True,
            service_name__icontains=query,
        )
        .prefetch_related("service_group")
        .distinct()
        .order_by("-view_count", "service_name")[:8]
    )

    salons_qs = (
        Salon.objects.filter(is_active=True)
        .filter(
            Q(salon_name__icontains=query)
            | Q(address__icontains=query)
            | Q(neighborhood__name__icontains=query)
        )
        .select_related("neighborhood")
        .distinct()[:6]
    )

    stylists_qs = (
        Stylist.objects.filter(
            is_active=True,
            public_visibility=Stylist.PublicVisibility.PUBLIC,
            stylists_of_salon__is_active=True,
        )
        .filter(
            Q(user__name__icontains=query)
            | Q(user__family__icontains=query)
            | Q(expert__icontains=query)
        )
        .select_related("user")
        .prefetch_related("stylists_of_salon")
        .distinct()[:6]
    )

    services = []
    for service in services_qs:
        group = service.service_group.filter(is_active=True).first()
        services.append(
            {
                "id": service.pk,
                "type": "service",
                "type_label": "خدمت",
                "name": service.service_name,
                "value": service.service_name,
                "meta": group.group_title if group else "خدمت قابل رزرو",
            }
        )

    salons = []
    for salon in salons_qs:
        salons.append(
            {
                "id": salon.pk,
                "type": "salon",
                "type_label": "مجموعه",
                "name": salon.salon_name,
                "value": salon.salon_name,
                "meta": (
                    salon.neighborhood.name
                    if salon.neighborhood
                    else salon.address or ""
                ),
            }
        )

    stylists = []
    for stylist in stylists_qs:
        salon = stylist.stylists_of_salon.filter(is_active=True).first()
        full_name = stylist.get_fullName()
        stylists.append(
            {
                "id": stylist.pk,
                "type": "stylist",
                "type_label": "متخصص",
                "name": full_name,
                "value": full_name,
                "meta": stylist.expert or (salon.salon_name if salon else "متخصص"),
            }
        )

    results = services + salons + stylists

    return JsonResponse(
        {
            "results": results,
            "services": services,
            "salons": salons,
            "stylists": stylists,
        },
        json_dumps_params={"ensure_ascii": False},
    )


@require_GET
def location_suggestions(request):
    query = _limited_query(
        request.GET.get("q"),
        setting_name="LOCATION_SUGGESTIONS_QUERY_MAX_CHARS",
        default=80,
    )

    if query is None:
        return JsonResponse({"error": "query_too_long"}, status=400)

    neighborhoods_qs = Neighborhood.objects.only("id", "name").order_by("name")
    if query:
        neighborhoods_qs = neighborhoods_qs.filter(name__icontains=query)

    neighborhoods = [
        {
            "id": item.pk,
            "type": "neighborhood",
            "type_label": "محله",
            "name": item.name,
            "value": item.name,
            "meta": "محله ثبت‌شده",
        }
        for item in neighborhoods_qs[:12]
    ]

    return JsonResponse(
        {
            "results": neighborhoods,
        },
        json_dumps_params={"ensure_ascii": False},
    )


# --------------------------------------------------------------------------------------
class SearchClickPayloadTooLarge(Exception):
    """Raised when search click payload exceeds the configured limit."""


class SearchClickPayloadInvalid(Exception):
    """Raised when search click payload is invalid."""


def _search_click_post_max_bytes():
    return max(
        int(getattr(settings, "SEARCH_CLICK_POST_MAX_BYTES", 4 * 1024) or 1),
        1,
    )


def _validate_search_click_payload_size(request):
    content_length = request.META.get("CONTENT_LENGTH")
    if not content_length:
        return

    try:
        if int(content_length) > _search_click_post_max_bytes():
            raise SearchClickPayloadTooLarge
    except ValueError:
        raise SearchClickPayloadInvalid


def _safe_search_click_target(request, target_url):
    target = str(target_url or "").strip()
    if not target:
        return ""

    parsed = urlparse(target)

    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise SearchClickPayloadInvalid

    if parsed.netloc and parsed.netloc != request.get_host():
        raise SearchClickPayloadInvalid

    return target[:500]


def _model_field_names(model):
    return {
        field.name for field in model._meta.get_fields() if hasattr(field, "attname")
    }


def _first_payload_value(request, *keys, default=""):
    for key in keys:
        value = request.POST.get(key)
        if value not in (None, ""):
            return value
    return default


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_search_click(request):
    """Record a search result click without exposing analytics internals."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        _validate_search_click_payload_size(request)
    except SearchClickPayloadTooLarge:
        return JsonResponse(
            {"ok": False, "recorded": False, "error": "payload_too_large"},
            status=413,
        )
    except SearchClickPayloadInvalid:
        return JsonResponse(
            {"ok": False, "recorded": False, "error": "invalid_payload"},
            status=400,
        )

    try:
        from django.apps import apps as django_apps

        SearchResultClick = None
        for app_label in ("search", "analytics"):
            try:
                SearchResultClick = django_apps.get_model(
                    app_label, "SearchResultClick"
                )
                break
            except LookupError:
                continue

        if SearchResultClick is None:
            return JsonResponse(
                {"ok": True, "recorded": False, "reason": "model_not_available"}
            )

        salon_id = _safe_int(
            _first_payload_value(request, "salon_id", "salon", "result_id", "id")
        )
        position = _safe_int(_first_payload_value(request, "position", "rank", "index"))
        search_log_id = _safe_int(
            _first_payload_value(request, "search_log_id", "log_id")
        )
        query = _first_payload_value(request, "q", "query", "search_query")
        target_url = _safe_search_click_target(
            request,
            _first_payload_value(request, "target_url", "url", "href", "detail_url"),
        )

        fields = _model_field_names(SearchResultClick)
        payload = {}

        if "user" in fields and request.user.is_authenticated:
            payload["user"] = request.user
        if "salon_id" in fields and salon_id:
            payload["salon_id"] = salon_id
        elif "result_salon_id" in fields and salon_id:
            payload["result_salon_id"] = salon_id
        if "position" in fields and position is not None:
            payload["position"] = position
        elif "rank" in fields and position is not None:
            payload["rank"] = position
        if "query" in fields and query:
            payload["query"] = str(query)[:255]
        elif "search_query" in fields and query:
            payload["search_query"] = str(query)[:255]
        if "target_url" in fields and target_url:
            payload["target_url"] = target_url
        elif "url" in fields and target_url:
            payload["url"] = target_url
        if "session_key" in fields:
            if not request.session.session_key:
                request.session.save()
            payload["session_key"] = request.session.session_key or ""
        if "ip_address" in fields:
            payload["ip_address"] = (
                request.META.get(
                    "HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")
                )
                .split(",")[0]
                .strip()
            )
        if "user_agent" in fields:
            payload["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:500]

        if search_log_id:
            for field_name in ("search_log_id", "log_id"):
                if field_name in fields:
                    payload[field_name] = search_log_id
                    break

        SearchResultClick.objects.create(**payload)
        return JsonResponse({"ok": True, "recorded": True})

    except SearchClickPayloadInvalid:
        return JsonResponse(
            {"ok": False, "recorded": False, "error": "invalid_payload"},
            status=400,
        )
    except Exception:
        logger.warning("Unable to record search click", exc_info=True)
        return JsonResponse(
            {"ok": True, "recorded": False, "reason": "recording_failed"}
        )
