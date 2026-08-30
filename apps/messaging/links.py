from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.urls import reverse


def absolute_site_url(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}" if base else path


def build_bale_start_payload(raw_token: str) -> str:
    return f"connect_{raw_token}"


def build_bale_start_url(raw_token: str) -> str:
    payload = build_bale_start_payload(raw_token)
    template = str(getattr(settings, "BALE_BOT_START_URL_TEMPLATE", "") or "").strip()
    if template:
        return template.format(payload=quote(payload), raw_token=quote(raw_token))

    username = str(getattr(settings, "BALE_BOT_USERNAME", "") or "").strip().lstrip("@")
    if not username:
        return ""

    # Keep the deep-link shape configurable for Bale deployments. If Bale changes
    # its public start-link format, BALE_BOT_START_URL_TEMPLATE can override this.
    return f"https://ble.ir/{username}?start={quote(payload)}"


def build_provider_start_payload(raw_token: str) -> str:
    return f"connect_{raw_token}"


def build_provider_start_url(provider_key: str, raw_token: str) -> str:
    provider_key = str(provider_key or "").strip().lower()
    if provider_key == "bale":
        return build_bale_start_url(raw_token)
    if provider_key == "telegram":
        username = str(
            getattr(settings, "TELEGRAM_BOT_USERNAME", "") or ""
        ).strip().lstrip("@")
        if not username:
            return ""
        payload = build_provider_start_payload(raw_token)
        return f"https://t.me/{username}?start={quote(payload)}"
    return ""


def build_login_next_url(request) -> str:
    return f"{reverse('accounts:login')}?next={quote(request.get_full_path())}"
