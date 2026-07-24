from __future__ import annotations

from dataclasses import dataclass
from datetime import date as dt_date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

PERSIAN_DIGITS_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹كي", "0123456789کی")


def normalize_search_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = str(value).translate(PERSIAN_DIGITS_MAP)
    normalized = " ".join(normalized.replace("‌", " ").split())
    return normalized.strip().lower()


def bool_from_query(value: Any) -> bool:
    if value in (True, 1):
        return True
    if value in (False, 0, None, ""):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "بله", "آری"}


def get_client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")


@dataclass(frozen=True)
class PaginationResult:
    items: list
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool


class SearchPaginationService:
    DEFAULT_PAGE_SIZE = 40
    MAX_PAGE_SIZE = 80

    @classmethod
    def paginate(cls, items: list, *, page: int = 1, page_size: int | None = None) -> PaginationResult:
        total_count = len(items)
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or cls.DEFAULT_PAGE_SIZE), 1), cls.MAX_PAGE_SIZE)
        start = (page - 1) * page_size
        end = start + page_size
        total_pages = max((total_count + page_size - 1) // page_size, 1)
        return PaginationResult(
            items=items[start:end],
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=end < total_count,
            has_previous=page > 1,
        )


class SalonFilterService:
    @staticmethod
    def filter_by_computed_fields(salons: list, filters) -> list:
        filtered = salons
        if getattr(filters, "discounted", False):
            filtered = [salon for salon in filtered if getattr(salon, "has_active_service_discount", False)]
        if getattr(filters, "min_price", None) is not None:
            filtered = [
                salon for salon in filtered
                if getattr(salon, "search_primary_price", None) is not None
                and int(getattr(salon, "search_primary_price") or 0) >= int(filters.min_price)
            ]
        if getattr(filters, "max_price", None) is not None:
            filtered = [
                salon for salon in filtered
                if getattr(salon, "search_primary_price", None) is not None
                and int(getattr(salon, "search_primary_price") or 0) <= int(filters.max_price)
            ]
        return filtered


class SalonRankingService:
    @staticmethod
    def quality_score(salon) -> float:
        score = 0.0
        avg = float(getattr(salon, "avg_score", 0) or 0)
        reviews = int(getattr(salon, "total_reviews", 0) or 0)
        if getattr(salon, "search_available_label", ""):
            score += 30
        score += avg * 10
        score += min(reviews, 50) * 0.5
        if getattr(salon, "has_active_service_discount", False):
            score += 4
        if getattr(salon, "verification_status", "") == "verified":
            score += 6
        if getattr(salon, "banner_image", None):
            score += 2
        if getattr(salon, "description", ""):
            score += 1
        distance = getattr(salon, "search_distance_km", None)
        if distance is not None:
            score += max(0, 12 - float(distance))
        return round(score, 3)

    @classmethod
    def sort(cls, salons: list, *, sort: str = "recommended", distance_supported: bool = False) -> list:
        sort = sort or "recommended"
        if sort == "price":
            salons.sort(key=lambda salon: (salon.search_primary_price is None, salon.search_primary_price or 0, -(salon.avg_score or 0)))
        elif sort == "nearest" and distance_supported:
            salons.sort(key=lambda salon: (salon.search_distance_km is None, salon.search_distance_km or 0, -(salon.avg_score or 0)))
        elif sort == "newest":
            salons.sort(key=lambda salon: salon.registere_date, reverse=True)
        elif sort == "rating":
            salons.sort(key=lambda salon: (-(salon.avg_score or 0), -(salon.total_reviews or 0), salon.registere_date))
        elif sort == "popular":
            salons.sort(key=lambda salon: (-(salon.total_reviews or 0), -(salon.avg_score or 0), salon.registere_date))
        elif sort == "discount":
            salons.sort(key=lambda salon: (not getattr(salon, "has_active_service_discount", False), -(getattr(salon, "active_service_discount_percent", 0) or 0), salon.search_primary_price or 0))
        elif sort in {"available", "available_soon"}:
            salons.sort(key=lambda salon: (0 if getattr(salon, "search_available_label", "") else 1, getattr(salon, "search_next_available_sort", 999999), -(salon.avg_score or 0)))
        else:
            salons.sort(key=lambda salon: (-cls.quality_score(salon), salon.registere_date))
        for idx, salon in enumerate(salons, start=1):
            salon.search_rank = idx
            salon.search_ranking_score = cls.quality_score(salon)
        return salons


class SearchLogService:
    @staticmethod
    def serialize_filters(filters) -> dict:
        return {
            "q_type": filters.q_type,
            "q_id": filters.q_id,
            "group": filters.group_id,
            "services": filters.service_ids_value,
            "date": filters.date_input,
            "period": filters.period,
            "time": filters.exact_time_input,
            "min_price": filters.min_price,
            "max_price": filters.max_price,
            "min_rating": filters.min_rating,
            "discounted": filters.discounted,
            "available": filters.available,
            "verified": filters.verified,
            "lat": filters.latitude,
            "lng": filters.longitude,
        }

    @classmethod
    def record(cls, request, filters, *, results_count: int, first_result_salon_id: int | None = None):
        from apps.search.models import SearchLog

        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        session_key = getattr(request.session, "session_key", "") or ""
        if not session_key and hasattr(request, "session"):
            try:
                request.session.save()
                session_key = request.session.session_key or ""
            except Exception:
                session_key = ""
        with transaction.atomic():
            return SearchLog.objects.create(
                user=user,
                session_key=session_key,
                query=filters.query[:255],
                normalized_query=normalize_search_text(filters.query)[:255],
                location=filters.location[:255],
                q_type=filters.q_type,
                q_id=filters.q_id,
                filters=cls.serialize_filters(filters),
                sort=filters.sort or "recommended",
                results_count=max(int(results_count or 0), 0),
                no_result=not bool(results_count),
                first_result_salon_id=first_result_salon_id,
                ip_address=get_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:2000],
            )


class AvailabilityWindowService:
    """Helperهای سبک برای فیلترهای امروز/این هفته.

    منطق دقیق availability همچنان در search utils استفاده می‌شود تا با ساختار فعلی پروژه
    سازگار بماند؛ این کلاس فقط تعیین بازه جستجو را متمرکز می‌کند.
    """

    @staticmethod
    def candidate_dates(filters) -> list[dt_date]:
        if filters.search_date:
            return [filters.search_date]
        today = timezone.localdate()
        if filters.available == "today":
            return [today]
        if filters.available in {"this_week", "available_soon"}:
            return [today + timedelta(days=offset) for offset in range(0, 7)]
        return []
