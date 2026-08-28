from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.dashboards.jalali_utils import format_jalali_numeric, format_time_fa, to_persian_digits
from apps.orders.booking_utils import get_available_slots_for_service
from apps.orders.models import BookingQuickLink
from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus
from apps.services.models import Services

from .links import absolute_site_url


PROMOTION_LOOKAHEAD_DAYS = 7
PROMOTION_SLOT_LIMIT = 5


def _url(base_url: str, name: str, *args, **kwargs) -> str:
    return absolute_site_url(base_url, reverse(name, args=args, kwargs=kwargs))


def _fallback_url(base_url: str, path: str) -> str:
    return absolute_site_url(base_url, path)


def _safe_url(base_url: str, name: str, *args, fallback_path: str = "/", **kwargs) -> str:
    try:
        return _url(base_url, name, *args, **kwargs)
    except NoReverseMatch:
        return _fallback_url(base_url, fallback_path)


def _booking_quick_link_url(base_url: str, quick_link: BookingQuickLink) -> str:
    try:
        return _url(base_url, "orders:quick_booking_entry", token=str(quick_link.token))
    except NoReverseMatch:
        return _fallback_url(base_url, f"/orders/quick-booking/{quick_link.token}/")


def _salon_url(base_url: str, salon: Salon) -> str:
    try:
        if getattr(salon, "slug", ""):
            return _url(base_url, "salons:detail_salon_slug", salon_slug=salon.slug)
        return _url(base_url, "salons:detail_salon", salon_id=salon.pk)
    except NoReverseMatch:
        return _fallback_url(base_url, f"/detail_salon/{salon.pk}/")


def _stylist(user) -> Stylist | None:
    return getattr(user, "stylist", None) if user else None


def _manager_profile(user):
    return getattr(user, "salon_manager_profile", None) if user else None


def _active_memberships(stylist: Stylist | None) -> list[SalonMembership]:
    if stylist is None:
        return []
    return list(
        SalonMembership.objects.filter(stylist=stylist, status=SalonMembershipStatus.ACTIVE)
        .select_related("salon")
        .prefetch_related("salon__services")
        .order_by("salon__salon_name", "id")
    )


def _manager_salons(user) -> list[Salon]:
    manager = _manager_profile(user)
    if manager is None:
        return []
    return list(
        Salon.objects.filter(salon_manager=manager)
        .prefetch_related("services", "stylists")
        .order_by("-is_active", "salon_name", "id")
    )


def _first_active_service(salon: Salon, stylist: Stylist | None = None) -> Services | None:
    qs = Services.objects.filter(is_active=True, services_of_salon=salon)
    if stylist is not None:
        qs = qs.filter(stylists=stylist)
    return qs.order_by("service_name", "id").first()


def _display_stylist_name(stylist: Stylist | None) -> str:
    if stylist is None:
        return "متخصص"
    getter = getattr(stylist, "get_fullName", None)
    if callable(getter):
        return getter() or "متخصص"
    return str(stylist)


def _get_or_create_stylist_link(*, user, salon: Salon, stylist: Stylist) -> BookingQuickLink:
    existing = (
        BookingQuickLink.objects.filter(
            creator=user,
            salon=salon,
            stylist=stylist,
            mode=BookingQuickLink.Mode.STYLIST,
            is_permanent=True,
            is_active=True,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if existing:
        return existing
    return BookingQuickLink.objects.create(
        creator=user,
        salon=salon,
        stylist=stylist,
        mode=BookingQuickLink.Mode.STYLIST,
        payload={
            "mode": BookingQuickLink.Mode.STYLIST,
            "salon_id": salon.pk,
            "service_ids": [],
            "stylist_user_id": stylist.pk,
            "date": "",
            "time": "",
            "summary": {
                "salon": salon.salon_name,
                "stylist": _display_stylist_name(stylist),
            },
        },
        title=f"لینک رزرو {_display_stylist_name(stylist)} در {salon.salon_name}",
        is_permanent=True,
        expires_at=None,
    )


def _get_or_create_service_link(*, user, salon: Salon, service: Services) -> BookingQuickLink:
    existing = (
        BookingQuickLink.objects.filter(
            creator=user,
            salon=salon,
            service=service,
            stylist__isnull=True,
            mode=BookingQuickLink.Mode.SERVICE,
            is_permanent=True,
            is_active=True,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if existing:
        return existing
    return BookingQuickLink.objects.create(
        creator=user,
        salon=salon,
        service=service,
        mode=BookingQuickLink.Mode.SERVICE,
        payload={
            "mode": BookingQuickLink.Mode.SERVICE,
            "salon_id": salon.pk,
            "service_ids": [service.pk],
            "stylist_user_id": None,
            "date": "",
            "time": "",
            "summary": {
                "salon": salon.salon_name,
                "service": service.service_name,
            },
        },
        title=f"لینک رزرو {service.service_name} در {salon.salon_name}",
        is_permanent=True,
        expires_at=None,
    )


def _find_slots_for_stylist(stylist: Stylist, memberships: Iterable[SalonMembership], limit: int = PROMOTION_SLOT_LIMIT) -> list[dict]:
    today = timezone.localdate()
    found: list[dict] = []
    for membership in memberships:
        salon = membership.salon
        service = _first_active_service(salon, stylist=stylist)
        if service is None:
            continue
        for offset in range(PROMOTION_LOOKAHEAD_DAYS):
            date_value = today + timedelta(days=offset)
            slots = get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=date_value,
            )[:2]
            for start, end in slots:
                found.append({
                    "salon": salon,
                    "stylist": stylist,
                    "service": service,
                    "date": date_value,
                    "start": start,
                    "end": end,
                })
                if len(found) >= limit:
                    return found
    return found


def _find_slots_for_salon(salon: Salon, limit: int = PROMOTION_SLOT_LIMIT) -> list[dict]:
    today = timezone.localdate()
    memberships = list(
        SalonMembership.objects.select_related("stylist__user")
        .filter(salon=salon, status=SalonMembershipStatus.ACTIVE, stylist__isnull=False)
        .order_by("stylist__user__family", "stylist__user__name", "id")[:8]
    )
    found: list[dict] = []
    for membership in memberships:
        stylist = membership.stylist
        service = _first_active_service(salon, stylist=stylist)
        if service is None:
            continue
        for offset in range(PROMOTION_LOOKAHEAD_DAYS):
            date_value = today + timedelta(days=offset)
            slots = get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=date_value,
            )[:1]
            for start, end in slots:
                found.append({
                    "salon": salon,
                    "stylist": stylist,
                    "service": service,
                    "date": date_value,
                    "start": start,
                    "end": end,
                })
                break
            if len(found) >= limit or slots:
                break
    return found[:limit]


def _slot_text(slot: dict, *, include_salon: bool = True, include_stylist: bool = True) -> str:
    parts = [
        getattr(slot["service"], "service_name", "خدمت"),
        f"{format_jalali_numeric(slot['date'])} ساعت {format_time_fa(slot['start'])}",
    ]
    if include_stylist:
        parts.append(_display_stylist_name(slot.get("stylist")))
    if include_salon:
        parts.append(getattr(slot.get("salon"), "salon_name", "سالن"))
    return " | ".join(parts)


def _latest_article_for_stylist(stylist: Stylist):
    try:
        from apps.articles.models import Article

        return Article.objects.published().filter(author_stylist=stylist).order_by("-published_at", "-id").first()
    except Exception:
        return None


def _latest_article_for_salon(salon: Salon):
    try:
        from apps.articles.models import Article

        return Article.objects.published().filter(author_salon=salon).order_by("-published_at", "-id").first()
    except Exception:
        return None


def _latest_story_for_salon(salon: Salon, stylist: Stylist | None = None):
    try:
        from apps.articles.models import SalonStory

        qs = SalonStory.objects.published().filter(salon=salon)
        if stylist is not None:
            qs = qs.filter(stylist=stylist)
        now = timezone.now()
        qs = qs.filter(expires_at__gte=now)
        return qs.order_by("-published_at", "-id").first()
    except Exception:
        return None


def _article_url(base_url: str, article) -> str:
    try:
        return absolute_site_url(base_url, article.get_absolute_url())
    except NoReverseMatch:
        return _safe_url(base_url, "articles:magazine_home", fallback_path="/magazine/")


def _story_url(base_url: str, story) -> str:
    try:
        return _url(base_url, "articles:story_view", pk=story.pk)
    except NoReverseMatch:
        return _safe_url(base_url, "articles:story_explore", fallback_path="/magazine/stories/")


def _content_dashboard_url(base_url: str) -> str:
    return _safe_url(base_url, "dashboards:content_hub", fallback_path="/dashboards/content/")


def _stylist_quick_links_url(base_url: str) -> str:
    return _safe_url(base_url, "dashboards:stylist_quick_links", fallback_path="/dashboards/stylist/quick-links/")


def _manager_quick_links_url(base_url: str) -> str:
    return _safe_url(base_url, "dashboards:quick_links", fallback_path="/dashboards/quick-links/")


def _build_stylist_story_text(*, stylist: Stylist, salon: Salon, booking_url: str, slots: list[dict]) -> str:
    stylist_name = _display_stylist_name(stylist)
    slot_lines = [f"• {_slot_text(slot, include_salon=False, include_stylist=False)}" for slot in slots[:3]]
    slots_part = "\n".join(slot_lines) if slot_lines else "برای دیدن اولین وقت‌های آزاد، لینک رزرو را باز کن."
    return (
        f"متن آماده استوری برای {stylist_name}:\n"
        f"{stylist_name} در {salon.salon_name} آماده پذیرش نوبت‌های جدید است ✨\n"
        f"وقت‌های نزدیک:\n{slots_part}\n"
        f"رزرو آنلاین:\n{booking_url}"
    )


def _build_manager_story_text(*, salon: Salon, salon_url: str, booking_url: str | None, slots: list[dict]) -> str:
    slot_lines = [f"• {_slot_text(slot, include_salon=False, include_stylist=True)}" for slot in slots[:4]]
    slots_part = "\n".join(slot_lines) if slot_lines else "برای دیدن وقت‌های آزاد، صفحه سالن را باز کن."
    cta = booking_url or salon_url
    return (
        f"متن آماده استوری سالن {salon.salon_name}:\n"
        f"نوبت‌های جدید {salon.salon_name} فعال شد 🌿\n"
        f"وقت‌های نزدیک:\n{slots_part}\n"
        f"مشاهده و رزرو:\n{cta}"
    )


def render_stylist_promotion_pack(user, base_url: str) -> tuple[str, dict]:
    stylist = _stylist(user)
    memberships = _active_memberships(stylist)
    if stylist is None or not memberships:
        return (
            "برای ساخت متن آماده استوری و لینک رزرو، ابتدا باید نقش متخصص و همکاری فعال با سالن داشته باشید.",
            {"inline_keyboard": [[{"text": "منوی متخصص", "callback_data": "menu:stylist"}]]},
        )

    first_membership = memberships[0]
    first_salon = first_membership.salon
    quick_link = _get_or_create_stylist_link(user=user, salon=first_salon, stylist=stylist)
    booking_url = _booking_quick_link_url(base_url, quick_link)
    slots = _find_slots_for_stylist(stylist, memberships)
    story_text = _build_stylist_story_text(stylist=stylist, salon=first_salon, booking_url=booking_url, slots=slots)

    lines = ["تبلیغ و لینک رزرو متخصص 📣", "", story_text]

    service = _first_active_service(first_salon, stylist=stylist)
    if service is not None:
        lines.extend([
            "",
            "متن معرفی خدمت:",
            f"خدمت {service.service_name} با {_display_stylist_name(stylist)} در {first_salon.salon_name} قابل رزرو است. برای انتخاب زمان مناسب از لینک زیر وارد شو:",
            booking_url,
        ])

    if slots:
        lines.extend(["", "چند وقت آزاد نزدیک:"])
        lines.extend(f"{to_persian_digits(index)}. {_slot_text(slot)}" for index, slot in enumerate(slots[:5], start=1))

    article = _latest_article_for_stylist(stylist)
    if article is not None:
        lines.extend(["", "محتوای قابل اشتراک متخصص:", f"{article.title}\n{_article_url(base_url, article)}"])

    story = _latest_story_for_salon(first_salon, stylist=stylist)
    if story is not None:
        lines.extend(["", "استوری منتشرشده مرتبط:", f"{story.title}\n{_story_url(base_url, story)}"])

    lines.extend([
        "",
        "این متن فقط برای کپی و انتشار دستی آماده شده است؛ انتشار خودکار استوری در این فاز انجام نمی‌شود.",
    ])

    rows: list[list[dict]] = [
        [{"text": "باز کردن لینک رزرو", "url": booking_url}],
        [
            {"text": "مدیریت لینک‌ها", "url": _stylist_quick_links_url(base_url)},
            {"text": "وقت‌های خالی من", "callback_data": "menu:stylist_slots"},
        ],
        [
            {"text": "محتوا و تبلیغ سایت", "url": _content_dashboard_url(base_url)},
            {"text": "منوی متخصص", "callback_data": "menu:stylist"},
        ],
    ]
    if article is not None:
        rows.insert(1, [{"text": "مشاهده مقاله", "url": _article_url(base_url, article)}])
    if story is not None:
        rows.insert(1, [{"text": "مشاهده استوری", "url": _story_url(base_url, story)}])

    return "\n".join(lines).strip(), {"inline_keyboard": rows[:7]}


def render_manager_promotion_pack(user, base_url: str, *, salon_id: int | None = None) -> tuple[str, dict]:
    salons = _manager_salons(user)
    if not salons:
        return (
            "برای ساخت متن آماده استوری سالن، نقش مدیر سالن باید روی حساب شما فعال باشد.",
            {"inline_keyboard": [[{"text": "منوی مدیر", "callback_data": "menu:manager"}]]},
        )

    salon = None
    if salon_id:
        salon = next((item for item in salons if int(item.pk) == int(salon_id)), None)
    salon = salon or salons[0]

    salon_url = _salon_url(base_url, salon)
    service = _first_active_service(salon)
    booking_url = None
    if service is not None:
        quick_link = _get_or_create_service_link(user=user, salon=salon, service=service)
        booking_url = _booking_quick_link_url(base_url, quick_link)

    slots = _find_slots_for_salon(salon)
    story_text = _build_manager_story_text(salon=salon, salon_url=salon_url, booking_url=booking_url, slots=slots)

    lines = ["تبلیغ سالن / متن آماده استوری 📣", "", story_text]

    if service is not None:
        lines.extend([
            "",
            "متن معرفی خدمت:",
            f"خدمت {service.service_name} در {salon.salon_name} قابل رزرو است. زمان‌های آزاد را از لینک زیر ببین:",
            booking_url or salon_url,
        ])

    if slots:
        first_slot = slots[0]
        lines.extend([
            "",
            "متن معرفی متخصص:",
            f"{_display_stylist_name(first_slot.get('stylist'))} برای {getattr(first_slot.get('service'), 'service_name', 'خدمت')} در {salon.salon_name} وقت آزاد دارد.",
        ])
        lines.extend(["", "چند وقت آزاد نزدیک:"])
        lines.extend(f"{to_persian_digits(index)}. {_slot_text(slot, include_salon=False)}" for index, slot in enumerate(slots[:5], start=1))

    article = _latest_article_for_salon(salon)
    if article is not None:
        lines.extend(["", "مقاله/محتوای قابل اشتراک سالن:", f"{article.title}\n{_article_url(base_url, article)}"])

    story = _latest_story_for_salon(salon)
    if story is not None:
        lines.extend(["", "استوری منتشرشده سالن:", f"{story.title}\n{_story_url(base_url, story)}"])

    lines.extend([
        "",
        "این متن فقط برای کپی و انتشار دستی آماده شده است؛ انتشار خودکار استوری در این فاز انجام نمی‌شود.",
    ])

    rows: list[list[dict]] = [[{"text": "صفحه سالن", "url": salon_url}]]
    if booking_url:
        rows.append([{"text": "لینک رزرو خدمت", "url": booking_url}])
    if article is not None:
        rows.append([{"text": "مشاهده مقاله", "url": _article_url(base_url, article)}])
    if story is not None:
        rows.append([{"text": "مشاهده استوری", "url": _story_url(base_url, story)}])
    rows.extend([
        [
            {"text": "مدیریت لینک‌ها", "url": _manager_quick_links_url(base_url)},
            {"text": "وقت خالی متخصصان", "callback_data": f"menu:manager_slots:{salon.pk}"},
        ],
        [
            {"text": "محتوا و تبلیغ سایت", "url": _content_dashboard_url(base_url)},
            {"text": "منوی مدیر", "callback_data": "menu:manager"},
        ],
    ])
    return "\n".join(lines).strip(), {"inline_keyboard": rows[:8]}
