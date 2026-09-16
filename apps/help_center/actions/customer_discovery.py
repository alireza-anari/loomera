from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from apps.locations.models import Neighborhood
from apps.search.utils import filters_from_querydict, normalize_period, normalize_text, search_salons
from apps.services.models import Services


PERSIAN_ARABIC_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

SEARCH_INTENT_TERMS = (
    "پیدا کن",
    "پیدا کنم",
    "پیدا میکنی",
    "پیدا می‌کنی",
    "بگرد",
    "بگردی",
    "میخوام",
    "می‌خوام",
    "می خواهم",
    "می‌خواهم",
    "وقت میخوام",
    "وقت می‌خوام",
    "نوبت میخوام",
    "نوبت می‌خوام",
    "رزرو میخوام",
    "رزرو می‌خوام",
    "نزدیکترین",
    "نزدیک‌ترین",
    "نزدیک من",
    "اطراف من",
)

NEAR_ME_TERMS = (
    "نزدیک من",
    "اطراف من",
    "دور و بر من",
    "دوروبر من",
    "نزدیکم",
)

DISCOVERY_CANCEL_TERMS = ("بیخیال", "بی‌خیال", "لغو جستجو", "ولش کن", "جستجو رو لغو کن")

DISCOVERY_ESCAPE_TERMS = (
    "رمز", "پسورد", "تیکت", "پشتیبانی", "مرخصی", "برنامه کاری",
    "برداشت", "کیف پول", "اعلان", "نوتیفیکیشن", "کد تخفیف", "عضو تیم",
)

PRICE_CONTEXT_TERMS = (
    "تومان",
    "تومن",
    "بودجه",
    "قیمت",
    "زیر",
    "حداکثر",
    "کمتر از",
    "تا",
    "با",
)

# Language aliases only. Product truth and availability still come from DB.
SERVICE_LANGUAGE_ALIASES = {
    "کوتاهی مو": ("کوتاه کردن مو", "موهامو کوتاه", "کوتاه کنم", "اصلاح مو"),
    "اصلاح صورت": ("اصلاح صورتم", "صورت اصلاح", "شیو صورت"),
    "رنگ مو": ("موهامو رنگ", "رنگ کردن مو", "رنگ کنم"),
    "کراتین مو": ("کراتین", "کراتینه مو"),
    "براشینگ": ("براشینگ مو", "براشینگ"),
    "مانیکور": ("مانیکور", "ناخن دست"),
    "پدیکور": ("پدیکور", "ناخن پا"),
}


@dataclass
class DiscoveryInput:
    service_id: int | None = None
    service_name: str = ""
    location: str = ""
    max_price: int | None = None
    date: str = ""
    date_label: str = ""
    period: str = ""
    latitude: float | None = None
    longitude: float | None = None
    near_me: bool = False

    def as_state(self) -> dict:
        return {
            "mode": "customer_discovery",
            "service_id": self.service_id,
            "service_name": self.service_name,
            "location": self.location,
            "max_price": self.max_price,
            "date": self.date,
            "date_label": self.date_label,
            "period": self.period,
            "near_me": self.near_me,
            "awaiting": "",
        }


def _normalized(value: str) -> str:
    text = normalize_text(str(value or "")).translate(PERSIAN_ARABIC_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    text = text.replace("\u200c", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _stem_token(value: str) -> str:
    token = _normalized(value)
    for suffix in ("های", "ها", "ام", "ات", "اش", "مون", "تون", "شون", "ی"):
        if len(token) >= len(suffix) + 3 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token


def _query_tokens(value: str) -> list[str]:
    return [item for item in re.split(r"[^0-9a-zA-Zآ-ی]+", _normalized(value)) if len(item) >= 2]


def _phrase_match_score(query: str, phrase: str) -> float:
    q = _normalized(query)
    phrase_norm = _normalized(phrase)
    if not q or not phrase_norm:
        return 0.0
    if phrase_norm in q:
        return 1.0

    q_tokens = _query_tokens(q)
    p_tokens = _query_tokens(phrase_norm)
    if not p_tokens:
        return 0.0

    matches = 0.0
    for ptoken in p_tokens:
        proot = _stem_token(ptoken)
        best = 0.0
        for qtoken in q_tokens:
            qroot = _stem_token(qtoken)
            if proot == qroot:
                best = max(best, 1.0)
            elif len(proot) >= 2 and (proot in qroot or qroot in proot):
                best = max(best, 0.9)
            else:
                best = max(best, SequenceMatcher(None, proot, qroot).ratio() * 0.7)
        matches += best
    return matches / len(p_tokens)


def _match_service(question: str, current_service_id=None) -> tuple[Services | None, list[dict]]:
    current_service = None
    if current_service_id:
        current_service = Services.objects.filter(
            pk=current_service_id,
            is_active=True,
            is_platform_catalog=True,
        ).first()

    candidates = list(
        Services.objects.filter(is_active=True, is_platform_catalog=True)
        .only("id", "service_name", "slug", "view_count")
        .order_by("-view_count", "service_name")[:500]
    )
    scored = []
    for service in candidates:
        phrases = [service.service_name]
        for canonical, aliases in SERVICE_LANGUAGE_ALIASES.items():
            if _normalized(canonical) == _normalized(service.service_name):
                phrases.extend(aliases)
        score = max((_phrase_match_score(question, item) for item in phrases), default=0.0)
        if score >= 0.35:
            scored.append((score, service))

    scored.sort(key=lambda item: (item[0], getattr(item[1], "view_count", 0)), reverse=True)
    if not scored:
        return current_service, []

    suggestions = [
        {"id": service.pk, "name": service.service_name}
        for score, service in scored[:4]
        if score >= 0.38
    ]
    top_score, top = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if top_score >= 0.72 and (top_score - second_score >= 0.10 or top_score >= 0.9):
        return top, suggestions
    if current_service:
        return current_service, suggestions
    return None, suggestions


def _number_value(raw: str, unit: str = "") -> int | None:
    value = str(raw or "").translate(PERSIAN_ARABIC_DIGITS).replace(",", "").replace("٬", "")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    unit_norm = _normalized(unit)
    if "میلیون" in unit_norm:
        number *= 1_000_000
    elif "هزار" in unit_norm:
        number *= 1_000
    return max(int(number), 0)


def _extract_budget(question: str) -> tuple[int | None, int | None]:
    """Return (resolved_budget, ambiguous_short_number)."""
    text = _normalized(question).replace(",", "").replace("٬", "")
    if not any(term in text for term in PRICE_CONTEXT_TERMS):
        return None, None

    patterns = (
        r"(?:زیر|حداکثر|کمتر از|تا|بودجه(?:م)?(?: حدود)?|با)\s*(\d+(?:\.\d+)?)\s*(میلیون|هزار)?\s*(?:تومان|تومن)?",
        r"(\d+(?:\.\d+)?)\s*(میلیون|هزار)\s*(?:تومان|تومن)?",
        r"(\d{4,})\s*(?:تومان|تومن)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        unit = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
        amount = _number_value(match.group(1), unit or "")
        if amount is None:
            continue
        # "۵۰۰ تومن" is ambiguous in conversational Persian. Never silently
        # convert it to 500k; ask the user instead.
        if not unit and amount < 10_000 and "دقیق" not in text:
            return None, amount
        return amount, None
    return None, None


def _extract_location(question: str, current_location: str = "") -> str:
    text = _normalized(question)
    neighborhoods = list(Neighborhood.objects.only("name").order_by("name"))
    matches = []
    for item in neighborhoods:
        name = _normalized(item.name)
        if name and name in text:
            matches.append(item.name)
    if matches:
        return max(matches, key=len)
    return str(current_location or "").strip()


def _extract_date_period(question: str, current_date="", current_date_label="", current_period=""):
    text = _normalized(question)
    date_value = current_date or ""
    date_label = current_date_label or ""
    today = timezone.localdate()
    if "پس فردا" in text or "پس‌فردا" in text:
        date_value = (today + timedelta(days=2)).isoformat()
        date_label = "پس‌فردا"
    elif "فردا" in text:
        date_value = (today + timedelta(days=1)).isoformat()
        date_label = "فردا"
    elif "امروز" in text:
        date_value = today.isoformat()
        date_label = "امروز"

    period = current_period or ""
    for candidate in ("صبح", "ظهر", "بعدازظهر", "عصر", "شب"):
        if candidate in text:
            period = normalize_period(candidate)
            break
    return date_value, date_label, period


def _near_me_requested(question: str, current=False) -> bool:
    text = _normalized(question)
    return bool(current or any(_normalized(term) in text for term in NEAR_ME_TERMS))


def _search_intent(question: str, state: dict | None = None) -> bool:
    state = state or {}
    text = _normalized(question)
    if any(_normalized(term) in text for term in SEARCH_INTENT_TERMS):
        return True
    if state.get("mode") != "customer_discovery":
        return False

    if any(term in text for term in DISCOVERY_CANCEL_TERMS):
        return True
    if any(term in text for term in DISCOVERY_ESCAPE_TERMS):
        return False
    if "چطور" in text or "چگونه" in text:
        return False

    if state.get("awaiting") and len(_query_tokens(text)) <= 12:
        return True

    refinement_terms = (
        "اولی", "دومی", "سومی", "چهارمی", "گزینه اول", "گزینه دوم", "گزینه سوم", "گزینه چهارم",
        "امروز", "فردا", "پس فردا", "صبح", "ظهر", "بعدازظهر", "عصر", "شب",
        "بودجه", "قیمت", "تومان", "تومن", "هزار", "میلیون", "زیر", "حداکثر",
        "بدون محدودیت", "همه محله", "همه محدوده", "نزدیک من", "اطراف من",
        "ارزان", "نزدیکتر", "نزدیک‌تر",
    )
    return any(term in text for term in refinement_terms)


def is_customer_discovery_candidate(question: str, state: dict | None = None) -> bool:
    return _search_intent(question, state)


def _safe_coord(value, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def _query_params(spec: DiscoveryInput) -> dict:
    params = {}
    if spec.service_id:
        params.update({"q_type": "service", "q_id": str(spec.service_id), "services": str(spec.service_id)})
    if spec.location:
        params["location"] = spec.location
    if spec.max_price:
        params["max_price"] = str(spec.max_price)
    if spec.date:
        params["date"] = spec.date
    if spec.period:
        params["period"] = spec.period
    if spec.latitude is not None and spec.longitude is not None:
        params["lat"] = str(spec.latitude)
        params["lng"] = str(spec.longitude)
        params["sort"] = "nearest"
        if spec.near_me:
            params["location"] = "نزدیک من"
    return params


def _filter_chips(spec: DiscoveryInput) -> list[dict]:
    chips = []
    if spec.service_name:
        chips.append({"icon": "scissors", "label": spec.service_name})
    if spec.location:
        chips.append({"icon": "location-dot", "label": spec.location})
    elif spec.near_me:
        chips.append({"icon": "location-crosshairs", "label": "نزدیک من"})
    if spec.max_price:
        chips.append({"icon": "wallet", "label": f"تا {spec.max_price:,} تومان"})
    if spec.date_label:
        chips.append({"icon": "calendar", "label": spec.date_label})
    if spec.period:
        period_label = {"morning": "صبح", "noon": "ظهر", "evening": "عصر", "night": "شب"}.get(spec.period, spec.period)
        chips.append({"icon": "clock", "label": period_label})
    return chips


def _result_payload(salon, *, distance_supported: bool, catalog_service_id: int | None = None) -> dict:
    image_url = ""
    try:
        if salon.banner_image:
            image_url = salon.banner_image.url
    except Exception:
        image_url = ""
    distance = getattr(salon, "search_distance_km", None) if distance_supported else None
    price = getattr(salon, "search_primary_price", None)
    return {
        "id": salon.pk,
        "name": salon.salon_name,
        "catalog_service_id": catalog_service_id,
        "location": getattr(salon, "search_location_label", "") or (salon.address or ""),
        "price": int(price) if price is not None else None,
        "rating": round(float(getattr(salon, "avg_score", 0) or 0), 1),
        "distance_km": distance,
        "availability": getattr(salon, "search_available_label", "") or "",
        "matched_services": list(getattr(salon, "search_matched_services", []) or []),
        "image_url": image_url,
        "url": salon.get_absolute_url(),
    }


def _clarification(*, answer: str, state: dict, suggestions=None, request_location=False, budget_hint=None, awaiting=""):
    state = dict(state or {})
    state["awaiting"] = str(awaiting or "")
    return {
        "handled": True,
        "kind": "discovery_clarification",
        "answer": answer,
        "action_state": state,
        "suggestions": suggestions or [],
        "request_location": bool(request_location),
        "budget_hint": budget_hint,
        "results": [],
        "filters": [],
    }



def _selected_result_from_message(question: str, state: dict) -> dict | None:
    results = state.get("result_salons") if isinstance(state.get("result_salons"), list) else []
    if not results:
        return None
    text = _normalized(question)
    mapping = (
        (0, ("اولی", "گزینه اول", "اولین گزینه", "همون اولی")),
        (1, ("دومی", "گزینه دوم", "دومین گزینه", "همون دومی")),
        (2, ("سومی", "گزینه سوم", "سومین گزینه", "همون سومی")),
        (3, ("چهارمی", "گزینه چهارم", "چهارمین گزینه", "همون چهارمی")),
    )
    for index, phrases in mapping:
        if any(_normalized(phrase) in text for phrase in phrases) and index < len(results):
            item = results[index]
            if isinstance(item, dict) and item.get("salon_id"):
                return item
    return None

def run_customer_discovery(
    question: str,
    *,
    state: dict | None = None,
    latitude=None,
    longitude=None,
) -> dict:
    state = state if isinstance(state, dict) else {}
    if not _search_intent(question, state):
        return {"handled": False}

    text = _normalized(question)
    if state.get("mode") == "customer_discovery" and any(term in text for term in DISCOVERY_CANCEL_TERMS):
        return {
            "handled": True,
            "kind": "discovery_cancelled",
            "answer": "باشه، جستجو رو کنار گذاشتم. هر کار دیگه‌ای با لومرا داری بگو.",
            "action_state": None,
            "filters": [],
            "results": [],
            "suggestions": [],
            "request_location": False,
        }

    selected_result = _selected_result_from_message(question, state)
    if selected_result:
        return {
            "handled": True,
            "kind": "discovery_select_result",
            "answer": "حتماً؛ بریم متخصص و زمان آزاد همین مجموعه رو انتخاب کنیم.",
            "action_state": state,
            "booking_request": {
                "salon_id": selected_result.get("salon_id"),
                "catalog_service_id": selected_result.get("catalog_service_id") or state.get("service_id"),
            },
            "results": [],
            "filters": [],
            "suggestions": [],
            "request_location": False,
        }

    if "بدون محدودیت قیمت" in text or "بدون سقف قیمت" in text:
        state["max_price"] = None
    if "همه محله" in text or "همه محدوده" in text:
        state["location"] = ""
        state["near_me"] = False
    if "بدون محدودیت تاریخ" in text or "بدون محدودیت زمان" in text:
        state["date"] = ""
        state["date_label"] = ""
        state["period"] = ""

    service, service_suggestions = _match_service(question, state.get("service_id"))
    budget, ambiguous_budget = _extract_budget(question)
    location = _extract_location(question, state.get("location", ""))
    date_value, date_label, period = _extract_date_period(
        question,
        state.get("date", ""),
        state.get("date_label", ""),
        state.get("period", ""),
    )
    near_me = _near_me_requested(question, state.get("near_me", False))
    lat = _safe_coord(latitude, -90, 90)
    lng = _safe_coord(longitude, -180, 180)

    spec = DiscoveryInput(
        service_id=service.pk if service else state.get("service_id"),
        service_name=service.service_name if service else state.get("service_name", ""),
        location=location,
        max_price=budget if budget is not None else state.get("max_price"),
        date=date_value,
        date_label=date_label,
        period=period,
        latitude=lat,
        longitude=lng,
        near_me=near_me,
    )

    if ambiguous_budget is not None:
        return _clarification(
            answer=(
                f"برای قیمت مطمئن شم: منظورت {ambiguous_budget:,} هزار تومانه یا "
                f"{ambiguous_budget:,} تومان؟"
            ),
            state=spec.as_state(),
            suggestions=[
                {"label": f"{ambiguous_budget:,} هزار تومان", "message": f"بودجه تا {ambiguous_budget} هزار تومان"},
                {"label": f"{ambiguous_budget:,} تومان", "message": f"بودجه تا {ambiguous_budget} تومان دقیق"},
            ],
            budget_hint=ambiguous_budget,
            awaiting="budget",
        )

    if not spec.service_id:
        if service_suggestions:
            return _clarification(
                answer="دقیقاً کدوم خدمت رو می‌خوای؟ یکی از این‌ها رو انتخاب کن یا اسم خدمت رو بنویس.",
                state=spec.as_state(),
                suggestions=[
                    {"label": item["name"], "message": f"خدمت {item['name']}"}
                    for item in service_suggestions[:4]
                ],
                awaiting="service",
            )
        return _clarification(
            answer="چه خدمتی مدنظرته؟ مثلاً «کوتاهی مو»، «رنگ مو» یا اسم دقیق خدمتی که می‌خوای.",
            state=spec.as_state(),
            awaiting="service",
        )

    if spec.near_me and (spec.latitude is None or spec.longitude is None):
        return _clarification(
            answer="برای اینکه واقعاً نزدیک‌ترین گزینه‌ها رو مرتب کنم، اجازه دسترسی به موقعیتت رو بده.",
            state=spec.as_state(),
            request_location=True,
            awaiting="location_permission",
        )

    params = _query_params(spec)
    filters = filters_from_querydict(params)
    search_data = search_salons(filters)
    salons = list(search_data.get("salons") or [])[:4]
    distance_supported = bool(search_data.get("distance_supported"))
    results = [
        _result_payload(
            item,
            distance_supported=distance_supported,
            catalog_service_id=spec.service_id,
        )
        for item in salons
    ]

    search_url = reverse("search:search_page")
    if params:
        search_url += "?" + urlencode(params)

    if results:
        location_phrase = ""
        if spec.near_me and distance_supported:
            location_phrase = " نزدیکت"
        elif spec.location:
            location_phrase = f" در {spec.location}"
        answer = f"{len(results)} گزینه مناسب{location_phrase} پیدا کردم. نتیجه‌ها از جستجوی واقعی لومرا هستند."
        if not spec.location and not spec.near_me:
            answer += " اگر محله‌ات رو هم بگی، نتیجه‌ها رو دقیق‌تر می‌کنم."
        return {
            "handled": True,
            "kind": "discovery_results",
            "answer": answer,
            "action_state": {
                **spec.as_state(),
                "result_salons": [
                    {
                        "salon_id": item["id"],
                        "catalog_service_id": spec.service_id,
                    }
                    for item in results
                ],
            },
            "filters": _filter_chips(spec),
            "results": results,
            "search_url": search_url,
            "search_label": "مشاهده همه نتایج",
            "suggestions": [],
            "request_location": False,
        }

    answer = "با این مشخصات نتیجه‌ای پیدا نکردم. می‌تونیم یکی از محدودیت‌ها رو بازتر کنیم."
    suggestions = []
    if spec.max_price:
        suggestions.append({"label": "بدون سقف قیمت", "message": "بدون محدودیت قیمت بگرد"})
    if spec.location:
        suggestions.append({"label": "همه محدوده‌ها", "message": "همه محله‌ها رو بگرد"})
    if spec.date:
        suggestions.append({"label": "بدون محدودیت زمان", "message": "بدون محدودیت تاریخ بگرد"})
    return {
        "handled": True,
        "kind": "discovery_empty",
        "answer": answer,
        "action_state": spec.as_state(),
        "filters": _filter_chips(spec),
        "results": [],
        "search_url": search_url,
        "search_label": "باز کردن جستجوی لومرا",
        "suggestions": suggestions,
        "request_location": False,
    }
