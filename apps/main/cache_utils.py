from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.core.cache import cache


def cache_key(namespace: str, *parts, version: str | None = None) -> str:
    raw = ":".join(str(p) for p in parts if p is not None)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return f"loomera:{version or getattr(settings, 'LOOMERA_CACHE_VERSION', 'v1')}:{namespace}:{digest}"


def get_or_set(namespace: str, parts, builder, *, timeout=None):
    key = cache_key(namespace, *parts)
    value = cache.get(key)
    if value is not None:
        return value
    value = builder()
    cache.set(key, value, timeout=timeout or getattr(settings, "LOOMERA_CACHE_TTL_MEDIUM", 600))
    return value


def stable_hash(value) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()
