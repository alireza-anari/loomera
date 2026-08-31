from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.salons.models import Salon, SalonMembership, SalonMembershipStatus


OAUTH_STATE_SALT = "loomera.instagram.oauth.v1"
SESSION_NONCE_KEY = "instagram_oauth_nonce"
SESSION_USER_KEY = "instagram_oauth_user_id"


class InstagramOAuthStateError(Exception):
    pass


class InstagramProviderError(Exception):
    pass


@dataclass(frozen=True)
class InstagramContext:
    salon: object
    stylist: object | None = None

    @property
    def kind(self):
        return "stylist" if self.stylist is not None else "salon"


@dataclass(frozen=True)
class InstagramOAuthResult:
    account_id: str
    username: str
    expires_in: int
    scopes: tuple[str, ...]
    access_token: str = field(repr=False)


def require_messaging_enabled():
    if not bool(getattr(settings, "INSTAGRAM_ENABLED", False)):
        raise PermissionDenied("Instagram integration is disabled.")
    if not bool(getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)):
        raise PermissionDenied("Instagram messaging is disabled.")


def resolve_context_for_user(*, user, salon_id, context_kind):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")

    if context_kind == "salon":
        manager = getattr(user, "salon_manager_profile", None)
        if manager is None:
            raise PermissionDenied("Salon manager role required.")
        if not getattr(manager, "is_active", False):
            raise PermissionDenied("Active salon manager role required.")

        salon = get_object_or_404(
            Salon.objects.select_related("salon_manager__user"),
            pk=salon_id,
            salon_manager=manager,
            is_active=True,
        )
        return InstagramContext(salon=salon, stylist=None)

    if context_kind == "stylist":
        stylist = getattr(user, "stylist", None)
        if stylist is None:
            raise PermissionDenied("Stylist role required.")
        if not getattr(stylist, "is_active", False):
            raise PermissionDenied("Active stylist role required.")

        membership = get_object_or_404(
            SalonMembership.objects.select_related("salon"),
            salon_id=salon_id,
            stylist=stylist,
            status=SalonMembershipStatus.ACTIVE,
            salon__is_active=True,
        )
        return InstagramContext(salon=membership.salon, stylist=stylist)

    raise PermissionDenied("Unsupported Instagram context.")


def issue_oauth_state(*, request, context):
    nonce = secrets.token_urlsafe(32)
    payload = {
        "v": 1,
        "user_id": request.user.pk,
        "salon_id": context.salon.pk,
        "kind": context.kind,
        "nonce": nonce,
    }

    request.session[SESSION_NONCE_KEY] = nonce
    request.session[SESSION_USER_KEY] = request.user.pk
    request.session.modified = True

    return signing.dumps(payload, salt=OAUTH_STATE_SALT, compress=True)


def consume_oauth_state(*, request, state):
    if not state:
        raise InstagramOAuthStateError("Missing OAuth state.")

    max_age = int(getattr(settings, "INSTAGRAM_OAUTH_STATE_TTL_SECONDS", 600))
    try:
        payload = signing.loads(
            state,
            salt=OAUTH_STATE_SALT,
            max_age=max_age,
        )
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise InstagramOAuthStateError("Invalid or expired OAuth state.") from exc

    session_nonce = request.session.get(SESSION_NONCE_KEY)
    session_user_id = request.session.get(SESSION_USER_KEY)

    if (
        not session_nonce
        or not secrets.compare_digest(
            str(session_nonce),
            str(payload.get("nonce") or ""),
        )
        or str(session_user_id) != str(request.user.pk)
        or str(payload.get("user_id")) != str(request.user.pk)
    ):
        raise InstagramOAuthStateError("OAuth state does not match this session.")

    request.session.pop(SESSION_NONCE_KEY, None)
    request.session.pop(SESSION_USER_KEY, None)
    request.session.modified = True

    return resolve_context_for_user(
        user=request.user,
        salon_id=payload.get("salon_id"),
        context_kind=payload.get("kind"),
    )


def build_authorization_url(*, state):
    params = {
        "client_id": settings.INSTAGRAM_APP_ID,
        "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(settings.INSTAGRAM_LOGIN_SCOPES),
        "state": state,
        "enable_fb_login": "0",
    }
    return (
        settings.INSTAGRAM_OAUTH_AUTHORIZE_URL.rstrip("?")
        + "?"
        + urlencode(params)
    )


def _json_or_provider_error(response):
    try:
        payload = response.json()
    except ValueError as exc:
        raise InstagramProviderError(
            "Instagram returned an invalid response."
        ) from exc

    if not response.ok:
        raise InstagramProviderError("Instagram authentication request failed.")
    return payload


def exchange_code_for_connection(*, code):
    code = str(code or "").strip()
    if not code:
        raise InstagramProviderError("Instagram authorization code is missing.")

    timeout = int(getattr(settings, "INSTAGRAM_REQUEST_TIMEOUT", 10))

    try:
        short_response = requests.post(
            settings.INSTAGRAM_OAUTH_TOKEN_URL,
            data={
                "client_id": settings.INSTAGRAM_APP_ID,
                "client_secret": settings.INSTAGRAM_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
                "code": code,
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise InstagramProviderError(
            "Instagram authentication request failed."
        ) from exc

    short_payload = _json_or_provider_error(short_response)
    short_token = str(short_payload.get("access_token") or "").strip()
    if not short_token:
        raise InstagramProviderError("Instagram did not return an access token.")

    graph_base = settings.INSTAGRAM_GRAPH_BASE_URL.rstrip("/")

    try:
        long_response = requests.get(
            f"{graph_base}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.INSTAGRAM_APP_SECRET,
                "access_token": short_token,
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise InstagramProviderError(
            "Instagram long-lived token exchange failed."
        ) from exc

    long_payload = _json_or_provider_error(long_response)
    long_token = str(long_payload.get("access_token") or "").strip()
    if not long_token:
        raise InstagramProviderError(
            "Instagram did not return a long-lived access token."
        )

    try:
        expires_in = int(long_payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0

    try:
        profile_response = requests.get(
            f"{graph_base}/me",
            params={"fields": "id,username"},
            headers={"Authorization": f"Bearer {long_token}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise InstagramProviderError(
            "Instagram account verification failed."
        ) from exc

    profile = _json_or_provider_error(profile_response)
    account_id = str(profile.get("id") or "").strip()
    username = str(profile.get("username") or "").strip()

    if not account_id:
        raise InstagramProviderError(
            "Instagram account identity could not be verified."
        )

    returned_scopes = long_payload.get("scope") or short_payload.get("scope") or ()
    if isinstance(returned_scopes, str):
        scopes = tuple(
            item.strip()
            for item in returned_scopes.replace(" ", ",").split(",")
            if item.strip()
        )
    elif isinstance(returned_scopes, (list, tuple)):
        scopes = tuple(
            str(item).strip()
            for item in returned_scopes
            if str(item).strip()
        )
    else:
        scopes = ()

    if not scopes:
        scopes = tuple(settings.INSTAGRAM_LOGIN_SCOPES)

    return InstagramOAuthResult(
        account_id=account_id,
        username=username,
        access_token=long_token,
        expires_in=expires_in,
        scopes=scopes,
    )


def expiry_from_result(result):
    if result.expires_in <= 0:
        return None
    return timezone.now() + timedelta(seconds=result.expires_in)
