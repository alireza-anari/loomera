from __future__ import annotations

import hashlib
import hmac

BALE_WEBHOOK_PATH_CONTEXT = b"loomera:bale:webhook:path:v1"


def derive_bale_webhook_path_token(secret: str) -> str:
    normalized_secret = str(secret or "").strip()

    if not normalized_secret:
        return ""

    return hmac.new(
        normalized_secret.encode("utf-8"),
        BALE_WEBHOOK_PATH_CONTEXT,
        hashlib.sha256,
    ).hexdigest()
