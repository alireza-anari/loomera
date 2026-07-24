from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import NoReverseMatch, reverse

from apps.bale_bot.client import BaleBotApiError, BaleBotClient

from ...constants import MessagingProviderKey
from ...models import MessagingProvider
from ...services import ensure_default_providers, provider_allowed


@dataclass(frozen=True)
class BaleWebhookAdminIssue:
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


def _setting_str(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _setting_bool(name: str, default=False) -> bool:
    return bool(getattr(settings, name, default))


def _public_base_url() -> str:
    return _setting_str("MESSAGING_PUBLIC_BASE_URL").rstrip("/")


def _redact_url(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if not parsed.query:
        return value

    query = []
    for key, val in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in {"secret", "token", "key", "signature"}:
            query.append((key, "***"))
        else:
            query.append((key, val))

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


def _safe_provider_response(response):
    if not isinstance(response, dict):
        return {"ok": False, "raw_type": type(response).__name__}

    result = response.get("result")
    safe = {
        "ok": bool(response.get("ok", False)),
    }

    if isinstance(result, dict):
        copied = {}
        for key in [
            "url",
            "has_custom_certificate",
            "pending_update_count",
            "last_error_date",
            "last_error_message",
            "max_connections",
            "allowed_updates",
        ]:
            if key in result:
                copied[key] = (
                    _redact_url(str(result[key])) if key == "url" else result[key]
                )
        safe["result"] = copied
    elif result is not None:
        safe["result_type"] = type(result).__name__

    description = response.get("description")
    if description:
        safe["description"] = str(description)[:240]

    return safe


def _add_issue(issues, *, code: str, severity: str, message: str, hint: str = ""):
    issues.append(
        BaleWebhookAdminIssue(
            code=code,
            severity=severity,
            message=message,
            hint=hint,
        )
    )


def build_bale_webhook_url(*, include_query_secret: bool = False) -> str:
    base_url = _public_base_url()
    if not base_url:
        return ""

    path = reverse("bale_bot:webhook")
    url = f"{base_url}{path}"

    if include_query_secret:
        secret = _setting_str("BALE_WEBHOOK_SECRET")
        if secret:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}secret={secret}"

    return url


def run_bale_webhook_admin(
    *,
    apply: bool = False,
    set_webhook: bool = False,
    delete_webhook: bool = False,
    check_provider: bool = False,
    include_query_secret: bool = False,
    drop_pending_updates: bool = False,
    strict: bool = False,
):
    issues: list[BaleWebhookAdminIssue] = []

    ensure_default_providers()

    token_configured = bool(_setting_str("BALE_BOT_TOKEN"))
    secret_configured = bool(_setting_str("BALE_WEBHOOK_SECRET"))
    messaging_enabled = _setting_bool("MESSAGING_ENABLED")
    bale_enabled = _setting_bool("BALE_BOT_ENABLED")
    webhook_require_secret = _setting_bool("BALE_WEBHOOK_REQUIRE_SECRET", True)
    webhook_allow_query_secret = _setting_bool("BALE_WEBHOOK_ALLOW_QUERY_SECRET", False)
    public_base_url = _public_base_url()

    provider = MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()
    bale_allowed = provider_allowed(MessagingProviderKey.BALE)

    webhook_url = ""
    webhook_path = ""
    reverse_ok = True
    reverse_error = ""

    try:
        webhook_path = reverse("bale_bot:webhook")
        webhook_url = build_bale_webhook_url(include_query_secret=include_query_secret)
    except NoReverseMatch as exc:
        reverse_ok = False
        reverse_error = str(exc)
        _add_issue(
            issues,
            code="BALE_WEBHOOK_REVERSE_FAILED",
            severity="error" if strict else "warning",
            message="مسیر webhook بله reverse نمی‌شود.",
            hint="namespace مربوط به bale_bot:webhook را بررسی کن.",
        )

    if not public_base_url:
        _add_issue(
            issues,
            code="MESSAGING_PUBLIC_BASE_URL_MISSING",
            severity="error" if strict else "warning",
            message="MESSAGING_PUBLIC_BASE_URL تنظیم نشده است.",
            hint="برای ثبت webhook نزد بله، URL عمومی لازم است.",
        )

    if (
        public_base_url
        and not public_base_url.startswith("https://")
        and not _setting_bool("DEBUG")
    ):
        _add_issue(
            issues,
            code="MESSAGING_PUBLIC_BASE_URL_NOT_HTTPS",
            severity="error" if strict else "warning",
            message="MESSAGING_PUBLIC_BASE_URL در محیط غیر DEBUG باید https باشد.",
        )

    if not messaging_enabled:
        _add_issue(
            issues,
            code="MESSAGING_DISABLED",
            severity="warning",
            message="MESSAGING_ENABLED خاموش است.",
            hint="با این وضعیت webhook ورودی بله 404 می‌دهد.",
        )

    if not bale_enabled:
        _add_issue(
            issues,
            code="BALE_BOT_DISABLED",
            severity="warning",
            message="BALE_BOT_ENABLED خاموش است.",
            hint="با این وضعیت webhook ورودی بله 404 می‌دهد.",
        )

    if not bale_allowed:
        _add_issue(
            issues,
            code="BALE_PROVIDER_NOT_ALLOWED",
            severity="warning",
            message="provider بله در MESSAGING_ALLOWED_PROVIDERS مجاز نیست.",
        )

    if provider is None:
        _add_issue(
            issues,
            code="BALE_PROVIDER_MISSING",
            severity="error" if strict else "warning",
            message="provider بله در دیتابیس وجود ندارد.",
        )
    else:
        if not provider.is_active:
            _add_issue(
                issues,
                code="BALE_PROVIDER_INACTIVE",
                severity="warning",
                message="provider بله در دیتابیس inactive است.",
            )

        if not provider.supports_webhook:
            _add_issue(
                issues,
                code="BALE_PROVIDER_WEBHOOK_UNSUPPORTED",
                severity="warning",
                message="provider بله supports_webhook ندارد.",
            )

    if not token_configured and (set_webhook or delete_webhook or check_provider):
        _add_issue(
            issues,
            code="BALE_BOT_TOKEN_MISSING",
            severity="error",
            message="BALE_BOT_TOKEN برای تماس با API بله تنظیم نشده است.",
            hint="مقدار token فقط در env تنظیم شود و هرگز چاپ یا commit نشود.",
        )

    if webhook_require_secret and not secret_configured:
        _add_issue(
            issues,
            code="BALE_WEBHOOK_SECRET_MISSING",
            severity="error" if strict else "warning",
            message="BALE_WEBHOOK_SECRET تنظیم نشده است.",
        )

    if include_query_secret and not webhook_allow_query_secret:
        _add_issue(
            issues,
            code="QUERY_SECRET_NOT_ALLOWED",
            severity="error",
            message="--include-query-secret درخواست شده اما BALE_WEBHOOK_ALLOW_QUERY_SECRET خاموش است.",
            hint="secret در query string فقط برای fallback کنترل‌شده مجاز است، نه حالت پیش‌فرض staging/production.",
        )

    if include_query_secret:
        _add_issue(
            issues,
            code="QUERY_SECRET_USED",
            severity="warning",
            message="secret در query string قرار می‌گیرد.",
            hint="این حالت فقط برای fallback موقت و کنترل‌شده استفاده شود.",
        )

    actions_requested = bool(set_webhook or delete_webhook or check_provider)
    if set_webhook and delete_webhook:
        _add_issue(
            issues,
            code="CONFLICTING_ACTIONS",
            severity="error",
            message="--set و --delete همزمان مجاز نیستند.",
        )

    provider_response = None
    operation = {
        "requested": {
            "set": bool(set_webhook),
            "delete": bool(delete_webhook),
            "check_provider": bool(check_provider),
        },
        "applied": False,
        "dry_run": not apply,
        "provider_response": None,
        "provider_error": "",
    }

    should_call_provider = (
        actions_requested
        and token_configured
        and not any(issue.severity == "error" for issue in issues)
    )

    if check_provider and should_call_provider:
        try:
            provider_response = BaleBotClient().get_webhook_info()
            operation["provider_response"] = _safe_provider_response(provider_response)
        except BaleBotApiError as exc:
            operation["provider_error"] = str(exc)
            operation["provider_response"] = _safe_provider_response(exc.response)
            _add_issue(
                issues,
                code="BALE_GET_WEBHOOK_INFO_FAILED",
                severity="warning",
                message="دریافت وضعیت webhook از API بله ناموفق بود.",
                hint="اگر Bale از getWebhookInfo پشتیبانی نکند، این مورد برای set/delete blocker نیست.",
            )

    if set_webhook and should_call_provider:
        if not apply:
            operation["provider_response"] = operation["provider_response"] or {
                "dry_run": True,
                "method": "setWebhook",
            }
        else:
            try:
                secret_token = (
                    _setting_str("BALE_WEBHOOK_SECRET") if secret_configured else ""
                )
                provider_response = BaleBotClient().set_webhook(
                    webhook_url,
                    secret_token=secret_token,
                    drop_pending_updates=drop_pending_updates,
                )
                operation["applied"] = True
                operation["provider_response"] = _safe_provider_response(
                    provider_response
                )
            except BaleBotApiError as exc:
                operation["provider_error"] = str(exc)
                operation["provider_response"] = _safe_provider_response(exc.response)
                _add_issue(
                    issues,
                    code="BALE_SET_WEBHOOK_FAILED",
                    severity="error",
                    message="ثبت webhook نزد API بله ناموفق بود.",
                    hint="token، URL عمومی، HTTPS و پشتیبانی secret_token را بررسی کن.",
                )

    if delete_webhook and should_call_provider:
        if not apply:
            operation["provider_response"] = operation["provider_response"] or {
                "dry_run": True,
                "method": "deleteWebhook",
            }
        else:
            try:
                provider_response = BaleBotClient().delete_webhook(
                    drop_pending_updates=drop_pending_updates,
                )
                operation["applied"] = True
                operation["provider_response"] = _safe_provider_response(
                    provider_response
                )
            except BaleBotApiError as exc:
                operation["provider_error"] = str(exc)
                operation["provider_response"] = _safe_provider_response(exc.response)
                _add_issue(
                    issues,
                    code="BALE_DELETE_WEBHOOK_FAILED",
                    severity="error",
                    message="حذف webhook از API بله ناموفق بود.",
                )

    summary = {
        "ok": not issues,
        "strict": bool(strict),
        "issue_count": len(issues),
        "warning_count": len(
            [issue for issue in issues if issue.severity == "warning"]
        ),
        "error_count": len([issue for issue in issues if issue.severity == "error"]),
    }

    return {
        "summary": summary,
        "settings": {
            "messaging_enabled": messaging_enabled,
            "bale_bot_enabled": bale_enabled,
            "bale_bot_token_configured": token_configured,
            "bale_webhook_secret_configured": secret_configured,
            "bale_webhook_require_secret": webhook_require_secret,
            "bale_webhook_allow_query_secret": webhook_allow_query_secret,
            "messaging_public_base_url_configured": bool(public_base_url),
        },
        "provider": {
            "exists": provider is not None,
            "allowed": bale_allowed,
            "is_active": bool(provider and provider.is_active),
            "supports_webhook": bool(provider and provider.supports_webhook),
        },
        "webhook": {
            "reverse_ok": reverse_ok,
            "path": webhook_path,
            "url": _redact_url(webhook_url),
            "reverse_error": reverse_error,
            "uses_query_secret": bool(include_query_secret and secret_configured),
            "uses_secret_token": bool(secret_configured and not include_query_secret),
        },
        "operation": operation,
        "issues": [issue.as_dict() for issue in issues],
    }


class Command(BaseCommand):
    help = "Inspect, set, or delete Bale webhook safely without printing token/secret."

    def add_arguments(self, parser):
        parser.add_argument(
            "--set",
            action="store_true",
            dest="set_webhook",
            help="Register Bale webhook with provider. Requires --apply for real API call.",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            dest="delete_webhook",
            help="Delete Bale webhook from provider. Requires --apply for real API call.",
        )
        parser.add_argument(
            "--check-provider",
            action="store_true",
            help="Call getWebhookInfo on provider when token is configured.",
        )
        parser.add_argument(
            "--include-query-secret",
            action="store_true",
            help="Append webhook secret to URL query string. Requires BALE_WEBHOOK_ALLOW_QUERY_SECRET=True.",
        )
        parser.add_argument(
            "--drop-pending-updates",
            action="store_true",
            help="Ask provider to drop pending updates during set/delete when supported.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Perform set/delete provider API calls. Without this flag, command is dry-run.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when any issue is found.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON output.",
        )

    def handle(self, *args, **options):
        result = run_bale_webhook_admin(
            apply=bool(options.get("apply")),
            set_webhook=bool(options.get("set_webhook")),
            delete_webhook=bool(options.get("delete_webhook")),
            check_provider=bool(options.get("check_provider")),
            include_query_secret=bool(options.get("include_query_secret")),
            drop_pending_updates=bool(options.get("drop_pending_updates")),
            strict=bool(options.get("strict")),
        )

        if options.get("json"):
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            summary = result["summary"]
            self.stdout.write("=== Bale Webhook Admin ===")
            self.stdout.write(f"strict={summary['strict']}")
            self.stdout.write(f"issues={summary['issue_count']}")
            self.stdout.write(f"errors={summary['error_count']}")
            self.stdout.write(f"warnings={summary['warning_count']}")
            self.stdout.write("")

            self.stdout.write("Settings:")
            for key, value in result["settings"].items():
                self.stdout.write(f"  {key}={value}")
            self.stdout.write("")

            self.stdout.write("Provider:")
            for key, value in result["provider"].items():
                self.stdout.write(f"  {key}={value}")
            self.stdout.write("")

            self.stdout.write("Webhook:")
            for key, value in result["webhook"].items():
                self.stdout.write(f"  {key}={value}")
            self.stdout.write("")

            self.stdout.write("Operation:")
            self.stdout.write(f"  requested={result['operation']['requested']}")
            self.stdout.write(f"  dry_run={result['operation']['dry_run']}")
            self.stdout.write(f"  applied={result['operation']['applied']}")
            self.stdout.write(
                f"  provider_response={result['operation']['provider_response']}"
            )
            self.stdout.write(
                f"  provider_error={result['operation']['provider_error']}"
            )
            self.stdout.write("")

            if result["issues"]:
                self.stdout.write("Issues:")
                for issue in result["issues"]:
                    line = f"[{issue['severity']}] {issue['code']}: {issue['message']}"
                    if issue.get("hint"):
                        line += f"\n  hint: {issue['hint']}"
                    if issue["severity"] == "error":
                        self.stdout.write(self.style.ERROR(line))
                    else:
                        self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(
                    self.style.SUCCESS("No Bale webhook admin issues found.")
                )

        if result["issues"] and options.get("strict"):
            raise CommandError(
                "Bale webhook admin check failed because --strict treats warnings as blocking issues."
            )
