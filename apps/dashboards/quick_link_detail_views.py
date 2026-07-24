from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from apps.dashboards.jalali_utils import (
    format_jalali_numeric,
)
from apps.dashboards.layout import build_dashboard_context
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_detail_stats import (
    build_booking_quick_link_detail_stats,
)
from apps.orders.quick_link_qr import (
    get_booking_quick_link_qr_warnings,
)
from apps.orders.quick_links import build_quick_link_url
from apps.salons.models import Salon

from .views import (
    StylistDashboardGuardMixin,
    _get_stylist_dashboard_context,
    _stylist_context_payload,
)


DETAIL_PERIOD_OPTIONS = (
    ("7", "۷ روز اخیر"),
    ("30", "۳۰ روز اخیر"),
    ("90", "۹۰ روز اخیر"),
    ("all", "همه زمان‌ها"),
)


def _user_display_name(user) -> str:
    if user is None:
        return "نامشخص"

    if hasattr(user, "get_fullName"):
        label = user.get_fullName()
    elif hasattr(user, "get_full_name"):
        label = user.get_full_name()
    else:
        label = ""

    label = str(label or "").strip()

    return label or str(
        getattr(user, "mobile_number", "")
        or "کاربر لومرا"
    )


def _stylist_display_name(stylist) -> str:
    if stylist is None:
        return "همه متخصصان مجاز"

    if hasattr(stylist, "get_fullName"):
        label = stylist.get_fullName()
    else:
        label = _user_display_name(
            getattr(stylist, "user", None)
        )

    return str(label or "متخصص")


def _format_daily_rows(detail_stats) -> None:
    for point in detail_stats["daily"]:
        point["date_label"] = (
            format_jalali_numeric(point["date"])
        )


def _serialize_detail(
    *,
    request,
    quick_link,
    detail_stats,
    manager_view,
):
    payload = (
        quick_link.payload
        if isinstance(quick_link.payload, dict)
        else {}
    )

    summary = (
        payload.get("summary")
        if isinstance(payload.get("summary"), dict)
        else {}
    )

    _format_daily_rows(detail_stats)

    if manager_view:
        qr_preview_url = reverse(
            "dashboards:quick_link_qr_preview",
            kwargs={"link_id": quick_link.pk},
        )
        qr_download_url = reverse(
            "dashboards:quick_link_qr_download",
            kwargs={"link_id": quick_link.pk},
        )
        back_url = reverse(
            "dashboards:quick_links"
        )
    else:
        qr_preview_url = reverse(
            "dashboards:stylist_quick_link_qr_preview",
            kwargs={"link_id": quick_link.pk},
        )
        qr_download_url = reverse(
            "dashboards:stylist_quick_link_qr_download",
            kwargs={"link_id": quick_link.pk},
        )
        back_url = reverse(
            "dashboards:stylist_quick_links"
        )

    return {
        "quick_link": quick_link,
        "title": (
            quick_link.title
            or quick_link.get_mode_display()
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
        "internal_note": (
            quick_link.internal_note or ""
        ),
        "service_name": (
            summary.get("service")
            or getattr(
                quick_link.service,
                "service_name",
                "",
            )
            or "همه خدمات مجاز"
        ),
        "stylist_name": (
            summary.get("stylist")
            or _stylist_display_name(
                quick_link.stylist
            )
        ),
        "creator_name": _user_display_name(
            quick_link.creator
        ),
        "date_label": summary.get("date") or "—",
        "time_label": summary.get("time") or "—",
        "url": build_quick_link_url(
            request,
            quick_link,
        ),
        "qr_preview_url": qr_preview_url,
        "qr_download_url": qr_download_url,
        "back_url": back_url,
        "period_options": DETAIL_PERIOD_OPTIONS,
        "warnings": list(
            get_booking_quick_link_qr_warnings(
                quick_link
            )
        ),
        **detail_stats,
    }


class ManagerQuickLinkDetailView(
    LoginRequiredMixin,
    View,
):
    template_name = (
        "dashboards/quick_links/detail.html"
    )

    def get(self, request, link_id, *args, **kwargs):
        salon = get_object_or_404(
            Salon.objects.select_related(
                "salon_manager__user"
            ),
            salon_manager__user=request.user,
        )

        quick_link = get_object_or_404(
            BookingQuickLink.objects.select_related(
                "salon",
                "service",
                "stylist__user",
                "creator",
            ),
            pk=link_id,
            salon=salon,
        )

        detail_stats = (
            build_booking_quick_link_detail_stats(
                quick_link=quick_link,
                period=request.GET.get("period"),
            )
        )

        detail = _serialize_detail(
            request=request,
            quick_link=quick_link,
            detail_stats=detail_stats,
            manager_view=True,
        )

        context = build_dashboard_context(
            request.user,
            nav_active="growth",
            sidebar_active="online_booking",
            page_title="جزئیات لینک رزرو",
            request_path=request.path,
            salon_override=salon,
        )

        context.update(
            {
                "salon": salon,
                "quick_link_detail": detail,
                "quick_link_detail_role": "manager",
            }
        )

        return render(
            request,
            self.template_name,
            context,
        )


class StylistQuickLinkDetailView(
    StylistDashboardGuardMixin,
    View,
):
    template_name = (
        "dashboards/quick_links/detail.html"
    )

    def get(self, request, link_id, *args, **kwargs):
        ctx = _get_stylist_dashboard_context(request)
        stylist, salon = ctx.stylist, ctx.salon

        if stylist is None or salon is None:
            raise Http404(
                "لینک رزرو در سالن فعال پیدا نشد."
            )

        quick_link = get_object_or_404(
            BookingQuickLink.objects.select_related(
                "salon",
                "service",
                "stylist__user",
                "creator",
            ),
            pk=link_id,
            salon=salon,
            stylist=stylist,
            creator=request.user,
        )

        detail_stats = (
            build_booking_quick_link_detail_stats(
                quick_link=quick_link,
                period=request.GET.get("period"),
            )
        )

        detail = _serialize_detail(
            request=request,
            quick_link=quick_link,
            detail_stats=detail_stats,
            manager_view=False,
        )

        context = build_dashboard_context(
            request.user,
            sidebar_active="my_appointments",
            page_title="جزئیات لینک رزرو",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )

        context.update(
            {
                "stylist_obj": stylist,
                "stylist_salon": salon,
                "quick_link_detail": detail,
                "quick_link_detail_role": "stylist",
            }
        )
        context.update(_stylist_context_payload(ctx))

        return render(
            request,
            self.template_name,
            context,
        )
