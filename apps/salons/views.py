from apps.main.ui_feedback import user_error_message
import logging
from collections import Counter
from urllib import request
from django.db.models import (
    Avg,
    Min,
    Prefetch,
    Q,
    Exists,
    OuterRef,
    BooleanField,
    Count,
    Value,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, HttpResponseBadRequest
from django.utils import timezone
from django.views import View
from django.conf import settings
from apps.accounts.models import WorkSamples, Customer, Stylist
from apps.comments_scores_favories.forms import CommentScoringForm
from apps.discounts.utils import (
    active_discount_basket_prefetch,
    active_discount_basket_queryset,
    attach_active_service_discount_meta,
    attach_service_discount_meta,
)
from apps.comments_scores_favories.models import Comments, Favorits
from apps.services.models import GroupServices, Services
from apps.services.views import service_group_image_url
from .models import Salon, SalonVisit, SalonOpeningHours
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from apps.orders.models import OrderDetail, Order
from django.urls import reverse
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist, ValidationError
from apps.articles.models import Article, SalonStory
from apps.articles.services import build_story_payload, published_stories_queryset
from apps.main.seo import build_breadcrumb_schema, build_salon_schema
from apps.stylists.profile_services import (
    build_salon_stylist_profile_context,
    can_show_stylist_on_salon_profile,
    public_salon_membership_prefetch,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------------------------------------------------
def _to_persian_digits(value):
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _format_persian_compact_number(value, show_plus=True):
    value = int(value or 0)

    if value >= 1_000_000:
        number = round(value / 1_000_000, 1)
        label = f"{number:g}M"
    elif value >= 1_000:
        number = round(value / 1_000, 1)
        label = f"{number:g}K"
    else:
        label = str(value)

    if show_plus and value > 0:
        label = f"+{label}"

    return _to_persian_digits(label)


def _format_persian_rating(value):
    value = float(value or 0)

    if value <= 0:
        return _to_persian_digits("0")

    return _to_persian_digits(f"{value:.1f}")


def _safe_media_url(file_field):
    """
    URL امن برای ImageField/FileField برمی‌گرداند.
    در Object Storage نباید مسیر تصویر را دستی با MEDIA_URL بسازیم؛
    باید از خود field.url استفاده شود تا asset-proxy/signed-url درست کار کند.
    """
    if not file_field:
        return ""

    try:
        return file_field.url or ""
    except Exception:
        return ""


PUBLIC_WORK_SAMPLE_REVIEW_STATUSES = {"published", "approved"}

PUBLIC_WORK_SAMPLE_ALLOWED_CLIENT_CONSENT_STATUSES = {
    "",
    "not_required",
    "approved",
    "granted",
    "obtained",
    "consented",
}


def _public_salon_detail_query_max_chars():
    return max(
        int(getattr(settings, "PUBLIC_SALON_DETAIL_QUERY_MAX_CHARS", 1024) or 1),
        1,
    )


def _public_salon_review_appointment_id_max_chars():
    return max(
        int(
            getattr(
                settings,
                "PUBLIC_SALON_REVIEW_APPOINTMENT_ID_MAX_CHARS",
                20,
            )
            or 1
        ),
        1,
    )


def _validate_public_salon_query_size(request):
    query_string = request.META.get("QUERY_STRING") or ""
    if len(query_string.encode("utf-8")) > _public_salon_detail_query_max_chars():
        raise ValidationError("حجم فیلترهای صفحه مجموعه بیش از حد مجاز است.")


def _public_work_sample_client_consent_filter():
    return Q(contains_identifiable_client=False) | Q(
        client_consent_status__in=PUBLIC_WORK_SAMPLE_ALLOWED_CLIENT_CONSENT_STATUSES
    )


def _public_work_sample_salon_scope_filter(salon):
    return (
        Q(salon=salon)
        | Q(salon__isnull=True, appointment__isnull=True)
        | Q(salon__isnull=True, appointment__salon=salon)
    )


def _public_work_samples_for_salon_queryset(salon):
    return (
        WorkSamples.objects.filter(
            _public_work_sample_salon_scope_filter(salon),
            _public_work_sample_client_consent_filter(),
            is_active=True,
            is_public=True,
            review_status__in=PUBLIC_WORK_SAMPLE_REVIEW_STATUSES,
        )
        .select_related("service", "salon", "appointment")
        .order_by("-is_verified_work", "-id")
    )


def _public_salon_is_favorite_for_customer(*, salon, customer):
    if customer is None:
        return False

    return Favorits.objects.filter(
        favorite_user=customer,
        salon=salon,
    ).exists()


def _public_salon_stories_queryset(*, salon, customer):
    visible_states = [
        SalonStory.Visibility.PUBLIC,
        SalonStory.Visibility.SALON_PAGE_ONLY,
    ]

    if _public_salon_is_favorite_for_customer(salon=salon, customer=customer):
        visible_states.append(SalonStory.Visibility.FAVORITES_ONLY)

    return published_stories_queryset().filter(
        salon=salon,
        visibility__in=visible_states,
    )


def _clean_public_salon_review_appointment_id(request, *, salon, customer):
    raw_value = str(request.GET.get("appointment_id") or "").strip()

    if not raw_value:
        return ""

    if len(raw_value) > _public_salon_review_appointment_id_max_chars():
        return ""

    if not raw_value.isdigit():
        return ""

    if customer is None:
        return ""

    appointment_id = int(raw_value)

    if not OrderDetail.objects.filter(
        pk=appointment_id,
        salon=salon,
        order__customer=customer,
    ).exists():
        return ""

    return str(appointment_id)


class PublicHomeView(View):
    """Public landing page aligned with the latest Loomera direction."""

    def get_service_categories(self):
        """Load active service groups from the backend for the homepage category cards."""

        categories_qs = GroupServices.objects.filter(
            is_active=True,
            group_parent__isnull=True,
        )

        categories = categories_qs.annotate(
            services_count=Count(
                "services_of_group",
                filter=Q(services_of_group__is_active=True),
                distinct=True,
            ),
            salons_count=Count(
                "services_of_group__services_of_salon",
                filter=Q(
                    services_of_group__is_active=True,
                    services_of_group__services_of_salon__is_active=True,
                ),
                distinct=True,
            ),
        ).order_by("group_title", "id")[:8]

        search_url = reverse("search:search_page")

        return [
            {
                "id": category.id,
                "label": category.group_title,
                "description": category.descriptions
                or "مشاهده مجموعه‌ها و متخصص‌های فعال این دسته",
                "image_url": service_group_image_url(category),
                "services_count": category.services_count,
                "services_count_label": (
                    f"{_to_persian_digits(category.services_count)} خدمت"
                    if category.services_count
                    else ""
                ),
                "salons_count": category.salons_count,
                "services_url": reverse("services:group_services", args=[category.id]),
                "search_url": f"{search_url}?group={category.id}",
            }
            for category in categories
        ]

    def get_service_select_groups(self):
        return (
            GroupServices.objects.filter(is_active=True)
            .order_by("group_title", "id")
            .values("id", "group_title")
        )

    def get_homepage_stats(self):
        active_salons_count = Salon.objects.filter(is_active=True).count()

        active_services_count = Services.objects.filter(is_active=True).count()

        successful_bookings_count = Order.objects.filter(
            status__in=["confirmed", "paid", "completed"]
        ).count()

        average_rating = (
            Salon.objects.filter(is_active=True)
            .aggregate(
                average=Avg(
                    "scoring_salon__score",
                    filter=Q(scoring_salon__score__gt=0),
                )
            )
            .get("average")
            or 0
        )

        return [
            {
                "value": _format_persian_compact_number(active_salons_count),
                "label": "مجموعه و متخصص معتبر",
                "icon": "fa-solid fa-shop",
            },
            {
                "value": _format_persian_compact_number(active_services_count),
                "label": "خدمات متنوع و تخصصی",
                "icon": "fa-solid fa-shield-halved",
            },
            {
                "value": _format_persian_compact_number(successful_bookings_count),
                "label": "کاربر راضی",
                "icon": "fa-solid fa-users",
            },
            {
                "value": _format_persian_rating(average_rating),
                "label": "میانگین امتیاز کاربران",
                "icon": "fa-solid fa-star",
            },
        ]

    def get_app_download_links(self):
        return {
            "android": {
                "label": "دانلود اپلیکیشن",
                "url": "#",
            },
            "webapp": {
                "label": "ورود به وب اپ",
                "url": reverse("salons:home"),
            },
        }

    def get(self, request):
        featured_salons_qs = (
            Salon.objects.filter(is_active=True)
            .select_related("neighborhood")
            .prefetch_related(active_discount_basket_prefetch())
            .annotate(
                avg_score=Avg("scoring_salon__score"),
                num_scores=Count("scoring_salon__score"),
            )
            .order_by("-avg_score", "-registere_date")[:4]
        )

        featured_salons = attach_active_service_discount_meta(list(featured_salons_qs))

        service_categories = self.get_service_categories()
        service_search_groups = self.get_service_select_groups()

        context = {
            "homepage_stats": self.get_homepage_stats(),
            "app_download_links": self.get_app_download_links(),
            "featured_salons": featured_salons,
            "hero_features": [
                {
                    "icon": "fa-solid fa-shield-halved",
                    "title": "محیطی امن و مطمئن",
                    "text": "مجموعه های معتبر با نظرات واقعی و انتخاب قابل اعتماد",
                },
                {
                    "icon": "fa-regular fa-clock",
                    "title": "رزرو سریع و آسان",
                    "text": "در چند دقیقه زمان مناسب خود را پیدا کنید و رزرو بگیرید",
                },
                {
                    "icon": "fa-solid fa-star",
                    "title": "تخصص و تجربه",
                    "text": "متخصص های حرفه ای برای خدمات زیبایی، درمانی و مراقبتی",
                },
            ],
            "service_categories": service_categories,
            "service_search_groups": service_search_groups,
            "homepage_stats": [
                {
                    "value": "+۵۰۰",
                    "label": "مجموعه و متخصص معتبر",
                    "icon": "fa-solid fa-shop",
                },
                {
                    "value": "+۱۰۰۰",
                    "label": "خدمات متنوع و تخصصی",
                    "icon": "fa-solid fa-shield-check",
                },
                {"value": "+۲۰K", "label": "کاربر راضی", "icon": "fa-solid fa-users"},
                {
                    "value": "+۴.۸",
                    "label": "میانگین امتیاز کاربران",
                    "icon": "fa-solid fa-star",
                },
            ],
        }

        return render(request, "pages/home.html", context)


# --------------------------------------------------------------------------------------------------------------------------------
def _safe_file_url(value):
    """
    ImageField/FileField/String URL را بدون خطا به url تبدیل می‌کند.
    """
    if value in (None, ""):
        return ""

    try:
        url = value.url
        return url or ""
    except Exception:
        pass

    if isinstance(value, str):
        return value

    return ""


def _first_url_from_fields(obj, field_names):
    for field_name in field_names:
        value = getattr(obj, field_name, None)
        url = _safe_file_url(value)
        if url:
            return url
    return ""


def _first_related_image_url(obj):
    """
    اگر تصویر مجموعه داخل گالری یا relationهای مشابه باشد، اولین تصویر را پیدا می‌کند.
    این helper عمداً defensive نوشته شده تا اگر related_name فرق داشت، صفحه crash نکند.
    """
    related_candidates = [
        "gallery",
        "galleries",
        "images",
        "salon_images",
        "gallery_images",
        "pictures",
        "photos",
        "portfolios",
    ]

    image_field_candidates = [
        "image",
        "photo",
        "picture",
        "file",
        "thumbnail",
        "cover_image",
        "banner_image",
    ]

    for related_name in related_candidates:
        related_manager = getattr(obj, related_name, None)
        if not related_manager:
            continue

        try:
            first_item = related_manager.first()
        except Exception:
            try:
                first_item = related_manager.all().first()
            except Exception:
                first_item = None

        if not first_item:
            continue

        url = _first_url_from_fields(first_item, image_field_candidates)
        if url:
            return url

    return ""


def _build_discount_label(salon):
    label = (
        getattr(salon, "active_service_discount_label", None)
        or getattr(salon, "discount_label", None)
        or ""
    )

    if label:
        return label

    percent = (
        getattr(salon, "active_service_discount_percent", None)
        or getattr(salon, "max_discount", None)
        or 0
    )

    try:
        percent = int(percent or 0)
    except Exception:
        percent = 0

    if percent > 0:
        return f"{percent}٪ تخفیف"

    return ""


def _normalize_salon_cards(salons):
    """
    هر Salon را برای template آماده می‌کند تا کارت مجموعه از fieldهای ثابت بخواند.
    """
    image_field_candidates = [
        "banner_image",
        "cover_image",
        "salon_image",
        "image_salon",
        "image",
        "logo",
        "salon_logo",
        "thumbnail",
        "main_image",
        "header_image",
        "profile_image",
    ]

    for salon in salons:
        salon.card_image_url = _first_url_from_fields(
            salon, image_field_candidates
        ) or _first_related_image_url(salon)

        salon.card_rating = (
            getattr(salon, "avg_score", None)
            or getattr(salon, "avg_rating", None)
            or getattr(salon, "rating", None)
            or 0
        )

        salon.card_reviews_count = (
            getattr(salon, "num_scores", None)
            or getattr(salon, "reviews_count", None)
            or getattr(salon, "total_reviews", None)
            or 0
        )

        salon.card_discount_label = _build_discount_label(salon)

        neighborhood = getattr(salon, "neighborhood", None)
        city = getattr(salon, "city", None)

        salon.card_location = (
            getattr(neighborhood, "name", None)
            or getattr(city, "name", None)
            or getattr(salon, "address", None)
            or getattr(salon, "location_text", None)
            or ""
        )

        salon.card_min_price = (
            getattr(salon, "min_price", None)
            or getattr(salon, "lowest_price", None)
            or getattr(salon, "starting_price", None)
            or getattr(salon, "active_service_discount_price", None)
            or None
        )

    return salons


def _normalize_book_again_orders(order_details):
    """
    OrderDetailها را برای کارت رزرو مجدد آماده می‌کند.
    """
    for item in order_details:
        stylist = getattr(item, "stylist", None)
        stylist_user = getattr(stylist, "user", None)

        if stylist_user and hasattr(stylist_user, "get_fullName"):
            item.stylist_name = stylist_user.get_fullName()
        elif stylist_user and hasattr(stylist_user, "get_full_name"):
            item.stylist_name = stylist_user.get_full_name()
        else:
            item.stylist_name = ""

        service = getattr(item, "service", None)
        order = getattr(item, "order", None)

        item.price = (
            getattr(item, "price", None)
            or getattr(item, "final_price", None)
            or getattr(item, "total_price", None)
            or getattr(item, "service_price", None)
            or getattr(service, "price", None)
            or 0
        )

        if order and hasattr(order, "get_status_display"):
            item.status_display = order.get_status_display()
        else:
            item.status_display = ""

    return order_details


def _model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _resolve_service_group_model():
    """
    چون اسم مدل دسته‌بندی خدمات در پروژه‌ها ممکن است فرق داشته باشد،
    چند اسم رایج را تست می‌کنیم.
    اگر اسم مدل پروژه‌ات مشخص است، می‌توانی این بخش را ساده‌تر کنی.
    """
    candidates = [
        ("services", "ServiceGroup"),
        ("services", "ServiceGroups"),
        ("services", "Group"),
        ("services", "GroupServices"),
        ("salons", "ServiceGroup"),
    ]

    for app_label, model_name in candidates:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            continue

    return None


def _get_service_groups():
    ServiceGroupModel = _resolve_service_group_model()
    if not ServiceGroupModel:
        return []

    qs = ServiceGroupModel.objects.all()

    if _model_has_field(ServiceGroupModel, "is_active"):
        qs = qs.filter(is_active=True)

    if _model_has_field(ServiceGroupModel, "is_deleted"):
        qs = qs.filter(is_deleted=False)

    if _model_has_field(ServiceGroupModel, "group_parent"):
        qs = qs.filter(group_parent__isnull=True)

    order_fields = []
    for field_name in [
        "sort_order",
        "display_order",
        "order",
        "priority",
        "group_title",
        "title",
        "name",
    ]:
        if _model_has_field(ServiceGroupModel, field_name):
            order_fields.append(field_name)

    if order_fields:
        qs = qs.order_by(*order_fields)
    else:
        qs = qs.order_by("pk")

    groups = list(qs[:24])

    for group in groups:
        title = (
            getattr(group, "group_title", None)
            or getattr(group, "title", None)
            or getattr(group, "name", None)
            or str(group)
        )

        group.group_title = title

        group.card_image_url = service_group_image_url(group) or _first_url_from_fields(
            group,
            [
                "image",
                "icon",
                "group_image",
                "cover_image",
                "thumbnail",
                "picture",
            ],
        )

    return groups


def _safe_datetime_value(value):
    """
    برای sort کردن فیلدهایی که ممکن است None باشند.
    """
    return value or timezone.datetime.min.replace(
        tzinfo=timezone.get_current_timezone()
    )


# @method_decorator(cache_page(60 * 30), name='dispatch') # کش به مدت ۱۰ دقیقه
class ShowSalonsView(View):

    def get(self, request):
        user = request.user

        # علاقه‌مندی کاربر
        is_favorite_ann = (
            Exists(
                Favorits.objects.filter(
                    salon=OuterRef("pk"),
                    favorite_user__user=user,
                )
            )
            if user.is_authenticated
            else Value(False, output_field=BooleanField())
        )

        # کوئری اصلی مجموعه‌ها
        all_salons_qs = (
            Salon.objects.filter(is_active=True)
            .select_related("neighborhood")
            .prefetch_related(active_discount_basket_prefetch())
            .annotate(
                avg_score=Avg("scoring_salon__score"),
                num_scores=Count("scoring_salon__score", distinct=True),
                is_favorite=is_favorite_ann,
            )
        )

        # اجرای یک‌باره کوئری + اتصال اطلاعات تخفیف فعال
        all_salons_list = attach_active_service_discount_meta(list(all_salons_qs))

        # آماده‌سازی اطلاعات ثابت برای کارت مجموعه
        all_salons_list = _normalize_salon_cards(all_salons_list)

        # دسته‌بندی خدمات از دیتابیس
        service_groups = _get_service_groups()

        # مجموعه‌های اخیراً ثبت‌شده
        recent_salons = sorted(
            all_salons_list,
            key=lambda salon: _safe_datetime_value(
                getattr(salon, "registere_date", None)
            ),
            reverse=True,
        )[:12]

        # مجموعه‌های برتر
        top_salons = sorted(
            all_salons_list,
            key=lambda salon: (
                getattr(salon, "card_rating", 0) or 0,
                getattr(salon, "card_reviews_count", 0) or 0,
            ),
            reverse=True,
        )[:12]

        # محبوب‌ترین مجموعه‌ها
        popular_salons = sorted(
            all_salons_list,
            key=lambda salon: (
                getattr(salon, "card_reviews_count", 0) or 0,
                getattr(salon, "card_rating", 0) or 0,
            ),
            reverse=True,
        )[:12]

        # مجموعه‌های دارای بیشترین تخفیف
        best_discount_salons = [
            salon
            for salon in all_salons_list
            if getattr(salon, "has_active_service_discount", False)
            or getattr(salon, "active_service_discount_percent", 0)
            or getattr(salon, "card_discount_label", "")
        ]

        best_discount_salons = sorted(
            best_discount_salons,
            key=lambda salon: (
                getattr(salon, "active_service_discount_percent", 0) or 0,
                getattr(salon, "active_service_discount_max_amount", 0) or 0,
                getattr(salon, "card_rating", 0) or 0,
            ),
            reverse=True,
        )[:12]

        # مجموعه‌های موردعلاقه کاربر
        favorits_salons = []
        if user.is_authenticated:
            favorits_salons = [
                salon
                for salon in all_salons_list
                if getattr(salon, "is_favorite", False)
            ][:12]

        # آخرین مجموعه‌های بازدید شده کاربر
        last_visited_salons = []
        if user.is_authenticated:
            visited_salon_ids = list(
                SalonVisit.objects.filter(user=user)
                .order_by("-visit_date")
                .values_list("salon_id", flat=True)[:12]
            )

            visited_salons_dict = {
                salon.pk: salon
                for salon in all_salons_list
                if salon.pk in visited_salon_ids
            }

            last_visited_salons = [
                visited_salons_dict[salon_id]
                for salon_id in visited_salon_ids
                if salon_id in visited_salons_dict
            ]

        # رزرو مجدد: آخرین خدمات پرداخت‌شده گذشته
        book_again_orders = []
        if user.is_authenticated:
            try:
                recent_completed_order_details = (
                    OrderDetail.objects.filter(
                        order__customer__user=user,
                        order__is_finally=True,
                        order__is_paid=True,
                        date__lt=timezone.now().date(),
                    )
                    .select_related(
                        "salon",
                        "service",
                        "stylist",
                        "stylist__user",
                        "order",
                        "order__customer",
                    )
                    .order_by("-date", "-time")[:30]
                )

                seen_keys = set()
                unique_order_details = []

                for item in recent_completed_order_details:
                    key = (
                        getattr(item, "salon_id", None),
                        getattr(item, "service_id", None),
                        getattr(item, "stylist_id", None),
                    )

                    if key in seen_keys:
                        continue

                    seen_keys.add(key)
                    unique_order_details.append(item)

                    if len(unique_order_details) >= 8:
                        break

                book_again_orders = _normalize_book_again_orders(unique_order_details)

            except Exception:
                try:
                    customer = Customer.objects.filter(user=user).first()

                    if customer:
                        recent_completed_order_details = (
                            OrderDetail.objects.filter(
                                order__customer=customer,
                                order__is_finally=True,
                                order__is_paid=True,
                                date__lt=timezone.now().date(),
                            )
                            .select_related(
                                "salon",
                                "service",
                                "stylist",
                                "stylist__user",
                                "order",
                            )
                            .order_by("-date", "-time")[:30]
                        )

                        seen_keys = set()
                        unique_order_details = []

                        for item in recent_completed_order_details:
                            key = (
                                getattr(item, "salon_id", None),
                                getattr(item, "service_id", None),
                                getattr(item, "stylist_id", None),
                            )

                            if key in seen_keys:
                                continue

                            seen_keys.add(key)
                            unique_order_details.append(item)

                            if len(unique_order_details) >= 8:
                                break

                        book_again_orders = _normalize_book_again_orders(
                            unique_order_details
                        )
                    else:
                        book_again_orders = []

                except Exception:
                    logger.exception("Failed to build book-again orders")
                    book_again_orders = []

        review_appointment_id = (request.GET.get("appointment_id") or "").strip()

        def _merge_unique_salons(*groups, limit=12):
            merged = []
            seen = set()
            for group in groups:
                for salon_item in list(group or []):
                    salon_id = getattr(salon_item, "pk", None)
                    if not salon_id or salon_id in seen:
                        continue
                    seen.add(salon_id)
                    merged.append(salon_item)
                    if len(merged) >= limit:
                        return merged
            return merged

        # Customer discovery intentionally exposes a few clear buckets rather
        # than repeating the same salons across discount/top/new/popular rails.
        for_you_salons = _merge_unique_salons(
            favorits_salons, last_visited_salons, limit=8
        )
        discover_salons = _merge_unique_salons(
            best_discount_salons, top_salons, popular_salons, recent_salons, limit=12
        )

        context = {
            "user": user,
            # بخش بالای صفحه
            "book_again_orders": book_again_orders,
            # دسته‌بندی خدمات
            "service_groups": service_groups,
            # اسلایدرهای مجموعه
            "best_discount_salons": best_discount_salons,
            "top_salons": top_salons,
            "recent_salons": recent_salons,
            "popular_salons": popular_salons,
            "favorits_salons": favorits_salons,
            "last_visited_salons": last_visited_salons,
            "for_you_salons": for_you_salons,
            "discover_salons": discover_salons,
            # موارد جانبی
            "review_appointment_id": review_appointment_id,
        }

        return render(request, "pages/show_salons.html", context)


# -------------------------------------------------------------------------------------------------------------------------------
class LegacySalonDetailRedirectView(View):
    def get(self, request, salon_id):
        salon = get_object_or_404(Salon, id=salon_id, is_active=True)
        return redirect(salon.get_absolute_url(), permanent=True)


# @method_decorator(cache_page(60 * 10), name='dispatch') # کش به مدت ۱۰ دقیقه
class DetailSalonView(View):
    def get(self, request, salon_slug=None, salon_id=None):
        try:
            _validate_public_salon_query_size(request)
        except ValidationError as exc:
            return HttpResponseBadRequest(user_error_message(exc, "درخواست صفحه مجموعه معتبر نیست."))
        # =================================================================
        # ۱. واکشی آبجکت اصلی مجموعه به همراه روابط اولیه
        # =================================================================
        salon = get_object_or_404(
            Salon.objects.prefetch_related(
                # ✨ OPTIMIZED: Use Prefetch to order the related data in the same query
                Prefetch(
                    "opening_hours",
                    queryset=SalonOpeningHours.objects.order_by("day_of_week"),
                    to_attr="ordered_opening_hours",  # Use a new attribute to store the sorted list
                ),
                "supplementary_info",
                "gallery_images",
            ),
            is_active=True,
            **({"slug": salon_slug} if salon_slug else {"id": salon_id}),
        )

        # =================================================================
        # ۲. واکشی متخصصان با تمام اطلاعات مورد نیاز تمپلیت (This was already good)
        # =================================================================
        stylists_qs = (
            salon.stylists.filter(is_active=True)
            .select_related("user")
            .annotate(avg_score=Avg("scoring_stylist__score"))
            .prefetch_related(
                public_salon_membership_prefetch(salon=salon),
                Prefetch(
                    "work_samples_of_stylist",
                    queryset=_public_work_samples_for_salon_queryset(salon),
                ),
            )
        )
        stylists_list = []
        salon_portfolio_count = 0
        for stylist in stylists_qs:
            profile_access = can_show_stylist_on_salon_profile(
                salon=salon,
                stylist=stylist,
                legacy_membership_confirmed=True,
            )
            if not profile_access.allowed:
                continue
            stylist.salon_membership = profile_access.membership
            stylist.salon_profile_url = reverse(
                "salons:stylist_profile_slug",
                args=[salon.slug, stylist.pk],
            )
            stylist.profile_image_url = _safe_media_url(stylist.profile_image)

            public_samples = []
            for sample in stylist.work_samples_of_stylist.all():
                sample.image_url = _safe_media_url(sample.sample_image)
                if sample.image_url:
                    public_samples.append(sample)

            stylist.public_work_samples = public_samples
            salon_portfolio_count += len(stylist.public_work_samples)
            stylists_list.append(stylist)

        # =================================================================
        # ۳. واکشی خدمات با تمام اطلاعات مورد نیاز تمپلیت (This was already good)
        # =================================================================
        services_qs = (
            Services.objects.filter(is_active=True, services_of_salon=salon)
            .prefetch_related("service_group", "stylists")
            .annotate(
                min_price=Min("service_prices__price"),
                avg_score=Avg("scoring_services__score"),
            )
        )
        active_baskets = list(active_discount_basket_queryset(salon=salon))
        services_list = attach_service_discount_meta(list(services_qs), active_baskets)

        # =================================================================
        # ۴. واکشی نظرات با تمام اطلاعات مورد نیاز تمپلیت
        # =================================================================
        comments_filter = Q(salon=salon, is_active=True)
        current_customer = None
        if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
            current_customer = request.user.customer_profile
            comments_filter |= Q(
                salon=salon, comment_user=current_customer, is_active=False
            )

        comments_qs = (
            Comments.objects.filter(comments_filter)
            # ✨ OPTIMIZED: Fetch the Customer's related User object to prevent N+1 queries in the loop.
            # Also prefetching the profile image's storage attribute if needed, though often not necessary.
            .select_related(
                "scoring",
                "stylist__user",
                "service",
                "comment_user__user",  # This is the key fix!
            ).order_by("-register_date")
        )

        # =================================================================
        # ۵. پردازش دیتا در پایتون (بدون کوئری اضافه)
        # =================================================================

        # ثبت بازدید کاربر
        if request.user.is_authenticated:
            SalonVisit.objects.update_or_create(
                user=request.user, salon=salon, defaults={"visit_date": timezone.now()}
            )

        # چیپ‌های فیلتر صفحه مجموعه فقط زیرگروه‌های واقعی را نشان می‌دهند.
        # گروه‌های والد بدون parent فقط برای دسته‌بندی کلی استفاده می‌شوند و نباید
        # در ریل بالای خدمات صفحه مجموعه نمایش داده شوند.
        service_groups = (
            GroupServices.objects.filter(
                services_of_group__in=services_qs,
                is_active=True,
                group_parent__isnull=False,
            )
            .select_related("group_parent")
            .distinct()
            .order_by("group_title", "id")
        )

        # پردازش لیست نظرات (This loop is now efficient)
        comments_list = []
        approved_scores = []
        for c in comments_qs:
            score_val = c.scoring.score if hasattr(c, "scoring") and c.scoring else None
            if c.is_active and score_val is not None:
                approved_scores.append(score_val)

            # Now, accessing c.comment_user.user will not cause a new query
            user_full_name = (
                c.comment_user.user.get_fullName()
                if c.comment_user and hasattr(c.comment_user, "user")
                else c.get_fullName()
            )  # Defensive check
            avatar_url = (
                c.comment_user.profile_image.url
                if c.comment_user and c.comment_user.profile_image
                else None
            )

            comments_list.append(
                {
                    "user_full_name": user_full_name,
                    "date": c.register_date,
                    "comment_text": c.comment_text,
                    "score": score_val,
                    "avatar_url": avatar_url,
                    "stylist_name": (
                        f"{c.stylist.user.name} {c.stylist.user.family}"
                        if c.stylist and hasattr(c.stylist, "user")
                        else None
                    ),
                    "service_name": c.service.service_name if c.service else None,
                    "is_pending": not c.is_active
                    and current_customer
                    and c.comment_user_id == current_customer.pk,
                }
            )

        # محاسبه آمار امتیازات
        score_counter = Counter(approved_scores)
        total_reviews = len(approved_scores)
        star_counts = {i: score_counter.get(i, 0) for i in range(1, 6)}
        average_score = (
            round(sum(approved_scores) / total_reviews, 1) if total_reviews > 0 else 0
        )

        # بررسی علاقمندی کاربر (یک کوئری ساده و ضروری)
        is_favorite = False
        if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
            is_favorite = Favorits.objects.filter(
                favorite_user=request.user.customer_profile, salon=salon
            ).exists()

        form = CommentScoringForm(salon=salon, customer=current_customer)

        # =================================================================
        # ۶. ساخت Context نهایی برای ارسال به Template
        # =================================================================
        review_is_allowed = (
            current_customer is not None and form.fields["service"].queryset.exists()
        )

        review_appointment_id = _clean_public_salon_review_appointment_id(
            request,
            salon=salon,
            customer=current_customer,
        )

        # =================================================================
        # ۶.۱ محتوای مجله و استوری‌های مرتبط با مجموعه
        # =================================================================
        salon_articles = (
            Article.objects.published()
            .filter(
                Q(author_salon=salon)
                | Q(author_stylist_id__in=[stylist.pk for stylist in stylists_list])
            )
            .filter(
                visibility=Article.Visibility.PUBLIC,
                allow_indexing=True,
            )
            .select_related(
                "category",
                "author_user",
                "author_stylist__user",
                "author_salon",
            )
            .prefetch_related("tags", "related_services", "related_service_groups")
            .distinct()[:6]
        )

        salon_stories = list(
            _public_salon_stories_queryset(
                salon=salon,
                customer=current_customer,
            )[:8]
        )

        salon_stories_payload = build_story_payload(
            salon_stories,
            user=request.user,
            request=request,
        )

        has_salon_content = bool(salon_articles) or bool(salon_stories)

        canonical_url = salon.canonical_url or request.build_absolute_uri(
            salon.get_absolute_url()
        )
        og_image_url = ""
        for candidate in (salon.og_image, salon.banner_image):
            try:
                if candidate and getattr(candidate, "url", ""):
                    og_image_url = request.build_absolute_uri(candidate.url)
                    break
            except Exception:
                continue
        salon_schema_json = build_salon_schema(
            request,
            salon,
            average_score=average_score,
            total_reviews=total_reviews,
            services=services_list,
        )
        breadcrumb_items = [
            ("خانه", reverse("salons:home")),
            ("مجموعه‌ها", reverse("salons:show_salons")),
        ]
        if salon.neighborhood_id:
            breadcrumb_items.append(
                (
                    salon.neighborhood.name,
                    reverse("salons:show_salons")
                    + f"?location={salon.neighborhood.name}",
                )
            )
        breadcrumb_items.append((salon.salon_name, salon.get_absolute_url()))
        salon_breadcrumb_schema_json = build_breadcrumb_schema(
            request, breadcrumb_items
        )

        context = {
            "salon": salon,
            "stylists": stylists_list,
            "services": services_list,
            "service_groups": service_groups,
            "comments_list": comments_list,
            "salon_portfolio_count": salon_portfolio_count,
            # ✨ OPTIMIZED: Access the prefetched, ordered attribute directly
            "opening_hours_list": salon.ordered_opening_hours,
            # ✨ OPTIMIZED: Access prefetched data directly without .all()
            "supplementary_info": salon.supplementary_info.all(),  # .all() is ok here, but direct access is cleaner
            "average_score": average_score,
            "total_reviews": total_reviews,
            "star_counts": star_counts,
            "is_favorite": is_favorite,
            "form": form,
            "review_is_allowed": review_is_allowed,
            "hide_navbar": True,
            "map_provider_enabled": getattr(settings, "MAP_PROVIDER_ENABLED", False),
            "review_appointment_id": review_appointment_id,
            "salon_articles": salon_articles,
            "salon_stories": salon_stories,
            "salon_stories_payload": salon_stories_payload,
            "has_salon_content": has_salon_content,
            "canonical_url": canonical_url,
            "og_image_url": og_image_url,
            "salon_schema_json": salon_schema_json,
            "salon_breadcrumb_schema_json": salon_breadcrumb_schema_json,
            "robots_noindex": not bool(salon.allow_indexing),
        }
        return render(request, "pages/detail_salon.html", context)


# -------------------------------------------------------------------------------------------------------------


class SalonStylistProfileView(View):
    """Public stylist profile scoped to a salon page.

    This page is intentionally salon-contextual: ratings, services,
    portfolio and reviews are shown in the context of the current salon first.
    """

    def get(self, request, stylist_id, salon_id=None, salon_slug=None):
        try:
            _validate_public_salon_query_size(request)
        except ValidationError as exc:
            return HttpResponseBadRequest(user_error_message(exc, "درخواست صفحه مجموعه معتبر نیست."))

        salon_lookup = {"slug": salon_slug} if salon_slug else {"id": salon_id}
        salon = get_object_or_404(
            Salon.objects.select_related("neighborhood"), is_active=True, **salon_lookup
        )
        stylist = get_object_or_404(
            Stylist.objects.select_related("user"),
            pk=stylist_id,
            is_active=True,
        )
        access = can_show_stylist_on_salon_profile(salon=salon, stylist=stylist)
        if not access.allowed:
            raise Http404("این پروفایل در این مجموعه قابل نمایش نیست.")

        if request.user.is_authenticated:
            SalonVisit.objects.update_or_create(
                user=request.user,
                salon=salon,
                defaults={"visit_date": timezone.now()},
            )

        context = build_salon_stylist_profile_context(
            salon=salon,
            stylist=stylist,
            request=request,
        )
        canonical_path = reverse(
            "salons:stylist_profile_slug", args=[salon.slug, stylist.pk]
        )
        context.update(
            {
                "canonical_url": request.build_absolute_uri(canonical_path),
                "robots_noindex": not bool(
                    getattr(stylist, "is_publicly_searchable", False)
                ),
            }
        )
        return render(request, "pages/salon_stylist_profile.html", context)
