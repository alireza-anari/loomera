from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required

from .models import NotificationAudienceRole, NotificationRecipient
from .services import list_user_notifications, mark_all_read, unread_count
from apps.dashboards.jalali_utils import format_jalali_numeric, format_time_fa
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def _expects_json(request):
    return request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or "")


def _safe_notifications_redirect_target(request):
    target = str(
        request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    ).strip()

    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target

    return "notifications:center"


def _redirect_back(request):
    return redirect(_safe_notifications_redirect_target(request))


def _notifications_summary_title_max_chars():
    return max(
        int(getattr(settings, "NOTIFICATIONS_SUMMARY_TITLE_MAX_CHARS", 160) or 1),
        1,
    )


def _notifications_summary_body_max_chars():
    return max(
        int(getattr(settings, "NOTIFICATIONS_SUMMARY_BODY_MAX_CHARS", 500) or 1),
        1,
    )


def _notifications_summary_action_url_max_chars():
    return max(
        int(getattr(settings, "NOTIFICATIONS_SUMMARY_ACTION_URL_MAX_CHARS", 500) or 1),
        1,
    )


def _truncate_notifications_summary_text(value, max_chars):
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _valid_notification_summary_roles():
    return {choice[0] for choice in NotificationAudienceRole.choices}


def _notification_role_from_value(value):
    role = str(value or "").strip()
    if not role:
        return ""

    if role not in _valid_notification_summary_roles():
        return None

    return role


def _notification_summary_role_from_request(request):
    return _notification_role_from_value(request.GET.get("role"))


def _notification_action_role_from_request(request):
    return _notification_role_from_value(
        request.POST.get("role") or request.GET.get("role")
    )


def _safe_notification_summary_action_url(request, action_url):
    target_url = str(action_url or "").strip()
    if not target_url or "\x00" in target_url:
        return ""

    target_url = target_url[: _notifications_summary_action_url_max_chars()]

    if not url_has_allowed_host_and_scheme(
        url=target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    return target_url


def _recipient_to_dict(recipient: NotificationRecipient, request):
    notification = recipient.notification
    created_at = timezone.localtime(notification.created_at)
    return {
        "id": recipient.id,
        "notification_id": notification.id,
        "event_type": notification.event_type,
        "category": notification.category,
        "category_label": notification.get_category_display(),
        "priority": notification.priority,
        "title": _truncate_notifications_summary_text(
            notification.title,
            _notifications_summary_title_max_chars(),
        ),
        "body": _truncate_notifications_summary_text(
            notification.body,
            _notifications_summary_body_max_chars(),
        ),
        "icon": notification.icon or "fa-regular fa-bell",
        "action_url": _safe_notification_summary_action_url(
            request,
            notification.action_url,
        ),
        "is_read": recipient.is_read,
        "created_at": notification.created_at.isoformat(),
        "created_at_label": f"{format_jalali_numeric(created_at.date())}، ساعت {format_time_fa(created_at.time())}",
    }


class NotificationCenterView(LoginRequiredMixin, View):
    template_name = "notifications/notification_center.html"
    paginate_by = 15

    def get(self, request):
        role = request.GET.get("role") or ""
        filter_status = request.GET.get("filter", "all")
        qs = list_user_notifications(
            request.user, audience_role=role or None, filter_status=filter_status
        )
        paginator = Paginator(qs, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "notifications": page_obj.object_list,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": page_obj.has_other_pages(),
                "active_filter": filter_status,
                "active_role": role,
                "unread_count": unread_count(request.user, audience_role=role or None),
            },
        )


@login_required
@require_GET
def notifications_summary(request):
    role = _notification_summary_role_from_request(request)
    if role is None:
        return JsonResponse(
            {"error": "invalid_role"},
            status=400,
        )

    latest = list_user_notifications(request.user, audience_role=role or None)[:5]
    return JsonResponse(
        {
            "unread_count": unread_count(request.user, audience_role=role or None),
            "notifications": [
                _recipient_to_dict(recipient, request) for recipient in latest
            ],
        }
    )


@require_POST
@login_required
def mark_notification_read(request, recipient_id):
    recipient = get_object_or_404(
        NotificationRecipient, id=recipient_id, user=request.user
    )
    recipient.mark_as_read()

    if not _expects_json(request):
        return _redirect_back(request)

    return JsonResponse(
        {
            "status": "success",
            "recipient_id": recipient.id,
            "unread_count": unread_count(request.user),
        }
    )


@require_POST
@login_required
def mark_notifications_read_all(request):
    role = _notification_action_role_from_request(request)
    if role is None:
        if _expects_json(request):
            return JsonResponse({"error": "invalid_role"}, status=400)
        return redirect("notifications:center")

    updated = mark_all_read(request.user, audience_role=role or None)

    if not _expects_json(request):
        return _redirect_back(request)

    return JsonResponse(
        {
            "status": "success",
            "updated": updated,
            "unread_count": unread_count(request.user, audience_role=role or None),
        }
    )
