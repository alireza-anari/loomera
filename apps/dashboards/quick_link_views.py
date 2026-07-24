from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.views import View

from apps.dashboards.layout import build_dashboard_context
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_management import (
    change_booking_quick_link_status,
    clone_booking_quick_link,
    update_booking_quick_link_metadata,
)
from apps.orders.quick_link_stats import (
    build_booking_quick_link_stats,
)
from apps.orders.quick_links import build_quick_link_url
from apps.salons.models import Salon

from .views import OnlineBookingView



PERIOD_OPTIONS = (
    ("7", "۷ روز اخیر"),
    ("30", "۳۰ روز اخیر"),
    ("90", "۹۰ روز اخیر"),
    ("all", "همه زمان‌ها"),
)

SORT_OPTIONS = (
    ("newest", "جدیدترین"),
    (
        "unique_visitors",
        "بیشترین بازدیدکننده یکتا",
    ),
    ("conversions", "بیشترین رزرو"),
    (
        "conversion_rate",
        "بالاترین نرخ تبدیل",
    ),
    ("last_activity", "آخرین فعالیت"),
)


def _quick_link_creator_label(creator) -> str:
    if creator is None:
        return "نامشخص"

    if hasattr(creator, "get_fullName"):
        label = creator.get_fullName()
    elif hasattr(creator, "get_full_name"):
        label = creator.get_full_name()
    else:
        label = ""

    label = str(label or "").strip()

    if label:
        return label

    return str(
        getattr(creator, "mobile_number", "")
        or "کاربر لومرا"
    )


def _quick_link_stylist_label(quick_link) -> str:
    if quick_link.stylist is None:
        return "همه متخصصان مجاز"

    if hasattr(quick_link.stylist, "get_fullName"):
        label = quick_link.stylist.get_fullName()
    else:
        user = getattr(quick_link.stylist, "user", None)

        label = (
            f"{getattr(user, 'name', '')} "
            f"{getattr(user, 'family', '')}"
        ).strip()

    return str(label or "متخصص")


def _serialize_manager_quick_link_row(
    *,
    request,
    stats_row,
) -> dict:
    quick_link = stats_row["quick_link"]

    return {
        **stats_row,
        "title": (
            quick_link.title
            or quick_link.get_mode_display()
        ),
        "url": build_quick_link_url(
            request,
            quick_link,
        ),
        "status_label": quick_link.status_label,
        "status_tone": quick_link.status_tone,
        "mode_label": quick_link.get_mode_display(),
        "placement_label": (
            quick_link.get_placement_display()
        ),
        "campaign_name": (
            quick_link.campaign_name
            or "بدون کمپین"
        ),
        "creator_label": (
            _quick_link_creator_label(
                quick_link.creator
            )
        ),
        "service_name": (
            getattr(
                quick_link.service,
                "service_name",
                "",
            )
            or "همه خدمات مجاز"
        ),
        "stylist_name": (
            _quick_link_stylist_label(
                quick_link
            )
        ),
        "qr_preview_url": reverse(
            "dashboards:quick_link_qr_preview",
            kwargs={"link_id": quick_link.pk},
        ),
        "qr_download_url": reverse(
            "dashboards:quick_link_qr_download",
            kwargs={"link_id": quick_link.pk},
        ),
    }


class ManagerQuickLinksView(
    LoginRequiredMixin,
    View,
):
    template_name = "dashboards/quick_links/index.html"

    def _get_salon(self, request):
        return get_object_or_404(
            Salon.objects.select_related(
                "salon_manager__user",
                "neighborhood",
            ),
            salon_manager__user=request.user,
        )

    def _build_create_workspace(
        self,
        request,
        salon,
        *,
        result=None,
    ):
        result = result or {}

        builder = OnlineBookingView()

        workspace = (
            builder._build_quick_booking_workspace(
                request,
                salon,
                generated_link=result.get(
                    "generated_link"
                ),
                generated_payload=result.get(
                    "generated_payload"
                ),
                generator_errors=result.get(
                    "errors"
                ),
            )
        )

        form_values = (
            result.get("form_values")
            if isinstance(
                result.get("form_values"),
                dict,
            )
            else {}
        )

        title_field = (
            BookingQuickLink._meta.get_field(
                "title"
            )
        )

        campaign_field = (
            BookingQuickLink._meta.get_field(
                "campaign_name"
            )
        )

        note_field = (
            BookingQuickLink._meta.get_field(
                "internal_note"
            )
        )

        workspace.update(
            {
                "placement_options": (
                    BookingQuickLink
                    .Placement
                    .choices
                ),
                "selected_placement": (
                    form_values.get(
                        "placement"
                    )
                    or (
                        BookingQuickLink
                        .Placement
                        .DIRECT
                    )
                ),
                "selected_title": (
                    form_values.get("title")
                    or ""
                ),
                "campaign_name": (
                    form_values.get(
                        "campaign_name"
                    )
                    or ""
                ),
                "internal_note": (
                    form_values.get(
                        "internal_note"
                    )
                    or ""
                ),
                "is_permanent": bool(
                    form_values.get(
                        "is_permanent"
                    )
                ),
                "title_max_length": (
                    title_field.max_length
                ),
                "campaign_name_max_length": (
                    campaign_field.max_length
                ),
                "internal_note_max_length": (
                    note_field.max_length
                ),
            }
        )

        return workspace

    def post(self, request, *args, **kwargs):
        salon = self._get_salon(request)

        action = str(
            request.POST.get("quick_link_action") or ""
        ).strip()

        if action:
            scoped_links = BookingQuickLink.objects.filter(
                salon=salon
            )

            try:
                if action == "edit":
                    _link, message = update_booking_quick_link_metadata(
                        links_queryset=scoped_links,
                        link_id=request.POST.get("quick_link_id"),
                        title=request.POST.get("quick_link_title"),
                        placement=request.POST.get("placement"),
                        campaign_name=request.POST.get("campaign_name"),
                        internal_note=request.POST.get("internal_note"),
                        is_permanent=(
                            request.POST.get("is_permanent") == "on"
                        ),
                    )
                elif action == "clone":
                    _link, message = clone_booking_quick_link(
                        links_queryset=scoped_links,
                        link_id=request.POST.get("quick_link_id"),
                        creator=request.user,
                    )
                else:
                    _link, message = change_booking_quick_link_status(
                        links_queryset=scoped_links,
                        link_id=request.POST.get("quick_link_id"),
                        action=action,
                    )

                messages.success(request, message)
            except ValidationError as exc:
                messages.error(
                    request,
                    " ".join(
                        getattr(exc, "messages", [str(exc)])
                    ),
                )

            return redirect("dashboards:quick_links")

        builder = OnlineBookingView()

        (
            generated_link,
            generated_payload,
            generator_errors,
        ) = builder._generate_quick_link(
            request,
            salon,
        )

        request.session[
            "dashboard_quick_booking_result"
        ] = {
            "generated_link": generated_link,
            "generated_payload": generated_payload,
            "errors": generator_errors,
            "form_values": {
                "title": (
                    request.POST.get(
                        "quick_link_title"
                    )
                    or ""
                ).strip(),
                "placement": (
                    request.POST.get(
                        "placement"
                    )
                    or (
                        BookingQuickLink
                        .Placement
                        .DIRECT
                    )
                ).strip(),
                "campaign_name": (
                    request.POST.get(
                        "campaign_name"
                    )
                    or ""
                ).strip(),
                "internal_note": (
                    request.POST.get(
                        "internal_note"
                    )
                    or ""
                ).strip(),
                "is_permanent": (
                    request.POST.get(
                        "is_permanent"
                    )
                    == "on"
                ),
            },
        }

        if generated_link:
            messages.success(
                request,
                "لینک رزرو با موفقیت ساخته شد.",
            )
        else:
            messages.error(
                request,
                "برای ساخت لینک، خطاهای فرم را بررسی کنید.",
            )

        return redirect(
            "dashboards:quick_links"
        )

    def get(self, request, *args, **kwargs):
        salon = self._get_salon(request)

        quick_link_result = request.session.pop(
            "dashboard_quick_booking_result",
            None,
        )

        create_workspace = (
            self._build_create_workspace(
                request,
                salon,
                result=quick_link_result,
            )
        )

        links_queryset = (
            BookingQuickLink.objects.filter(
                salon=salon
            )
        )

        stats = build_booking_quick_link_stats(
            links_queryset=links_queryset,
            period=request.GET.get("period"),
            sort=request.GET.get("sort"),
        )

        rows = [
            _serialize_manager_quick_link_row(
                request=request,
                stats_row=row,
            )
            for row in stats["links"]
        ]

        best_link = stats["summary"]["best_link"]

        if best_link:
            best_link = {
                "id": best_link["id"],
                "title": (
                    best_link["quick_link"].title
                    or best_link[
                        "quick_link"
                    ].get_mode_display()
                ),
                "converted_count": (
                    best_link["converted_count"]
                ),
                "conversion_rate": (
                    best_link["conversion_rate"]
                ),
            }

        context = build_dashboard_context(
            request.user,
            nav_active="growth",
            sidebar_active="online_booking",
            page_title="لینک‌های رزرو",
            request_path=request.path,
            salon_override=salon,
        )

        context.update(
            {
                "salon": salon,
                "quick_link_create_workspace": (
                    create_workspace
                ),
                "quick_link_page": {
                    "period": stats["period"],
                    "sort": stats["sort"],
                    "period_options": PERIOD_OPTIONS,
                    "sort_options": SORT_OPTIONS,
                    "summary": {
                        **stats["summary"],
                        "best_link": best_link,
                    },
                    "links": rows,
                    "create_url": (
                        "#create-quick-link"
                    ),
                    "online_booking_url": reverse(
                        "dashboards:online_booking"
                    ),
                },
            }
        )

        return render(
            request,
            self.template_name,
            context,
        )
