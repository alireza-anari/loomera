from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from apps.dashboards.layout import build_dashboard_context
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_print_templates import (
    generate_booking_quick_link_print_template,
    list_booking_quick_link_print_templates,
    generate_booking_quick_link_business_card_side,
    generate_booking_quick_link_business_card_zip,
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


PRINT_TEMPLATE_NAME_MAP = {
    "manager": {
        "gallery": "dashboards:quick_link_print_templates",
        "preview": "dashboards:quick_link_print_template_preview",
        "download": "dashboards:quick_link_print_template_download",
        "detail": "dashboards:quick_link_detail",
        "business_card_back_preview": (
            "dashboards:quick_link_business_card_back_preview"
        ),
        "business_card_back_download": (
            "dashboards:quick_link_business_card_back_download"
        ),
        "business_card_zip": (
            "dashboards:quick_link_business_card_zip"
        ),
    },
    "stylist": {
        "gallery": "dashboards:stylist_quick_link_print_templates",
        "preview": "dashboards:stylist_quick_link_print_template_preview",
        "download": "dashboards:stylist_quick_link_print_template_download",
        "detail": "dashboards:stylist_quick_link_detail",
        "business_card_back_preview": (
            "dashboards:stylist_quick_link_business_card_back_preview"
        ),
        "business_card_back_download": (
            "dashboards:stylist_quick_link_business_card_back_download"
        ),
        "business_card_zip": (
            "dashboards:stylist_quick_link_business_card_zip"
        ),
    },
}


def _manager_scope(request, link_id):
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
    return salon, None, None, quick_link


def _stylist_scope(request, link_id):
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
    return salon, stylist, ctx, quick_link


def _template_cards(*, role, quick_link, warnings):
    names = PRINT_TEMPLATE_NAME_MAP[role]
    cards = []

    for spec in list_booking_quick_link_print_templates():
        route_kwargs = {
            "link_id": quick_link.pk,
            "template_key": spec.key,
        }
        preview_url = reverse(
            names["preview"],
            kwargs=route_kwargs,
        )
        download_url = reverse(
            names["download"],
            kwargs=route_kwargs,
        )

        if warnings:
            download_url = (
                f"{download_url}?"
                + urlencode({"confirm": "1"})
            )

        item = {
            "key": spec.key,
            "label": spec.label,
            "description": spec.description,
            "width_mm": spec.width_mm,
            "height_mm": spec.height_mm,
            "transparent": spec.transparent,
            "preview_url": preview_url,
            "download_url": download_url,
            "is_two_sided": spec.key == "business_card",
        }

        if item["is_two_sided"]:
            kwargs = {"link_id": quick_link.pk}
            back_download_url = reverse(
                names["business_card_back_download"],
                kwargs=kwargs,
            )
            zip_download_url = reverse(
                names["business_card_zip"],
                kwargs=kwargs,
            )

            if warnings:
                query = urlencode({"confirm": "1"})
                back_download_url = f"{back_download_url}?{query}"
                zip_download_url = f"{zip_download_url}?{query}"

            item.update(
                {
                    "back_preview_url": reverse(
                        names["business_card_back_preview"],
                        kwargs=kwargs,
                    ),
                    "back_download_url": back_download_url,
                    "zip_download_url": zip_download_url,
                }
            )

        cards.append(item)

    return cards


class _PrintTemplateGalleryView(View):
    role = None

    def get_scope(self, request, link_id):
        if self.role == "manager":
            return _manager_scope(request, link_id)
        return _stylist_scope(request, link_id)

    def get(self, request, link_id, *args, **kwargs):
        salon, stylist, ctx, quick_link = self.get_scope(
            request,
            link_id,
        )
        warnings = list(
            get_booking_quick_link_qr_warnings(
                quick_link
            )
        )
        names = PRINT_TEMPLATE_NAME_MAP[self.role]
        gallery = {
            "quick_link": quick_link,
            "title": (
                quick_link.title
                or quick_link.get_mode_display()
            ),
            "salon_name": salon.salon_name,
            "mode_label": quick_link.get_mode_display(),
            "placement_label": quick_link.get_placement_display(),
            "public_url": build_quick_link_url(
                request,
                quick_link,
            ),
            "back_url": reverse(
                names["detail"],
                kwargs={"link_id": quick_link.pk},
            ),
            "warnings": warnings,
            "templates": _template_cards(
                role=self.role,
                quick_link=quick_link,
                warnings=warnings,
            ),
        }

        if self.role == "manager":
            context = build_dashboard_context(
                request.user,
                nav_active="growth",
                sidebar_active="online_booking",
                page_title="قالب‌های چاپی QR",
                request_path=request.path,
                salon_override=salon,
            )
            context.update(
                {
                    "salon": salon,
                    "quick_link_print_gallery": gallery,
                    "quick_link_print_role": "manager",
                }
            )
        else:
            context = build_dashboard_context(
                request.user,
                sidebar_active="my_appointments",
                page_title="قالب‌های چاپی QR",
                request_path=request.path,
                role="stylist",
                salon_override=salon,
                stylist_override=stylist,
            )
            context.update(
                {
                    "stylist_obj": stylist,
                    "stylist_salon": salon,
                    "quick_link_print_gallery": gallery,
                    "quick_link_print_role": "stylist",
                }
            )
            context.update(
                _stylist_context_payload(ctx)
            )

        return render(
            request,
            "dashboards/quick_links/print_templates.html",
            context,
        )


class ManagerQuickLinkPrintTemplatesView(
    LoginRequiredMixin,
    _PrintTemplateGalleryView,
):
    role = "manager"


class StylistQuickLinkPrintTemplatesView(
    StylistDashboardGuardMixin,
    _PrintTemplateGalleryView,
):
    role = "stylist"


class _PrintTemplateImageView(View):
    role = None
    download = False

    def get_scope(self, request, link_id):
        if self.role == "manager":
            return _manager_scope(request, link_id)
        return _stylist_scope(request, link_id)

    def get(
        self,
        request,
        link_id,
        template_key,
        *args,
        **kwargs,
    ):
        _salon, _stylist, _ctx, quick_link = (
            self.get_scope(request, link_id)
        )
        warnings = list(
            get_booking_quick_link_qr_warnings(
                quick_link
            )
        )

        if (
            self.download
            and warnings
            and request.GET.get("confirm") != "1"
        ):
            return HttpResponse(
                "\n".join(warnings),
                status=409,
                content_type=(
                    "text/plain; charset=utf-8"
                ),
            )

        try:
            generated = (
                generate_booking_quick_link_print_template(
                    request=request,
                    quick_link=quick_link,
                    template_key=template_key,
                    preview=not self.download,
                )
            )
        except ValueError as exc:
            raise Http404(str(exc)) from exc

        response = HttpResponse(
            generated.content,
            content_type=generated.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["X-Loomera-Template"] = (
            generated.template.key
        )
        response["X-Loomera-Image-Size"] = (
            f"{generated.width}x{generated.height}"
        )

        if self.download:
            response["Content-Disposition"] = (
                f'attachment; filename="{generated.filename}"'
            )
        else:
            response["Content-Disposition"] = (
                f'inline; filename="preview-{generated.filename}"'
            )

        return response


class ManagerQuickLinkPrintTemplatePreviewView(
    LoginRequiredMixin,
    _PrintTemplateImageView,
):
    role = "manager"
    download = False


class ManagerQuickLinkPrintTemplateDownloadView(
    LoginRequiredMixin,
    _PrintTemplateImageView,
):
    role = "manager"
    download = True


class StylistQuickLinkPrintTemplatePreviewView(
    StylistDashboardGuardMixin,
    _PrintTemplateImageView,
):
    role = "stylist"
    download = False


class StylistQuickLinkPrintTemplateDownloadView(
    StylistDashboardGuardMixin,
    _PrintTemplateImageView,
):
    role = "stylist"
    download = True

class _BusinessCardSideImageView(_PrintTemplateImageView):
    side = "back"

    def get(self, request, link_id, *args, **kwargs):
        _salon, _stylist, _ctx, quick_link = self.get_scope(
            request,
            link_id,
        )
        warnings = list(
            get_booking_quick_link_qr_warnings(quick_link)
        )

        if (
            self.download
            and warnings
            and request.GET.get("confirm") != "1"
        ):
            return HttpResponse(
                "\n".join(warnings),
                status=409,
                content_type="text/plain; charset=utf-8",
            )

        generated = generate_booking_quick_link_business_card_side(
            request=request,
            quick_link=quick_link,
            side=self.side,
            preview=not self.download,
        )

        response = HttpResponse(
            generated.content,
            content_type=generated.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["X-Loomera-Template"] = "business_card"
        response["X-Loomera-Business-Card-Side"] = self.side
        response["X-Loomera-Image-Size"] = (
            f"{generated.width}x{generated.height}"
        )
        disposition = "attachment" if self.download else "inline"
        response["Content-Disposition"] = (
            f'{disposition}; filename="{generated.filename}"'
        )
        return response


class _BusinessCardZipView(_PrintTemplateImageView):
    download = True

    def get(self, request, link_id, *args, **kwargs):
        _salon, _stylist, _ctx, quick_link = self.get_scope(
            request,
            link_id,
        )
        warnings = list(
            get_booking_quick_link_qr_warnings(quick_link)
        )

        if warnings and request.GET.get("confirm") != "1":
            return HttpResponse(
                "\n".join(warnings),
                status=409,
                content_type="text/plain; charset=utf-8",
            )

        generated = generate_booking_quick_link_business_card_zip(
            request=request,
            quick_link=quick_link,
        )
        response = HttpResponse(
            generated.content,
            content_type=generated.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = (
            f'attachment; filename="{generated.filename}"'
        )
        return response


class ManagerQuickLinkBusinessCardBackPreviewView(
    LoginRequiredMixin,
    _BusinessCardSideImageView,
):
    role = "manager"
    side = "back"
    download = False


class ManagerQuickLinkBusinessCardBackDownloadView(
    LoginRequiredMixin,
    _BusinessCardSideImageView,
):
    role = "manager"
    side = "back"
    download = True


class ManagerQuickLinkBusinessCardZipView(
    LoginRequiredMixin,
    _BusinessCardZipView,
):
    role = "manager"


class StylistQuickLinkBusinessCardBackPreviewView(
    StylistDashboardGuardMixin,
    _BusinessCardSideImageView,
):
    role = "stylist"
    side = "back"
    download = False


class StylistQuickLinkBusinessCardBackDownloadView(
    StylistDashboardGuardMixin,
    _BusinessCardSideImageView,
):
    role = "stylist"
    side = "back"
    download = True


class StylistQuickLinkBusinessCardZipView(
    StylistDashboardGuardMixin,
    _BusinessCardZipView,
):
    role = "stylist"
