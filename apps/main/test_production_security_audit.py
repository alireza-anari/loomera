from __future__ import annotations

import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.main.management.commands.production_security_audit import (
    run_production_security_audit,
)


class ProductionSecurityAuditTests(SimpleTestCase):
    @override_settings(
        DEBUG=True,
        SECRET_KEY="dev-secret",
        ALLOWED_HOSTS=["*"],
        CSRF_TRUSTED_ORIGINS=[],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_SSL_REDIRECT=False,
        SECURE_PROXY_SSL_HEADER=None,
        SECURE_HSTS_SECONDS=0,
        X_FRAME_OPTIONS="",
        SECURE_CONTENT_TYPE_NOSNIFF=False,
        SESSION_COOKIE_SAMESITE="",
        CSRF_COOKIE_SAMESITE="",
        STATIC_URL="/static/",
        MEDIA_URL="/media/",
    )
    def test_audit_flags_unsafe_production_settings(self):
        issues = run_production_security_audit(strict=True)
        codes = {issue.code for issue in issues}

        self.assertIn("SECURITY_DEBUG_ENABLED", codes)
        self.assertIn("SECURITY_ALLOWED_HOSTS_UNSAFE", codes)
        self.assertIn("SECURITY_SECRET_KEY_UNSAFE", codes)
        self.assertIn("SECURITY_SESSION_COOKIE_NOT_SECURE", codes)
        self.assertIn("SECURITY_CSRF_COOKIE_NOT_SECURE", codes)

    @override_settings(
        DEBUG=False,
        SECRET_KEY="x" * 64,
        ALLOWED_HOSTS=["loomera.example", "www.loomera.example"],
        CSRF_TRUSTED_ORIGINS=[
            "https://loomera.example",
            "https://www.loomera.example",
        ],
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
        SECURE_HSTS_SECONDS=3600,
        X_FRAME_OPTIONS="DENY",
        SECURE_CONTENT_TYPE_NOSNIFF=True,
        SESSION_COOKIE_SAMESITE="Lax",
        CSRF_COOKIE_SAMESITE="Lax",
        STATIC_URL="/static/",
        MEDIA_URL="https://cdn.loomera.example/media/",
    )
    def test_audit_accepts_safe_baseline_settings(self):
        issues = run_production_security_audit(strict=True)
        error_codes = {issue.code for issue in issues if issue.severity == "error"}

        self.assertEqual(error_codes, set())

    @override_settings(
        DEBUG=True,
        SECRET_KEY="dev-secret",
        ALLOWED_HOSTS=["*"],
        CSRF_TRUSTED_ORIGINS=[],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
    )
    def test_strict_command_fails_with_error_issues(self):
        out = io.StringIO()

        with self.assertRaises(CommandError):
            call_command("production_security_audit", "--strict", stdout=out)

    @override_settings(
        DEBUG=True,
        SECRET_KEY="dev-secret",
        ALLOWED_HOSTS=["*"],
        CSRF_TRUSTED_ORIGINS=[],
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
    )
    def test_json_output_does_not_include_secret_value(self):
        out = io.StringIO()

        try:
            call_command("production_security_audit", "--json", stdout=out)
        except CommandError:
            self.fail("Non-strict JSON audit should not raise CommandError.")

        payload = json.loads(out.getvalue())

        self.assertIn("issues", payload)
        self.assertNotIn("dev-secret", out.getvalue())
