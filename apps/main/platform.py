"""Central helpers for Loomera release flags.

The database-backed PlatformSetting model is intentionally secondary to env
settings for high-risk switches. Env/config remains the source of truth for
financial and payment capabilities; DB settings are used for operational labels
and controlled rollout values.
"""

from django.conf import settings

from .models import PlatformSetting


_FLAG_DEFAULTS = {
    "BETA_MODE": True,
    "COMMISSION_ENABLED": False,
    "ONLINE_PAYMENT_ENABLED": False,
    "DEPOSIT_ENABLED": False,
    "BNPL_ENABLED": False,
    "DEBT_ENFORCEMENT_ENABLED": False,
    "SALON_VERIFICATION_ENFORCED": False,
    "SALON_WITHDRAWAL_ENABLED": False,
    "AUTOMATIC_REFUND_ENABLED": False,
}


def get_platform_flag(flag_name: str) -> bool:
    """Return the effective boolean value for a known platform flag."""
    normalized = (flag_name or "").strip().upper()
    if normalized not in _FLAG_DEFAULTS:
        raise KeyError(f"Unknown Loomera platform flag: {flag_name}")

    env_value = bool(getattr(settings, normalized, _FLAG_DEFAULTS[normalized]))

    # Sensitive financial/payment gates remain env-first. The DB setting can only
    # turn a feature off, not force-enable it when env/config keeps it disabled.
    if normalized in {
        "COMMISSION_ENABLED",
        "ONLINE_PAYMENT_ENABLED",
        "DEPOSIT_ENABLED",
        "BNPL_ENABLED",
        "DEBT_ENFORCEMENT_ENABLED",
        "SALON_WITHDRAWAL_ENABLED",
        "AUTOMATIC_REFUND_ENABLED",
    }:
        return env_value and bool(PlatformSetting.get_value(normalized.lower(), env_value))

    return bool(PlatformSetting.get_value(normalized.lower(), env_value))


def beta_mode_enabled() -> bool:
    return get_platform_flag("BETA_MODE")
