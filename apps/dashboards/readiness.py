from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts.models import Stylist
from apps.dashboards.jalali_utils import to_persian_digits
from apps.salons.models import SalonVerificationStatus
from apps.stylists.models import StylistSchedule


def _safe_reverse(name, fallback="#", kwargs=None):
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return fallback


def _safe_count(queryset_or_manager, **filters):
    try:
        if filters:
            queryset_or_manager = queryset_or_manager.filter(**filters)
        return queryset_or_manager.count()
    except Exception:
        return 0


def _safe_exists(queryset_or_manager, **filters):
    try:
        if filters:
            queryset_or_manager = queryset_or_manager.filter(**filters)
        return queryset_or_manager.exists()
    except Exception:
        return False


PUBLIC_BOOKING_STYLIST_VISIBILITIES = (
    Stylist.PublicVisibility.PUBLIC,
    Stylist.PublicVisibility.SALON_ONLY,
)


def _has_bookable_service_schedule_path(
    salon,
    *,
    active_services_qs=None,
    active_stylists_qs=None,
):
    """بررسی وجود حداقل یک مسیر واقعی برای رزرو عمومی سالن.

    متخصص باید در همین سالن فعال و قابل‌نمایش باشد، به یک خدمت فعال و
    قیمت‌گذاری‌شده متصل باشد و برای همان خدمت یا به‌صورت عمومی، برنامه کاری
    امروز یا آینده در همین سالن داشته باشد.
    """
    if salon is None:
        return False

    services_qs = active_services_qs
    if services_qs is None:
        services_qs = salon.services.filter(is_active=True)

    bookable_service_ids = set(
        services_qs.filter(
            base_price__gt=0,
            duration_minutes__gt=0,
        ).values_list("pk", flat=True)
    )
    if not bookable_service_ids:
        return False

    stylists_qs = active_stylists_qs
    if stylists_qs is None:
        stylists_qs = salon.stylists.filter(is_active=True)

    stylists_qs = stylists_qs.filter(
        public_visibility__in=PUBLIC_BOOKING_STYLIST_VISIBILITIES
    )

    stylist_ids = set(stylists_qs.values_list("pk", flat=True))
    if not stylist_ids:
        return False

    linked_pairs = set(
        stylists_qs.filter(services_of_stylist__pk__in=bookable_service_ids)
        .values_list("pk", "services_of_stylist__pk")
        .distinct()
    )
    if not linked_pairs:
        return False

    schedule_pairs = set(
        StylistSchedule.objects.filter(
            salon=salon,
            stylist_id__in=stylist_ids,
            date__gte=timezone.localdate(),
        ).values_list("stylist_id", "service_id")
    )

    general_schedule_stylists = {
        stylist_id for stylist_id, service_id in schedule_pairs if service_id is None
    }

    return any(
        stylist_id in general_schedule_stylists
        or (stylist_id, service_id) in schedule_pairs
        for stylist_id, service_id in linked_pairs
    )


def _build_item(
    *,
    key,
    title,
    description,
    is_done,
    action_label,
    action_url,
    weight=1,
):
    return {
        "key": key,
        "title": title,
        "description": description,
        "is_done": bool(is_done),
        "action_label": action_label,
        "action_url": action_url,
        "weight": weight,
    }


def build_salon_readiness_checklist(
    salon,
    *,
    schedule_exists=None,
    facts=None,
):
    """
    Read-only checklist for salon launch readiness.

    This helper does not mutate models, does not create rows, and does not
    change booking/payment behavior. It only reads the current salon state.
    """
    if salon is None:
        return {
            "enabled": False,
            "is_ready": False,
            "percent": 0,
            "percent_label": "۰٪",
            "completed_count": 0,
            "total_count": 0,
            "missing_count": 0,
            "items": [],
            "missing_items": [],
            "summary": "برای نمایش چک‌لیست، ابتدا باید سالن ساخته شود.",
        }
    facts = facts or {}

    def fact_or_default(key, factory):
        if key in facts:
            return facts[key]
        return factory()

    active_services_qs = salon.services.filter(is_active=True)
    active_stylists_qs = salon.stylists.filter(is_active=True)

    active_services_count = int(
        fact_or_default(
            "active_services_count",
            lambda: _safe_count(active_services_qs),
        )
        or 0
    )

    priced_services_count = int(
        fact_or_default(
            "priced_services_count",
            lambda: _safe_count(
                active_services_qs,
                base_price__gt=0,
                duration_minutes__gt=0,
            ),
        )
        or 0
    )

    active_stylists_count = int(
        fact_or_default(
            "active_stylists_count",
            lambda: _safe_count(active_stylists_qs),
        )
        or 0
    )

    has_stylist_service_link = bool(
        fact_or_default(
            "has_stylist_service_link",
            lambda: _safe_exists(
                active_stylists_qs.filter(
                    services_of_stylist__in=active_services_qs
                ).distinct()
            ),
        )
    )

    if schedule_exists is None:
        schedule_exists = bool(
            fact_or_default(
                "schedule_exists",
                lambda: StylistSchedule.objects.filter(
                    salon=salon,
                    stylist__is_active=True,
                    stylist__public_visibility__in=(
                        PUBLIC_BOOKING_STYLIST_VISIBILITIES
                    ),
                    date__gte=timezone.localdate(),
                ).exists(),
            )
        )

    has_bookable_path = bool(
        fact_or_default(
            "has_bookable_path",
            lambda: _has_bookable_service_schedule_path(
                salon,
                active_services_qs=active_services_qs,
                active_stylists_qs=active_stylists_qs,
            ),
        )
    )

    has_location = bool(getattr(salon, "location", None))

    has_gallery = bool(
        fact_or_default(
            "has_gallery",
            lambda: _safe_exists(salon.gallery_images),
        )
    )

    has_opening_hours = bool(
        fact_or_default(
            "has_opening_hours",
            lambda: _safe_exists(
                salon.opening_hours,
                is_closed=False,
                open_time__isnull=False,
                close_time__isnull=False,
            ),
        )
    )

    profile_is_complete = bool(
        str(getattr(salon, "salon_name", "") or "").strip()
        and str(getattr(salon, "description", "") or "").strip()
        and str(getattr(salon, "address", "") or "").strip()
        and getattr(salon, "phone_number", None)
    )

    payout_is_complete = bool(getattr(salon, "payout_profile_complete", False))
    is_verified = (
        getattr(salon, "verification_status", "") == SalonVerificationStatus.VERIFIED
    )
    is_public_active = bool(getattr(salon, "is_active", False))

    items = [
        _build_item(
            key="profile",
            title="اطلاعات اصلی سالن کامل است",
            description="نام، توضیحات، شماره تماس و آدرس سالن باید تکمیل شده باشد.",
            is_done=profile_is_complete,
            action_label="تکمیل پروفایل",
            action_url=_safe_reverse("dashboards:salon_profile"),
            weight=2,
        ),
        _build_item(
            key="location",
            title="موقعیت مکانی ثبت شده است",
            description="برای نمایش درست سالن و اعتماد مشتری، موقعیت روی نقشه لازم است.",
            is_done=has_location,
            action_label="ویرایش موقعیت",
            action_url=_safe_reverse("dashboards:salon_profile"),
            weight=1,
        ),
        _build_item(
            key="gallery",
            title="گالری یا تصویر سالن ثبت شده است",
            description="تصویر واقعی سالن روی تصمیم مشتری برای رزرو اثر مستقیم دارد.",
            is_done=has_gallery,
            action_label="مدیریت گالری",
            action_url=_safe_reverse("dashboards:salon_profile"),
            weight=1,
        ),
        _build_item(
            key="services",
            title="حداقل ۳ خدمت فعال با قیمت و مدت‌زمان وجود دارد",
            description="برای شروع رزرو آنلاین، بهتر است حداقل سه خدمت قابل انتخاب فعال باشد.",
            is_done=active_services_count >= 3 and priced_services_count >= 3,
            action_label="مدیریت خدمات",
            action_url=_safe_reverse("dashboards:service_menu"),
            weight=2,
        ),
        _build_item(
            key="team",
            title="حداقل یک متخصص فعال ثبت شده است",
            description="رزرو آنلاین بدون متخصص فعال برای مشتری قابل انجام نیست.",
            is_done=active_stylists_count >= 1,
            action_label="مدیریت تیم",
            action_url=_safe_reverse("dashboards:team_managment"),
            weight=2,
        ),
        _build_item(
            key="stylist_services",
            title="متخصص به خدمات فعال متصل شده است",
            description="هر متخصص باید حداقل به یکی از خدمات فعال سالن متصل باشد.",
            is_done=has_stylist_service_link,
            action_label="اتصال خدمات",
            action_url=_safe_reverse("dashboards:team_managment"),
            weight=2,
        ),
        _build_item(
            key="schedule",
            title="برنامه کاری متخصص ثبت شده است",
            description="تا وقتی شیفت یا برنامه کاری وجود نداشته باشد، ظرفیت رزرو واقعی شکل نمی‌گیرد.",
            is_done=schedule_exists,
            action_label="تنظیم شیفت",
            action_url=_safe_reverse("dashboards:scheduled_shifts"),
            weight=2,
        ),
        _build_item(
            key="bookable_path",
            title="حداقل یک مسیر رزرو واقعی وجود دارد",
            description=(
                "یک متخصص قابل‌نمایش باید هم‌زمان به خدمت فعال و قیمت‌گذاری‌شده "
                "متصل باشد و برای همان متخصص در همین سالن برنامه کاری جاری یا آینده ثبت شود."
            ),
            is_done=has_bookable_path,
            action_label="بررسی تیم و شیفت‌ها",
            action_url=_safe_reverse("dashboards:scheduled_shifts"),
            weight=3,
        ),
        _build_item(
            key="opening_hours",
            title="ساعت کاری سالن مشخص است",
            description="ساعت کاری سالن باید با ظرفیت رزرو و برنامه تیم هماهنگ باشد.",
            is_done=has_opening_hours,
            action_label="تنظیم ساعت کاری",
            action_url=_safe_reverse("dashboards:online_booking"),
            weight=1,
        ),
        _build_item(
            key="payout",
            title="اطلاعات تسویه تکمیل شده است",
            description="برای تسویه منظم، شبا، نام صاحب حساب و موبایل مسئول تسویه باید ثبت شود.",
            is_done=payout_is_complete,
            action_label="تنظیمات تسویه",
            action_url=_safe_reverse("dashboards:payout_settings"),
            weight=1,
        ),
        _build_item(
            key="verification",
            title="وضعیت احراز سالن تأیید شده است",
            description="برای نمایش مطمئن‌تر در فضای عمومی، وضعیت احراز باید تأیید شود.",
            is_done=is_verified,
            action_label="مشاهده پروفایل",
            action_url=_safe_reverse("dashboards:salon_profile"),
            weight=1,
        ),
        _build_item(
            key="public_active",
            title="سالن برای نمایش و رزرو فعال است",
            description="بعد از تکمیل موارد اصلی، سالن باید فعال باشد تا در مسیر رزرو عمومی استفاده شود.",
            is_done=is_public_active,
            action_label="تنظیم رزرو آنلاین",
            action_url=_safe_reverse("dashboards:online_booking"),
            weight=2,
        ),
    ]

    total_weight = sum(item["weight"] for item in items) or 1
    completed_weight = sum(item["weight"] for item in items if item["is_done"])
    percent = round((completed_weight / total_weight) * 100)

    completed_count = sum(1 for item in items if item["is_done"])
    total_count = len(items)
    missing_items = [item for item in items if not item["is_done"]]

    is_ready = percent >= 90 and not missing_items

    if not has_bookable_path:
        summary = (
            "برای رزرو واقعی، یک متخصص قابل‌نمایش را به خدمت فعال متصل کنید "
            "و برای همان متخصص در همین سالن برنامه کاری جاری یا آینده بسازید."
        )
    elif is_ready:
        summary = "سالن از نظر اطلاعات پایه، تیم، خدمات و رزرو آنلاین آماده شروع است."
    elif percent >= 70:
        summary = "سالن به وضعیت آماده نزدیک است؛ چند مورد باقی‌مانده را تکمیل کنید."
    else:
        summary = "برای شروع رزرو آنلاین، چند بخش اصلی سالن هنوز نیاز به تکمیل دارد."

    return {
        "enabled": True,
        "is_ready": is_ready,
        "percent": percent,
        "percent_label": f"{to_persian_digits(percent)}٪",
        "completed_count": completed_count,
        "completed_count_label": to_persian_digits(completed_count),
        "total_count": total_count,
        "total_count_label": to_persian_digits(total_count),
        "missing_count": len(missing_items),
        "missing_count_label": to_persian_digits(len(missing_items)),
        "items": items,
        "missing_items": missing_items,
        "has_bookable_path": has_bookable_path,
        "summary": summary,
    }
