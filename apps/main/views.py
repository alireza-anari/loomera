import mimetypes
from pathlib import PurePosixPath
import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.db import connection, transaction
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.core.exceptions import ValidationError
from .forms import SupportForm, SupportTicketReplyForm
from .models import SupportTicket, SupportTicketMessage

from apps.dashboards.jalali_utils import format_jalali_with_weekday, format_time_fa
from apps.accounts.notifications import (
    notify_support_reply,
    notify_support_ticket_created,
)
from .support_services import (
    add_support_message,
    initialize_support_ticket,
    update_support_ticket_status,
)
from django.db.models import Prefetch

logger = logging.getLogger(__name__)


class RobotsTxtView(View):
    def get(self, request, *args, **kwargs):
        host = request.get_host()
        scheme = "https" if request.is_secure() else request.scheme
        lines = [
            "User-agent: *",
            "Disallow: /admin/",
            "Disallow: /platform/",
            "Disallow: /dashboards/",
            "Disallow: /accounts/",
            "Disallow: /orders/",
            "Disallow: /payments/",
            "Disallow: /notifications/",
            "Disallow: /search/?*",
            "Disallow: /*?*",
            f"Sitemap: {scheme}://{host}/sitemap.xml",
        ]
        return HttpResponse(
            "\n".join(lines) + "\n", content_type="text/plain; charset=utf-8"
        )


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _support_rate_limit_key(request):
    if request.user.is_authenticated:
        return f"support-ticket:user:{request.user.pk}"
    mobile = (request.POST.get("mobile") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    identity = mobile or email or _client_ip(request) or "anonymous"
    return f"support-ticket:anon:{identity}"


def _support_rate_limited(request):
    from django.core.cache import cache

    limit = max(int(getattr(settings, "LOOMERA_SUPPORT_TICKET_RATE_LIMIT", 5) or 5), 1)
    window = max(
        int(
            getattr(settings, "LOOMERA_SUPPORT_TICKET_RATE_WINDOW_SECONDS", 3600)
            or 3600
        ),
        60,
    )
    fail_closed = bool(
        getattr(settings, "LOOMERA_SUPPORT_TICKET_RATE_LIMIT_FAIL_CLOSED", False)
    )

    key = _support_rate_limit_key(request)

    try:
        count = cache.get(key, 0)
        if int(count or 0) >= limit:
            return True

        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window)

        return False
    except Exception as exc:
        logger.warning(
            "Support ticket rate limit cache unavailable; fail_closed=%s",
            fail_closed,
            exc_info=exc,
        )
        return fail_closed


def _support_request_body_too_large(request, max_bytes):
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        content_length = 0

    return content_length > max_bytes


def _support_ticket_post_max_bytes():
    return max(
        int(getattr(settings, "SUPPORT_TICKET_POST_MAX_BYTES", 2 * 1024 * 1024) or 1),
        1,
    )


def _support_ticket_reply_post_max_bytes():
    return max(
        int(
            getattr(
                settings,
                "SUPPORT_TICKET_REPLY_POST_MAX_BYTES",
                2 * 1024 * 1024,
            )
            or 1
        ),
        1,
    )


def _validate_support_post_size(request, max_bytes):
    if _support_request_body_too_large(request, max_bytes):
        raise ValidationError("حجم اطلاعات ارسالی بیش از حد مجاز است.")


def _public_support_messages_queryset():
    return (
        SupportTicketMessage.objects.filter(
            message_type=SupportTicketMessage.MESSAGE_TYPE_PUBLIC,
        )
        .prefetch_related("attachments")
        .order_by("created_at", "id")
    )


def _user_support_ticket_queryset(request):
    if not request.user.is_authenticated:
        return SupportTicket.objects.none()

    return (
        SupportTicket.objects.filter(user=request.user)
        .select_related("user", "salon", "stylist__user", "order", "order_detail")
        .prefetch_related(
            Prefetch(
                "messages",
                queryset=_public_support_messages_queryset(),
                to_attr="public_messages",
            ),
            "attachments",
            "dispute_cases",
        )
    )


def _get_user_support_ticket_or_404(request, pk, *, for_update=False):
    if for_update:
        queryset = SupportTicket.objects.select_for_update().filter(
            user=request.user,
        )
        return get_object_or_404(queryset, pk=pk)

    return get_object_or_404(_user_support_ticket_queryset(request), pk=pk)


# --------------------------------------------------------------------
# Media settings
def madia_admin(request):
    return {"media_url": settings.MEDIA_URL}


def _normalize_media_proxy_path(requested_path):
    raw_path = str(requested_path or "").strip()
    max_length = max(
        int(getattr(settings, "MEDIA_PROXY_MAX_PATH_LENGTH", 512) or 512), 1
    )

    if not raw_path or len(raw_path) > max_length:
        raise Http404("Invalid media path")

    if "\x00" in raw_path or "\\" in raw_path:
        raise Http404("Invalid media path")

    clean_path = str(PurePosixPath(raw_path.lstrip("/")))
    path_parts = PurePosixPath(clean_path).parts

    if not path_parts or any(part in {"", ".", ".."} for part in path_parts):
        raise Http404("Invalid media path")

    if clean_path.startswith("../") or clean_path == "..":
        raise Http404("Invalid media path")

    return clean_path


def _media_proxy_svg_allowed():
    return bool(getattr(settings, "MEDIA_PROXY_ALLOW_SVG", False))


def _detect_image_content_type(clean_path, file_obj):
    """
    بعضی نمونه‌کارهای قبلی ممکن است محتوای JPEG داشته باشند
    اما با پسوند png/webp ذخیره شده باشند. برای نمایش صحیح،
    content-type را از magic bytes تشخیص می‌دهیم.
    """
    default_content_type = (
        mimetypes.guess_type(clean_path)[0] or "application/octet-stream"
    )

    try:
        head = file_obj.read(512)
        file_obj.seek(0)
    except Exception:
        return default_content_type

    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"

    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"

    if b"ftypavif" in head[:32]:
        return "image/avif"

    if (
        PurePosixPath(clean_path).suffix.lower() == ".svg"
        and _media_proxy_svg_allowed()
        and head.lstrip().startswith(b"<svg")
    ):
        return "image/svg+xml"

    return default_content_type


def media_proxy(request, path=None):
    """Serve uploaded image media through Loomera domain.

    Browser-facing media URLs use ``/media-proxy/?path=...`` so Liara/Nginx
    will pass the request to Django instead of trying to serve a static file by
    extension. A path route is kept as a legacy fallback. For safety, this proxy
    is limited to image extensions.
    """

    requested_path = path if path is not None else request.GET.get("path", "")
    clean_path = _normalize_media_proxy_path(requested_path)

    ext = PurePosixPath(clean_path).suffix.lower()
    allowed = getattr(settings, "MEDIA_PROXY_IMAGE_EXTENSIONS", set())
    if ext == ".svg" and not _media_proxy_svg_allowed():
        raise Http404("Unsupported media type")

    if allowed and ext not in allowed:
        raise Http404("Unsupported media type")

    try:
        file_obj = default_storage.open(clean_path, "rb")
    except Exception as exc:  # pragma: no cover - storage/network specific
        raise Http404("Media file unavailable") from exc

    content_type = _detect_image_content_type(clean_path, file_obj)
    response = FileResponse(file_obj, content_type=content_type)
    response["Cache-Control"] = "public, max-age=3600"
    return response


def _decorate_support_tickets(tickets):
    items = list(tickets)
    for ticket in items:
        ticket.created_at_label = f"{format_jalali_with_weekday(ticket.created_at)} • {format_time_fa(ticket.created_at)}"
        ticket.updated_at_label = f"{format_jalali_with_weekday(ticket.updated_at)} • {format_time_fa(ticket.updated_at)}"
    return items


class SupportView(View):
    template_name = "main/support/contact_form.html"

    def get(self, request, *args, **kwargs):
        initial = {}
        if request.GET.get("topic"):
            initial["support_reason"] = request.GET.get("topic")

        if request.user.is_authenticated:
            initial.update({
                "email": request.user.email,
                "full_name": request.user.get_fullName(),
                "mobile": request.user.mobile_number,
            })

        form = SupportForm(initial=initial)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "hide_navbar": True,
            },
        )

    def post(self, request, *args, **kwargs):
        try:
            _validate_support_post_size(request, _support_ticket_post_max_bytes())
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("main:contact")

        if _support_rate_limited(request):
            messages.error(
                request,
                "تعداد درخواست‌های پشتیبانی شما در این بازه زیاد است. لطفاً کمی بعد دوباره تلاش کنید.",
            )
            return redirect("main:contact")

        form = SupportForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.cleaned_data.get("attachment")
            ticket = SupportTicket.objects.create(
                user=request.user if request.user.is_authenticated else None,
                email=form.cleaned_data.get("email"),
                issue_type=form.cleaned_data.get("issue_type"),
                full_name=form.cleaned_data.get("full_name", ""),
                city=form.cleaned_data.get("city", ""),
                mobile=form.cleaned_data.get("mobile", ""),
                support_reason=form.cleaned_data.get("support_reason", ""),
                subject=form.cleaned_data.get("support_reason", "")
                or form.cleaned_data.get("issue_type", ""),
                description=form.cleaned_data.get("description", ""),
                attachment=attachment,
            )
            initialize_support_ticket(
                ticket,
                actor=request.user if request.user.is_authenticated else None,
                attachment_file=attachment,
                request=request,
            )

            transaction.on_commit(
                lambda ticket=ticket, user=request.user: notify_support_ticket_created(
                    user=user if user.is_authenticated else None,
                    ticket=ticket,
                    action_url=reverse(
                        "main:support_ticket_detail", kwargs={"pk": ticket.pk}
                    ),
                )
            )

            if request.user.is_authenticated:
                messages.success(
                    request,
                    f"درخواست شما با شماره #{ticket.id} ثبت شد و از همین بخش قابل پیگیری است.",
                )
                return redirect("main:support_ticket_detail", pk=ticket.pk)
            messages.success(
                request,
                f"درخواست شما با شماره #{ticket.id} ثبت شد. پاسخ از راه اطلاعات تماس ثبت‌شده ارسال می‌شود.",
            )
            return redirect("main:success")

        messages.error(request, "لطفاً خطاهای فرم را بررسی و دوباره تلاش کنید.")
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "hide_navbar": True,
            },
        )


class SupportTicketListView(View):
    template_name = "main/support/ticket_list.html"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        tickets = _decorate_support_tickets(
            SupportTicket.objects.filter(user=request.user)
            .prefetch_related("messages")
            .order_by("-updated_at", "-created_at")
        )
        return render(
            request, self.template_name, {"tickets": tickets, "hide_navbar": True}
        )


class SupportTicketDetailView(View):
    template_name = "main/support/ticket_detail.html"

    def _get_ticket(self, request, pk):
        return _get_user_support_ticket_or_404(request, pk)

    def get(self, request, pk, *args, **kwargs):
        ticket = self._get_ticket(request, pk)

        return render(
            request,
            self.template_name,
            {
                "ticket": ticket,
                "messages_list": getattr(ticket, "public_messages", []),
                "reply_form": SupportTicketReplyForm(),
                "hide_navbar": True,
            },
        )


class SupportTicketReplyView(View):
    def post(self, request, pk, *args, **kwargs):
        try:
            _validate_support_post_size(
                request,
                _support_ticket_reply_post_max_bytes(),
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("main:support_ticket_detail", pk=pk)

        with transaction.atomic():
            ticket = _get_user_support_ticket_or_404(
                request,
                pk,
                for_update=True,
            )

            if not ticket.is_open:
                messages.error(
                    request, "این تیکت بسته شده و امکان ثبت پاسخ جدید ندارد."
                )
                return redirect("main:support_ticket_detail", pk=ticket.pk)

            form = SupportTicketReplyForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, "متن پیام را بررسی کنید.")
                return redirect("main:support_ticket_detail", pk=ticket.pk)

            add_support_message(
                ticket=ticket,
                sender=request.user,
                body=form.cleaned_data["body"],
                attachment_file=request.FILES.get("attachment"),
                request=request,
            )

        messages.success(request, "پیام شما ثبت شد.")
        return redirect("main:support_ticket_detail", pk=ticket.pk)


class SupportTicketCloseView(View):
    def post(self, request, pk, *args, **kwargs):
        try:
            _validate_support_post_size(
                request,
                _support_ticket_reply_post_max_bytes(),
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect("main:support_ticket_detail", pk=pk)

        with transaction.atomic():
            ticket = _get_user_support_ticket_or_404(
                request,
                pk,
                for_update=True,
            )

            if ticket.status == "closed":
                messages.info(request, "این تیکت قبلاً بسته شده است.")
                return redirect("main:support_ticket_detail", pk=ticket.pk)

            update_support_ticket_status(
                ticket=ticket,
                status="closed",
                actor=request.user,
                note="بسته‌شده توسط کاربر",
                request=request,
            )

        messages.success(request, "تیکت بسته شد.")
        return redirect("main:support_ticket_detail", pk=ticket.pk)


class HealthCheckView(View):
    """Health endpoint for staging/production monitoring.

    ``?live=1`` is intentionally dependency-light and is used by Liara's
    container health check. The default/full checks still verify database and
    cache for manual diagnostics.
    """

    def get(self, request, *args, **kwargs):
        if request.GET.get("live") == "1":
            return JsonResponse(
                {
                    "status": "ok",
                    "checks": {
                        "app": "ok",
                    },
                },
                status=200,
            )

        checks = {
            "app": "ok",
            "database": "unknown",
            "cache": "unknown",
            "media_guard": "ok",
        }
        status_code = 200

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = "error"
            checks["database_error"] = exc.__class__.__name__
            status_code = 503

        try:
            from django.core.cache import cache

            cache.set("loomera:health", "ok", timeout=30)
            checks["cache"] = "ok" if cache.get("loomera:health") == "ok" else "error"
            if checks["cache"] != "ok":
                status_code = 503
        except Exception as exc:
            checks["cache"] = "error"
            checks["cache_error"] = exc.__class__.__name__
            status_code = 503

        if getattr(settings, "SERVE_MEDIA_INSECURELY", False) and not getattr(
            settings, "DEBUG", False
        ):
            checks["media_guard"] = "error"
            status_code = 503

        payload = {
            "status": "ok" if status_code == 200 else "degraded",
            "checks": checks,
        }
        if request.GET.get("full") == "1":
            payload["runtime"] = {
                "environment": getattr(settings, "LOOMERA_ENVIRONMENT", "local"),
                "debug": bool(getattr(settings, "DEBUG", False)),
                "cache_backend": settings.CACHES.get("default", {}).get("BACKEND", ""),
                "celery_enabled": bool(
                    getattr(settings, "LOOMERA_ENABLE_CELERY", False)
                ),
                "sentry_enabled": bool(getattr(settings, "SENTRY_DSN", "")),
                "media_processing_enabled": bool(
                    getattr(settings, "LOOMERA_MEDIA_PROCESSING_ENABLED", True)
                ),
            }
        return JsonResponse(payload, status=status_code)


def success_view(request):
    return render(request, "main/support/success.html")


class PartnerPageView(View):
    template_name = "main/partners.html"

    def get(self, request, *args, **kwargs):
        return render(
            request,
            self.template_name,
            {
                "hide_navbar": False,
                "hide_footer": False,
            },
        )
