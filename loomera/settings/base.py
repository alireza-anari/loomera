# loomera/settings/base.py

import os
import sys
import importlib
from pathlib import Path
import environ
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# مسیر پایه پروژه را سه سطح بالاتر تنظیم می‌کنیم تا به ریشه پروژه (کنار manage.py) برسیم
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# راه‌اندازی django-environ برای خواندن متغیرهای محیطی
env = environ.Env(
    # مقدار پیش‌فرض و نوع متغیر DEBUG را مشخص می‌کنیم
    DEBUG=(bool, False)
)
# فایل .env را از ریشه پروژه می‌خوانیم
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))


def _module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


# ==============================================================================
# CORE SETTINGS
# ==============================================================================

IS_COLLECTSTATIC_COMMAND = any(arg == "collectstatic" for arg in sys.argv)

SECRET_KEY = env(
    "SECRET_KEY",
    default=(
        "collectstatic-build-only-not-for-runtime" if IS_COLLECTSTATIC_COMMAND else None
    ),
)

if not SECRET_KEY:
    raise ImproperlyConfigured("Set the SECRET_KEY environment variable")

DEBUG = env.bool("DEBUG", default=False)

# Liara ZIP/Django platform may run collectstatic during the build phase before
# runtime environment variables are attached to the process. collectstatic only
# needs to import settings and gather files; it must not weaken runtime security.
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"] if IS_COLLECTSTATIC_COMMAND else [],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=(
        ["http://localhost", "http://127.0.0.1"] if IS_COLLECTSTATIC_COMMAND else []
    ),
)

SERVE_MEDIA_INSECURELY = env.bool("SERVE_MEDIA_INSECURELY", default=DEBUG)

SESSION_COOKIE_HTTPONLY = env.bool("SESSION_COOKIE_HTTPONLY", default=True)
CSRF_COOKIE_HTTPONLY = env.bool("CSRF_COOKIE_HTTPONLY", default=False)

SECURE_CROSS_ORIGIN_OPENER_POLICY = env(
    "SECURE_CROSS_ORIGIN_OPENER_POLICY",
    default="same-origin",
)

CSF_REVIEW_POST_MAX_BYTES = env.int(
    "CSF_REVIEW_POST_MAX_BYTES",
    default=16 * 1024,
)
CSF_REVIEW_COMMENT_MAX_CHARS = env.int(
    "CSF_REVIEW_COMMENT_MAX_CHARS",
    default=1000,
)
# ==============================================================================
# LOOMERA BRAND / INTEGRATION METADATA
# ==============================================================================
# Keep external machine-readable strings in one place so future brand/runtime
# touchpoints do not reintroduce legacy Salonify names.
BRAND_NAME = env("BRAND_NAME", default="Loomera").strip() or "Loomera"
BRAND_DISPLAY_NAME = env("BRAND_DISPLAY_NAME", default=BRAND_NAME).strip() or BRAND_NAME
BRAND_DOMAIN = env("BRAND_DOMAIN", default="loomera.local").strip() or "loomera.local"
PUBLIC_BASE_URL = (
    env(
        "PUBLIC_BASE_URL",
        default="",
    )
    .strip()
    .rstrip("/")
)

SITE_URL = (
    env(
        "SITE_URL",
        default=PUBLIC_BASE_URL,
    )
    .strip()
    .rstrip("/")
)
LOOMERA_USER_AGENT = (
    env("LOOMERA_USER_AGENT", default=f"{BRAND_NAME}/1.0").strip()
    or f"{BRAND_NAME}/1.0"
)
LOOMERA_CALENDAR_PRODID = env(
    "LOOMERA_CALENDAR_PRODID",
    default=f"-//{BRAND_NAME}//Appointment//FA",
).strip()
LOOMERA_CALENDAR_NAME = env(
    "LOOMERA_CALENDAR_NAME",
    default=f"{BRAND_NAME} Appointment",
).strip()
LOOMERA_EMAIL_SENDER_NAME = (
    env(
        "LOOMERA_EMAIL_SENDER_NAME",
        default=BRAND_DISPLAY_NAME,
    ).strip()
    or BRAND_DISPLAY_NAME
)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default=f"{LOOMERA_EMAIL_SENDER_NAME} <no-reply@{BRAND_DOMAIN}>",
).strip()
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL).strip()
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.dummy.EmailBackend"
    ),
).strip()
LOOMERA_SUPPORT_EMAIL = env(
    "LOOMERA_SUPPORT_EMAIL",
    default=f"support@{BRAND_DOMAIN}",
).strip()
LOOMERA_PARTNER_EMAIL = env(
    "LOOMERA_PARTNER_EMAIL",
    default=f"partners@{BRAND_DOMAIN}",
).strip()
LOOMERA_MARKETING_EMAIL = env(
    "LOOMERA_MARKETING_EMAIL",
    default=f"hello@{BRAND_DOMAIN}",
).strip()
LOOMERA_CRM_SENDER_NAME = (
    env(
        "LOOMERA_CRM_SENDER_NAME",
        default=LOOMERA_EMAIL_SENDER_NAME,
    ).strip()
    or LOOMERA_EMAIL_SENDER_NAME
)
LOOMERA_CRM_REPLY_TO_EMAIL = env(
    "LOOMERA_CRM_REPLY_TO_EMAIL",
    default=LOOMERA_SUPPORT_EMAIL,
).strip()
LOOMERA_CRM_TEMPLATE_DOCS_DIR = env(
    "LOOMERA_CRM_TEMPLATE_DOCS_DIR",
    default="docs/crm/source/templates",
).strip()

DATA_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "DATA_UPLOAD_MAX_MEMORY_SIZE",
    default=5 * 1024 * 1024,  # 5 MB
)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "FILE_UPLOAD_MAX_MEMORY_SIZE",
    default=5 * 1024 * 1024,  # 5 MB
)

# ==============================================================================
# LOOMERA PRODUCT / RELEASE FLAGS
# ==============================================================================
# These flags keep incomplete or high-risk capabilities disabled until the
# corresponding backend, UI, support, finance and legal workflows are ready.
BETA_MODE = env.bool("BETA_MODE", default=True)
COMMISSION_ENABLED = env.bool("COMMISSION_ENABLED", default=False)
ONLINE_PAYMENT_ENABLED = env.bool("ONLINE_PAYMENT_ENABLED", default=False)
DEPOSIT_ENABLED = env.bool("DEPOSIT_ENABLED", default=False)
BNPL_ENABLED = env.bool("BNPL_ENABLED", default=False)
DEBT_ENFORCEMENT_ENABLED = env.bool("DEBT_ENFORCEMENT_ENABLED", default=False)
SALON_VERIFICATION_ENFORCED = env.bool("SALON_VERIFICATION_ENFORCED", default=False)
SALON_WITHDRAWAL_ENABLED = env.bool("SALON_WITHDRAWAL_ENABLED", default=False)
AUTOMATIC_REFUND_ENABLED = env.bool("AUTOMATIC_REFUND_ENABLED", default=False)

MESSAGING_ENABLED = env.bool("MESSAGING_ENABLED", default=False)
MESSAGING_OUTBOUND_ENABLED = env.bool("MESSAGING_OUTBOUND_ENABLED", default=False)
MESSAGING_ACTIONS_ENABLED = env.bool("MESSAGING_ACTIONS_ENABLED", default=False)
MESSAGING_ALLOWED_PROVIDERS = env.list("MESSAGING_ALLOWED_PROVIDERS", default=[])
BALE_BOT_ENABLED = env.bool("BALE_BOT_ENABLED", default=False)
if BALE_BOT_ENABLED and "bale" not in MESSAGING_ALLOWED_PROVIDERS:
    MESSAGING_ALLOWED_PROVIDERS.append("bale")
BALE_BOT_TOKEN = env("BALE_BOT_TOKEN", default="").strip()
BALE_BOT_API_BASE_URL = env(
    "BALE_BOT_API_BASE_URL", default="https://tapi.bale.ai/bot"
).strip()
BALE_BOT_REQUEST_TIMEOUT = env.int("BALE_BOT_REQUEST_TIMEOUT", default=10)
BALE_BOT_USERNAME = env("BALE_BOT_USERNAME", default="").strip().lstrip("@")
BALE_BOT_START_URL_TEMPLATE = env("BALE_BOT_START_URL_TEMPLATE", default="").strip()
BALE_WEBHOOK_SECRET = env("BALE_WEBHOOK_SECRET", default="").strip()
BALE_WEBHOOK_REQUIRE_SECRET = env.bool("BALE_WEBHOOK_REQUIRE_SECRET", default=True)
BALE_WEBHOOK_ALLOW_QUERY_SECRET = env.bool(
    "BALE_WEBHOOK_ALLOW_QUERY_SECRET",
    default=False,
)
BALE_WEBHOOK_ALLOW_PATH_TOKEN = env.bool(
    "BALE_WEBHOOK_ALLOW_PATH_TOKEN",
    default=False,
)
BALE_WEBHOOK_MAX_BYTES = env.int("BALE_WEBHOOK_MAX_BYTES", default=256 * 1024)
BALE_POLLING_ENABLED = env.bool("BALE_POLLING_ENABLED", default=False)
BALE_POLLING_LIMIT = env.int("BALE_POLLING_LIMIT", default=100)
BALE_POLLING_TIMEOUT_SECONDS = env.int("BALE_POLLING_TIMEOUT_SECONDS", default=0)
BALE_POLLING_LOCK_TTL_SECONDS = env.int("BALE_POLLING_LOCK_TTL_SECONDS", default=120)
MESSAGING_PUBLIC_BASE_URL = (
    env("MESSAGING_PUBLIC_BASE_URL", default="").strip().rstrip("/")
)
MESSAGING_CONNECT_TOKEN_TTL_MINUTES = env.int(
    "MESSAGING_CONNECT_TOKEN_TTL_MINUTES", default=30
)
MESSAGING_NOTIFICATION_TEXT_MAX_CHARS = env.int(
    "MESSAGING_NOTIFICATION_TEXT_MAX_CHARS", default=3500
)
MESSAGING_ACTION_TOKEN_TTL_MINUTES = env.int(
    "MESSAGING_ACTION_TOKEN_TTL_MINUTES", default=60
)
MESSAGING_PRIVACY_TEXT_VERSION = env(
    "MESSAGING_PRIVACY_TEXT_VERSION", default="1403-01"
).strip()

# Lightweight operational limits. More advanced rate limiting will be moved to
# Redis-backed middleware/service when the full security phase is implemented.
LOOMERA_SUPPORT_TICKET_RATE_LIMIT = env.int(
    "LOOMERA_SUPPORT_TICKET_RATE_LIMIT", default=5
)
LOOMERA_SUPPORT_TICKET_RATE_WINDOW_SECONDS = env.int(
    "LOOMERA_SUPPORT_TICKET_RATE_WINDOW_SECONDS", default=3600
)

# ==============================================================================
# APPLICATION DEFINITION
# ==============================================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "apps.main.apps.MainConfig",
    "apps.help_center.apps.HelpCenterConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.services.apps.ServicesConfig",
    "apps.stylists.apps.StylistsConfig",
    "apps.blogs.apps.BlogsConfig",
    "apps.articles.apps.ArticlesConfig",
    "apps.salons.apps.SalonsConfig",
    "apps.comments_scores_favories.apps.CommentsScoresFavoriesConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.discounts.apps.DiscountsConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.search.apps.SearchConfig",
    "apps.locations.apps.LocationsConfig",
    "apps.dashboards.apps.DashboardsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.messaging.apps.MessagingConfig",
    "apps.bale_bot.apps.BaleBotConfig",
    "apps.platform_admin.apps.PlatformAdminConfig",
    "apps.analytics.apps.AnalyticsConfig",
    "apps.api.apps.ApiConfig",
    # Third-party apps
    "rest_framework",
    "django_render_partial",
    "django.contrib.gis",
    "django_jalali",
]

OPTIONAL_APPS = [
    "django_admin_listfilter_dropdown",
    "storages",
]
if DEBUG:
    OPTIONAL_APPS.append("debug_toolbar")

for optional_app in OPTIONAL_APPS:
    if _module_available(optional_app):
        INSTALLED_APPS.append(optional_app)


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "middlewares.middlewares.RequestMiddleware",
    "django.middleware.locale.LocaleMiddleware",
]

if _module_available("whitenoise"):
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

if DEBUG and _module_available("debug_toolbar"):
    MIDDLEWARE.insert(7, "debug_toolbar.middleware.DebugToolbarMiddleware")


ROOT_URLCONF = "loomera.urls"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csrf",
                "apps.main.views.madia_admin",
            ],
        },
    },
]

WSGI_APPLICATION = "loomera.wsgi.application"
ASGI_APPLICATION = "loomera.asgi.application"

# ==============================================================================
# DATABASES
# ==============================================================================

# Liara runs collectstatic during the build phase. In ZIP deploys, runtime envs
# such as DATABASE_URL may not be available to that build command. collectstatic
# does not need the production database, so only that command may fall back to a
# temporary local sqlite database. Runtime and all other management commands must
# still fail loudly if DATABASE_URL is missing.
COLLECTSTATIC_DATABASE_URL = f"sqlite:///{BASE_DIR / 'collectstatic.sqlite3'}"

DATABASE_URL = env(
    "DATABASE_URL",
    default=COLLECTSTATIC_DATABASE_URL if IS_COLLECTSTATIC_COMMAND else "",
).strip()

if not DATABASE_URL:
    raise ImproperlyConfigured("Set the DATABASE_URL environment variable")

DATABASES = {"default": env.db_url("DATABASE_URL", default=DATABASE_URL)}

if DATABASE_URL.startswith("postgis://"):
    DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
elif DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    DATABASES["default"].setdefault("ENGINE", "django.db.backends.postgresql")

# ==============================================================================
# AUTHENTICATION
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTH_USER_MODEL = "accounts.CustomUser"

# ==============================================================================
# INTERNATIONALIZATION
# ==============================================================================

LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# ==============================================================================
# STATIC & MEDIA FILES
# ==============================================================================

STATIC_URL = env("STATIC_URL", default="/static/").strip()
if not STATIC_URL.endswith("/"):
    STATIC_URL = f"{STATIC_URL}/"

STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = env(
    "STATIC_ROOT",
    default=os.path.join(BASE_DIR, "staticfiles"),
).strip()

MEDIA_URL = env("MEDIA_URL", default="/media/").strip()
if not MEDIA_URL.endswith("/"):
    MEDIA_URL = f"{MEDIA_URL}/"

MEDIA_ROOT = env("MEDIA_ROOT", default=os.path.join(BASE_DIR, "media")).strip()
MEDIA_PROXY_ENABLED = env.bool("MEDIA_PROXY_ENABLED", default=False)
MEDIA_PROXY_URL = env("MEDIA_PROXY_URL", default="/asset-proxy/").strip()
if not MEDIA_PROXY_URL.endswith("/"):
    MEDIA_PROXY_URL = f"{MEDIA_PROXY_URL}/"

MEDIA_PROXY_IMAGE_EXTENSIONS = {
    ext.strip().lower()
    for ext in env(
        "MEDIA_PROXY_IMAGE_EXTENSIONS",
        default=".jpg,.jpeg,.png,.webp,.gif,.avif",
    ).split(",")
    if ext.strip()
}
MEDIA_PROXY_ALLOW_SVG = env.bool("MEDIA_PROXY_ALLOW_SVG", default=False)
MEDIA_PROXY_MAX_PATH_LENGTH = env.int("MEDIA_PROXY_MAX_PATH_LENGTH", default=512)

USE_S3_MEDIA = env.bool("USE_S3_MEDIA", default=False)
LOOMERA_REQUIRE_OBJECT_STORAGE = env.bool(
    "LOOMERA_REQUIRE_OBJECT_STORAGE",
    default=False,
)

STATICFILES_STORAGE_BACKEND = env(
    "STATICFILES_STORAGE_BACKEND",
    default=(
        "whitenoise.storage.CompressedStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    ),
).strip()

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": STATICFILES_STORAGE_BACKEND},
}

if not _module_available("whitenoise") and STATICFILES_STORAGE_BACKEND.startswith(
    "whitenoise."
):
    STORAGES["staticfiles"] = {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    }

if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="").strip()
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="").strip()
    AWS_STORAGE_BUCKET_NAME = env(
        "AWS_STORAGE_BUCKET_NAME",
        default=env("AWS_BUCKET", default=""),
    ).strip()
    AWS_S3_ENDPOINT_URL = (
        env(
            "AWS_S3_ENDPOINT_URL",
            default=env("AWS_ENDPOINT", default=""),
        )
        .strip()
        .rstrip("/")
    )
    AWS_S3_REGION_NAME = env(
        "AWS_S3_REGION_NAME",
        default=env("AWS_DEFAULT_REGION", default="us-east-1"),
    ).strip()
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path").strip()
    AWS_S3_SIGNATURE_VERSION = env("AWS_S3_SIGNATURE_VERSION", default="s3v4").strip()
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=True)
    AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=3600)
    AWS_S3_FILE_OVERWRITE = env.bool("AWS_S3_FILE_OVERWRITE", default=False)
    AWS_S3_OBJECT_PARAMETERS = {
        "CacheControl": env(
            "AWS_S3_CACHE_CONTROL",
            default="max-age=86400",
        ).strip()
    }

    MEDIA_PROXY_ENABLED = env.bool("MEDIA_PROXY_ENABLED", default=True)

    STORAGES["default"] = {
        "BACKEND": "apps.main.storage_backends.LoomeraS3MediaStorage",
    }
# ==============================================================================
# THIRD-PARTY LIBRARIES CONFIGURATION
# ==============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Legacy Zarinpal Wallet Gateway
MERCHANT = env("MERCHANT", default="")
PAYMENT_CALLBACK_URL = env(
    "PAYMENT_CALLBACK_URL", default="/payments/charge/verify/"
).strip()
SANDBOX = env.bool("SANDBOX", default=True)

# Appointment Payment Gateway
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="zibal").strip().lower()
PAYMENT_MODE = env("PAYMENT_MODE", default="mock").strip().lower()
PAYMENT_TIMEOUT_SECONDS = env.int("PAYMENT_TIMEOUT_SECONDS", default=15)
PAYMENT_PUBLIC_BASE_URL = env("PAYMENT_PUBLIC_BASE_URL", default="").strip().rstrip("/")
WALLET_WITHDRAW_MIN_AMOUNT = env.int("WALLET_WITHDRAW_MIN_AMOUNT", default=50000)
WALLET_WITHDRAW_MAX_AMOUNT = env.int("WALLET_WITHDRAW_MAX_AMOUNT", default=50000000)
SALON_WALLET_WITHDRAW_MIN_AMOUNT = env.int(
    "SALON_WALLET_WITHDRAW_MIN_AMOUNT", default=100000
)
SALON_WALLET_WITHDRAW_MAX_AMOUNT = env.int(
    "SALON_WALLET_WITHDRAW_MAX_AMOUNT", default=200000000
)
PLATFORM_FIRST_VISIT_COMMISSION_PERCENT = env.int(
    "PLATFORM_FIRST_VISIT_COMMISSION_PERCENT", default=0
)
ZIBAL_MERCHANT = env("ZIBAL_MERCHANT", default="")
ZIBAL_SANDBOX_MERCHANT = env("ZIBAL_SANDBOX_MERCHANT", default="zibal")
ZIBAL_REQUEST_URL = env(
    "ZIBAL_REQUEST_URL", default="https://gateway.zibal.ir/v1/request"
)
ZIBAL_VERIFY_URL = env("ZIBAL_VERIFY_URL", default="https://gateway.zibal.ir/v1/verify")
ZIBAL_STARTPAY_BASE_URL = env(
    "ZIBAL_STARTPAY_BASE_URL", default="https://gateway.zibal.ir"
)
# -------------------------------------------------------------------------
# Payment live-mode hardening guards
if not DEBUG and str(PAYMENT_MODE or "").lower() == "live":
    if not PAYMENT_PUBLIC_BASE_URL:
        raise ImproperlyConfigured(
            "PAYMENT_PUBLIC_BASE_URL برای حالت live باید تنظیم شود."
        )

    if not str(PAYMENT_PUBLIC_BASE_URL).startswith("https://"):
        raise ImproperlyConfigured(
            "PAYMENT_PUBLIC_BASE_URL در حالت live باید با https:// شروع شود."
        )

    if PAYMENT_PROVIDER == "zibal" and not str(ZIBAL_MERCHANT or "").strip():
        raise ImproperlyConfigured("ZIBAL_MERCHANT برای حالت live باید تنظیم شود.")

    if str(PAYMENT_CALLBACK_URL or "").startswith("http://"):
        raise ImproperlyConfigured(
            "PAYMENT_CALLBACK_URL در حالت live نباید http:// باشد."
        )

    if SANDBOX:
        raise ImproperlyConfigured("در حالت live، SANDBOX باید False باشد.")


# Production hardening guards
if not DEBUG:
    if SERVE_MEDIA_INSECURELY:
        raise ImproperlyConfigured(
            "SERVE_MEDIA_INSECURELY در production نباید True باشد. "
            "media باید توسط Nginx/Apache یا storage مناسب سرو شود."
        )

    if not ALLOWED_HOSTS and not IS_COLLECTSTATIC_COMMAND:
        raise ImproperlyConfigured("در production، ALLOWED_HOSTS نباید خالی باشد.")

    if not CSRF_TRUSTED_ORIGINS and not IS_COLLECTSTATIC_COMMAND:
        raise ImproperlyConfigured(
            "در production، CSRF_TRUSTED_ORIGINS نباید خالی باشد."
        )

# OTP / SMS
SMS_PROVIDER = env("SMS_PROVIDER", default="disabled").strip().lower()
SMS_OTP_ENABLED = env.bool("SMS_OTP_ENABLED", default=False)
SMS_OTP_CODE_LENGTH = env.int("SMS_OTP_CODE_LENGTH", default=5)
SMS_DEBUG_SHOW_OTP = env.bool("SMS_DEBUG_SHOW_OTP", default=DEBUG)
OTP_EXPIRY_SECONDS = env.int("OTP_EXPIRY_SECONDS", default=180)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_COOLDOWN_SECONDS = env.int("OTP_RESEND_COOLDOWN_SECONDS", default=60)
OTP_RATE_LIMIT_FAIL_CLOSED = env.bool(
    "OTP_RATE_LIMIT_FAIL_CLOSED",
    default=True,
)
PASSWORD_RESET_SESSION_TTL_SECONDS = env.int(
    "PASSWORD_RESET_SESSION_TTL_SECONDS", default=900
)
SMSIR_API_KEY = env("SMSIR_API_KEY", default="")
SMSIR_SANDBOX_API_KEY = env("SMSIR_SANDBOX_API_KEY", default="")
SMSIR_USE_SANDBOX = env.bool("SMSIR_USE_SANDBOX", default=True)
SMSIR_SIGNUP_TEMPLATE_ID = env("SMSIR_SIGNUP_TEMPLATE_ID", default="")
SMSIR_RESET_TEMPLATE_ID = env("SMSIR_RESET_TEMPLATE_ID", default="")
SMSIR_OTP_PARAMETER_NAME = env("SMSIR_OTP_PARAMETER_NAME", default="CODE")
SMSIR_TIMEOUT_SECONDS = env.int("SMSIR_TIMEOUT_SECONDS", default=10)
SMSIR_BULK_URL = env(
    "SMSIR_BULK_URL",
    default="https://api.sms.ir/v1/send/bulk",
)

SMSIR_LINE_NUMBER = env(
    "SMSIR_LINE_NUMBER",
    default="",
).strip()

SMSIR_VERIFY_URL = env(
    "SMSIR_VERIFY_URL",
    default="https://api.sms.ir/v1/send/verify",
).strip()
SMSIR_TRANSACTIONAL_TEMPLATES_ENABLED = env.bool(
    "SMSIR_TRANSACTIONAL_TEMPLATES_ENABLED",
    default=False,
)
SMSIR_BOOKING_CREATED_TEMPLATE_ID = env(
    "SMSIR_BOOKING_CREATED_TEMPLATE_ID",
    default="",
).strip()
SMSIR_STYLIST_NEW_BOOKING_TEMPLATE_ID = env(
    "SMSIR_STYLIST_NEW_BOOKING_TEMPLATE_ID",
    default="",
).strip()
SMSIR_BOOKING_CONFIRMED_TEMPLATE_ID = env(
    "SMSIR_BOOKING_CONFIRMED_TEMPLATE_ID",
    default="",
).strip()
SMSIR_BOOKING_CANCELLED_TEMPLATE_ID = env(
    "SMSIR_BOOKING_CANCELLED_TEMPLATE_ID",
    default="",
).strip()
SMSIR_BOOKING_REMINDER_TEMPLATE_ID = env(
    "SMSIR_BOOKING_REMINDER_TEMPLATE_ID",
    default="",
).strip()
SMSIR_BOOKING_RESCHEDULED_TEMPLATE_ID = env(
    "SMSIR_BOOKING_RESCHEDULED_TEMPLATE_ID",
    default="",
).strip()


LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY = env.bool(
    "LOOMERA_SEND_NOTIFICATIONS_IMMEDIATELY",
    default=True,
)

LOOMERA_NOTIFICATION_MAX_ATTEMPTS = env.int(
    "LOOMERA_NOTIFICATION_MAX_ATTEMPTS",
    default=3,
)
CUSTOMER_NOTIFICATION_SETTINGS_MAX_BYTES = env.int(
    "CUSTOMER_NOTIFICATION_SETTINGS_MAX_BYTES",
    default=4 * 1024,
)

CUSTOMER_NOTIFICATION_SUMMARY_BODY_MAX_CHARS = env.int(
    "CUSTOMER_NOTIFICATION_SUMMARY_BODY_MAX_CHARS",
    default=500,
)

CUSTOMER_NOTIFICATION_SUMMARY_ACTION_URL_MAX_CHARS = env.int(
    "CUSTOMER_NOTIFICATION_SUMMARY_ACTION_URL_MAX_CHARS",
    default=500,
)

NOTIFICATIONS_SUMMARY_TITLE_MAX_CHARS = env.int(
    "NOTIFICATIONS_SUMMARY_TITLE_MAX_CHARS",
    default=160,
)

NOTIFICATIONS_SUMMARY_BODY_MAX_CHARS = env.int(
    "NOTIFICATIONS_SUMMARY_BODY_MAX_CHARS",
    default=500,
)

NOTIFICATIONS_SUMMARY_ACTION_URL_MAX_CHARS = env.int(
    "NOTIFICATIONS_SUMMARY_ACTION_URL_MAX_CHARS",
    default=500,
)

# GIS Libraries Path
if os.name == "nt":
    GDAL_LIBRARY_PATH = env("GDAL_LIBRARY_PATH", default=r"C:\OSGeo4W\bin\gdal311.dll")
    GEOS_LIBRARY_PATH = env("GEOS_LIBRARY_PATH", default=r"C:\OSGeo4W\bin\geos_c.dll")
    PROJ_LIBRARY_PATH = env("PROJ_LIBRARY_PATH", default=r"C:\OSGeo4W\bin\proj.dll")
else:
    GDAL_LIBRARY_PATH = env("GDAL_LIBRARY_PATH", default="")
    GEOS_LIBRARY_PATH = env("GEOS_LIBRARY_PATH", default="")
    PROJ_LIBRARY_PATH = env("PROJ_LIBRARY_PATH", default="")


# ==============================================================================
# LOGGING
# ==============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_sensitive": {
            "()": "loomera.logging_utils.SensitiveDataMaskingFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["mask_sensitive"],
        },
    },
    "loggers": {
        "accounts": {
            "handlers": ["console"],
            "level": env("ACCOUNTS_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps.accounts.services.sms": {
            "handlers": ["console"],
            "level": env("SMS_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps.orders": {
            "handlers": ["console"],
            "level": env("ORDERS_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps.salons": {
            "handlers": ["console"],
            "level": env("SALONS_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "loomera.celery": {
            "handlers": ["console"],
            "level": env("CELERY_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "apps.payments": {
            "handlers": ["console"],
            "level": env("PAYMENTS_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": env("DJANGO_SERVER_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}


# ==============================================================================
# CACHING CONFIGURATION
# ==============================================================================
if _module_available("django_redis"):
    CACHES = {
        "default": {
            "BACKEND": env("CACHE_BACKEND", default="django_redis.cache.RedisCache"),
            "LOCATION": env("CACHE_LOCATION", default="redis://127.0.0.1:6379/1"),
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "loomera-local-cache",
        }
    }


# ==============================================================================
# INFRASTRUCTURE, CACHE, BACKGROUND JOBS & MONITORING
# ==============================================================================
LOOMERA_ENVIRONMENT = env("LOOMERA_ENVIRONMENT", default="local").strip().lower()
LOOMERA_ENABLE_CELERY = env.bool("LOOMERA_ENABLE_CELERY", default=False)
LOOMERA_CELERY_BEAT_ENABLED = env.bool("LOOMERA_CELERY_BEAT_ENABLED", default=False)
CELERY_BROKER_URL = env(
    "CELERY_BROKER_URL",
    default=env("CACHE_LOCATION", default="redis://127.0.0.1:6379/1"),
)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool(
    "CELERY_TASK_ALWAYS_EAGER", default=DEBUG or not LOOMERA_ENABLE_CELERY
)
CELERY_TASK_IGNORE_RESULT = env.bool("CELERY_TASK_IGNORE_RESULT", default=True)
# Liara Redis may restrict PUB/SUB channels used by Celery remote-control/inspect.
# Keep task processing enabled, but disable remote-control/event channels by default.
CELERY_WORKER_ENABLE_REMOTE_CONTROL = env.bool(
    "CELERY_WORKER_ENABLE_REMOTE_CONTROL", default=False
)
CELERY_WORKER_SEND_TASK_EVENTS = env.bool(
    "CELERY_WORKER_SEND_TASK_EVENTS", default=False
)
CELERY_TASK_SEND_SENT_EVENT = env.bool("CELERY_TASK_SEND_SENT_EVENT", default=False)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = env.bool(
    "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP", default=True
)
CELERY_TIMEZONE = TIME_ZONE

LOOMERA_CACHE_TTL_SHORT = env.int("LOOMERA_CACHE_TTL_SHORT", default=60)
LOOMERA_CACHE_TTL_MEDIUM = env.int("LOOMERA_CACHE_TTL_MEDIUM", default=600)
LOOMERA_CACHE_TTL_LONG = env.int("LOOMERA_CACHE_TTL_LONG", default=86400)
LOOMERA_CACHE_VERSION = env("LOOMERA_CACHE_VERSION", default="v1")

LOOMERA_MAX_UPLOAD_SIZE_MB = env.int("LOOMERA_MAX_UPLOAD_SIZE_MB", default=8)
LOOMERA_IMAGE_MAX_WIDTH = env.int("LOOMERA_IMAGE_MAX_WIDTH", default=1920)
LOOMERA_IMAGE_THUMBNAIL_WIDTH = env.int("LOOMERA_IMAGE_THUMBNAIL_WIDTH", default=640)
LOOMERA_IMAGE_WEBP_QUALITY = env.int("LOOMERA_IMAGE_WEBP_QUALITY", default=82)
LOOMERA_PRIVATE_MEDIA_ROOT = env(
    "LOOMERA_PRIVATE_MEDIA_ROOT", default=os.path.join(BASE_DIR, "private_media")
)
LOOMERA_MEDIA_PROCESSING_ENABLED = env.bool(
    "LOOMERA_MEDIA_PROCESSING_ENABLED", default=True
)

LOOMERA_EXPORT_RETENTION_DAYS = env.int("LOOMERA_EXPORT_RETENTION_DAYS", default=7)
LOOMERA_NOTIFICATION_RETENTION_DAYS = env.int(
    "LOOMERA_NOTIFICATION_RETENTION_DAYS", default=180
)
LOOMERA_REPORT_EXPORT_STALE_AFTER_MINUTES = env.int(
    "LOOMERA_REPORT_EXPORT_STALE_AFTER_MINUTES",
    default=60,
)
LOOMERA_SUPPORT_ATTACHMENT_RETENTION_DAYS = env.int(
    "LOOMERA_SUPPORT_ATTACHMENT_RETENTION_DAYS", default=365
)

SENTRY_DSN = env("SENTRY_DSN", default="").strip()
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

from loomera.release import RELEASE as LOOMERA_BUILD_RELEASE

SENTRY_RELEASE = (
    env("SENTRY_RELEASE", default="").strip() or LOOMERA_BUILD_RELEASE.strip()
)

if SENTRY_DSN and _module_available("sentry_sdk"):
    import sentry_sdk

    from sentry_sdk.integrations.django import DjangoIntegration

    from apps.main.sentry_privacy import (
        sentry_before_breadcrumb,
        sentry_before_send,
        sentry_before_send_transaction,
    )

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=LOOMERA_ENVIRONMENT,
        # Privacy baseline.
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=sentry_before_send,
        before_send_transaction=sentry_before_send_transaction,
        before_breadcrumb=sentry_before_breadcrumb,
        # Performance monitoring remains disabled during privacy validation.
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        release=SENTRY_RELEASE or None,
    )
LOOMERA_API_VERSION = env("LOOMERA_API_VERSION", default="v1").strip() or "v1"
LOOMERA_PUBLIC_APP_VERSION = (
    env("LOOMERA_PUBLIC_APP_VERSION", default="beta").strip() or "beta"
)
LOOMERA_PUBLIC_BUILD_ID = env("LOOMERA_PUBLIC_BUILD_ID", default="").strip()
# ==============================================================================
USE_L10N = True  # فعال بودن localization
USE_THOUSAND_SEPARATOR = True

# =============================================================================
# Map.ir
MAPIR_API_KEY = env("MAPIR_API_KEY", default="")
MAP_PROVIDER_ENABLED = bool(MAPIR_API_KEY)
MAPIR_WMS_BASE_URL = env("MAPIR_WMS_BASE_URL", default="https://map.ir/shiveh")
MAPIR_WMS_LAYER = env("MAPIR_WMS_LAYER", default="Shiveh:Shiveh")
MAPIR_REVERSE_BASE_URL = env(
    "MAPIR_REVERSE_BASE_URL", default="https://map.ir/reverse/no"
)
MAPIR_TILE_TIMEOUT_SECONDS = env.int("MAPIR_TILE_TIMEOUT_SECONDS", default=15)
MAPIR_REVERSE_TIMEOUT_SECONDS = env.int("MAPIR_REVERSE_TIMEOUT_SECONDS", default=15)
MAPIR_UPSTREAM_RETRY_COUNT = env.int("MAPIR_UPSTREAM_RETRY_COUNT", default=1)
MAPIR_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in env(
        "MAPIR_ALLOWED_HOSTS",
        default="map.ir",
    ).split(",")
    if host.strip()
}
MAPIR_MAX_TILE_RESPONSE_BYTES = env.int(
    "MAPIR_MAX_TILE_RESPONSE_BYTES",
    default=1024 * 1024,
)
MAPIR_MAX_REVERSE_RESPONSE_BYTES = env.int(
    "MAPIR_MAX_REVERSE_RESPONSE_BYTES",
    default=256 * 1024,
)

LOOMERA_USE_DETAIL_FINANCE = True

SEARCH_JSON_BODY_MAX_BYTES = env.int(
    "SEARCH_JSON_BODY_MAX_BYTES",
    default=16 * 1024,
)
SEARCH_CLICK_POST_MAX_BYTES = env.int(
    "SEARCH_CLICK_POST_MAX_BYTES",
    default=4 * 1024,
)

ARTICLE_STORY_TRACK_POST_MAX_BYTES = env.int(
    "ARTICLE_STORY_TRACK_POST_MAX_BYTES",
    default=2 * 1024,
)

ARTICLE_CONTENT_REPORT_POST_MAX_BYTES = env.int(
    "ARTICLE_CONTENT_REPORT_POST_MAX_BYTES",
    default=8 * 1024,
)

ARTICLE_CONTENT_REPORT_DESCRIPTION_MAX_CHARS = env.int(
    "ARTICLE_CONTENT_REPORT_DESCRIPTION_MAX_CHARS",
    default=1000,
)

ARTICLE_STORY_EXPLORE_TEXT_MAX_CHARS = env.int(
    "ARTICLE_STORY_EXPLORE_TEXT_MAX_CHARS",
    default=80,
)

CUSTOMER_NOTIFICATION_ACTION_POST_MAX_BYTES = env.int(
    "CUSTOMER_NOTIFICATION_ACTION_POST_MAX_BYTES",
    default=2 * 1024,
)

CUSTOMER_PROFILE_IMAGE_MAX_DIMENSION = env.int(
    "CUSTOMER_PROFILE_IMAGE_MAX_DIMENSION",
    default=5000,
)

CUSTOMER_PROFILE_IMAGE_MAX_PIXELS = env.int(
    "CUSTOMER_PROFILE_IMAGE_MAX_PIXELS",
    default=10_000_000,
)
SALON_GALLERY_IMAGE_MAX_SIZE_BYTES = env.int(
    "SALON_GALLERY_IMAGE_MAX_SIZE_BYTES",
    default=4 * 1024 * 1024,
)

SALON_GALLERY_IMAGE_MAX_DIMENSION = env.int(
    "SALON_GALLERY_IMAGE_MAX_DIMENSION",
    default=7000,
)

SALON_GALLERY_IMAGE_MAX_PIXELS = env.int(
    "SALON_GALLERY_IMAGE_MAX_PIXELS",
    default=20_000_000,
)
WORK_SAMPLE_IMAGE_MAX_SIZE_BYTES = env.int(
    "WORK_SAMPLE_IMAGE_MAX_SIZE_BYTES",
    default=2 * 1024 * 1024,
)

WORK_SAMPLE_IMAGE_MAX_DIMENSION = env.int(
    "WORK_SAMPLE_IMAGE_MAX_DIMENSION",
    default=2500,
)

WORK_SAMPLE_IMAGE_MAX_PIXELS = env.int(
    "WORK_SAMPLE_IMAGE_MAX_PIXELS",
    default=4_000_000,
)

STYLIST_PROFILE_IMAGE_MAX_SIZE_BYTES = env.int(
    "STYLIST_PROFILE_IMAGE_MAX_SIZE_BYTES",
    default=2 * 1024 * 1024,
)

STYLIST_PROFILE_IMAGE_MAX_DIMENSION = env.int(
    "STYLIST_PROFILE_IMAGE_MAX_DIMENSION",
    default=5000,
)

STYLIST_PROFILE_IMAGE_MAX_PIXELS = env.int(
    "STYLIST_PROFILE_IMAGE_MAX_PIXELS",
    default=10_000_000,
)

ARTICLE_COVER_IMAGE_MAX_SIZE_BYTES = env.int(
    "ARTICLE_COVER_IMAGE_MAX_SIZE_BYTES",
    default=4 * 1024 * 1024,
)

ARTICLE_COVER_IMAGE_MAX_DIMENSION = env.int(
    "ARTICLE_COVER_IMAGE_MAX_DIMENSION",
    default=7000,
)

ARTICLE_COVER_IMAGE_MAX_PIXELS = env.int(
    "ARTICLE_COVER_IMAGE_MAX_PIXELS",
    default=20_000_000,
)

SUPPORT_ATTACHMENT_MAX_SIZE_BYTES = env.int(
    "SUPPORT_ATTACHMENT_MAX_SIZE_BYTES",
    default=5 * 1024 * 1024,
)

SUPPORT_ATTACHMENT_IMAGE_MAX_DIMENSION = env.int(
    "SUPPORT_ATTACHMENT_IMAGE_MAX_DIMENSION",
    default=7000,
)

SUPPORT_ATTACHMENT_IMAGE_MAX_PIXELS = env.int(
    "SUPPORT_ATTACHMENT_IMAGE_MAX_PIXELS",
    default=20_000_000,
)

LOOMERA_SUPPORT_TICKET_RATE_LIMIT_FAIL_CLOSED = env.bool(
    "LOOMERA_SUPPORT_TICKET_RATE_LIMIT_FAIL_CLOSED",
    default=False,
)

FINANCE_PAYMENT_RECEIPT_MAX_SIZE_BYTES = env.int(
    "FINANCE_PAYMENT_RECEIPT_MAX_SIZE_BYTES",
    default=5 * 1024 * 1024,
)

FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_DIMENSION = env.int(
    "FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_DIMENSION",
    default=7000,
)

FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_PIXELS = env.int(
    "FINANCE_PAYMENT_RECEIPT_IMAGE_MAX_PIXELS",
    default=20_000_000,
)

STAFF_CONTENT_MEDIA_MAX_SIZE_BYTES = env.int(
    "STAFF_CONTENT_MEDIA_MAX_SIZE_BYTES",
    default=25 * 1024 * 1024,
)

STAFF_CONTENT_MEDIA_IMAGE_MAX_DIMENSION = env.int(
    "STAFF_CONTENT_MEDIA_IMAGE_MAX_DIMENSION",
    default=7000,
)

STAFF_CONTENT_MEDIA_IMAGE_MAX_PIXELS = env.int(
    "STAFF_CONTENT_MEDIA_IMAGE_MAX_PIXELS",
    default=20_000_000,
)
CUSTOMER_NOTE_TEXT_MAX_CHARS = env.int(
    "CUSTOMER_NOTE_TEXT_MAX_CHARS",
    default=2000,
)
SERVICE_SUGGESTIONS_QUERY_MAX_CHARS = env.int(
    "SERVICE_SUGGESTIONS_QUERY_MAX_CHARS",
    default=80,
)
SEARCH_SUGGESTIONS_QUERY_MAX_CHARS = env.int(
    "SEARCH_SUGGESTIONS_QUERY_MAX_CHARS",
    default=80,
)

LOCATION_SUGGESTIONS_QUERY_MAX_CHARS = env.int(
    "LOCATION_SUGGESTIONS_QUERY_MAX_CHARS",
    default=80,
)

SALON_SEARCH_QUERY_MAX_CHARS = env.int(
    "SALON_SEARCH_QUERY_MAX_CHARS",
    default=80,
)
APPOINTMENT_ICS_TEXT_MAX_CHARS = env.int(
    "APPOINTMENT_ICS_TEXT_MAX_CHARS",
    default=300,
)
PAY_IN_SALON_SETTLEMENT_POST_MAX_BYTES = env.int(
    "PAY_IN_SALON_SETTLEMENT_POST_MAX_BYTES",
    default=2 * 1024,
)
APPOINTMENT_CHECKOUT_POST_MAX_BYTES = env.int(
    "APPOINTMENT_CHECKOUT_POST_MAX_BYTES",
    default=8 * 1024,
)

APPOINTMENT_CHECKOUT_COUPON_CODE_MAX_CHARS = env.int(
    "APPOINTMENT_CHECKOUT_COUPON_CODE_MAX_CHARS",
    default=64,
)
FINANCE_COUPON_POST_MAX_BYTES = env.int(
    "FINANCE_COUPON_POST_MAX_BYTES",
    default=8 * 1024,
)

FINANCE_COUPON_CODE_MAX_CHARS = env.int(
    "FINANCE_COUPON_CODE_MAX_CHARS",
    default=64,
)

FINANCE_COUPON_DESCRIPTION_MAX_CHARS = env.int(
    "FINANCE_COUPON_DESCRIPTION_MAX_CHARS",
    default=1000,
)
DASHBOARD_SCHEDULE_POST_MAX_BYTES = env.int(
    "DASHBOARD_SCHEDULE_POST_MAX_BYTES",
    default=16 * 1024,
)

DASHBOARD_SCHEDULE_REVIEW_NOTE_MAX_CHARS = env.int(
    "DASHBOARD_SCHEDULE_REVIEW_NOTE_MAX_CHARS",
    default=500,
)

DASHBOARD_SCHEDULE_MAX_SHIFT_ROWS = env.int(
    "DASHBOARD_SCHEDULE_MAX_SHIFT_ROWS",
    default=24,
)
FINANCE_REPORT_QUERY_MAX_CHARS = env.int(
    "FINANCE_REPORT_QUERY_MAX_CHARS",
    default=2048,
)

FINANCE_REPORT_MAX_RANGE_DAYS = env.int(
    "FINANCE_REPORT_MAX_RANGE_DAYS",
    default=370,
)

FINANCE_REPORT_EXPORT_MAX_ROWS = env.int(
    "FINANCE_REPORT_EXPORT_MAX_ROWS",
    default=5000,
)

FINANCE_EXPORT_CELL_MAX_CHARS = env.int(
    "FINANCE_EXPORT_CELL_MAX_CHARS",
    default=500,
)
SUPPORT_TICKET_POST_MAX_BYTES = env.int(
    "SUPPORT_TICKET_POST_MAX_BYTES",
    default=2 * 1024 * 1024,
)

SUPPORT_TICKET_REPLY_POST_MAX_BYTES = env.int(
    "SUPPORT_TICKET_REPLY_POST_MAX_BYTES",
    default=2 * 1024 * 1024,
)

PLATFORM_SUPPORT_QUERY_MAX_CHARS = env.int(
    "PLATFORM_SUPPORT_QUERY_MAX_CHARS",
    default=2048,
)

PLATFORM_SUPPORT_ACTION_POST_MAX_BYTES = env.int(
    "PLATFORM_SUPPORT_ACTION_POST_MAX_BYTES",
    default=16 * 1024,
)

PLATFORM_SUPPORT_ADMIN_REPLY_MAX_CHARS = env.int(
    "PLATFORM_SUPPORT_ADMIN_REPLY_MAX_CHARS",
    default=3000,
)

PLATFORM_SUPPORT_INTERNAL_NOTE_MAX_CHARS = env.int(
    "PLATFORM_SUPPORT_INTERNAL_NOTE_MAX_CHARS",
    default=2000,
)
PUBLIC_SALON_DETAIL_QUERY_MAX_CHARS = env.int(
    "PUBLIC_SALON_DETAIL_QUERY_MAX_CHARS",
    default=1024,
)

PUBLIC_SALON_REVIEW_APPOINTMENT_ID_MAX_CHARS = env.int(
    "PUBLIC_SALON_REVIEW_APPOINTMENT_ID_MAX_CHARS",
    default=20,
)
LOOMERA_API_PUBLIC_QUERY_MAX_CHARS = env.int(
    "LOOMERA_API_PUBLIC_QUERY_MAX_CHARS",
    default=256,
)
LOOMERA_API_PUBLIC_LIST_MAX_LIMIT = env.int(
    "LOOMERA_API_PUBLIC_LIST_MAX_LIMIT",
    default=50,
)
LOOMERA_API_AVAILABILITY_MAX_DAYS_AHEAD = env.int(
    "LOOMERA_API_AVAILABILITY_MAX_DAYS_AHEAD",
    default=45,
)
LOOMERA_API_AVAILABILITY_MAX_SLOTS_PER_STYLIST = env.int(
    "LOOMERA_API_AVAILABILITY_MAX_SLOTS_PER_STYLIST",
    default=40,
)
LOOMERA_API_NEXT_AVAILABLE_MAX_DAYS = env.int(
    "LOOMERA_API_NEXT_AVAILABLE_MAX_DAYS",
    default=14,
)
LOOMERA_API_AUTH_OTP_LENGTH = env.int(
    "LOOMERA_API_AUTH_OTP_LENGTH",
    default=6,
)
LOOMERA_API_AUTH_OTP_TTL_SECONDS = env.int(
    "LOOMERA_API_AUTH_OTP_TTL_SECONDS",
    default=120,
)
LOOMERA_API_AUTH_OTP_RESEND_SECONDS = env.int(
    "LOOMERA_API_AUTH_OTP_RESEND_SECONDS",
    default=60,
)
LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS = env.int(
    "LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS",
    default=5,
)
LOOMERA_API_AUTH_PHONE_REGION = env(
    "LOOMERA_API_AUTH_PHONE_REGION",
    default="IR",
).strip()
LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES = env.int(
    "LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES",
    default=2 * 1024,
)
LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR = env.int(
    "LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR",
    default=5,
)
LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR = env.int(
    "LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR",
    default=30,
)
LOOMERA_API_AUTH_OTP_CACHE_PREFIX = env(
    "LOOMERA_API_AUTH_OTP_CACHE_PREFIX",
    default="loomera:api-auth-otp",
).strip()
LOOMERA_API_AUTH_OTP_FAIL_CLOSED = env.bool(
    "LOOMERA_API_AUTH_OTP_FAIL_CLOSED",
    default=True,
)
LOOMERA_API_BOOKING_DRAFT_MAX_BYTES = env.int(
    "LOOMERA_API_BOOKING_DRAFT_MAX_BYTES",
    default=4 * 1024,
)

# Loomera SMS.ir Stage 3 safety controls
SMSIR_TRANSACTIONAL_LINKS_ENABLED = env.bool(
    "SMSIR_TRANSACTIONAL_LINKS_ENABLED",
    default=False,
)
SMSIR_BULK_NOTIFICATIONS_ENABLED = env.bool(
    "SMSIR_BULK_NOTIFICATIONS_ENABLED",
    default=False,
)
SMS_PUBLIC_BASE_URL = (
    env(
        "SMS_PUBLIC_BASE_URL",
        default="",
    )
    .strip()
    .rstrip("/")
)


HELP_AI_ENABLED = env.bool(
    "HELP_AI_ENABLED",
    default=True,
)

GROQ_API_KEY = env(
    "GROQ_API_KEY",
    default="",
).strip()

HELP_AI_MODEL = env(
    "HELP_AI_MODEL",
    default="qwen/qwen3-32b",
).strip()

HELP_AI_TIMEOUT_SECONDS = env.int(
    "HELP_AI_TIMEOUT_SECONDS",
    default=12,
)

HELP_CHAT_GUEST_LIMIT = env.int(
    "HELP_CHAT_GUEST_LIMIT",
    default=10,
)

HELP_CHAT_USER_LIMIT = env.int(
    "HELP_CHAT_USER_LIMIT",
    default=30,
)

HELP_CHAT_RATE_WINDOW_SECONDS = env.int(
    "HELP_CHAT_RATE_WINDOW_SECONDS",
    default=3600,
)

HELP_SUPPORT_HANDOFF_LIMIT = env.int(
    "HELP_SUPPORT_HANDOFF_LIMIT",
    default=3,
)

HELP_SUPPORT_HANDOFF_WINDOW_SECONDS = env.int(
    "HELP_SUPPORT_HANDOFF_WINDOW_SECONDS",
    default=3600,
)

HELP_CONVERSATION_RETENTION_DAYS = env.int(
    "HELP_CONVERSATION_RETENTION_DAYS",
    default=30,
)
