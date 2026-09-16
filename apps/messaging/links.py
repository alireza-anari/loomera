from __future__ import annotations

import logging
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def absolute_site_url(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}" if base else path


def build_bale_start_payload(raw_token: str) -> str:
    return f"connect_{raw_token}"


def build_bale_start_url(raw_token: str) -> str:
    payload = build_bale_start_payload(raw_token)
    return _provider_start_url("bale", payload, raw_token=raw_token)


def _provider_start_url(provider_key: str, payload: str, *, raw_token: str) -> str:
    if provider_key not in {"telegram", "bale"}:
        return ""
    username = str(getattr(settings, f"{provider_key.upper()}_BOT_USERNAME", "") or "").strip().lstrip("@")
    if not username:
        return ""
    host = "t.me" if provider_key == "telegram" else "ble.ir"
    canonical = f"https://{host}/{quote(username, safe='')}?start={quote(payload, safe='')}"
    if provider_key == "bale":
        template = str(getattr(settings, "BALE_BOT_START_URL_TEMPLATE", "") or "").strip()
        if template:
            try:
                candidate = template.format(
                    username=quote(username, safe=""),
                    payload=quote(payload, safe=""), raw_token=quote(raw_token, safe=""),
                )
                parsed = urlsplit(candidate)
                # A template customizes link shape, never the environment's bot.
                if (parsed.scheme == "https" and parsed.netloc.lower() == host
                        and parsed.path.rstrip("/").casefold() == f"/{username}".casefold()
                        and not parsed.fragment):
                    return candidate
            except (ValueError, KeyError, IndexError, AttributeError):
                pass
            # Never log the template/candidate: connect links contain raw tokens.
            logger.warning("Ignoring invalid or mismatched BALE_BOT_START_URL_TEMPLATE; using BALE_BOT_USERNAME")
    return canonical


def build_provider_start_payload(raw_token: str) -> str:
    return f"connect_{raw_token}"


def build_provider_start_url(provider_key: str, raw_token: str) -> str:
    provider_key = str(provider_key or "").strip().lower()
    return _provider_start_url(provider_key, build_provider_start_payload(raw_token), raw_token=raw_token)


def build_loomi_start_payload(scope_type: str, object_id: int) -> str:
    scope = {"salon": "s", "stylist": "p"}.get(scope_type)
    value = str(object_id)
    if not scope or not value.isascii() or not value.isdecimal() or not 0 < int(value) <= 2147483647:
        raise ValueError("Invalid Loomi scope or object ID")
    return f"loomi_{scope}_{int(value)}"


def build_loomi_provider_start_url(provider_key: str, scope_type: str, object_id: int) -> str:
    payload = build_loomi_start_payload(scope_type, object_id)
    provider_key = str(provider_key or "").strip().lower()
    return _provider_start_url(provider_key, payload, raw_token=payload)


def build_login_next_url(request) -> str:
    return f"{reverse('accounts:login')}?next={quote(request.get_full_path())}"


def loomi_provider_links(scope_type, target) -> list[dict]:
    """Links for an already-authorized/public target, gated by deployment flags."""
    from .loomi import loomi_messaging_enabled
    from .services import messaging_enabled, provider_allowed

    if not messaging_enabled() or not getattr(target, "is_active", False):
        return []
    links = []
    for key, label in [("telegram", "تلگرام"), ("bale", "بله")]:
        if (loomi_messaging_enabled(key) and provider_allowed(key)
                and getattr(settings, f"{key.upper()}_BOT_ENABLED", False)):
            url = build_loomi_provider_start_url(key, scope_type, target.pk)
            if url.startswith("https://"):
                links.append({"url": url, "label": label})
    return links
