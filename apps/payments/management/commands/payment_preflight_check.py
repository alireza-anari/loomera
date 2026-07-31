from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.payments.gateways import (
    get_gateway_mode,
    get_gateway_provider,
)
from apps.payments.models import Payment


@dataclass
class CheckResult:
    level: str
    code: str
    message: str


class PreflightReporter:
    def __init__(self, command):
        self.command = command
        self.results: list[CheckResult] = []

    def ok(self, code: str, message: str):
        self.results.append(CheckResult("OK", code, message))

    def warn(self, code: str, message: str):
        self.results.append(CheckResult("WARN", code, message))

    def error(self, code: str, message: str):
        self.results.append(CheckResult("ERROR", code, message))

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.results if item.level == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.results if item.level == "WARN")

    def write(self):
        for item in self.results:
            if item.level == "OK":
                style = self.command.style.SUCCESS
            elif item.level == "WARN":
                style = self.command.style.WARNING
            else:
                style = self.command.style.ERROR

            self.command.stdout.write(
                style(f"[{item.level}] {item.code}: " f"{item.message}")
            )


def _setting(name: str, default=None):
    return getattr(settings, name, default)


def _bool_setting(name: str, default=False) -> bool:
    return bool(getattr(settings, name, default))


def _has_value(value) -> bool:
    return bool(str(value or "").strip())


def _is_safe_url(value: str) -> bool:
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _check_route(reporter, route_name, kwargs):
    try:
        path = reverse(route_name, kwargs=kwargs)
    except NoReverseMatch as exc:
        reporter.error(
            "route.reverse_failed",
            f"مسیر {route_name} قابل reverse شدن نیست: {exc}",
        )
        return None

    reporter.ok(
        "route.ok",
        f"مسیر {route_name} آماده است: {path}",
    )
    return path


def _check_payment_settings(
    reporter,
    *,
    allow_live: bool,
):
    mode = get_gateway_mode()
    provider = get_gateway_provider()
    online_enabled = _bool_setting(
        "ONLINE_PAYMENT_ENABLED",
        False,
    )

    if mode in {"mock", "sandbox", "live"}:
        reporter.ok(
            "payment.mode",
            f"PAYMENT_MODE={mode}",
        )
    else:
        reporter.error(
            "payment.mode.invalid",
            ("PAYMENT_MODE نامعتبر است. مقدار مجاز: " "mock, sandbox, live"),
        )

    if provider == "zibal":
        reporter.ok(
            "payment.provider",
            "PAYMENT_PROVIDER=zibal",
        )
    else:
        reporter.error(
            "payment.provider.invalid",
            ("PAYMENT_PROVIDER باید zibal باشد. " f"مقدار فعلی: {provider}"),
        )

    if online_enabled:
        reporter.warn(
            "payment.online_enabled",
            (
                "ONLINE_PAYMENT_ENABLED=True است. "
                "برای Production فقط بعد از تأیید کامل Staging "
                "روشن شود."
            ),
        )
    else:
        reporter.ok(
            "payment.online_disabled",
            ("ONLINE_PAYMENT_ENABLED=False است؛ " "برای بتای پرداخت در سالن امن است."),
        )

    if mode == "live" and not allow_live:
        reporter.error(
            "payment.live.blocked",
            (
                "PAYMENT_MODE=live است، اما --allow-live ارسال "
                "نشده. برای جلوگیری از تست ناخواسته روی live، "
                "preflight متوقف می‌شود."
            ),
        )

    if mode == "sandbox":
        merchant = _setting("ZIBAL_SANDBOX_MERCHANT", "")
        if _has_value(merchant):
            reporter.ok(
                "zibal.sandbox_merchant",
                "ZIBAL_SANDBOX_MERCHANT تنظیم شده است.",
            )
        else:
            reporter.error(
                "zibal.sandbox_merchant.missing",
                "ZIBAL_SANDBOX_MERCHANT تنظیم نشده است.",
            )

    if mode == "live":
        merchant = (
            _setting("ZIBAL_MERCHANT", "")
            or _setting("ZIBAL_MERCHANT_ID", "")
            or _setting("ZIBAL_LIVE_MERCHANT", "")
        )

        if _has_value(merchant):
            reporter.ok(
                "zibal.live_merchant",
                "Merchant live زیبال تنظیم شده است.",
            )
        else:
            reporter.error(
                "zibal.live_merchant.missing",
                (
                    "Merchant live زیبال تنظیم نشده است. "
                    "نام‌های بررسی‌شده: ZIBAL_MERCHANT, "
                    "ZIBAL_MERCHANT_ID, ZIBAL_LIVE_MERCHANT"
                ),
            )

    verify_url = _setting(
        "ZIBAL_VERIFY_URL",
        "https://gateway.zibal.ir/v1/verify",
    )

    if _is_safe_url(verify_url):
        reporter.ok(
            "zibal.verify_url",
            f"ZIBAL_VERIFY_URL معتبر است: {verify_url}",
        )
    else:
        reporter.error(
            "zibal.verify_url.invalid",
            "ZIBAL_VERIFY_URL معتبر نیست.",
        )

    timeout = _setting("PAYMENT_TIMEOUT_SECONDS", None)

    if timeout is None:
        reporter.error(
            "payment.timeout.missing",
            "PAYMENT_TIMEOUT_SECONDS تنظیم نشده است.",
        )
    else:
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError):
            reporter.error(
                "payment.timeout.invalid",
                "PAYMENT_TIMEOUT_SECONDS باید یک عدد معتبر باشد.",
            )
        else:
            if 1 <= timeout_value <= 30:
                reporter.ok(
                    "payment.timeout",
                    ("PAYMENT_TIMEOUT_SECONDS معتبر است: " f"{timeout_value:g}"),
                )
            else:
                reporter.warn(
                    "payment.timeout.range",
                    (
                        "PAYMENT_TIMEOUT_SECONDS خارج از بازه پیشنهادی "
                        "۱ تا ۳۰ ثانیه است."
                    ),
                )


def _check_url_settings(reporter):
    allowed_hosts = list(_setting("ALLOWED_HOSTS", []) or [])

    if allowed_hosts:
        reporter.ok(
            "django.allowed_hosts",
            f"ALLOWED_HOSTS دارای {len(allowed_hosts)} مقدار است.",
        )
    else:
        reporter.error(
            "django.allowed_hosts.empty",
            "ALLOWED_HOSTS خالی است.",
        )

    csrf_trusted = list(_setting("CSRF_TRUSTED_ORIGINS", []) or [])

    if csrf_trusted:
        reporter.ok(
            "django.csrf_trusted_origins",
            ("CSRF_TRUSTED_ORIGINS تنظیم شده است " f"({len(csrf_trusted)} مقدار)."),
        )
    else:
        reporter.warn(
            "django.csrf_trusted_origins.empty",
            ("CSRF_TRUSTED_ORIGINS خالی است. " "برای Staging/Production بررسی شود."),
        )

    candidate_base_urls = [
        "SITE_URL",
        "BASE_URL",
        "PUBLIC_BASE_URL",
        "APP_BASE_URL",
        "LOOMERA_PUBLIC_BASE_URL",
    ]

    found_base_url = False

    for name in candidate_base_urls:
        value = _setting(name, "")
        if _has_value(value):
            found_base_url = True
            if _is_safe_url(value):
                reporter.ok(
                    "public_base_url",
                    f"{name} معتبر است: {value}",
                )
            else:
                reporter.error(
                    "public_base_url.invalid",
                    f"{name} معتبر نیست: {value}",
                )

    if not found_base_url:
        reporter.warn(
            "public_base_url.missing",
            (
                "Base URL عمومی صریح پیدا نشد. "
                "اگر callback با request.build_absolute_uri "
                "ساخته می‌شود، Host و proxy headers در "
                "Staging دقیق تست شوند."
            ),
        )


def _check_payment_routes(reporter):
    _check_route(
        reporter,
        "payments:charge_verify",
        {
            "payment_id": 1,
            "token": "test-token",
        },
    )
    _check_route(
        reporter,
        "payments:appointment_verify",
        {
            "payment_id": 1,
            "token": "test-token",
        },
    )
    _check_route(
        reporter,
        "payments:appointment_result",
        {
            "payment_id": 1,
            "token": "test-token",
        },
    )

    try:
        reverse("payments:detail")
        reporter.ok(
            "route.wallet_detail",
            "مسیر payments:detail آماده است.",
        )
    except NoReverseMatch as exc:
        reporter.error(
            "route.wallet_detail.failed",
            f"مسیر payments:detail آماده نیست: {exc}",
        )


def _check_pending_payments(
    reporter,
    *,
    max_pending_age_hours: int,
):
    pending_qs = Payment.objects.filter(
        state__in=[
            Payment.State.INITIATED,
            Payment.State.PENDING,
        ],
        is_finally=False,
        provider__in=[
            Payment.Provider.ZIBAL,
            Payment.Provider.MOCK,
        ],
    )

    total_pending = pending_qs.count()

    if total_pending == 0:
        reporter.ok(
            "payments.pending.none",
            "Payment معلق درگاهی وجود ندارد.",
        )
        return

    reporter.warn(
        "payments.pending.exists",
        f"{total_pending} Payment معلق درگاهی وجود دارد.",
    )

    missing_track_count = (
        pending_qs.filter(
            gateway_track_id__isnull=True,
        ).count()
        + pending_qs.filter(
            gateway_track_id="",
        ).count()
    )

    if missing_track_count:
        reporter.error(
            "payments.pending.missing_track_id",
            (f"{missing_track_count} Payment معلق بدون " "gateway_track_id وجود دارد."),
        )
    else:
        reporter.ok(
            "payments.pending.track_id",
            "همه Paymentهای معلق gateway_track_id دارند.",
        )

    cutoff = timezone.now() - timedelta(hours=max_pending_age_hours)

    stale_count = pending_qs.filter(
        update_date__lt=cutoff,
    ).count()

    if stale_count:
        reporter.warn(
            "payments.pending.stale",
            (
                f"{stale_count} Payment معلق قدیمی‌تر از "
                f"{max_pending_age_hours} ساعت وجود دارد. "
                "قبل از Staging/Production با command "
                "reconcile_pending_gateway_payments بررسی شود."
            ),
        )
    else:
        reporter.ok(
            "payments.pending.age",
            ("Payment معلق خیلی قدیمی‌تر از حد تعیین‌شده " "وجود ندارد."),
        )

    review_count = pending_qs.filter(meta__verify_pending__requires_review=True).count()

    if review_count:
        reporter.warn(
            "payments.pending.requires_review",
            (f"{review_count} Payment نیازمند بررسی دستی " "وجود دارد."),
        )


def _check_secrets_not_printed(reporter):
    reporter.ok(
        "secrets.redaction",
        (
            "Preflight فقط وجود تنظیمات حساس را بررسی می‌کند "
            "و مقدار secretها را چاپ نمی‌کند."
        ),
    )


class Command(BaseCommand):
    help = "بررسی ایمن تنظیمات و وضعیت پرداخت قبل از تست " "Local/Staging/Production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help=("در صورت وجود ERROR با exit code غیرصفر خارج شود."),
        )
        parser.add_argument(
            "--allow-live",
            action="store_true",
            help=(
                "اجازه اجرای preflight در PAYMENT_MODE=live. "
                "بدون این گزینه live خطا محسوب می‌شود."
            ),
        )
        parser.add_argument(
            "--max-pending-age-hours",
            type=int,
            default=24,
            help=("حداکثر سن قابل قبول Paymentهای معلق، " "بر حسب ساعت."),
        )

    def handle(self, *args, **options):
        reporter = PreflightReporter(self)

        strict = bool(options["strict"])
        allow_live = bool(options["allow_live"])
        max_pending_age_hours = max(
            int(options["max_pending_age_hours"] or 24),
            1,
        )

        self.stdout.write(self.style.NOTICE("=== Loomera payment preflight check ==="))

        _check_secrets_not_printed(reporter)
        _check_payment_settings(
            reporter,
            allow_live=allow_live,
        )
        _check_url_settings(reporter)
        _check_payment_routes(reporter)
        _check_pending_payments(
            reporter,
            max_pending_age_hours=max_pending_age_hours,
        )

        reporter.write()

        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("=== Summary ==="))
        self.stdout.write(f"errors={reporter.error_count}")
        self.stdout.write(f"warnings={reporter.warning_count}")

        if strict and reporter.error_count:
            raise SystemExit(1)
