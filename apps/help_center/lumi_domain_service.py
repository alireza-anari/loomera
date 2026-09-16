"""Loomera-side compatibility service for Lumi v2.

This module owns the temporary bridge to current Django models/application helpers.
`apps.lumi` depends only on the plain-dict functions exposed here; the AI/tool layer
never imports ORM models directly.

As first-class domain services are extracted into their owning apps, implementations
can move behind these functions without changing Lumi's tool contracts.
"""

from __future__ import annotations

from typing import Any, Iterable


def get_lumi_profile(*, actor: Any, authenticated: bool, primary_role: str, roles: Iterable[str]) -> dict[str, Any]:
    if actor is None or not authenticated:
        return {
            "name": "",
            "role": "guest",
            "roles": ["guest"],
            "phone_verified": False,
            "preferences": {},
        }

    name = ""
    for getter in ("get_full_name", "get_fullName"):
        method = getattr(actor, getter, None)
        if not callable(method):
            continue
        try:
            name = str(method() or "").strip()
        except Exception:
            name = ""
        if name:
            break
    if not name:
        name = str(getattr(actor, "first_name", "") or getattr(actor, "username", "") or "").strip()

    verified = False
    for attr in ("phone_verified", "is_phone_verified", "mobile_verified", "is_mobile_verified"):
        try:
            if hasattr(actor, attr):
                verified = bool(getattr(actor, attr))
                break
        except Exception:
            continue

    return {
        "name": name,
        "role": str(primary_role or "user"),
        "roles": sorted(str(role) for role in roles),
        "phone_verified": verified,
        "preferences": {},
    }


def get_services(*, salon_id: int | None = None, query: str = "", limit: int = 20) -> dict[str, Any]:
    from django.db.models import Q

    from apps.services.models import Services

    safe_limit = min(max(int(limit or 20), 1), 50)
    qs = Services.objects.filter(is_active=True)
    if salon_id:
        qs = qs.filter(services_of_salon_id=int(salon_id))
    else:
        qs = qs.filter(is_platform_catalog=True)

    query = str(query or "").strip()
    if query:
        qs = qs.filter(Q(service_name__icontains=query) | Q(slug__icontains=query))

    rows = list(qs.order_by("service_name", "id")[:safe_limit])
    return {
        "services": [
            {
                # Tool/public IDs stay anchored to the platform catalog when a
                # salon-owned service is linked to one.
                "id": int(item.catalog_source_id or item.pk),
                "salon_service_id": int(item.pk),
                "name": item.service_name,
                "slug": str(getattr(item, "slug", "") or ""),
            }
            for item in rows
        ]
    }


def _booking_scope(*, salon_id: int, service_id: int):
    from apps.help_center.actions.customer_booking import _active_salon, _salon_service

    salon = _active_salon(salon_id)
    service = _salon_service(salon, service_id)
    return salon, service


def get_service_price(*, salon_id: int, service_id: int, stylist_id: int | None = None) -> dict[str, Any]:
    from apps.help_center.actions.customer_booking import (
        PUBLIC_BOOKING_STYLIST_VISIBILITIES,
        _eligible_stylist,
    )
    from apps.orders.booking_utils import get_price_for_stylist_service

    salon, service = _booking_scope(salon_id=salon_id, service_id=service_id)

    if stylist_id is not None:
        stylist = _eligible_stylist(salon, service, stylist_id)
        rows = [
            {
                "stylist_id": stylist.user_id,
                "stylist_name": stylist.get_fullName(),
                "price": int(get_price_for_stylist_service(stylist, service)),
            }
        ]
    else:
        stylists = list(
            salon.stylists.filter(
                is_active=True,
                public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES,
                services_of_stylist=service,
            )
            .select_related("user")
            .distinct()
            .order_by("user_id")[:50]
        )
        rows = [
            {
                "stylist_id": stylist.user_id,
                "stylist_name": stylist.get_fullName(),
                "price": int(get_price_for_stylist_service(stylist, service)),
            }
            for stylist in stylists
        ]

    prices = [row["price"] for row in rows]
    return {
        "salon_id": salon.pk,
        "service_id": int(service_id),
        "salon_service_id": service.pk,
        "service_name": service.service_name,
        "available": bool(rows),
        "prices": rows,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
    }


def get_contact(*, salon_id: int) -> dict[str, Any]:
    from apps.salons.models import Salon

    salon = Salon.objects.filter(pk=int(salon_id), is_active=True).first()
    if salon is None:
        raise ValueError("این مجموعه فعال نیست یا در دسترس نیست.")

    phone = ""
    for field_name in ("phone", "phone_number", "mobile", "telephone"):
        value = getattr(salon, field_name, "")
        if value:
            phone = str(value)
            break

    return {
        "salon_id": salon.pk,
        "name": salon.salon_name,
        "address": str(getattr(salon, "address", "") or ""),
        "phone": phone,
    }


def get_availability(
    *,
    salon_id: int,
    service_id: int,
    stylist_id: int | None = None,
    date: str = "",
    period: str = "",
    limit: int = 18,
) -> dict[str, Any]:
    from apps.help_center.actions.customer_booking import (
        _eligible_stylist,
        _provider_rows,
        _requested_start_date,
        _slot_rows,
    )

    salon, service = _booking_scope(salon_id=salon_id, service_id=service_id)
    state = {"date": str(date or ""), "period": str(period or "")}
    start_date = _requested_start_date(state)
    safe_limit = min(max(int(limit or 18), 1), 50)

    if stylist_id is not None:
        stylist = _eligible_stylist(salon, service, stylist_id)
        slots = _slot_rows(
            salon=salon,
            stylist=stylist,
            service=service,
            state=state,
            max_slots=safe_limit,
        )
        return {
            "salon_id": salon.pk,
            "service_id": int(service_id),
            "salon_service_id": service.pk,
            "service_name": service.service_name,
            "options": [
                {
                    "salon_id": salon.pk,
                    "service_id": int(service_id),
                    "salon_service_id": service.pk,
                    "stylist_id": stylist.user_id,
                    "stylist_name": stylist.get_fullName(),
                    **slot,
                }
                for slot in slots
            ],
        }

    providers = _provider_rows(salon=salon, service=service, start_date=start_date)
    options: list[dict[str, Any]] = []
    for provider in providers:
        stylist = _eligible_stylist(salon, service, provider["id"])
        remaining = safe_limit - len(options)
        if remaining <= 0:
            break
        slots = _slot_rows(
            salon=salon,
            stylist=stylist,
            service=service,
            state=state,
            max_slots=remaining,
        )
        options.extend(
            {
                "salon_id": salon.pk,
                "service_id": int(service_id),
                "salon_service_id": service.pk,
                "stylist_id": stylist.user_id,
                "stylist_name": stylist.get_fullName(),
                "price": int(provider.get("price") or 0),
                **slot,
            }
            for slot in slots
        )

    options.sort(key=lambda item: (item.get("date", ""), item.get("time", ""), item.get("stylist_name", "")))
    return {
        "salon_id": salon.pk,
        "service_id": int(service_id),
        "salon_service_id": service.pk,
        "service_name": service.service_name,
        "options": options[:safe_limit],
    }


def prepare_booking(*, request: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Reuse the current safe booking-preview flow; this creates no Order."""
    from apps.help_center.actions.customer_booking import run_customer_booking_action

    if request is None:
        raise ValueError("برای آماده‌سازی رزرو، request معتبر لازم است.")

    salon_id = arguments.get("salon_id")
    service_id = arguments.get("service_id")
    stylist_id = arguments.get("stylist_id")
    selected_date = str(arguments.get("date") or "").strip()
    selected_time = str(arguments.get("time") or arguments.get("start_time") or "").strip()
    period = str(arguments.get("period") or "").strip()

    first = run_customer_booking_action(
        request,
        {
            "action": "select_salon",
            "salon_id": salon_id,
            "catalog_service_id": service_id,
            "discovery_state": {"date": selected_date, "date_label": "", "period": period},
        },
    )
    if first.get("kind") not in {"booking_stylists", "booking_no_stylists"}:
        return first
    if first.get("kind") == "booking_no_stylists":
        return first

    state = first.get("action_state") or {}
    second = run_customer_booking_action(
        request,
        {"action": "select_stylist", "stylist_id": stylist_id, "action_state": state},
    )
    if second.get("kind") != "booking_slots":
        return second

    state = second.get("action_state") or state
    return run_customer_booking_action(
        request,
        {
            "action": "select_slot",
            "date": selected_date,
            "time": selected_time,
            "action_state": state,
        },
    )
