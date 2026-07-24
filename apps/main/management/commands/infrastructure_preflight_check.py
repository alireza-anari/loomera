from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Check infrastructure readiness: db, cache, celery settings, media and static config."

    def _ok(self, message):
        self.stdout.write(self.style.SUCCESS(f"OK  {message}"))

    def _warn(self, message):
        self.stdout.write(self.style.WARNING(f"WARN {message}"))

    def _fail(self, message):
        self.stdout.write(self.style.ERROR(f"FAIL {message}"))
        self.failed = True

    def _environment(self) -> str:
        return str(getattr(settings, "LOOMERA_ENVIRONMENT", "local") or "local").lower()

    def _is_deployed_environment(self) -> bool:
        return self._environment() in {"staging", "production"}

    def _is_local_redis_url(self, value: str) -> bool:
        if not value:
            return False
        parsed = urlparse(value)
        return parsed.hostname in {"127.0.0.1", "localhost"}

    def _check_database(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self._ok("database")
        except Exception as exc:
            self._fail(f"database: {exc.__class__.__name__}")

        engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
        if "postgis" in engine:
            self._ok(f"database engine: {engine}")
        elif self._is_deployed_environment():
            self._fail("staging/production must use PostGIS database engine")
        else:
            self._warn(f"database engine is not PostGIS: {engine}")

    def _check_cache(self):
        try:
            cache.set("loomera:infra-preflight", "ok", timeout=30)
            if cache.get("loomera:infra-preflight") == "ok":
                self._ok("cache")
            else:
                self._fail("cache read/write mismatch")
        except Exception as exc:
            self._fail(f"cache: {exc.__class__.__name__}")

        cache_config = settings.CACHES.get("default", {})
        cache_backend = cache_config.get("BACKEND", "")
        cache_location = str(cache_config.get("LOCATION", "") or "")

        if "LocMemCache" in cache_backend and not settings.DEBUG:
            self._fail("production/staging must not use LocMemCache")
        else:
            self._ok(f"cache backend: {cache_backend}")

        if self._is_deployed_environment() and self._is_local_redis_url(cache_location):
            self._fail("staging/production cache must not point to localhost Redis")

    def _check_static_and_media(self):
        static_backend = settings.STORAGES.get("staticfiles", {}).get("BACKEND", "")
        default_backend = settings.STORAGES.get("default", {}).get("BACKEND", "")

        if static_backend:
            self._ok(f"static storage backend: {static_backend}")
        else:
            self._fail("staticfiles storage backend is not configured")

        if getattr(settings, "SERVE_MEDIA_INSECURELY", False) and not settings.DEBUG:
            self._fail("SERVE_MEDIA_INSECURELY must be False outside DEBUG")
        else:
            self._ok("media serving guard")

        use_s3_media = bool(getattr(settings, "USE_S3_MEDIA", False))
        require_object_storage = bool(
            getattr(settings, "LOOMERA_REQUIRE_OBJECT_STORAGE", False)
        )

        if use_s3_media:
            self._ok(f"media storage backend: {default_backend}")
            if (
                "storages.backends.s3" not in default_backend
                and "LoomeraS3MediaStorage" not in default_backend
            ):
                self._fail("USE_S3_MEDIA=True but default storage is not S3-compatible")

            required = [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_STORAGE_BUCKET_NAME",
                "AWS_S3_ENDPOINT_URL",
            ]
            for setting_name in required:
                if not getattr(settings, setting_name, ""):
                    self._fail(f"{setting_name} is required when USE_S3_MEDIA=True")
                else:
                    self._ok(f"{setting_name} configured")
        else:
            if self._is_deployed_environment() or require_object_storage:
                self._fail(
                    "Object Storage is required for staging/production. "
                    "Set USE_S3_MEDIA=True and configure S3 envs."
                )
            else:
                self._warn(
                    "local filesystem media storage is only acceptable for local dev"
                )

    def _check_celery_and_cron(self):
        if getattr(settings, "LOOMERA_ENABLE_CELERY", False):
            broker = getattr(settings, "CELERY_BROKER_URL", "")
            if not broker:
                self._fail("CELERY_BROKER_URL is required when celery is enabled")
            elif self._is_deployed_environment() and self._is_local_redis_url(broker):
                self._fail(
                    "staging/production CELERY_BROKER_URL must not point to localhost"
                )
            else:
                self._ok("celery broker configured")
        else:
            self._warn("celery disabled; use Liara cron + management commands")

    def _check_monitoring(self):
        if not getattr(settings, "SENTRY_DSN", ""):
            self._warn("SENTRY_DSN is not configured")
        else:
            self._ok("sentry configured")

    def handle(self, *args, **options):
        self.failed = False

        self._check_database()
        self._check_cache()
        self._check_static_and_media()
        self._check_celery_and_cron()
        self._check_monitoring()

        if self.failed:
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(
                "Infrastructure preflight passed with possible warnings."
            )
        )
