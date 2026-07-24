from __future__ import annotations

import json
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.urls import Resolver404, resolve


class Command(BaseCommand):
    help = "Check Loomera App API v1 readiness before app/staging rollout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Output machine-readable JSON.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with error when readiness errors are found.",
        )
        parser.add_argument(
            "--require-remote-cache",
            action="store_true",
            help="Fail if the default cache backend is local memory.",
        )
        parser.add_argument(
            "--require-online-payment-disabled",
            action="store_true",
            help="Fail if ONLINE_PAYMENT_ENABLED is enabled.",
        )

    def handle(self, *args, **options):
        checks = []

        self._check_url_routes(checks)
        self._check_drf_settings(checks)
        self._check_api_settings(checks)
        self._check_cache(checks, require_remote_cache=options["require_remote_cache"])
        self._check_payment_policy(
            checks,
            require_online_payment_disabled=options["require_online_payment_disabled"],
        )

        errors = [
            check
            for check in checks
            if check["status"] == "fail" and check["severity"] == "error"
        ]
        warnings = [check for check in checks if check["status"] == "warn"]

        payload = {
            "ok": not errors,
            "summary": {
                "total": len(checks),
                "errors": len(errors),
                "warnings": len(warnings),
            },
            "checks": checks,
        }

        if options["json_output"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            self._write_text_report(payload)

        if options["strict"] and errors:
            raise CommandError("App API readiness check failed.")

    def _add_check(
        self,
        checks,
        *,
        code,
        ok,
        message,
        severity="error",
        details=None,
    ):
        if ok:
            status = "pass"
        elif severity == "warning":
            status = "warn"
        else:
            status = "fail"

        checks.append(
            {
                "code": code,
                "status": status,
                "severity": severity,
                "message": message,
                "details": details or {},
            }
        )

    def _check_url_routes(self, checks):
        route_paths = [
            ("route_health", "/api/v1/health/"),
            ("route_meta", "/api/v1/meta/"),
            ("route_public_salons", "/api/v1/salons/"),
            ("route_public_salon_detail", "/api/v1/salons/readiness-salon/"),
            (
                "route_public_salon_services",
                "/api/v1/salons/readiness-salon/services/",
            ),
            (
                "route_public_salon_stylists",
                "/api/v1/salons/readiness-salon/stylists/",
            ),
            (
                "route_public_salon_availability",
                "/api/v1/salons/readiness-salon/availability/",
            ),
            (
                "route_public_salon_next_available",
                "/api/v1/salons/readiness-salon/next-available/",
            ),
            ("route_public_services", "/api/v1/services/"),
            ("route_auth_status", "/api/v1/auth/status/"),
            ("route_auth_me", "/api/v1/auth/me/"),
            ("route_auth_policy", "/api/v1/auth/policy/"),
            ("route_otp_request", "/api/v1/auth/otp/request/"),
            ("route_otp_verify", "/api/v1/auth/otp/verify/"),
            ("route_auth_logout", "/api/v1/auth/logout/"),
            ("route_booking_draft_validate", "/api/v1/bookings/draft/validate/"),
            ("route_booking_draft_summary", "/api/v1/bookings/draft/summary/"),
            ("route_booking_confirm", "/api/v1/bookings/confirm/"),
            ("route_my_appointments", "/api/v1/me/appointments/"),
            ("route_my_appointment_detail", "/api/v1/me/appointments/1/"),
        ]

        for code, path in route_paths:
            try:
                resolve(path)
            except Resolver404:
                self._add_check(
                    checks,
                    code=code,
                    ok=False,
                    message=f"API route is not registered: {path}",
                    details={"path": path},
                )
            except Exception as exc:
                self._add_check(
                    checks,
                    code=code,
                    ok=False,
                    message=f"API route could not be resolved safely: {path}",
                    details={"path": path, "error": str(exc)},
                )
            else:
                self._add_check(
                    checks,
                    code=code,
                    ok=True,
                    message=f"API route is registered: {path}",
                    details={"path": path},
                )

    def _check_drf_settings(self, checks):
        rest_framework = getattr(settings, "REST_FRAMEWORK", {}) or {}

        renderer_classes = rest_framework.get("DEFAULT_RENDERER_CLASSES", [])
        parser_classes = rest_framework.get("DEFAULT_PARSER_CLASSES", [])
        authentication_classes = rest_framework.get(
            "DEFAULT_AUTHENTICATION_CLASSES", []
        )
        permission_classes = rest_framework.get("DEFAULT_PERMISSION_CLASSES", [])

        self._add_check(
            checks,
            code="drf_json_renderer",
            ok="rest_framework.renderers.JSONRenderer" in renderer_classes,
            message="DRF default renderer includes JSONRenderer.",
            details={"DEFAULT_RENDERER_CLASSES": renderer_classes},
        )
        self._add_check(
            checks,
            code="drf_json_parser",
            ok="rest_framework.parsers.JSONParser" in parser_classes,
            message="DRF default parsers include JSONParser.",
            details={"DEFAULT_PARSER_CLASSES": parser_classes},
        )
        self._add_check(
            checks,
            code="drf_session_authentication",
            ok=(
                "rest_framework.authentication.SessionAuthentication"
                in authentication_classes
            ),
            message="DRF default authentication includes SessionAuthentication.",
            details={"DEFAULT_AUTHENTICATION_CLASSES": authentication_classes},
        )
        self._add_check(
            checks,
            code="drf_default_permission_authenticated",
            ok="rest_framework.permissions.IsAuthenticated" in permission_classes,
            message="DRF default permission is authenticated by default.",
            details={"DEFAULT_PERMISSION_CLASSES": permission_classes},
        )

    def _check_api_settings(self, checks):
        required_positive_int_settings = [
            "LOOMERA_API_PUBLIC_QUERY_MAX_CHARS",
            "LOOMERA_API_PUBLIC_LIST_MAX_LIMIT",
            "LOOMERA_API_AVAILABILITY_MAX_DAYS_AHEAD",
            "LOOMERA_API_AVAILABILITY_MAX_SLOTS_PER_STYLIST",
            "LOOMERA_API_NEXT_AVAILABLE_MAX_DAYS",
            "LOOMERA_API_AUTH_OTP_LENGTH",
            "LOOMERA_API_AUTH_OTP_TTL_SECONDS",
            "LOOMERA_API_AUTH_OTP_RESEND_SECONDS",
            "LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS",
            "LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES",
            "LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR",
            "LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR",
            "LOOMERA_API_BOOKING_DRAFT_MAX_BYTES",
        ]

        for setting_name in required_positive_int_settings:
            value = getattr(settings, setting_name, None)
            self._add_check(
                checks,
                code=f"setting_{setting_name.lower()}",
                ok=isinstance(value, int) and value > 0,
                message=f"{setting_name} is configured as a positive integer.",
                details={"value": value},
            )

        api_version = getattr(settings, "LOOMERA_API_VERSION", "")
        self._add_check(
            checks,
            code="setting_loomera_api_version",
            ok=bool(str(api_version).strip()),
            message="LOOMERA_API_VERSION is configured.",
            details={"value": api_version},
        )

        public_app_version = getattr(settings, "LOOMERA_PUBLIC_APP_VERSION", "")
        self._add_check(
            checks,
            code="setting_loomera_public_app_version",
            ok=bool(str(public_app_version).strip()),
            message="LOOMERA_PUBLIC_APP_VERSION is configured.",
            details={"value": public_app_version},
        )

        otp_cache_prefix = getattr(settings, "LOOMERA_API_AUTH_OTP_CACHE_PREFIX", "")
        self._add_check(
            checks,
            code="setting_otp_cache_prefix",
            ok=bool(str(otp_cache_prefix).strip()),
            message="OTP cache prefix is configured.",
            details={"value": otp_cache_prefix},
        )

        otp_fail_closed = getattr(settings, "LOOMERA_API_AUTH_OTP_FAIL_CLOSED", None)
        self._add_check(
            checks,
            code="setting_otp_fail_closed",
            ok=otp_fail_closed is True,
            message="OTP auth cache policy is fail-closed.",
            details={"value": otp_fail_closed},
        )

    def _check_cache(self, checks, *, require_remote_cache):
        configured_backend = (
            getattr(settings, "CACHES", {}).get("default", {}).get("BACKEND", "")
        )
        runtime_backend = f"{cache.__class__.__module__}.{cache.__class__.__name__}"

        backend_identity = " ".join(
            str(part)
            for part in [
                configured_backend,
                runtime_backend,
            ]
            if part
        ).lower()

        is_locmem = "locmem" in backend_identity

        cache_probe_ok, cache_probe_error = self._cache_probe()

        self._add_check(
            checks,
            code="cache_probe",
            ok=cache_probe_ok,
            message="Default cache backend can write/read/delete readiness probe key.",
            details={
                "configured_backend": configured_backend,
                "runtime_backend": runtime_backend,
                "error": cache_probe_error,
            },
        )

        severity = "error" if require_remote_cache else "warning"
        self._add_check(
            checks,
            code="cache_remote_backend",
            ok=not is_locmem,
            message=(
                "Default cache backend is remote/shared. "
                "LocMemCache is acceptable only for Local development."
            ),
            severity=severity,
            details={
                "configured_backend": configured_backend,
                "runtime_backend": runtime_backend,
                "require_remote_cache": require_remote_cache,
            },
        )

    def _cache_probe(self):
        key = f"loomera:api-readiness:{uuid.uuid4().hex}"
        value = "ok"

        try:
            cache.set(key, value, timeout=10)
            ok = cache.get(key) == value
            return ok, ""
        except Exception as exc:
            return False, str(exc)
        finally:
            try:
                cache.delete(key)
            except Exception:
                pass

    def _check_payment_policy(self, checks, *, require_online_payment_disabled):
        online_payment_enabled = getattr(settings, "ONLINE_PAYMENT_ENABLED", None)

        if require_online_payment_disabled:
            self._add_check(
                checks,
                code="payment_online_disabled",
                ok=online_payment_enabled is False,
                message="ONLINE_PAYMENT_ENABLED is disabled for current app booking rollout.",
                details={"ONLINE_PAYMENT_ENABLED": online_payment_enabled},
            )
            return

        self._add_check(
            checks,
            code="payment_online_policy_visible",
            ok=online_payment_enabled is False,
            message=(
                "ONLINE_PAYMENT_ENABLED is disabled. "
                "If enabled later, booking API still needs a dedicated online-payment phase."
            ),
            severity="warning",
            details={"ONLINE_PAYMENT_ENABLED": online_payment_enabled},
        )

    def _write_text_report(self, payload):
        if payload["ok"]:
            self.stdout.write(self.style.SUCCESS("App API readiness: OK"))
        else:
            self.stdout.write(self.style.ERROR("App API readiness: FAILED"))

        summary = payload["summary"]
        self.stdout.write(
            f"Total: {summary['total']} | "
            f"Errors: {summary['errors']} | "
            f"Warnings: {summary['warnings']}"
        )

        for check in payload["checks"]:
            status = check["status"].upper()
            line = f"[{status}] {check['code']}: {check['message']}"

            if check["status"] == "pass":
                self.stdout.write(self.style.SUCCESS(line))
            elif check["status"] == "warn":
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(self.style.ERROR(line))
