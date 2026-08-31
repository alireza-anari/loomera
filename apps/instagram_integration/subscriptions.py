from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings


class InstagramWebhookSubscriptionError(Exception):
    pass


@dataclass(frozen=True)
class InstagramWebhookSubscriptionResult:
    success: bool
    fields: tuple[str, ...]


def _endpoint(account_id):
    base = str(
        getattr(settings, "INSTAGRAM_GRAPH_BASE_URL", "https://graph.instagram.com")
        or "https://graph.instagram.com"
    ).strip().rstrip("/")
    version = str(
        getattr(settings, "INSTAGRAM_GRAPH_API_VERSION", "v24.0") or "v24.0"
    ).strip().strip("/")
    return f"{base}/{version}/{account_id}/subscribed_apps"


def _fields():
    values = getattr(
        settings,
        "INSTAGRAM_WEBHOOK_SUBSCRIBED_FIELDS",
        ["messages"],
    )
    return tuple(
        str(item).strip()
        for item in values
        if str(item).strip()
    )


def subscribe_professional_account(*, account_id, access_token):
    account_id = str(account_id or "").strip()
    token = str(access_token or "").strip()
    fields = _fields()

    if not account_id or not token:
        raise InstagramWebhookSubscriptionError(
            "Instagram account or access token is missing."
        )
    if "messages" not in fields:
        raise InstagramWebhookSubscriptionError(
            "Instagram messaging subscription must include messages."
        )

    timeout = int(getattr(settings, "INSTAGRAM_REQUEST_TIMEOUT", 10))

    try:
        response = requests.post(
            _endpoint(account_id),
            json={"subscribed_fields": list(fields)},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise InstagramWebhookSubscriptionError(
            "Instagram webhook subscription request failed."
        ) from exc

    if not response.ok:
        raise InstagramWebhookSubscriptionError(
            "Instagram webhook subscription was rejected."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise InstagramWebhookSubscriptionError(
            "Instagram webhook subscription returned invalid JSON."
        ) from exc

    if payload.get("success") is not True:
        raise InstagramWebhookSubscriptionError(
            "Instagram webhook subscription did not succeed."
        )

    return InstagramWebhookSubscriptionResult(
        success=True,
        fields=fields,
    )


def unsubscribe_professional_account(*, account_id, access_token):
    account_id = str(account_id or "").strip()
    token = str(access_token or "").strip()

    if not account_id or not token:
        return False

    timeout = int(getattr(settings, "INSTAGRAM_REQUEST_TIMEOUT", 10))

    try:
        response = requests.delete(
            _endpoint(account_id),
            headers={
                "Authorization": f"Bearer {token}",
            },
            timeout=timeout,
        )
    except requests.RequestException:
        return False

    if not response.ok:
        return False

    try:
        payload = response.json()
    except ValueError:
        return False

    return payload.get("success") is True
