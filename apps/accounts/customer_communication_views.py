from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

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


class CustomerCommunicationSettingsView(LoginRequiredMixin, View):
    """One customer-facing place for usable notification channels.

    Legacy Customer booleans for email/SMS are preserved because existing
    notification delivery code can still read them. WhatsApp is intentionally
    not exposed while that channel is not an active product surface. Bale uses
    the role-aware NotificationPreference system shared with manager/stylist.
    """

    template_name = "accounts/customer_communication_settings.html"
    audience_role = NotificationAudienceRole.CUSTOMER

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "customer_profile"):
            return redirect("accounts:customer_panel")
        return super().dispatch(request, *args, **kwargs)

    def _provider(self):
        ensure_default_providers()
        return MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()

    def _connection(self, request):
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
        customer = request.user.customer_profile
        provider = self._provider()
        connection = self._connection(request)
        bale_ready = bool(
            messaging_enabled()
            and provider is not None
            and provider.is_active
            and provider_allowed(MessagingProviderKey.BALE)
        )
        connect_url = reverse("messaging:bale_quick_connect")
        connect_url = f"{connect_url}?{urlencode({'next': request.path})}"
        return {
            "customer": customer,
            "bale_ready": bale_ready,
            "bale_connected": bool(connection),
            "bale_connection": connection,
            "bale_connect_url": connect_url,
            "bale_operational": stream_enabled(
                user=request.user,
                channel=NotificationChannel.BALE.value,
                stream=STREAM_OPERATIONAL,
                audience_role=self.audience_role,
            ),
            "bale_marketing": stream_enabled(
                user=request.user,
                channel=NotificationChannel.BALE.value,
                stream=STREAM_MARKETING,
                audience_role=self.audience_role,
            ),
            "notification_center_url": reverse("accounts:notifications"),
            "settings_return_url": reverse("accounts:customer_settings"),
            "messaging_privacy_url": reverse("messaging:privacy"),
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        customer = request.user.customer_profile
        customer.notify_appointment_email = normalize_bool(request.POST.get("appointment_email"))
        customer.notify_appointment_sms = normalize_bool(request.POST.get("appointment_sms"))
        customer.notify_marketing_email = normalize_bool(request.POST.get("marketing_email"))
        customer.notify_marketing_sms = normalize_bool(request.POST.get("marketing_sms"))
        customer.save(update_fields=[
            "notify_appointment_email",
            "notify_appointment_sms",
            "notify_marketing_email",
            "notify_marketing_sms",
        ])

        set_stream_enabled(
            user=request.user, channel=NotificationChannel.BALE.value,
            stream=STREAM_OPERATIONAL, enabled=normalize_bool(request.POST.get("bale_operational")),
            audience_role=self.audience_role,
        )
        set_stream_enabled(
            user=request.user, channel=NotificationChannel.BALE.value,
            stream=STREAM_MARKETING, enabled=normalize_bool(request.POST.get("bale_marketing")),
            audience_role=self.audience_role,
        )
        messages.success(request, "تنظیم اعلان‌ها و ارتباطات ذخیره شد.")
        return redirect("accounts:customer_communication_settings")
