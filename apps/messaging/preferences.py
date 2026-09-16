from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from apps.notifications.models import (
    NotificationAudienceRole,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
)

from .constants import MessagingConnectionStatus, MessagingProviderKey
from .models import MessagingAccountConnection
from .roles import ROLE_LABELS, detect_user_bot_roles


OPERATIONAL_CATEGORIES: tuple[str, ...] = (
    NotificationCategory.BOOKING,
    NotificationCategory.PAYMENT,
    NotificationCategory.FINANCE,
    NotificationCategory.STAFF,
    NotificationCategory.CONTENT,
    NotificationCategory.SUPPORT,
    NotificationCategory.VERIFICATION,
    NotificationCategory.SYSTEM,
)

MARKETING_CATEGORIES: tuple[str, ...] = (NotificationCategory.MARKETING,)

MESSAGING_CHANNELS: tuple[str, ...] = (
    NotificationChannel.BALE.value,
    NotificationChannel.TELEGRAM.value,
)

CHANNEL_PROVIDER_KEY = {
    NotificationChannel.BALE.value: MessagingProviderKey.BALE,
    NotificationChannel.TELEGRAM.value: MessagingProviderKey.TELEGRAM,
    NotificationChannel.WHATSAPP.value: MessagingProviderKey.WHATSAPP,
    NotificationChannel.RUBIKA.value: MessagingProviderKey.RUBIKA,
}

CHANNEL_DESCRIPTIONS = {
    NotificationChannel.BALE: "اعلان‌ها و اکشن‌های Loomera در ربات بله.",
    NotificationChannel.TELEGRAM: "اعلان‌ها و اکشن‌های Loomera در ربات تلگرام.",
}

STREAM_OPERATIONAL = "operational"
STREAM_MARKETING = "marketing"
STREAM_CHOICES = {STREAM_OPERATIONAL, STREAM_MARKETING}


def channel_value(channel: str) -> str:
    return str(getattr(channel, "value", channel))


@dataclass(frozen=True)
class MessagingPreferenceRow:
    channel: str
    channel_label: str
    provider_key: str
    description: str
    operational_enabled: bool
    marketing_enabled: bool
    is_currently_connectable: bool = False
    is_connected: bool = False
    connected_identity_id: int | None = None


def normalize_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes", "y", "بله"}


def user_messaging_roles(user) -> list[dict[str, str]]:
    context = detect_user_bot_roles(user)
    roles = [{"key": "", "label": "همه نقش‌ها"}]
    for role in context.roles:
        if role.key in {NotificationAudienceRole.CUSTOMER, NotificationAudienceRole.STYLIST, NotificationAudienceRole.MANAGER}:
            roles.append({"key": role.key, "label": ROLE_LABELS.get(role.key, role.label)})
    return roles


def _preference_for(*, user, channel: str, audience_role: str, category: str):
    return (
        NotificationPreference.objects.filter(
            user=user,
            channel=channel,
            audience_role=audience_role or "",
            category=category,
            event_type="",
        )
        .order_by("-id")
        .first()
    )


def stream_enabled(*, user, channel: str, stream: str, audience_role: str = "") -> bool:
    categories = OPERATIONAL_CATEGORIES if stream == STREAM_OPERATIONAL else MARKETING_CATEGORIES
    for category in categories:
        pref = _preference_for(user=user, channel=channel, audience_role=audience_role, category=category)
        if pref is not None:
            return bool(pref.is_enabled)
    return True


def set_stream_enabled(*, user, channel: str, stream: str, enabled: bool, audience_role: str = "") -> None:
    if stream not in STREAM_CHOICES:
        return
    categories = OPERATIONAL_CATEGORIES if stream == STREAM_OPERATIONAL else MARKETING_CATEGORIES
    for category in categories:
        NotificationPreference.objects.update_or_create(
            user=user,
            channel=channel,
            audience_role=audience_role or "",
            category=category,
            event_type="",
            defaults={"is_enabled": bool(enabled)},
        )


def build_messaging_preference_rows(user, *, audience_role: str = "", active_provider_keys: Iterable[str] = ()) -> list[MessagingPreferenceRow]:
    active_provider_set = {str(item) for item in active_provider_keys or []}
    active_connections = (
        MessagingAccountConnection.objects.select_related("identity", "provider")
        .filter(
            user=user,
            status=MessagingConnectionStatus.ACTIVE,
            provider__key__in=[
                MessagingProviderKey.BALE, MessagingProviderKey.TELEGRAM
            ],
        )
        .order_by("-connected_at", "-id")
    )
    connection_by_provider = {}
    for connection in active_connections:
        connection_by_provider.setdefault(str(connection.provider.key), connection)

    rows: list[MessagingPreferenceRow] = []
    for channel in MESSAGING_CHANNELS:
        channel_key = channel_value(channel)
        provider_key = str(CHANNEL_PROVIDER_KEY.get(channel_key, channel_key))
        rows.append(
            MessagingPreferenceRow(
                channel=channel_key,
                channel_label=dict(NotificationChannel.choices).get(channel_key, channel_key),
                provider_key=provider_key,
                description=CHANNEL_DESCRIPTIONS.get(channel, ""),
                operational_enabled=stream_enabled(
                    user=user,
                    channel=channel_key,
                    stream=STREAM_OPERATIONAL,
                    audience_role=audience_role,
                ),
                marketing_enabled=stream_enabled(
                    user=user,
                    channel=channel_key,
                    stream=STREAM_MARKETING,
                    audience_role=audience_role,
                ),
                is_currently_connectable=provider_key in active_provider_set,
                is_connected=provider_key in connection_by_provider,
                connected_identity_id=(
                    connection_by_provider[provider_key].identity_id
                    if provider_key in connection_by_provider
                    else None
                ),
            )
        )
    return rows


def update_messaging_preferences_from_post(
    user, post_data, *, audience_role: str = ""
) -> None:
    for channel in MESSAGING_CHANNELS:
        channel_key = channel_value(channel)

        set_stream_enabled(
            user=user,
            channel=channel_key,
            stream=STREAM_OPERATIONAL,
            enabled=normalize_bool(
                post_data.get(f"{channel_key}_{STREAM_OPERATIONAL}")
            ),
            audience_role=audience_role,
        )
        set_stream_enabled(
            user=user,
            channel=channel_key,
            stream=STREAM_MARKETING,
            enabled=normalize_bool(post_data.get(f"{channel_key}_{STREAM_MARKETING}")),
            audience_role=audience_role,
        )
