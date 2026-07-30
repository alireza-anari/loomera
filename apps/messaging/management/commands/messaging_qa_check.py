from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse

from apps.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
)

from ...constants import (
    MessagingActionStatus,
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
    MessagingWebhookEventStatus,
)
from ...models import (
    MessagingActionExecution,
    MessagingMessageLog,
    MessagingProvider,
    MessagingWebhookEvent,
)
from ...notification_delivery import bale_outbound_queue_ready
from ...services import ensure_default_providers, provider_allowed


@dataclass(frozen=True)
class MessagingQAIssue:
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


def _as_list(value):
    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]

    return [str(value).strip()]


def _setting_bool(name: str, default=False) -> bool:
    return bool(getattr(settings, name, default))


def _setting_int(name: str, default=0) -> int:
    try:
        return int(getattr(settings, name, default) or 0)
    except (TypeError, ValueError):
        return default


def _setting_str(name: str, default="") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _public_base_url() -> str:
    return _setting_str("MESSAGING_PUBLIC_BASE_URL").rstrip("/")


def _url_is_public_http_url(value: str) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _url_is_https(value: str) -> bool:
    return urlparse(str(value or "")).scheme == "https"


def _add_issue(
    issues: list[MessagingQAIssue],
    *,
    code: str,
    severity: str,
    message: str,
    hint: str = "",
):
    issues.append(
        MessagingQAIssue(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
        )
    )


def _webhook_reverse_info():
    try:
        path = reverse("bale_bot:webhook")
    except NoReverseMatch as exc:
        return {
            "reverse_ok": False,
            "path": "",
            "error": str(exc),
        }

    base_url = _public_base_url()
    absolute_url = f"{base_url}{path}" if base_url else ""

    return {
        "reverse_ok": True,
        "path": path,
        "absolute_url": absolute_url,
        "error": "",
    }


def _provider_snapshot(provider: MessagingProvider | None):
    if provider is None:
        return {
            "exists": False,
            "is_active": False,
            "supports_webhook": False,
            "supports_callback": False,
            "supports_outbound": False,
        }

    return {
        "exists": True,
        "is_active": bool(provider.is_active),
        "supports_webhook": bool(provider.supports_webhook),
        "supports_callback": bool(provider.supports_callback),
        "supports_outbound": bool(provider.supports_outbound),
    }


def _bale_queue_snapshot():
    return {
        "queued": NotificationDelivery.objects.filter(
            channel=NotificationChannel.BALE,
            status=NotificationDeliveryStatus.QUEUED,
        ).count(),
        "failed": NotificationDelivery.objects.filter(
            channel=NotificationChannel.BALE,
            status=NotificationDeliveryStatus.FAILED,
        ).count(),
        "pending_setup": NotificationDelivery.objects.filter(
            channel=NotificationChannel.BALE,
            status=NotificationDeliveryStatus.PENDING_SETUP,
        ).count(),
    }


def _bale_webhook_snapshot(provider: MessagingProvider | None):
    queryset = MessagingWebhookEvent.objects.none()
    if provider is not None:
        queryset = MessagingWebhookEvent.objects.filter(provider=provider)

    return {
        "received": queryset.filter(
            status=MessagingWebhookEventStatus.RECEIVED
        ).count(),
        "failed": queryset.filter(status=MessagingWebhookEventStatus.FAILED).count(),
        "processed": queryset.filter(
            status=MessagingWebhookEventStatus.PROCESSED
        ).count(),
        "ignored": queryset.filter(status=MessagingWebhookEventStatus.IGNORED).count(),
        "duplicate": queryset.filter(
            status=MessagingWebhookEventStatus.DUPLICATE
        ).count(),
    }


def _bale_message_log_snapshot(provider: MessagingProvider | None):
    queryset = MessagingMessageLog.objects.none()
    if provider is not None:
        queryset = MessagingMessageLog.objects.filter(provider=provider)

    return {
        "outbound_queued": queryset.filter(
            direction=MessagingMessageDirection.OUTBOUND,
            status=MessagingMessageStatus.QUEUED,
        ).count(),
        "outbound_sent": queryset.filter(
            direction=MessagingMessageDirection.OUTBOUND,
            status=MessagingMessageStatus.SENT,
        ).count(),
        "outbound_failed": queryset.filter(
            direction=MessagingMessageDirection.OUTBOUND,
            status=MessagingMessageStatus.FAILED,
        ).count(),
        "inbound_received": queryset.filter(
            direction=MessagingMessageDirection.INBOUND,
            status=MessagingMessageStatus.RECEIVED,
        ).count(),
    }


def _messaging_action_snapshot(provider: MessagingProvider | None):
    queryset = MessagingActionExecution.objects.none()
    if provider is not None:
        queryset = MessagingActionExecution.objects.filter(provider=provider)

    return {
        "started": queryset.filter(status=MessagingActionStatus.STARTED).count(),
        "succeeded": queryset.filter(status=MessagingActionStatus.SUCCEEDED).count(),
        "failed": queryset.filter(status=MessagingActionStatus.FAILED).count(),
        "denied": queryset.filter(status=MessagingActionStatus.DENIED).count(),
        "expired": queryset.filter(status=MessagingActionStatus.EXPIRED).count(),
        "already_used": queryset.filter(
            status=MessagingActionStatus.ALREADY_USED
        ).count(),
    }


def run_messaging_qa_check(*, strict=False):
    issues: list[MessagingQAIssue] = []

    ensure_default_providers()

    messaging_enabled = _setting_bool("MESSAGING_ENABLED")
    outbound_enabled = _setting_bool("MESSAGING_OUTBOUND_ENABLED")
    actions_enabled = _setting_bool("MESSAGING_ACTIONS_ENABLED")
    bale_enabled = _setting_bool("BALE_BOT_ENABLED")
    token_configured = bool(_setting_str("BALE_BOT_TOKEN"))
    webhook_secret_configured = bool(_setting_str("BALE_WEBHOOK_SECRET"))
    webhook_require_secret = _setting_bool("BALE_WEBHOOK_REQUIRE_SECRET", True)
    webhook_allow_query_secret = _setting_bool("BALE_WEBHOOK_ALLOW_QUERY_SECRET", False)
    allowed_providers = _as_list(getattr(settings, "MESSAGING_ALLOWED_PROVIDERS", []))
    public_base_url = _public_base_url()

    bale_provider = MessagingProvider.objects.filter(
        key=MessagingProviderKey.BALE
    ).first()
    bale_provider_snapshot = _provider_snapshot(bale_provider)
    bale_allowed = provider_allowed(MessagingProviderKey.BALE)
    queue_ready = bale_outbound_queue_ready()
    webhook = _webhook_reverse_info()

    if outbound_enabled and not messaging_enabled:
        _add_issue(
            issues,
            code="MESSAGING_OUTBOUND_WITH_MESSAGING_DISABLED",
            severity="warning",
            message="MESSAGING_OUTBOUND_ENABLED روشن است اما MESSAGING_ENABLED خاموش است.",
            hint="یا messaging را روشن کن یا outbound را خاموش نگه دار.",
        )

    if bale_enabled and not messaging_enabled:
        _add_issue(
            issues,
            code="BALE_ENABLED_WITH_MESSAGING_DISABLED",
            severity="warning",
            message="BALE_BOT_ENABLED روشن است اما MESSAGING_ENABLED خاموش است.",
            hint="برای تست واقعی بله، هر دو flag باید هماهنگ باشند.",
        )

    if bale_enabled and MessagingProviderKey.BALE not in allowed_providers:
        _add_issue(
            issues,
            code="BALE_PROVIDER_NOT_ALLOWED",
            severity="warning",
            message="BALE_BOT_ENABLED روشن است اما bale در MESSAGING_ALLOWED_PROVIDERS نیست.",
            hint="برای فعال‌سازی بله مقدار bale را در providerهای مجاز قرار بده.",
        )

    if outbound_enabled and not token_configured:
        _add_issue(
            issues,
            code="BALE_TOKEN_MISSING_FOR_OUTBOUND",
            severity="error" if strict else "warning",
            message="ارسال خروجی روشن است اما BALE_BOT_TOKEN تنظیم نشده است.",
            hint="مقدار واقعی token فقط در env تنظیم شود و در خروجی یا commit نیاید.",
        )

    if bale_enabled and webhook_require_secret and not webhook_secret_configured:
        _add_issue(
            issues,
            code="BALE_WEBHOOK_SECRET_MISSING",
            severity="error" if strict else "warning",
            message="BALE_BOT_ENABLED روشن است اما BALE_WEBHOOK_SECRET تنظیم نشده است.",
            hint="یک secret قوی در env تنظیم کن؛ مقدار واقعی چاپ یا commit نشود.",
        )

    if bale_enabled and not webhook_require_secret:
        _add_issue(
            issues,
            code="BALE_WEBHOOK_SECRET_NOT_REQUIRED",
            severity="warning",
            message="BALE_WEBHOOK_REQUIRE_SECRET خاموش است.",
            hint="برای staging/production باید secret اجباری باشد.",
        )

    environment = str(
        getattr(
            settings,
            "LOOMERA_ENVIRONMENT",
            "local",
        )
        or "local"
    ).lower()

    if webhook_allow_query_secret:
        if environment == "production":
            _add_issue(
                issues,
                code="BALE_WEBHOOK_QUERY_SECRET_ENABLED",
                severity="error" if strict else "warning",
                message=("BALE_WEBHOOK_ALLOW_QUERY_SECRET " "در production روشن است."),
                hint=("در production فقط احراز هویت " "مبتنی بر header مجاز است."),
            )
        elif environment != "staging":
            _add_issue(
                issues,
                code="BALE_WEBHOOK_QUERY_SECRET_ENABLED",
                severity="warning",
                message=("BALE_WEBHOOK_ALLOW_QUERY_SECRET " "در محیط local روشن است."),
                hint=("این حالت فقط برای fallback " "کنترل‌شده استفاده شود."),
            )

    if bale_enabled and not webhook["reverse_ok"]:
        _add_issue(
            issues,
            code="BALE_WEBHOOK_REVERSE_FAILED",
            severity="error" if strict else "warning",
            message="مسیر webhook بله reverse نمی‌شود.",
            hint="namespace/path مربوط به bale_bot:webhook را بررسی کن.",
        )

    if (bale_enabled or outbound_enabled or actions_enabled) and not public_base_url:
        _add_issue(
            issues,
            code="MESSAGING_PUBLIC_BASE_URL_MISSING",
            severity="warning",
            message="MESSAGING_PUBLIC_BASE_URL تنظیم نشده است.",
            hint="برای لینک‌های ربات و webhook در staging/production مقدار https عمومی لازم است.",
        )

    if public_base_url and not _url_is_public_http_url(public_base_url):
        _add_issue(
            issues,
            code="MESSAGING_PUBLIC_BASE_URL_INVALID",
            severity="warning",
            message="MESSAGING_PUBLIC_BASE_URL فرمت URL عمومی معتبر ندارد.",
            hint="مثلاً https://staging.example.com",
        )

    if (
        public_base_url
        and not _url_is_https(public_base_url)
        and not _setting_bool("DEBUG")
    ):
        _add_issue(
            issues,
            code="MESSAGING_PUBLIC_BASE_URL_NOT_HTTPS",
            severity="warning",
            message="MESSAGING_PUBLIC_BASE_URL با https شروع نمی‌شود.",
            hint="برای staging/production باید HTTPS باشد.",
        )

    if bale_provider is None:
        _add_issue(
            issues,
            code="BALE_PROVIDER_MISSING",
            severity="error" if strict else "warning",
            message="provider بله در دیتابیس وجود ندارد.",
            hint="ensure_default_providers باید providerهای پیش‌فرض را بسازد.",
        )
    else:
        if bale_enabled and not bale_provider.is_active:
            _add_issue(
                issues,
                code="BALE_PROVIDER_INACTIVE",
                severity="warning",
                message="BALE_BOT_ENABLED روشن است اما provider بله در دیتابیس inactive است.",
                hint="provider بله باید active و مجاز باشد.",
            )

        if outbound_enabled and not bale_provider.supports_outbound:
            _add_issue(
                issues,
                code="BALE_PROVIDER_OUTBOUND_UNSUPPORTED",
                severity="error" if strict else "warning",
                message="ارسال خروجی روشن است اما provider بله supports_outbound ندارد.",
                hint="supports_outbound را برای provider بله بررسی کن.",
            )

        if bale_enabled and not bale_provider.supports_webhook:
            _add_issue(
                issues,
                code="BALE_PROVIDER_WEBHOOK_UNSUPPORTED",
                severity="warning",
                message="BALE_BOT_ENABLED روشن است اما provider بله supports_webhook ندارد.",
                hint="supports_webhook باید برای بله فعال باشد.",
            )

    max_bytes = _setting_int("BALE_WEBHOOK_MAX_BYTES", 0)
    if max_bytes <= 0 or max_bytes > 1024 * 1024:
        _add_issue(
            issues,
            code="BALE_WEBHOOK_MAX_BYTES_UNSAFE",
            severity="warning",
            message="BALE_WEBHOOK_MAX_BYTES مقدار امن ندارد.",
            hint="مقدار مثبت و ترجیحاً کمتر یا مساوی ۱MB تنظیم کن.",
        )

    request_timeout = _setting_int("BALE_BOT_REQUEST_TIMEOUT", 0)
    if request_timeout <= 0 or request_timeout > 30:
        _add_issue(
            issues,
            code="BALE_BOT_REQUEST_TIMEOUT_UNSAFE",
            severity="warning",
            message="BALE_BOT_REQUEST_TIMEOUT مقدار مناسب ندارد.",
            hint="برای staging/production معمولاً بازه ۵ تا ۱۵ ثانیه مناسب است.",
        )

    action_ttl = _setting_int("MESSAGING_ACTION_TOKEN_TTL_MINUTES", 0)
    connect_ttl = _setting_int("MESSAGING_CONNECT_TOKEN_TTL_MINUTES", 0)
    if action_ttl <= 0:
        _add_issue(
            issues,
            code="MESSAGING_ACTION_TOKEN_TTL_INVALID",
            severity="warning",
            message="MESSAGING_ACTION_TOKEN_TTL_MINUTES باید مثبت باشد.",
        )
    if connect_ttl <= 0:
        _add_issue(
            issues,
            code="MESSAGING_CONNECT_TOKEN_TTL_INVALID",
            severity="warning",
            message="MESSAGING_CONNECT_TOKEN_TTL_MINUTES باید مثبت باشد.",
        )

    if (
        outbound_enabled
        and bale_enabled
        and bale_allowed
        and token_configured
        and not queue_ready
    ):
        _add_issue(
            issues,
            code="BALE_QUEUE_NOT_READY",
            severity="warning",
            message="flagهای بله روشن هستند اما صف خروجی بله ready نیست.",
            hint="وضعیت provider، token، allowed providers و supports_outbound را بررسی کن.",
        )

    webhook_counts = _bale_webhook_snapshot(bale_provider)
    if webhook_counts["failed"] > 0:
        _add_issue(
            issues,
            code="BALE_FAILED_WEBHOOK_EVENTS_EXIST",
            severity="warning",
            message="event وبهوک شکست‌خورده برای بله وجود دارد.",
            hint="قبل از فعال‌سازی کامل، علت خطاها را بررسی کن.",
        )

    if webhook_counts["received"] > 0:
        _add_issue(
            issues,
            code="BALE_UNPROCESSED_WEBHOOK_EVENTS_EXIST",
            severity="warning",
            message="event وبهوک پردازش‌نشده برای بله وجود دارد.",
            hint="وضعیت worker/handler و خطاهای پردازش webhook را بررسی کن.",
        )

    message_log_counts = _bale_message_log_snapshot(bale_provider)
    if message_log_counts["outbound_failed"] > 0:
        _add_issue(
            issues,
            code="BALE_FAILED_OUTBOUND_MESSAGES_EXIST",
            severity="warning",
            message="پیام خروجی ناموفق برای بله وجود دارد.",
            hint="قبل از staging/production علت خطاهای provider بررسی شود.",
        )

    action_counts = _messaging_action_snapshot(bale_provider)
    if action_counts["started"] > 0:
        _add_issue(
            issues,
            code="BALE_STARTED_ACTIONS_EXIST",
            severity="warning",
            message="اکشن پیام‌رسان در وضعیت started باقی مانده است.",
            hint="اکشن‌های نیمه‌کاره را بررسی کن.",
        )

    summary = {
        "ok": not issues,
        "strict": bool(strict),
        "issue_count": len(issues),
        "error_count": len([issue for issue in issues if issue.severity == "error"]),
        "warning_count": len(
            [issue for issue in issues if issue.severity == "warning"]
        ),
    }

    return {
        "summary": summary,
        "settings": {
            "messaging_enabled": messaging_enabled,
            "messaging_outbound_enabled": outbound_enabled,
            "messaging_actions_enabled": actions_enabled,
            "bale_bot_enabled": bale_enabled,
            "bale_bot_token_configured": token_configured,
            "bale_webhook_secret_configured": webhook_secret_configured,
            "bale_webhook_require_secret": webhook_require_secret,
            "bale_webhook_allow_query_secret": webhook_allow_query_secret,
            "messaging_public_base_url_configured": bool(public_base_url),
            "messaging_public_base_url_is_https": bool(
                public_base_url and _url_is_https(public_base_url)
            ),
            "messaging_allowed_providers": allowed_providers,
        },
        "provider": {
            "bale_allowed": bale_allowed,
            "bale": bale_provider_snapshot,
        },
        "webhook": webhook,
        "queue": {
            "bale_outbound_queue_ready": bool(queue_ready),
            "bale": _bale_queue_snapshot(),
        },
        "webhook_events": {
            "bale": webhook_counts,
        },
        "message_logs": {
            "bale": message_log_counts,
        },
        "actions": {
            "bale": action_counts,
        },
        "issues": [issue.as_dict() for issue in issues],
    }


class Command(BaseCommand):
    help = "Run messaging/Bale configuration and readiness checks without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with a non-zero status when any issue is found.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output.",
        )

    def handle(self, *args, **options):
        strict = bool(options.get("strict"))
        as_json = bool(options.get("json"))

        result = run_messaging_qa_check(strict=strict)

        if as_json:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            summary = result["summary"]

            self.stdout.write("=== Messaging / Bale QA Check ===")
            self.stdout.write(f"strict={strict}")
            self.stdout.write(f"issues={summary['issue_count']}")
            self.stdout.write(f"errors={summary['error_count']}")
            self.stdout.write(f"warnings={summary['warning_count']}")
            self.stdout.write("")

            settings_snapshot = result["settings"]
            self.stdout.write("Settings:")
            self.stdout.write(
                f"  MESSAGING_ENABLED={settings_snapshot['messaging_enabled']}"
            )
            self.stdout.write(
                f"  MESSAGING_OUTBOUND_ENABLED={settings_snapshot['messaging_outbound_enabled']}"
            )
            self.stdout.write(
                f"  MESSAGING_ACTIONS_ENABLED={settings_snapshot['messaging_actions_enabled']}"
            )
            self.stdout.write(
                f"  BALE_BOT_ENABLED={settings_snapshot['bale_bot_enabled']}"
            )
            self.stdout.write(
                f"  BALE_BOT_TOKEN configured={settings_snapshot['bale_bot_token_configured']}"
            )
            self.stdout.write(
                f"  BALE_WEBHOOK_SECRET configured={settings_snapshot['bale_webhook_secret_configured']}"
            )
            self.stdout.write(
                f"  MESSAGING_PUBLIC_BASE_URL configured={settings_snapshot['messaging_public_base_url_configured']}"
            )
            self.stdout.write("")

            self.stdout.write("Bale:")
            self.stdout.write(
                f"  provider_allowed={result['provider']['bale_allowed']}"
            )
            self.stdout.write(f"  provider={result['provider']['bale']}")
            self.stdout.write(f"  webhook={result['webhook']}")
            self.stdout.write(
                f"  outbound_queue_ready={result['queue']['bale_outbound_queue_ready']}"
            )
            self.stdout.write(f"  deliveries={result['queue']['bale']}")
            self.stdout.write(f"  webhook_events={result['webhook_events']['bale']}")
            self.stdout.write(f"  message_logs={result['message_logs']['bale']}")
            self.stdout.write(f"  actions={result['actions']['bale']}")
            self.stdout.write("")

            issues = result["issues"]
            if issues:
                self.stdout.write("Issues:")
                for issue in issues:
                    line = f"[{issue['severity']}] {issue['code']}: {issue['message']}"
                    if issue.get("hint"):
                        line += f"\n  hint: {issue['hint']}"
                    if issue["severity"] == "error":
                        self.stdout.write(self.style.ERROR(line))
                    else:
                        self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(
                    self.style.SUCCESS("No messaging/Bale QA issues found.")
                )

        if result["issues"] and strict:
            raise CommandError(
                "Messaging/Bale QA check failed because --strict treats warnings as blocking issues."
            )
