from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from .constants import MessagingConnectionStatus, MessagingProviderKey, MessagingTokenPurpose
from .links import (
    build_bale_start_payload,
    build_bale_start_url,
    build_provider_start_url,
)
from .models import MessagingAccountConnection, MessagingIdentity, MessagingProvider
from .preferences import (
    build_messaging_preference_rows,
    update_messaging_preferences_from_post,
    user_messaging_roles,
)
from .services import (
    disconnect_identity,
    ensure_default_providers,
    issue_messaging_token,
    messaging_enabled,
    provider_allowed,
)


def _get_bale_provider() -> MessagingProvider | None:
    ensure_default_providers()
    return MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()


def _active_provider_keys() -> list[str]:
    ensure_default_providers()
    return list(
        MessagingProvider.objects.filter(is_active=True, supports_outbound=True)
        .order_by("key")
        .values_list("key", flat=True)
    )


def _bale_ready(provider: MessagingProvider | None) -> bool:
    return bool(
        messaging_enabled()
        and provider is not None
        and provider.is_active
        and provider_allowed(MessagingProviderKey.BALE)
    )


class MessagingStatusView(LoginRequiredMixin, View):
    template_name = "messaging/status.html"

    def _context(self, request, **extra):
        provider = _get_bale_provider()
        identities = (
            MessagingIdentity.objects.select_related("provider", "user")
            .filter(user=request.user, provider__key=MessagingProviderKey.BALE)
            .order_by("-updated_at", "-id")
        )
        active_connections = (
            MessagingAccountConnection.objects.select_related("provider", "identity")
            .filter(user=request.user, provider__key=MessagingProviderKey.BALE, status=MessagingConnectionStatus.ACTIVE)
            .order_by("-connected_at", "-id")
        )
        context = {
            "provider": provider,
            "bale_ready": _bale_ready(provider),
            "identities": identities,
            "active_connections": active_connections,
            "connect_ttl_minutes": int(getattr(settings, "MESSAGING_CONNECT_TOKEN_TTL_MINUTES", 30)),
            "hide_footer": True,
        }
        context.update(extra)
        return context

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        provider = _get_bale_provider()
        if not _bale_ready(provider):
            messages.warning(request, "اتصال ربات بله هنوز فعال نشده است.", "warning")
            return render(request, self.template_name, self._context(request))

        ttl_minutes = max(1, int(getattr(settings, "MESSAGING_CONNECT_TOKEN_TTL_MINUTES", 30)))
        raw_token, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT,
            provider=provider,
            user=request.user,
            expires_in=timedelta(minutes=ttl_minutes),
            metadata={"source": "messaging_status_page"},
        )
        start_payload = build_bale_start_payload(raw_token)
        start_url = build_bale_start_url(raw_token)
        messages.success(
            request,
            "توکن اتصال ساخته شد. این کد فقط یک‌بار و تا زمان انقضا معتبر است.",
            "success",
        )
        return render(
            request,
            self.template_name,
            self._context(
                request,
                connect_token=raw_token,
                connect_token_prefix=token.token_prefix,
                connect_start_payload=start_payload,
                connect_start_url=start_url,
            ),
        )


class MessagingBaleQuickConnectView(LoginRequiredMixin, View):
    """Create a one-time Bale connect token and redirect the user to the bot.

    This is used by profile pages for customer, stylist and manager accounts.
    It does not enable sensitive bot actions; it only links the Bale chat_id to
    the authenticated Loomera user after the user opens the bot link.
    """

    def _safe_next_url(self, request) -> str:
        next_url = str(request.GET.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url
        return reverse("messaging:status")

    def get(self, request, *args, **kwargs):
        provider = _get_bale_provider()
        fallback_url = self._safe_next_url(request)
        if not _bale_ready(provider):
            messages.warning(request, "اتصال ربات بله هنوز برای این محیط فعال نیست.", "warning")
            return redirect(fallback_url)

        ttl_minutes = max(1, int(getattr(settings, "MESSAGING_CONNECT_TOKEN_TTL_MINUTES", 30)))
        raw_token, token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT,
            provider=provider,
            user=request.user,
            expires_in=timedelta(minutes=ttl_minutes),
            metadata={"source": "profile_quick_connect", "next": fallback_url},
        )
        start_url = build_bale_start_url(raw_token)
        if not start_url:
            messages.warning(
                request,
                "لینک شروع ربات بله ساخته نشد. نام کاربری ربات را در تنظیمات بررسی کنید.",
                "warning",
            )
            return redirect(reverse("messaging:status"))
        return redirect(start_url)


class MessagingProviderQuickConnectView(LoginRequiredMixin, View):
    BETA_PROVIDERS = {
        str(MessagingProviderKey.BALE): ("بله", "BALE_BOT_ENABLED"),
        str(MessagingProviderKey.TELEGRAM): ("تلگرام", "TELEGRAM_BOT_ENABLED"),
    }

    def _safe_next_url(self, request) -> str:
        next_url = str(request.GET.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url
        return reverse("messaging:preferences")

    def get(self, request, provider_key: str, *args, **kwargs):
        provider_key = str(provider_key or "").strip().lower()
        config = self.BETA_PROVIDERS.get(provider_key)
        fallback_url = self._safe_next_url(request)
        if config is None:
            messages.warning(request, "این پیام‌رسان برای اتصال Beta فعال نیست.", "warning")
            return redirect(fallback_url)

        label, enabled_setting = config
        ensure_default_providers()
        provider = MessagingProvider.objects.filter(key=provider_key).first()
        ready = bool(
            messaging_enabled()
            and bool(getattr(settings, enabled_setting, False))
            and provider is not None
            and provider.is_active
            and provider_allowed(provider_key)
        )
        if not ready:
            messages.warning(
                request, f"اتصال ربات {label} هنوز برای این محیط فعال نیست.", "warning"
            )
            return redirect(fallback_url)

        ttl_minutes = max(
            1, int(getattr(settings, "MESSAGING_CONNECT_TOKEN_TTL_MINUTES", 30))
        )
        raw_token, _token = issue_messaging_token(
            purpose=MessagingTokenPurpose.CONNECT_ACCOUNT,
            provider=provider,
            user=request.user,
            expires_in=timedelta(minutes=ttl_minutes),
            metadata={
                "source": "messaging_provider_quick_connect",
                "provider": provider_key,
                "next": fallback_url,
            },
        )
        start_url = build_provider_start_url(provider_key, raw_token)
        if not start_url:
            messages.warning(
                request,
                f"لینک شروع ربات {label} ساخته نشد. نام کاربری ربات را بررسی کن.",
                "warning",
            )
            return redirect(reverse("messaging:preferences"))
        return redirect(start_url)


class MessagingPreferencesView(LoginRequiredMixin, View):
    template_name = "messaging/preferences.html"

    def _selected_role(self, request) -> str:
        requested = str(request.POST.get("audience_role") or request.GET.get("audience_role") or "").strip()
        allowed = {item["key"] for item in user_messaging_roles(request.user)}
        return requested if requested in allowed else ""

    def _context(self, request, *, selected_role: str | None = None):
        role = selected_role if selected_role is not None else self._selected_role(request)
        roles = user_messaging_roles(request.user)
        role_label = next((item["label"] for item in roles if item["key"] == role), "همه نقش‌ها")
        return {
            "roles": roles,
            "selected_role": role,
            "selected_role_label": role_label,
            "preference_rows": build_messaging_preference_rows(
                request.user,
                audience_role=role,
                active_provider_keys=_active_provider_keys(),
            ),
            "privacy_version": getattr(settings, "MESSAGING_PRIVACY_TEXT_VERSION", "1403-01"),
            "hide_footer": True,
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._context(request))

    def post(self, request, *args, **kwargs):
        selected_role = self._selected_role(request)
        update_messaging_preferences_from_post(request.user, request.POST, audience_role=selected_role)
        messages.success(request, "تنظیمات اعلان پیام‌رسان‌ها ذخیره شد.", "success")
        return redirect(f"{reverse('messaging:preferences')}?audience_role={selected_role}")


class MessagingPrivacyView(TemplateView):
    template_name = "messaging/privacy.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["privacy_version"] = getattr(settings, "MESSAGING_PRIVACY_TEXT_VERSION", "1403-01")
        context["hide_footer"] = True
        return context


class MessagingDisconnectView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def _safe_next_url(self, request) -> str:
        next_url = str(request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url
        return reverse("messaging:status")

    def post(self, request, identity_id: int, *args, **kwargs):
        identity = get_object_or_404(
            MessagingIdentity.objects.select_related("provider", "user"),
            pk=identity_id,
            user=request.user,
            provider__key__in=[
                MessagingProviderKey.BALE,
                MessagingProviderKey.TELEGRAM,
            ],
        )
        provider_title = identity.provider.title or identity.provider.key
        disconnect_identity(identity)
        messages.success(
            request, f"اتصال {provider_title} با حساب شما قطع شد.", "success"
        )
        return redirect(self._safe_next_url(request))
