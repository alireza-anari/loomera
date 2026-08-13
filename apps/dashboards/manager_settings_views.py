from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.dashboards.layout import build_dashboard_context
from apps.messaging.constants import MessagingConnectionStatus, MessagingProviderKey
from apps.messaging.models import MessagingAccountConnection, MessagingProvider
from apps.messaging.preferences import (
    STREAM_MARKETING,
    STREAM_OPERATIONAL,
    normalize_bool,
    set_stream_enabled,
    stream_enabled,
)
from apps.messaging.services import ensure_default_providers, messaging_enabled, provider_allowed
from apps.notifications.models import NotificationAudienceRole, NotificationChannel
from apps.salons.membership import get_active_salon_for_stylist


class ManagerCommunicationSettingsView(LoginRequiredMixin, View):
    """Manager-facing notification and messenger configuration.

    This page intentionally exposes only the channel that is usable today
    (Bale). Future messaging adapters remain in the shared messaging layer but
    are not presented as configurable manager settings before they are usable.
    """

    template_name = "dashboards/manager_communication_settings.html"
    audience_role = NotificationAudienceRole.MANAGER

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "salon_manager_profile"):
            return redirect("dashboards:salon_manager_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def _bale_provider(self):
        ensure_default_providers()
        return MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()

    def _bale_ready(self, provider):
        return bool(
            messaging_enabled()
            and provider is not None
            and provider.is_active
            and provider_allowed(MessagingProviderKey.BALE)
        )

    def _active_connection(self, request):
        return (
            MessagingAccountConnection.objects.select_related("provider", "identity")
            .filter(
                user=request.user,
                provider__key=MessagingProviderKey.BALE,
                status=MessagingConnectionStatus.ACTIVE,
            )
            .order_by("-connected_at", "-id")
            .first()
        )

    def _context(self, request):
        provider = self._bale_provider()
        connection = self._active_connection(request)
        operational_enabled = stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_OPERATIONAL,
            audience_role=self.audience_role,
        )
        marketing_enabled = stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_MARKETING,
            audience_role=self.audience_role,
        )

        connect_url = reverse("messaging:bale_quick_connect")
        connect_url = f"{connect_url}?{urlencode({'next': request.path})}"

        context = build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title="اعلان‌ها و ارتباطات",
            request_path=request.path,
        )
        context.update(
            {
                "hide_dashboard_header": True,
                "hide_dashboard_top_nav": True,
                "page_meta": {
                    "title": "اعلان‌ها و ارتباطات",
                    "description": "اعلان‌های نقش مدیر و اتصال بله را از یک صفحه مدیریت کن.",
                    "icon": "fa-regular fa-bell",
                    "badges": [],
                    "primary_action": {
                        "label": "بازگشت به تنظیمات",
                        "url": reverse("dashboards:workspace_settings"),
                    },
                },
                "bale_ready": self._bale_ready(provider),
                "bale_connection": connection,
                "bale_connected": bool(connection),
                "bale_connect_url": connect_url,
                "operational_enabled": operational_enabled,
                "marketing_enabled": marketing_enabled,
                "messaging_privacy_url": reverse("messaging:privacy"),
                "notification_center_url": reverse("dashboards:notifications_center"),
                "settings_return_url": reverse("dashboards:workspace_settings"),
                "communication_role_label": "مدیر",
                "communication_owner_label": "مدیر مجموعه",
                "communication_description": "مشخص کن چه پیام‌هایی برای نقش مدیر در بله دریافت کنی و اتصال بله را از همین صفحه مدیریت کن.",
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        set_stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_OPERATIONAL,
            enabled=normalize_bool(request.POST.get("bale_operational")),
            audience_role=self.audience_role,
        )
        set_stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_MARKETING,
            enabled=normalize_bool(request.POST.get("bale_marketing")),
            audience_role=self.audience_role,
        )
        messages.success(request, "تنظیم اعلان‌های مدیر ذخیره شد.")
        return redirect("dashboards:manager_communication_settings")


class StylistCommunicationSettingsView(ManagerCommunicationSettingsView):
    """Stylist-facing Bale preferences using the same safe messaging primitives."""

    audience_role = NotificationAudienceRole.STYLIST

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "stylist"):
            return redirect("dashboards:stylist_dashboard")
        return LoginRequiredMixin.dispatch(self, request, *args, **kwargs)

    def _context(self, request):
        provider = self._bale_provider()
        connection = self._active_connection(request)
        operational_enabled = stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_OPERATIONAL,
            audience_role=self.audience_role,
        )
        marketing_enabled = stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_MARKETING,
            audience_role=self.audience_role,
        )
        connect_url = reverse("messaging:bale_quick_connect")
        connect_url = f"{connect_url}?{urlencode({'next': request.path})}"
        salon = get_active_salon_for_stylist(request.user, request=request)
        stylist = request.user.stylist
        context = build_dashboard_context(
            request.user,
            sidebar_active="my_settings",
            page_title="اعلان‌ها و ارتباطات",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
        context.update(
            {
                "page_meta": {
                    "title": "اعلان‌ها و ارتباطات",
                    "description": "اعلان‌های نقش متخصص و اتصال بله را از یک صفحه مدیریت کن.",
                    "icon": "fa-regular fa-bell",
                    "badges": [],
                    "primary_action": {
                        "label": "بازگشت به تنظیمات",
                        "url": reverse("dashboards:stylist_settings"),
                    },
                },
                "bale_ready": self._bale_ready(provider),
                "bale_connection": connection,
                "bale_connected": bool(connection),
                "bale_connect_url": connect_url,
                "operational_enabled": operational_enabled,
                "marketing_enabled": marketing_enabled,
                "messaging_privacy_url": reverse("messaging:privacy"),
                "notification_center_url": reverse("dashboards:stylist_notifications"),
                "settings_return_url": reverse("dashboards:stylist_settings"),
                "communication_role_label": "متخصص",
                "communication_owner_label": "متخصص",
                "communication_description": "مشخص کن چه پیام‌هایی برای نقش متخصص در بله دریافت کنی و اتصال بله را از همین صفحه مدیریت کن.",
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        set_stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_OPERATIONAL,
            enabled=normalize_bool(request.POST.get("bale_operational")),
            audience_role=self.audience_role,
        )
        set_stream_enabled(
            user=request.user,
            channel=NotificationChannel.BALE.value,
            stream=STREAM_MARKETING,
            enabled=normalize_bool(request.POST.get("bale_marketing")),
            audience_role=self.audience_role,
        )
        messages.success(request, "تنظیم اعلان‌های متخصص ذخیره شد.")
        return redirect("dashboards:stylist_communication_settings")
