"""Short-lived signup continuation; a supplied mobile never authorizes an account."""

import time

ROLE_INTENT_KEY = "multirole_signup_intent"
ROLE_INTENT_TTL_SECONDS = 600
ALLOWED_ROLE_KINDS = frozenset({"customer", "stylist", "manager"})


def set_role_intent(request, *, mobile, kind):
    if kind not in ALLOWED_ROLE_KINDS or not mobile:
        return
    request.session[ROLE_INTENT_KEY] = {
        "mobile": mobile,
        "kind": kind,
        "expires_at": int(time.time()) + ROLE_INTENT_TTL_SECONDS,
    }


def consume_role_intent(request, user):
    """Return the role only after an actual login to the same mobile identity."""
    intent = request.session.pop(ROLE_INTENT_KEY, None)
    if not isinstance(intent, dict):
        return None
    if (
        intent.get("kind") not in ALLOWED_ROLE_KINDS
        or intent.get("mobile") != getattr(user, "mobile_number", None)
        or not getattr(user, "is_active", False)
    ):
        return None
    try:
        expires_at = int(intent.get("expires_at", 0))
    except (ValueError, TypeError):
        return None
    if not expires_at or int(time.time()) > expires_at:
        return None
    return intent["kind"]
