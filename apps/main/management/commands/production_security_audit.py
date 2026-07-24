from __future__ import annotations

import json
from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


@dataclass(frozen=True)
class AuditIssue:
    code: str
    severity: str
    message: str
    hint: str = ""

    def as_dict(self):
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
        }


SEVERITY_ORDER = {
    "info": 0,
    "warning": 1,
    "error": 2,
}


def _as_list(value):
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]

    return [str(value).strip()]


def _is_blank_or_wildcard(values):
    cleaned = _as_list(values)
    return not cleaned or "*" in cleaned or "0.0.0.0" in cleaned


def _secret_key_looks_unsafe(secret_key):
    value = str(secret_key or "")
    lowered = value.lower()

    unsafe_fragments = {
        "django-insecure",
        "change-me",
        "changeme",
        "secret",
        "dev",
        "local",
        "test",
        "dummy",
    }

    return len(value) < 32 or any(fragment in lowered for fragment in unsafe_fragments)


def _has_https_origin(values):
    return any(str(item).strip().startswith("https://") for item in _as_list(values))


def _setting_bool(name, default=False):
    return bool(getattr(settings, name, default))


def _setting_int(name, default=0):
    try:
        return int(getattr(settings, name, default) or 0)
    except (TypeError, ValueError):
        return default


def run_production_security_audit(*, strict=False):
    issues: list[AuditIssue] = []

    debug = _setting_bool("DEBUG", False)
    if debug:
        issues.append(
            AuditIssue(
                code="SECURITY_DEBUG_ENABLED",
                severity="error" if strict else "warning",
                message="DEBUG فعال است.",
                hint="برای Staging/Production مقدار DEBUG باید False باشد.",
            )
        )

    if _is_blank_or_wildcard(getattr(settings, "ALLOWED_HOSTS", [])):
        issues.append(
            AuditIssue(
                code="SECURITY_ALLOWED_HOSTS_UNSAFE",
                severity="error" if strict else "warning",
                message="ALLOWED_HOSTS خالی یا wildcard است.",
                hint="دامنه‌های دقیق production/staging را تنظیم کن.",
            )
        )

    if _secret_key_looks_unsafe(getattr(settings, "SECRET_KEY", "")):
        issues.append(
            AuditIssue(
                code="SECURITY_SECRET_KEY_UNSAFE",
                severity="error" if strict else "warning",
                message="SECRET_KEY ناامن، کوتاه، یا شبیه مقدار توسعه است.",
                hint="یک مقدار قوی و اختصاصی از env استفاده کن. مقدار واقعی را لاگ نکن.",
            )
        )

    csrf_origins = _as_list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
    if not csrf_origins:
        issues.append(
            AuditIssue(
                code="SECURITY_CSRF_TRUSTED_ORIGINS_EMPTY",
                severity="warning",
                message="CSRF_TRUSTED_ORIGINS خالی است.",
                hint="برای دامنه اصلی و www/staging مقدار https تنظیم کن.",
            )
        )
    elif not _has_https_origin(csrf_origins):
        issues.append(
            AuditIssue(
                code="SECURITY_CSRF_TRUSTED_ORIGINS_NO_HTTPS",
                severity="warning",
                message="CSRF_TRUSTED_ORIGINS مقدار https ندارد.",
                hint="originها باید با https:// ثبت شوند.",
            )
        )

    if not _setting_bool("SESSION_COOKIE_SECURE", False):
        issues.append(
            AuditIssue(
                code="SECURITY_SESSION_COOKIE_NOT_SECURE",
                severity="error" if strict else "warning",
                message="SESSION_COOKIE_SECURE فعال نیست.",
                hint="برای HTTPS production باید True باشد.",
            )
        )

    if not _setting_bool("CSRF_COOKIE_SECURE", False):
        issues.append(
            AuditIssue(
                code="SECURITY_CSRF_COOKIE_NOT_SECURE",
                severity="error" if strict else "warning",
                message="CSRF_COOKIE_SECURE فعال نیست.",
                hint="برای HTTPS production باید True باشد.",
            )
        )

    if not _setting_bool("SECURE_SSL_REDIRECT", False):
        issues.append(
            AuditIssue(
                code="SECURITY_SSL_REDIRECT_DISABLED",
                severity="warning",
                message="SECURE_SSL_REDIRECT فعال نیست.",
                hint="اگر reverse proxy درست تنظیم شده، برای production باید True باشد.",
            )
        )

    if not getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        issues.append(
            AuditIssue(
                code="SECURITY_PROXY_SSL_HEADER_MISSING",
                severity="warning",
                message="SECURE_PROXY_SSL_HEADER تنظیم نشده است.",
                hint="روی Liara/Proxy بررسی کن که header صحیح HTTPS تنظیم باشد.",
            )
        )

    hsts_seconds = _setting_int("SECURE_HSTS_SECONDS", 0)
    if hsts_seconds < 3600:
        issues.append(
            AuditIssue(
                code="SECURITY_HSTS_TOO_LOW",
                severity="warning",
                message="SECURE_HSTS_SECONDS کم یا صفر است.",
                hint="بعد از اطمینان از HTTPS پایدار، HSTS را تدریجی افزایش بده.",
            )
        )

    if getattr(settings, "X_FRAME_OPTIONS", "").upper() not in {"DENY", "SAMEORIGIN"}:
        issues.append(
            AuditIssue(
                code="SECURITY_X_FRAME_OPTIONS_UNSAFE",
                severity="warning",
                message="X_FRAME_OPTIONS مقدار امن ندارد.",
                hint="معمولاً DENY یا SAMEORIGIN مناسب است.",
            )
        )

    if not _setting_bool("SECURE_CONTENT_TYPE_NOSNIFF", False):
        issues.append(
            AuditIssue(
                code="SECURITY_CONTENT_TYPE_NOSNIFF_DISABLED",
                severity="warning",
                message="SECURE_CONTENT_TYPE_NOSNIFF فعال نیست.",
                hint="برای جلوگیری از MIME sniffing فعال شود.",
            )
        )

    session_samesite = str(
        getattr(settings, "SESSION_COOKIE_SAMESITE", "") or ""
    ).lower()
    if session_samesite not in {"lax", "strict"}:
        issues.append(
            AuditIssue(
                code="SECURITY_SESSION_SAMESITE_UNSAFE",
                severity="warning",
                message="SESSION_COOKIE_SAMESITE مقدار امن ندارد.",
                hint="برای Loomera معمولاً Lax مناسب است.",
            )
        )

    csrf_samesite = str(getattr(settings, "CSRF_COOKIE_SAMESITE", "") or "").lower()
    if csrf_samesite not in {"lax", "strict"}:
        issues.append(
            AuditIssue(
                code="SECURITY_CSRF_SAMESITE_UNSAFE",
                severity="warning",
                message="CSRF_COOKIE_SAMESITE مقدار امن ندارد.",
                hint="برای Loomera معمولاً Lax مناسب است.",
            )
        )

    static_url = str(getattr(settings, "STATIC_URL", "") or "")
    media_url = str(getattr(settings, "MEDIA_URL", "") or "")

    if not static_url:
        issues.append(
            AuditIssue(
                code="SECURITY_STATIC_URL_EMPTY",
                severity="warning",
                message="STATIC_URL خالی است.",
                hint="تنظیمات static را قبل از deploy بررسی کن.",
            )
        )

    if not media_url:
        issues.append(
            AuditIssue(
                code="SECURITY_MEDIA_URL_EMPTY",
                severity="warning",
                message="MEDIA_URL خالی است.",
                hint="تنظیمات media/storage را قبل از deploy بررسی کن.",
            )
        )

    if str(media_url).startswith("http://"):
        issues.append(
            AuditIssue(
                code="SECURITY_MEDIA_URL_INSECURE_HTTP",
                severity="warning",
                message="MEDIA_URL با http تنظیم شده است.",
                hint="برای production از https استفاده کن.",
            )
        )

    return issues


class Command(BaseCommand):
    help = "Audit production/staging security-sensitive Django settings without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail with non-zero exit code when error-level issues are found.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output.",
        )

    def handle(self, *args, **options):
        strict = bool(options["strict"])
        as_json = bool(options["json"])

        issues = run_production_security_audit(strict=strict)
        payload = {
            "ok": not any(issue.severity == "error" for issue in issues),
            "strict": strict,
            "issues_count": len(issues),
            "errors_count": sum(1 for issue in issues if issue.severity == "error"),
            "warnings_count": sum(1 for issue in issues if issue.severity == "warning"),
            "issues": [issue.as_dict() for issue in issues],
        }

        if as_json:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            self.stdout.write("=== Production Security Audit ===")
            self.stdout.write(f"strict={strict}")
            self.stdout.write(f"issues={payload['issues_count']}")
            self.stdout.write(f"errors={payload['errors_count']}")
            self.stdout.write(f"warnings={payload['warnings_count']}")
            self.stdout.write("")

            if not issues:
                self.stdout.write(
                    self.style.SUCCESS("No security setting issues found.")
                )
            else:
                for issue in issues:
                    style = (
                        self.style.ERROR
                        if issue.severity == "error"
                        else self.style.WARNING
                    )
                    self.stdout.write(
                        style(f"[{issue.severity}] {issue.code}: {issue.message}")
                    )
                    if issue.hint:
                        self.stdout.write(f"  hint: {issue.hint}")

        if strict and payload["errors_count"]:
            raise CommandError(
                f"Production security audit failed with {payload['errors_count']} error(s)."
            )
