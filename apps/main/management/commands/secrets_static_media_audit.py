from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


@dataclass(frozen=True)
class DeploymentAuditIssue:
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


SECRET_ENV_NAMES_DEFAULT = (
    "SECRET_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "CACHE_URL",
    "EMAIL_HOST_PASSWORD",
    "PAYMENT_MERCHANT_ID",
    "PAYMENT_CALLBACK_SECRET",
    "PAYMENT_PROVIDER_SECRET",
    "ZIBAL_MERCHANT",
    "ZIBAL_SECRET",
    "MAPIR_API_KEY",
    "MAP_IR_API_KEY",
    "BALE_BOT_TOKEN",
    "BALE_WEBHOOK_SECRET",
    "LIARA_ACCESS_KEY",
    "LIARA_SECRET_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_ENDPOINT_URL",
)

SENSITIVE_FILENAMES = (
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    "secrets.json",
    "credentials.json",
    "service-account.json",
    "google-credentials.json",
    "private_key.pem",
    "id_rsa",
)

UNSAFE_SECRET_FRAGMENTS = (
    "django-insecure",
    "change-me",
    "changeme",
    "dummy",
    "test",
    "local",
    "dev",
    "example",
    "password",
    "secret",
)


def _setting_int(name, default=0):
    try:
        return int(getattr(settings, name, default) or 0)
    except (TypeError, ValueError):
        return default


def _base_dir():
    return Path(getattr(settings, "BASE_DIR", Path.cwd())).resolve()


def _as_path(value):
    if not value:
        return None

    try:
        return Path(value).expanduser().resolve()
    except Exception:
        return None


def _paths_same_or_nested(parent, child):
    if parent is None or child is None:
        return False

    try:
        parent = Path(parent).resolve()
        child = Path(child).resolve()
        return parent == child or parent in child.parents
    except Exception:
        return False


def _url_text(name):
    return str(getattr(settings, name, "") or "").strip()


def _url_looks_local_or_insecure(url):
    lowered = str(url or "").strip().lower()
    return (
        lowered.startswith("http://")
        or "localhost" in lowered
        or "127.0.0.1" in lowered
        or "0.0.0.0" in lowered
    )


def _secret_value_looks_unsafe(value):
    text = str(value or "").strip()
    lowered = text.lower()

    if not text:
        return True

    if len(text) < 16:
        return True

    return any(fragment in lowered for fragment in UNSAFE_SECRET_FRAGMENTS)


def _secret_env_names():
    custom_names = getattr(settings, "DEPLOYMENT_AUDIT_SECRET_ENV_NAMES", None)
    if custom_names:
        return tuple(str(item).strip() for item in custom_names if str(item).strip())

    return SECRET_ENV_NAMES_DEFAULT


def _storage_backend(alias):
    storages = getattr(settings, "STORAGES", None) or {}

    if isinstance(storages, dict) and alias in storages:
        config = storages.get(alias) or {}
        if isinstance(config, dict):
            return str(config.get("BACKEND") or "").strip()

    if alias == "default":
        return str(getattr(settings, "DEFAULT_FILE_STORAGE", "") or "").strip()

    if alias == "staticfiles":
        return str(getattr(settings, "STATICFILES_STORAGE", "") or "").strip()

    return ""


def _is_local_filesystem_backend(backend):
    text = str(backend or "").strip()

    if not text:
        return True

    return (
        "FileSystemStorage" in text
        or text == "django.core.files.storage.FileSystemStorage"
        or text == "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


def _find_sensitive_files():
    base_dir = _base_dir()
    found = []

    for filename in SENSITIVE_FILENAMES:
        candidate = base_dir / filename
        if candidate.exists():
            found.append(filename)

    return found


def run_secrets_static_media_audit(
    *,
    strict=False,
    require_remote_media_storage=False,
):
    issues: list[DeploymentAuditIssue] = []

    # Secret env audit: فقط نام کلید را گزارش می‌کنیم، نه مقدار را.
    for env_name in _secret_env_names():
        if env_name not in os.environ:
            continue

        if _secret_value_looks_unsafe(os.environ.get(env_name)):
            issues.append(
                DeploymentAuditIssue(
                    code="DEPLOYMENT_SECRET_ENV_VALUE_UNSAFE",
                    severity="error" if strict else "warning",
                    message=f"مقدار env حساس {env_name} خالی، کوتاه، یا شبیه مقدار توسعه است.",
                    hint="مقدار secret را در خروجی چاپ نکن؛ فقط در محیط deploy با مقدار امن جایگزین کن.",
                )
            )

    sensitive_files = _find_sensitive_files()
    for filename in sensitive_files:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_SENSITIVE_FILE_PRESENT",
                severity="warning",
                message=f"فایل حساس {filename} در BASE_DIR پیدا شد.",
                hint="مطمئن شو این فایل داخل artifact deploy یا repository عمومی قرار نمی‌گیرد.",
            )
        )

    static_url = _url_text("STATIC_URL")
    media_url = _url_text("MEDIA_URL")

    if not static_url:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_STATIC_URL_EMPTY",
                severity="warning",
                message="STATIC_URL خالی است.",
                hint="قبل از deploy مسیر static را مشخص کن.",
            )
        )

    if not media_url:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_MEDIA_URL_EMPTY",
                severity="warning",
                message="MEDIA_URL خالی است.",
                hint="قبل از deploy مسیر media/storage را مشخص کن.",
            )
        )

    if static_url and media_url and static_url == media_url:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_STATIC_MEDIA_URL_COLLISION",
                severity="error" if strict else "warning",
                message="STATIC_URL و MEDIA_URL یکسان هستند.",
                hint="مسیر static و media باید جدا باشند.",
            )
        )

    if media_url and _url_looks_local_or_insecure(media_url):
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_MEDIA_URL_LOCAL_OR_INSECURE",
                severity="error" if strict else "warning",
                message="MEDIA_URL لوکال یا http است.",
                hint="در Production از مسیر امن https یا storage/CDN معتبر استفاده کن.",
            )
        )

    if static_url and static_url.startswith("http://"):
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_STATIC_URL_INSECURE_HTTP",
                severity="warning",
                message="STATIC_URL با http شروع شده است.",
                hint="برای production بهتر است static از https سرو شود.",
            )
        )

    static_root = _as_path(getattr(settings, "STATIC_ROOT", None))
    media_root = _as_path(getattr(settings, "MEDIA_ROOT", None))

    if static_root is None:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_STATIC_ROOT_EMPTY",
                severity="warning",
                message="STATIC_ROOT تنظیم نشده است.",
                hint="برای collectstatic در deploy مقدار STATIC_ROOT را تنظیم کن.",
            )
        )

    if media_root is None:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_MEDIA_ROOT_EMPTY",
                severity="warning",
                message="MEDIA_ROOT تنظیم نشده است.",
                hint="اگر media روی local filesystem ذخیره می‌شود، MEDIA_ROOT باید مشخص باشد.",
            )
        )

    if static_root and media_root:
        if static_root == media_root:
            issues.append(
                DeploymentAuditIssue(
                    code="DEPLOYMENT_STATIC_MEDIA_ROOT_COLLISION",
                    severity="error" if strict else "warning",
                    message="STATIC_ROOT و MEDIA_ROOT یکسان هستند.",
                    hint="فایل‌های user-uploaded نباید کنار static جمع‌آوری‌شده قرار بگیرند.",
                )
            )
        elif _paths_same_or_nested(static_root, media_root):
            issues.append(
                DeploymentAuditIssue(
                    code="DEPLOYMENT_MEDIA_ROOT_INSIDE_STATIC_ROOT",
                    severity="error" if strict else "warning",
                    message="MEDIA_ROOT داخل STATIC_ROOT قرار دارد.",
                    hint="media کاربران را از static جدا کن تا فایل‌های upload شده با collectstatic قاطی نشوند.",
                )
            )
        elif _paths_same_or_nested(media_root, static_root):
            issues.append(
                DeploymentAuditIssue(
                    code="DEPLOYMENT_STATIC_ROOT_INSIDE_MEDIA_ROOT",
                    severity="warning",
                    message="STATIC_ROOT داخل MEDIA_ROOT قرار دارد.",
                    hint="مسیر static و media را جدا نگه دار.",
                )
            )

    default_storage_backend = _storage_backend("default")
    static_storage_backend = _storage_backend("staticfiles")

    if require_remote_media_storage and _is_local_filesystem_backend(
        default_storage_backend
    ):
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_MEDIA_STORAGE_LOCAL_FILESYSTEM",
                severity="error" if strict else "warning",
                message="default media storage روی local filesystem است.",
                hint="برای Production/Liara اگر storage پایدار جدا می‌خواهی، remote/object storage را تنظیم کن.",
            )
        )

    if not static_storage_backend:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_STATIC_STORAGE_BACKEND_UNSPECIFIED",
                severity="warning",
                message="staticfiles storage backend صریحاً مشخص نشده است.",
                hint="اگر Whitenoise/CDN استفاده می‌کنی، backend مناسب را بررسی کن.",
            )
        )

    data_upload_limit = _setting_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 0)
    file_upload_limit = _setting_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 0)

    if data_upload_limit <= 0:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_DATA_UPLOAD_LIMIT_UNSET",
                severity="warning",
                message="DATA_UPLOAD_MAX_MEMORY_SIZE تنظیم نشده یا نامعتبر است.",
                hint="برای محدودسازی request body مقدار منطقی تنظیم کن.",
            )
        )
    elif data_upload_limit > 10 * 1024 * 1024:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_DATA_UPLOAD_LIMIT_HIGH",
                severity="warning",
                message="DATA_UPLOAD_MAX_MEMORY_SIZE خیلی بزرگ است.",
                hint="برای کاهش ریسک payload بزرگ، مقدار را محدود نگه دار.",
            )
        )

    if file_upload_limit <= 0:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_FILE_UPLOAD_LIMIT_UNSET",
                severity="warning",
                message="FILE_UPLOAD_MAX_MEMORY_SIZE تنظیم نشده یا نامعتبر است.",
                hint="برای کنترل memory مصرفی upload مقدار منطقی تنظیم کن.",
            )
        )
    elif file_upload_limit > 10 * 1024 * 1024:
        issues.append(
            DeploymentAuditIssue(
                code="DEPLOYMENT_FILE_UPLOAD_LIMIT_HIGH",
                severity="warning",
                message="FILE_UPLOAD_MAX_MEMORY_SIZE خیلی بزرگ است.",
                hint="برای uploadهای بزرگ از temporary file/storage استفاده کن.",
            )
        )

    return issues


class Command(BaseCommand):
    help = "Audit secrets, static and media deployment settings without printing secret values."

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
        parser.add_argument(
            "--require-remote-media-storage",
            action="store_true",
            help="Treat local filesystem media storage as an error in strict mode.",
        )

    def handle(self, *args, **options):
        strict = bool(options["strict"])
        as_json = bool(options["json"])
        require_remote_media_storage = bool(options["require_remote_media_storage"])

        issues = run_secrets_static_media_audit(
            strict=strict,
            require_remote_media_storage=require_remote_media_storage,
        )

        payload = {
            "ok": not any(issue.severity == "error" for issue in issues),
            "strict": strict,
            "require_remote_media_storage": require_remote_media_storage,
            "issues_count": len(issues),
            "errors_count": sum(1 for issue in issues if issue.severity == "error"),
            "warnings_count": sum(1 for issue in issues if issue.severity == "warning"),
            "issues": [issue.as_dict() for issue in issues],
        }

        if as_json:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            self.stdout.write("=== Secrets / Static / Media Deployment Audit ===")
            self.stdout.write(f"strict={strict}")
            self.stdout.write(
                f"require_remote_media_storage={require_remote_media_storage}"
            )
            self.stdout.write(f"issues={payload['issues_count']}")
            self.stdout.write(f"errors={payload['errors_count']}")
            self.stdout.write(f"warnings={payload['warnings_count']}")
            self.stdout.write("")

            if not issues:
                self.stdout.write(
                    self.style.SUCCESS(
                        "No secrets/static/media deployment issues found."
                    )
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
                f"Secrets/static/media deployment audit failed with {payload['errors_count']} error(s)."
            )
