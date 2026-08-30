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
    """Manager/stylist notification and messenger configuration for Beta."""

    template_name = "dashboards/manager_communication_settings.html"
    audience_role = NotificationAudienceRole.MANAGER
    communication_role_label = "مدیر"
    communication_owner_label = "مدیر مجموعه"
    communication_description = (
        "مشخص کن چه پیام‌هایی را در بله و تلگرام دریافت کنی و اتصال هر پیام‌رسان "
        "را از همین صفحه مدیریت کن."
    )
    redirect_name = "dashboards:manager_communication_settings"
    settings_return_name = "dashboards:workspace_settings"
    notification_center_name = "dashboards:notifications_center"
    success_message = "تنظیم اعلان‌های مدیر ذخیره شد."

    provider_specs = (
        (
            "bale",
            MessagingProviderKey.BALE,
            NotificationChannel.BALE.value,
        ),
        (
            "telegram",
            MessagingProviderKey.TELEGRAM,
            NotificationChannel.TELEGRAM.value,
        ),
    )

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "salon_manager_profile"):
            return redirect("dashboards:salon_manager_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def _provider(self, provider_key):
        ensure_default_providers()
        return MessagingProvider.objects.filter(key=provider_key).first()

    def _provider_ready(self, provider, provider_key):
        return bool(
            messaging_enabled()
            and provider is not None
            and provider.is_active
            and provider_allowed(provider_key)
        )

    def _active_connection(self, request, provider_key):
        return (
            MessagingAccountConnection.objects.select_related("provider", "identity")
            .filter(
                user=request.user,
                provider__key=provider_key,
                status=MessagingConnectionStatus.ACTIVE,
            )
            .order_by("-connected_at", "-id")
            .first()
        )

    def _connect_url(self, request, provider_key):
        connect_url = reverse(
            "messaging:provider_quick_connect",
            kwargs={"provider_key": str(provider_key)},
        )
        return f"{connect_url}?{urlencode({'next': request.path})}"

    def _provider_context(
        self,
        *,
        request,
        prefix,
        provider_key,
        channel,
    ):
        provider = self._provider(provider_key)
        connection = self._active_connection(request, provider_key)
        return {
            f"{prefix}_ready": self._provider_ready(provider, provider_key),
            f"{prefix}_connection": connection,
            f"{prefix}_connected": bool(connection),
            f"{prefix}_connect_url": self._connect_url(request, provider_key),
            f"{prefix}_operational": stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_OPERATIONAL,
                audience_role=self.audience_role,
            ),
            f"{prefix}_marketing": stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_MARKETING,
                audience_role=self.audience_role,
            ),
        }

    def _dashboard_context(self, request):
        return build_dashboard_context(
            request.user,
            nav_active="home",
            sidebar_active="settings",
            page_title="اعلان‌ها و ارتباطات",
            request_path=request.path,
        )

    def _context(self, request):
        context = self._dashboard_context(request)
        context.update(
            {
                "hide_dashboard_header": True,
                "hide_dashboard_top_nav": True,
                "page_meta": {
                    "title": "اعلان‌ها و ارتباطات",
                    "description": self.communication_description,
                    "icon": "fa-regular fa-bell",
                    "badges": [],
                    "primary_action": {
                        "label": "بازگشت به تنظیمات",
                        "url": reverse(self.settings_return_name),
                    },
                },
                "messaging_privacy_url": reverse("messaging:privacy"),
                "notification_center_url": reverse(self.notification_center_name),
                "settings_return_url": reverse(self.settings_return_name),
                "communication_role_label": self.communication_role_label,
                "communication_owner_label": self.communication_owner_label,
                "communication_description": self.communication_description,
            }
        )
        for prefix, provider_key, channel in self.provider_specs:
            context.update(
                self._provider_context(
                    request=request,
                    prefix=prefix,
                    provider_key=provider_key,
                    channel=channel,
                )
            )
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        for prefix, _provider_key, channel in self.provider_specs:
            set_stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_OPERATIONAL,
                enabled=normalize_bool(request.POST.get(f"{prefix}_operational")),
                audience_role=self.audience_role,
            )
            set_stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_MARKETING,
                enabled=normalize_bool(request.POST.get(f"{prefix}_marketing")),
                audience_role=self.audience_role,
            )

        messages.success(request, self.success_message)
        return redirect(self.redirect_name)


class StylistCommunicationSettingsView(ManagerCommunicationSettingsView):
    """Stylist-facing Bale/Telegram preferences using shared messaging primitives."""

    audience_role = NotificationAudienceRole.STYLIST
    communication_role_label = "متخصص"
    communication_owner_label = "متخصص"
    communication_description = (
        "مشخص کن چه پیام‌هایی را برای نقش متخصص در بله و تلگرام دریافت کنی و "
        "اتصال هر پیام‌رسان را از همین صفحه مدیریت کن."
    )
    redirect_name = "dashboards:stylist_communication_settings"
    settings_return_name = "dashboards:stylist_settings"
    notification_center_name = "dashboards:stylist_notifications"
    success_message = "تنظیم اعلان‌های متخصص ذخیره شد."

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "stylist"):
            return redirect("dashboards:stylist_dashboard")
        return LoginRequiredMixin.dispatch(self, request, *args, **kwargs)

    def _dashboard_context(self, request):
        salon = get_active_salon_for_stylist(request.user, request=request)
        stylist = request.user.stylist
        return build_dashboard_context(
            request.user,
            sidebar_active="my_settings",
            page_title="اعلان‌ها و ارتباطات",
            request_path=request.path,
            role="stylist",
            salon_override=salon,
            stylist_override=stylist,
        )
