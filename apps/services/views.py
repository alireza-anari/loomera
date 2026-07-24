import mimetypes

from django.db.models import Avg, F, Min, Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.views import View
from django.views.decorators.http import require_GET
from apps.salons.models import Salon
from .models import GroupServices, Services
from apps.main.seo import build_breadcrumb_schema, build_service_schema
from django.conf import settings

SERVICE_DYNAMIC_CONTENT_TYPES = {"info", "comments", "stylists"}
PUBLIC_SERVICE_GROUPS_ATTR = "public_service_groups"


def _with_public_service_list_data(queryset):
    """Attach all data needed by public service cards.

    Average scores are calculated in the service query, while active service
    groups are loaded in one shared prefetch query. Rendering a prepared list
    must not perform per-service database queries.
    """

    return (
        queryset.annotate(
            public_avg_score=Avg("scoring_services__score"),
        )
        .prefetch_related(
            Prefetch(
                "service_group",
                queryset=GroupServices.objects.filter(
                    is_active=True,
                ).order_by(
                    "group_title",
                    "id",
                ),
                to_attr=PUBLIC_SERVICE_GROUPS_ATTR,
            )
        )
        .distinct()
    )


def _service_suggestions_query_max_chars():
    return max(
        int(getattr(settings, "SERVICE_SUGGESTIONS_QUERY_MAX_CHARS", 80) or 1),
        1,
    )


def _is_ajax_request(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _clean_service_suggestion_query(raw_query):
    query = (raw_query or "").strip()
    if len(query) > _service_suggestions_query_max_chars():
        return None
    return query


def group_service_image(request, group_id):
    """Serve public service-group thumbnails through Loomera domain.

    Liara Object Storage SDK URLs can be reachable from the server while some
    clients fail to load the storage host directly. This lightweight proxy is
    intentionally limited to active service-group images, which are public
    marketing assets.
    """

    group = get_object_or_404(GroupServices, id=group_id, is_active=True)
    image = getattr(group, "group_image", None)

    if not image or not getattr(image, "name", ""):
        raise Http404("Service group image not found")

    try:
        file_obj = image.open("rb")
    except Exception as exc:  # pragma: no cover - storage/network specific
        raise Http404("Service group image unavailable") from exc

    content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
    response = FileResponse(file_obj, content_type=content_type)
    response["Cache-Control"] = "public, max-age=3600"
    return response


def service_group_image_url(group):
    if group and getattr(getattr(group, "group_image", None), "name", ""):
        return reverse("services:group_service_image", args=[group.id])
    return ""


# ------------------------------------------------------------------------------------------
# class IndexServiceGroupsView(View):
#     def get(self, request):
#         # ✅ بهینه‌سازی: واکشی زیرگروه‌ها و شمارش خدمات در یک کوئری
#         service_groups = GroupServices.objects.filter(
#             is_active=True,
#             group_parent=None
#         ).prefetch_related(
#             # واکشی تمام زیرگروه‌های فعال هر گروه اصلی
#             Prefetch(
#                 'groups',
#                 queryset=GroupServices.objects.filter(is_active=True),
#                 to_attr='active_subgroups'
#             ),
#             # واکشی تمام خدمات فعال هر گروه اصلی
#             Prefetch(
#                 'services_of_group',
#                 queryset=Services.objects.filter(is_active=True),
#                 to_attr='active_services'
#             )
#         )

#         context = {"service_groups": service_groups}
#         print(service_groups)
#         return render(request, "services/partials/service_group_index.html", context)


# #------------------------------------------------------------------------------------------
# # زیرگروه ها
# class SubGroupView(View):
#     def get(self, request, *args, **kwargs):
#         current_group = get_object_or_404(GroupServices, slug=kwargs["slug"])
#         sub_group = GroupServices.objects.filter(Q(is_active=True) & Q(group_parent=current_group))
#         print(sub_group)

#         context = {
#             "current_group": current_group,
#             "sub_group": sub_group,
#         }
#         return render(request, "services/sub_group.html", context)


# ---------------------------------------------------------------------------------------------
# تمام محصولات گروه
class ServicesView(View):
    def get(self, request, group_id=None, slug=None):
        parent_groups = GroupServices.objects.filter(
            is_active=True,
            group_parent=None,
        ).order_by("group_title")

        selected_group = None
        subgroups = GroupServices.objects.filter(
            is_active=True,
            group_parent__isnull=False,
        ).order_by("group_title")

        services = _with_public_service_list_data(
            Services.objects.filter(
                is_active=True,
                is_platform_catalog=True,
            )
        ).order_by("-view_count")

        if group_id or slug:
            selected_group = get_object_or_404(
                GroupServices,
                is_active=True,
                **({"slug": slug} if slug else {"id": group_id}),
            )

            direct_subgroups = GroupServices.objects.filter(
                is_active=True,
                group_parent=selected_group,
            ).order_by("group_title")

            if direct_subgroups.exists():
                # وقتی گروه اصلی انتخاب شده، زیرگروه‌های همان گروه را نشان بده
                subgroups = direct_subgroups
                group_ids = [
                    selected_group.id,
                    *direct_subgroups.values_list("id", flat=True),
                ]
            else:
                # وقتی خود زیرگروه انتخاب شده، خودش و هم‌سطح‌هایش را برای ناوبری نگه دار
                if selected_group.group_parent_id:
                    subgroups = GroupServices.objects.filter(
                        is_active=True,
                        group_parent=selected_group.group_parent,
                    ).order_by("group_title")
                else:
                    subgroups = GroupServices.objects.none()

                group_ids = [selected_group.id]

            services = _with_public_service_list_data(
                Services.objects.filter(
                    is_active=True,
                    is_platform_catalog=True,
                    service_group__id__in=group_ids,
                )
            ).order_by("-view_count")

        canonical_url = request.build_absolute_uri(
            selected_group.get_absolute_url()
            if selected_group and selected_group.slug
            else request.path
        )
        context = {
            "groups": parent_groups,
            "services": services,
            "selected_group": selected_group,
            "subgroups": subgroups,
            "canonical_url": canonical_url,
            "robots_noindex": bool(
                selected_group and not selected_group.allow_indexing
            ),
        }

        return render(request, "services/all_services.html", context)


class ServiceDetailView(View):
    template_name = "services/service_detail.html"

    def get(self, request, slug):
        service = get_object_or_404(
            Services.objects.prefetch_related("service_group", "gallery_images"),
            slug=slug,
            is_active=True,
            is_platform_catalog=True,
        )
        Services.objects.filter(pk=service.pk).update(view_count=F("view_count") + 1)
        groups = list(service.service_group.filter(is_active=True))
        related_salons = (
            Salon.objects.filter(is_active=True, services=service)
            .select_related("neighborhood")
            .annotate(
                avg_score=Avg("scoring_salon__score"),
                min_price=Min("services__service_prices__price"),
            )
            .distinct()[:8]
        )
        breadcrumb_items = [("خانه", "/"), ("خدمات", "/services/all_services/")]
        if groups:
            breadcrumb_items.append(
                (groups[0].group_title, groups[0].get_absolute_url())
            )
        breadcrumb_items.append((service.service_name, service.get_absolute_url()))
        context = {
            "service": service,
            "service_groups": groups,
            "related_salons": related_salons,
            "canonical_url": service.canonical_url
            or request.build_absolute_uri(service.get_absolute_url()),
            "robots_noindex": not bool(service.allow_indexing),
            "service_schema_json": build_service_schema(request, service),
            "breadcrumb_schema_json": build_breadcrumb_schema(
                request, breadcrumb_items
            ),
        }
        return render(request, self.template_name, context)


# -------------------------------------------------------------------------------------------
@require_GET
def get_subgroups(request, group_id):
    group = get_object_or_404(
        GroupServices,
        id=group_id,
        is_active=True,
    )

    subgroups = (
        GroupServices.objects.filter(
            group_parent=group,
            is_active=True,
        )
        .order_by("group_title")
        .distinct()
    )

    subgroup_list = [
        {"title": subgroup.group_title, "id": subgroup.id} for subgroup in subgroups
    ]

    response_data = {
        "group_title": group.group_title,
        "subgroups": subgroup_list,
    }
    return JsonResponse(response_data)


# -------------------------------------------------------------------------------------------
@require_GET
def get_service_of_subgroups(request, subgroup_id):
    subgroup = get_object_or_404(
        GroupServices,
        id=subgroup_id,
        is_active=True,
    )

    services = _with_public_service_list_data(
        Services.objects.filter(
            is_active=True,
            is_platform_catalog=True,
            service_group__id=subgroup.id,
        )
    ).order_by("-view_count")

    return render(
        request,
        "services/partials/filtered_services.html",
        {"services": services},
    )


# -------------------------------------------------------------------------------------------
@require_GET
def get_service_of_sorting(request, subgroup_id, sort_type):
    subgroup = get_object_or_404(
        GroupServices,
        id=subgroup_id,
        is_active=True,
    )

    services = _with_public_service_list_data(
        Services.objects.filter(
            is_active=True,
            is_platform_catalog=True,
            service_group__id=subgroup.id,
        )
    )

    if sort_type == 0:
        services = services.order_by("-view_count")
    elif sort_type == 1:
        services = services.order_by("-registere_date")
    elif sort_type == 2:
        services = services.order_by("service_name")
    else:
        services = services.order_by("-view_count")

    return render(
        request,
        "services/partials/filtered_services.html",
        {"services": services},
    )


# ---------------------------------------------------------------------------------------------------
@require_GET
def categories(request):
    service_groups = GroupServices.objects.filter(
        Q(is_active=True) & Q(group_parent=None)
    )

    context = {"service_groups": service_groups}
    return render(request, "components/categories.html", context)


# ---------------------------------------------------------------------------------------------------
@require_GET
def service_dynamic_content(request):
    if not _is_ajax_request(request):
        return JsonResponse(
            {"status": "error", "message": "Invalid request"},
            status=400,
        )

    service_id = str(request.GET.get("service_id") or "").strip()
    content_type = str(request.GET.get("content_type") or "").strip()

    if not service_id.isdigit():
        return JsonResponse(
            {"status": "error", "message": "Invalid service"},
            status=400,
        )

    if content_type not in SERVICE_DYNAMIC_CONTENT_TYPES:
        return JsonResponse(
            {"status": "error", "message": "Invalid content type"},
            status=400,
        )

    service = get_object_or_404(
        Services,
        id=int(service_id),
        is_active=True,
        is_platform_catalog=True,
    )

    if content_type == "info":
        html = render_to_string(
            "services/partials/service_info.html",
            {"service": service},
        )
    elif content_type == "comments":
        comments = service.comment_services.filter(is_active=True)
        html = render_to_string(
            "services/partials/service_comments.html",
            {"comments": comments},
        )
    else:
        html = render_to_string(
            "services/partials/service_stylists.html",
            {"service": service},
        )

    return JsonResponse({"status": "success", "html": html})


# --------------------------------------------------------------------------------------------------------------------------------
@require_GET
def get_service_priceList(request, service_id):
    service = get_object_or_404(
        Services,
        id=service_id,
        is_active=True,
        is_platform_catalog=True,
    )

    stylists = (
        service.stylists.filter(is_active=True)
        .select_related("user")
        .prefetch_related("stylists_of_salon")
        .distinct()
    )

    service_price_list = []

    for stylist in stylists:
        active_salons_count = (
            stylist.stylists_of_salon.filter(
                is_active=True,
                services=service,
            )
            .distinct()
            .count()
        )

        if active_salons_count == 0:
            continue

        price = stylist.get_price_for_service(service)
        average_score = round(stylist.get_average_score() or 0)

        service_price_list.append(
            {
                "stylist_id": stylist.pk,
                "stylist_fullName": stylist.get_fullName(),
                "stylist_image": stylist.profile_image,
                "stylist_expert": stylist.expert or "",
                "active_salons_count": active_salons_count,
                "duration_minutes": service.duration_minutes,
                "score": average_score,
                "price": price,
                "star_range": range(1, 6),
            }
        )

    context = {
        "service": service,
        "service_price_list": service_price_list,
    }

    return render(request, "services/partials/priceList.html", context)


# --------------------------------------------------------------------------------
@require_GET
def service_suggestions(request):
    """
    API ساجست برای سرچ مشترک خدمات و مجموعه‌ها:
    ?q=متن
    """
    query = _clean_service_suggestion_query(request.GET.get("q"))
    if query is None:
        return JsonResponse({"error": "query_too_long"}, status=400)

    if not query:
        return JsonResponse({"results": [], "services": [], "salons": []})

    services_qs = Services.objects.filter(
        Q(is_active=True)
        & Q(is_platform_catalog=True)
        & Q(service_name__icontains=query)
    ).order_by("-view_count")[:8]

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

    services = [
        {
            "id": s.pk,
            "name": s.service_name,
            "service_name": s.service_name,
            "type": "service",
        }
        for s in services_qs
    ]

    salons = [
        {
            "id": s.pk,
            "name": s.salon_name,
            "salon_name": s.salon_name,
            "address": s.address or "",
            "neighborhood": s.neighborhood.name if s.neighborhood else "",
            "type": "salon",
        }
        for s in salons_qs
    ]

    return JsonResponse(
        {"results": services + salons, "services": services, "salons": salons}
    )
