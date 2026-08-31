from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import run_checks
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import timezone

from apps.instagram_integration.models import (
    InstagramAccountConnection,
    InstagramConnectionStatus,
)


REQUIRED_DM_SCOPES = {
    "instagram_business_basic",
    "instagram_business_manage_messages",
}


def _bool(value):
    return bool(value)


def _webhook_url():
    redirect_uri = str(
        getattr(settings, "INSTAGRAM_REDIRECT_URI", "") or ""
    ).strip()
    if not redirect_uri:
        return ""

    parts = urlsplit(redirect_uri)
    if not parts.scheme or not parts.netloc:
        return ""

    path = reverse("instagram_integration:webhook")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _fernet_key_valid():
    key = str(
        getattr(settings, "INSTAGRAM_TOKEN_ENCRYPTION_KEY", "") or ""
    ).strip()
    if not key:
        return False
    try:
        Fernet(key.encode("ascii"))
    except Exception:
        return False
    return True


class Command(BaseCommand):
    help = (
        "Check Instagram + Lumi DM staging readiness without changing data. "
        "Use --live with --connection-id to verify one stored token against Meta."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero unless the full DM auto-reply stack is ready.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Perform a read-only Meta identity check for one connection.",
        )
        parser.add_argument(
            "--connection-id",
            type=int,
            default=None,
            help="InstagramAccountConnection id used by --live.",
        )

    def handle(self, *args, **options):
        strict = bool(options["strict"])
        live = bool(options["live"])
        connection_id = options["connection_id"]

        if live and not connection_id:
            raise CommandError("--live requires --connection-id.")

        errors = []
        warnings = []

        def error(code, message):
            errors.append((code, message))

        def warning(code, message):
            warnings.append((code, message))

        flags = {
            "INSTAGRAM_ENABLED": _bool(
                getattr(settings, "INSTAGRAM_ENABLED", False)
            ),
            "INSTAGRAM_MESSAGING_ENABLED": _bool(
                getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)
            ),
            "INSTAGRAM_SEND_ENABLED": _bool(
                getattr(settings, "INSTAGRAM_SEND_ENABLED", False)
            ),
            "INSTAGRAM_AUTO_REPLY_ENABLED": _bool(
                getattr(settings, "INSTAGRAM_AUTO_REPLY_ENABLED", False)
            ),
            "LOOMERA_ENABLE_CELERY": _bool(
                getattr(settings, "LOOMERA_ENABLE_CELERY", False)
            ),
        }

        self.stdout.write("=== Instagram / Lumi DM QA Check ===")
        self.stdout.write(f"strict={strict}")
        self.stdout.write(f"live={live}")
        self.stdout.write("")

        self.stdout.write("Flags:")
        for name, value in flags.items():
            self.stdout.write(f"  {name}={value}")
        eager = _bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
        self.stdout.write(f"  CELERY_TASK_ALWAYS_EAGER={eager}")
        self.stdout.write("")

        # Reuse Django's release/configuration checks, but only report Instagram.
        instagram_checks = [
            issue
            for issue in run_checks()
            if str(getattr(issue, "id", "")).startswith("instagram.")
        ]
        for issue in instagram_checks:
            error(str(issue.id), str(issue.msg))

        if not flags["INSTAGRAM_ENABLED"]:
            warning("READY.W001", "Instagram master flag is OFF.")
        if not flags["INSTAGRAM_MESSAGING_ENABLED"]:
            warning("READY.W002", "Instagram messaging flag is OFF.")
        if not flags["INSTAGRAM_SEND_ENABLED"]:
            warning("READY.W003", "Instagram outbound send flag is OFF.")
        if not flags["INSTAGRAM_AUTO_REPLY_ENABLED"]:
            warning("READY.W004", "Instagram auto-reply flag is OFF.")

        if strict:
            for flag in (
                "INSTAGRAM_ENABLED",
                "INSTAGRAM_MESSAGING_ENABLED",
                "INSTAGRAM_SEND_ENABLED",
                "INSTAGRAM_AUTO_REPLY_ENABLED",
            ):
                if not flags[flag]:
                    error("READY.E001", f"{flag} must be True in strict mode.")

        if flags["INSTAGRAM_AUTO_REPLY_ENABLED"]:
            if not flags["LOOMERA_ENABLE_CELERY"]:
                error(
                    "READY.E002",
                    "Auto Reply requires LOOMERA_ENABLE_CELERY=True.",
                )
            if eager:
                error(
                    "READY.E003",
                    "Auto Reply requires CELERY_TASK_ALWAYS_EAGER=False.",
                )
            broker = str(
                getattr(settings, "CELERY_BROKER_URL", "") or ""
            ).strip()
            if not broker:
                error(
                    "READY.E004",
                    "CELERY_BROKER_URL is empty while Auto Reply is enabled.",
                )

        if flags["INSTAGRAM_ENABLED"] and not _fernet_key_valid():
            error(
                "READY.E005",
                "INSTAGRAM_TOKEN_ENCRYPTION_KEY is not a valid Fernet key.",
            )

        scopes = set(
            str(item).strip()
            for item in getattr(settings, "INSTAGRAM_LOGIN_SCOPES", [])
            if str(item).strip()
        )
        missing_global_scopes = sorted(REQUIRED_DM_SCOPES - scopes)
        if flags["INSTAGRAM_MESSAGING_ENABLED"] and missing_global_scopes:
            error(
                "READY.E006",
                "Missing configured DM scopes: "
                + ", ".join(missing_global_scopes),
            )

        webhook_url = _webhook_url()
        self.stdout.write("Public URLs:")
        self.stdout.write(
            "  OAuth callback="
            + str(getattr(settings, "INSTAGRAM_REDIRECT_URI", "") or "")
        )
        self.stdout.write(f"  Webhook={webhook_url or '(unavailable)'}")
        self.stdout.write("")

        connected = list(
            InstagramAccountConnection.objects.select_related(
                "salon",
                "stylist",
            )
            .filter(status=InstagramConnectionStatus.CONNECTED)
            .order_by("pk")
        )

        self.stdout.write(f"Connected Instagram accounts: {len(connected)}")
        if strict and not connected:
            error(
                "READY.E007",
                "No connected Instagram Professional account exists.",
            )
        elif not connected:
            warning(
                "READY.W005",
                "No connected Instagram Professional account exists yet.",
            )

        now = timezone.now()
        for connection in connected:
            context = (
                f"stylist:{connection.stylist_id}"
                if connection.stylist_id
                else f"salon:{connection.salon_id}"
            )
            label = connection.username or connection.instagram_account_id
            self.stdout.write(
                f"  id={connection.pk} @{label} context={context}"
            )

            if not connection.is_context_active():
                error(
                    "READY.E008",
                    f"Connection {connection.pk} has an inactive Loomera context.",
                )

            missing = sorted(
                REQUIRED_DM_SCOPES - set(connection.granted_scopes or [])
            )
            if missing:
                error(
                    "READY.E009",
                    f"Connection {connection.pk} missing scopes: "
                    + ", ".join(missing),
                )

            if (
                connection.token_expires_at is not None
                and connection.token_expires_at <= now
            ):
                error(
                    "READY.E010",
                    f"Connection {connection.pk} token is expired.",
                )

            try:
                token = connection.get_access_token()
            except Exception:
                token = ""
                error(
                    "READY.E011",
                    f"Connection {connection.pk} token cannot be decrypted.",
                )

            if not token:
                error(
                    "READY.E012",
                    f"Connection {connection.pk} has no usable access token.",
                )

        if live:
            self._live_identity_check(
                connection_id=connection_id,
                error=error,
            )

        self.stdout.write("")
        self.stdout.write(f"errors={len(errors)}")
        self.stdout.write(f"warnings={len(warnings)}")

        if errors:
            self.stdout.write("")
            self.stdout.write("Errors:")
            for code, message in errors:
                self.stdout.write(f"  [{code}] {message}")

        if warnings:
            self.stdout.write("")
            self.stdout.write("Warnings:")
            for code, message in warnings:
                self.stdout.write(f"  [{code}] {message}")

        if strict and errors:
            raise CommandError(
                f"Instagram QA check failed with {len(errors)} error(s)."
            )

        if errors:
            self.stdout.write(
                self.style.WARNING("INSTAGRAM NOT READY")
            )
        elif strict:
            self.stdout.write(
                self.style.SUCCESS("INSTAGRAM READY FOR LIVE SMOKE")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Instagram check completed.")
            )

    def _live_identity_check(self, *, connection_id, error):
        try:
            connection = InstagramAccountConnection.objects.get(
                pk=connection_id
            )
        except InstagramAccountConnection.DoesNotExist:
            error(
                "LIVE.E001",
                f"Connection {connection_id} does not exist.",
            )
            return

        try:
            token = connection.get_access_token()
        except Exception:
            error(
                "LIVE.E002",
                f"Connection {connection_id} token is unavailable.",
            )
            return

        base = str(
            getattr(settings, "INSTAGRAM_GRAPH_BASE_URL", "") or ""
        ).strip().rstrip("/")
        version = str(
            getattr(settings, "INSTAGRAM_GRAPH_API_VERSION", "v24.0")
            or "v24.0"
        ).strip().strip("/")
        timeout = int(
            getattr(settings, "INSTAGRAM_REQUEST_TIMEOUT", 10)
        )

        self.stdout.write("")
        self.stdout.write(
            f"Live identity check: connection={connection_id}"
        )

        try:
            response = requests.get(
                f"{base}/{version}/me",
                params={"fields": "id,username"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
        except requests.RequestException:
            error(
                "LIVE.E003",
                "Meta identity request failed at network level.",
            )
            return

        if not response.ok:
            error(
                "LIVE.E004",
                f"Meta identity request returned HTTP {response.status_code}.",
            )
            return

        try:
            payload = response.json()
        except ValueError:
            error(
                "LIVE.E005",
                "Meta identity response was not valid JSON.",
            )
            return

        provider_id = str(payload.get("id") or "").strip()
        username = str(payload.get("username") or "").strip()

        if provider_id != connection.instagram_account_id:
            error(
                "LIVE.E006",
                "Meta account id does not match the stored connection.",
            )
            return

        self.stdout.write(
            f"  verified id={provider_id} username=@{username or '(unknown)'}"
        )
