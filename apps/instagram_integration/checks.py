from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, register


CURRENT_BASIC_SCOPE = "instagram_business_basic"
CURRENT_MESSAGING_SCOPE = "instagram_business_manage_messages"
DEPRECATED_SCOPES = {
    "business_basic",
    "business_content_publish",
    "business_manage_messages",
    "business_manage_comments",
}


def _error(message, hint, error_id):
    return Error(message, hint=hint, id=error_id)


def _is_safe_redirect_uri(uri):
    if not uri:
        return False
    parsed = urlparse(uri)
    if parsed.scheme == "https" and bool(parsed.netloc):
        return True
    return bool(
        getattr(settings, "DEBUG", False)
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    )


def check_instagram_configuration():
    errors = []
    enabled = bool(getattr(settings, "INSTAGRAM_ENABLED", False))
    messaging_enabled = bool(
        getattr(settings, "INSTAGRAM_MESSAGING_ENABLED", False)
    )

    if messaging_enabled and not enabled:
        errors.append(
            _error(
                "Instagram messaging cannot be enabled while Instagram is disabled.",
                "Set INSTAGRAM_ENABLED=True first, or keep "
                "INSTAGRAM_MESSAGING_ENABLED=False.",
                "instagram.E001",
            )
        )

    send_enabled = bool(getattr(settings, "INSTAGRAM_SEND_ENABLED", False))
    auto_reply_enabled = bool(
        getattr(settings, "INSTAGRAM_AUTO_REPLY_ENABLED", False)
    )

    if send_enabled and not messaging_enabled:
        errors.append(
            _error(
                "Instagram sending cannot be enabled while messaging is disabled.",
                "Enable INSTAGRAM_MESSAGING_ENABLED first.",
                "instagram.E010",
            )
        )

    if auto_reply_enabled and not send_enabled:
        errors.append(
            _error(
                "Instagram auto reply requires outbound sending.",
                "Enable INSTAGRAM_SEND_ENABLED first.",
                "instagram.E011",
            )
        )

    if auto_reply_enabled and (
        not bool(getattr(settings, "LOOMERA_ENABLE_CELERY", False))
        or bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
    ):
        errors.append(
            _error(
                "Instagram auto reply requires an asynchronous Celery worker.",
                "Enable Celery worker mode before Auto Reply.",
                "instagram.E012",
            )
        )

    # Default OFF must be startup-safe and require no Instagram secrets.
    if not enabled:
        return errors

    required = {
        "INSTAGRAM_APP_ID": getattr(settings, "INSTAGRAM_APP_ID", ""),
        "INSTAGRAM_APP_SECRET": getattr(settings, "INSTAGRAM_APP_SECRET", ""),
        "INSTAGRAM_REDIRECT_URI": getattr(settings, "INSTAGRAM_REDIRECT_URI", ""),
        "INSTAGRAM_TOKEN_ENCRYPTION_KEY": getattr(
            settings, "INSTAGRAM_TOKEN_ENCRYPTION_KEY", ""
        ),
    }
    if messaging_enabled:
        required["INSTAGRAM_WEBHOOK_VERIFY_TOKEN"] = getattr(
            settings, "INSTAGRAM_WEBHOOK_VERIFY_TOKEN", ""
        )

    for setting_name, value in required.items():
        if not str(value or "").strip():
            errors.append(
                _error(
                    f"{setting_name} is required when Instagram is enabled.",
                    f"Configure {setting_name} in the runtime environment; "
                    "never commit its value to the repository.",
                    "instagram.E002",
                )
            )

    redirect_uri = getattr(settings, "INSTAGRAM_REDIRECT_URI", "")
    if redirect_uri and not _is_safe_redirect_uri(redirect_uri):
        errors.append(
            _error(
                "Instagram OAuth redirect URI must use HTTPS.",
                "Use the exact HTTPS callback registered in Meta. HTTP is accepted "
                "only for localhost/127.0.0.1 while DEBUG=True.",
                "instagram.E003",
            )
        )

    scopes = {
        str(scope).strip()
        for scope in getattr(settings, "INSTAGRAM_LOGIN_SCOPES", [])
        if str(scope).strip()
    }
    deprecated = sorted(scopes.intersection(DEPRECATED_SCOPES))
    if deprecated:
        errors.append(
            _error(
                "Deprecated Instagram permission names are configured.",
                "Remove deprecated scopes: " + ", ".join(deprecated),
                "instagram.E004",
            )
        )

    if CURRENT_BASIC_SCOPE not in scopes:
        errors.append(
            _error(
                f"{CURRENT_BASIC_SCOPE} is required for Instagram Login.",
                "Add the current official basic Instagram business scope.",
                "instagram.E005",
            )
        )

    if messaging_enabled and CURRENT_MESSAGING_SCOPE not in scopes:
        errors.append(
            _error(
                f"{CURRENT_MESSAGING_SCOPE} is required for Instagram DM replies.",
                "Add the current official Instagram messaging scope.",
                "instagram.E006",
            )
        )

    timeout = getattr(settings, "INSTAGRAM_REQUEST_TIMEOUT", 0)
    if not isinstance(timeout, int) or timeout <= 0 or timeout > 60:
        errors.append(
            _error(
                "INSTAGRAM_REQUEST_TIMEOUT must be between 1 and 60 seconds.",
                "Use a short bounded timeout so Meta failures cannot block Loomera.",
                "instagram.E007",
            )
        )

    max_bytes = getattr(settings, "INSTAGRAM_WEBHOOK_MAX_BYTES", 0)
    if not isinstance(max_bytes, int) or max_bytes < 1024 or max_bytes > 1024 * 1024:
        errors.append(
            _error(
                "INSTAGRAM_WEBHOOK_MAX_BYTES must be between 1 KiB and 1 MiB.",
                "Keep webhook payload size bounded.",
                "instagram.E008",
            )
        )

    state_ttl = getattr(settings, "INSTAGRAM_OAUTH_STATE_TTL_SECONDS", 0)
    if not isinstance(state_ttl, int) or state_ttl < 60 or state_ttl > 1800:
        errors.append(
            _error(
                "INSTAGRAM_OAUTH_STATE_TTL_SECONDS must be between 60 and 1800.",
                "Keep OAuth state short-lived; 600 seconds is the default.",
                "instagram.E009",
            )
        )

    return errors


@register(Tags.security)
def instagram_configuration_check(app_configs, **kwargs):
    return check_instagram_configuration()
