from __future__ import annotations

from urllib.parse import urlencode

from django import template
from django.urls import reverse

from apps.messaging.constants import MessagingConnectionStatus, MessagingProviderKey
from apps.messaging.models import MessagingAccountConnection, MessagingProvider
from apps.messaging.services import messaging_enabled, provider_allowed

register = template.Library()


@register.inclusion_tag("messaging/components/bale_connect_card.html", takes_context=True)
def bale_connect_card(context, compact: bool = False):
    request = context.get("request")
    user = getattr(request, "user", None)
    provider = MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()
    ready = bool(
        user
        and user.is_authenticated
        and messaging_enabled()
        and provider is not None
        and provider.is_active
        and provider_allowed(MessagingProviderKey.BALE)
    )
    active_connection = None
    if user and user.is_authenticated:
        active_connection = (
            MessagingAccountConnection.objects.select_related("identity", "provider")
            .filter(
                user=user,
                provider__key=MessagingProviderKey.BALE,
                status=MessagingConnectionStatus.ACTIVE,
            )
            .order_by("-connected_at", "-id")
            .first()
        )

    next_path = request.get_full_path() if request else ""
    quick_connect_url = reverse("messaging:bale_quick_connect")
    if next_path:
        quick_connect_url = f"{quick_connect_url}?{urlencode({'next': next_path})}"

    return {
        "ready": ready,
        "connected": bool(active_connection),
        "connection": active_connection,
        "quick_connect_url": quick_connect_url,
        "status_url": reverse("messaging:status"),
        "compact": compact,
    }
