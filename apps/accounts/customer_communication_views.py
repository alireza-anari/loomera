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
    user_messaging_roles,
)
from apps.messaging.services import (
    ensure_default_providers,
    messaging_enabled,
    provider_allowed,
)
from apps.notifications.models import NotificationAudienceRole, NotificationChannel


class CustomerCommunicationSettingsView(LoginRequiredMixin, View):
    """Canonical notification + messaging settings surface.

    Email/SMS keep using the legacy Customer booleans because existing delivery
    code still reads them. Bale and Telegram both use the shared, role-aware
    NotificationPreference model. Connection state and notification preference
    remain independent.
    """

    template_name = "accounts/customer_communication_settings.html"

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, "customer_profile"):
            return redirect("accounts:customer_panel")
        return super().dispatch(request, *args, **kwargs)

    def _audience_role(self, user):
        roles = {item["key"]: item["label"] for item in user_messaging_roles(user)}
        for candidate in (
            NotificationAudienceRole.MANAGER,
            NotificationAudienceRole.STYLIST,
            NotificationAudienceRole.CUSTOMER,
        ):
            if candidate in roles:
                return candidate, roles[candidate]
        return NotificationAudienceRole.CUSTOMER, "مشتری"

    def _provider(self, provider_key):
        ensure_default_providers()
        return MessagingProvider.objects.filter(key=provider_key).first()

    def _connection(self, request, provider_key):
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

    def _provider_ready(self, provider, provider_key):
        return bool(
            messaging_enabled()
            and provider is not None
            and provider.is_active
            and provider_allowed(provider_key)
        )

    def _connect_url(self, request, provider_key):
        url = reverse(
            "messaging:provider_quick_connect",
            kwargs={"provider_key": str(provider_key)},
        )
        return f"{url}?{urlencode({'next': request.path})}"

    def _provider_context(
        self,
        *,
        request,
        prefix,
        provider_key,
        channel,
        audience_role,
    ):
        provider = self._provider(provider_key)
        connection = self._connection(request, provider_key)
        return {
            f"{prefix}_ready": self._provider_ready(provider, provider_key),
            f"{prefix}_connected": bool(connection),
            f"{prefix}_connection": connection,
            f"{prefix}_connect_url": self._connect_url(request, provider_key),
            f"{prefix}_operational": stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_OPERATIONAL,
                audience_role=audience_role,
            ),
            f"{prefix}_marketing": stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_MARKETING,
                audience_role=audience_role,
            ),
        }

    def _context(self, request):
        customer = request.user.customer_profile
        audience_role, audience_role_label = self._audience_role(request.user)

        context = {
            "customer": customer,
            "audience_role": audience_role,
            "audience_role_label": audience_role_label,
            "notification_center_url": reverse("accounts:notifications"),
            "settings_return_url": reverse("accounts:customer_settings"),
            "messaging_privacy_url": reverse("messaging:privacy"),
        }
        context.update(
            self._provider_context(
                request=request,
                prefix="bale",
                provider_key=MessagingProviderKey.BALE,
                channel=NotificationChannel.BALE.value,
                audience_role=audience_role,
            )
        )
        context.update(
            self._provider_context(
                request=request,
                prefix="telegram",
                provider_key=MessagingProviderKey.TELEGRAM,
                channel=NotificationChannel.TELEGRAM.value,
                audience_role=audience_role,
            )
        )
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        customer = request.user.customer_profile
        audience_role, _audience_role_label = self._audience_role(request.user)

        customer.notify_appointment_email = normalize_bool(
            request.POST.get("appointment_email")
        )
        customer.notify_appointment_sms = normalize_bool(
            request.POST.get("appointment_sms")
        )
        customer.notify_marketing_email = normalize_bool(
            request.POST.get("marketing_email")
        )
        customer.notify_marketing_sms = normalize_bool(
            request.POST.get("marketing_sms")
        )
        customer.save(
            update_fields=[
                "notify_appointment_email",
                "notify_appointment_sms",
                "notify_marketing_email",
                "notify_marketing_sms",
            ]
        )

        for prefix, channel in (
            ("bale", NotificationChannel.BALE.value),
            ("telegram", NotificationChannel.TELEGRAM.value),
        ):
            set_stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_OPERATIONAL,
                enabled=normalize_bool(
                    request.POST.get(f"{prefix}_operational")
                ),
                audience_role=audience_role,
            )
            set_stream_enabled(
                user=request.user,
                channel=channel,
                stream=STREAM_MARKETING,
                enabled=normalize_bool(
                    request.POST.get(f"{prefix}_marketing")
                ),
                audience_role=audience_role,
            )

        messages.success(request, "تنظیم اعلان‌ها و ارتباطات ذخیره شد.")
        return redirect("accounts:customer_communication_settings")
