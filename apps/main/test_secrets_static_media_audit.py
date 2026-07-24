from __future__ import annotations

import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.main.management.commands.secrets_static_media_audit import (
    run_secrets_static_media_audit,
)


class SecretsStaticMediaAuditTests(SimpleTestCase):
    def test_audit_flags_unsafe_secret_env_without_printing_value(self):
        secret_value = "dev-secret-value"

        with patch.dict(os.environ, {"SECRET_KEY": secret_value}, clear=False):
            issues = run_secrets_static_media_audit(strict=True)

        codes = {issue.code for issue in issues}

        self.assertIn("DEPLOYMENT_SECRET_ENV_VALUE_UNSAFE", codes)
        self.assertNotIn(
            secret_value,
            "\n".join(issue.message for issue in issues),
        )

    def test_audit_flags_static_media_root_collision(self):
        with TemporaryDirectory() as tmp:
            with self.settings(
                STATIC_ROOT=tmp,
                MEDIA_ROOT=tmp,
                STATIC_URL="/static/",
                MEDIA_URL="/media/",
            ):
                issues = run_secrets_static_media_audit(strict=True)

        codes = {issue.code for issue in issues}

        self.assertIn("DEPLOYMENT_STATIC_MEDIA_ROOT_COLLISION", codes)

    def test_audit_flags_media_root_inside_static_root(self):
        with TemporaryDirectory() as tmp:
            static_root = Path(tmp) / "static"
            media_root = static_root / "media"
            static_root.mkdir()
            media_root.mkdir()

            with self.settings(
                STATIC_ROOT=str(static_root),
                MEDIA_ROOT=str(media_root),
                STATIC_URL="/static/",
                MEDIA_URL="/media/",
            ):
                issues = run_secrets_static_media_audit(strict=True)

        codes = {issue.code for issue in issues}

        self.assertIn("DEPLOYMENT_MEDIA_ROOT_INSIDE_STATIC_ROOT", codes)

    def test_require_remote_media_storage_flags_local_filesystem_backend(self):
        with self.settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
            STATIC_URL="/static/",
            MEDIA_URL="/media/",
        ):
            issues = run_secrets_static_media_audit(
                strict=True,
                require_remote_media_storage=True,
            )

        codes = {issue.code for issue in issues}

        self.assertIn("DEPLOYMENT_MEDIA_STORAGE_LOCAL_FILESYSTEM", codes)

    def test_json_output_does_not_include_secret_value(self):
        secret_value = "dev-secret-value"

        out = io.StringIO()

        with patch.dict(os.environ, {"SECRET_KEY": secret_value}, clear=False):
            call_command("secrets_static_media_audit", "--json", stdout=out)

        payload = json.loads(out.getvalue())

        self.assertIn("issues", payload)
        self.assertNotIn(secret_value, out.getvalue())

    def test_strict_command_fails_when_error_issue_exists(self):
        with TemporaryDirectory() as tmp:
            out = io.StringIO()

            with self.settings(
                STATIC_ROOT=tmp,
                MEDIA_ROOT=tmp,
                STATIC_URL="/static/",
                MEDIA_URL="/media/",
            ):
                with self.assertRaises(CommandError):
                    call_command("secrets_static_media_audit", "--strict", stdout=out)
