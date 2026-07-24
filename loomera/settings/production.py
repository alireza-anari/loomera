from .base import *

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=ALLOWED_HOSTS)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=CSRF_TRUSTED_ORIGINS,
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
SESSION_COOKIE_HTTPONLY = env.bool("SESSION_COOKIE_HTTPONLY", default=True)
CSRF_COOKIE_HTTPONLY = env.bool("CSRF_COOKIE_HTTPONLY", default=False)
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", default="Lax")

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = env("SECURE_REFERRER_POLICY", default="same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = env(
    "SECURE_CROSS_ORIGIN_OPENER_POLICY",
    default="same-origin",
)

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

WSGI_APPLICATION = "loomera.wsgi.application"
ASGI_APPLICATION = "loomera.asgi.application"

STATIC_ROOT = env("STATIC_ROOT", default=os.path.join(BASE_DIR, "staticfiles")).strip()

try:
    STORAGES
except NameError:
    STORAGES = {}

STORAGES.setdefault(
    "default",
    {"BACKEND": "django.core.files.storage.FileSystemStorage"},
)

STORAGES["staticfiles"] = {
    "BACKEND": env(
        "STATICFILES_STORAGE_BACKEND",
        default="whitenoise.storage.CompressedStaticFilesStorage",
    )
}

WHITENOISE_MANIFEST_STRICT = env.bool(
    "WHITENOISE_MANIFEST_STRICT",
    default=False,
)
