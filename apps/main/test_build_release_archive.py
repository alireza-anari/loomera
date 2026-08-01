from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.main.management.commands.build_release_archive import (
    forbidden_release_reason,
)


class BuildReleaseArchiveTests(SimpleTestCase):
    def test_environment_secret_files_are_forbidden(self):
        forbidden_paths = (
            ".env",
            ".env.local",
            ".env.staging",
            ".env.production",
            "config/.env",
            "config/.env.secret",
        )

        for path in forbidden_paths:
            with self.subTest(path=path):
                self.assertIsNotNone(forbidden_release_reason(path))

    def test_env_example_is_allowed(self):
        self.assertIsNone(forbidden_release_reason(".env.example"))

    def test_python_cache_artifacts_are_forbidden(self):
        forbidden_paths = (
            "__pycache__/module.cpython-313.pyc",
            "apps/orders/__pycache__/views.cpython-313.pyc",
            "apps/orders/views.pyc",
            "apps/orders/views.pyo",
        )

        for path in forbidden_paths:
            with self.subTest(path=path):
                self.assertIsNotNone(forbidden_release_reason(path))

    def test_database_dump_and_nested_archive_are_forbidden(self):
        forbidden_paths = (
            "backup.sql",
            "database.dump",
            "local.sqlite3",
            "exports/project.zip",
            "exports/project.tar.gz",
        )

        for path in forbidden_paths:
            with self.subTest(path=path):
                self.assertIsNotNone(forbidden_release_reason(path))

    def test_normal_project_files_are_allowed(self):
        allowed_paths = (
            "manage.py",
            "requirements.txt",
            "apps/orders/views.py",
            "static/branding/share/loomera-social-preview-v1.png",
            "templates/base.html",
        )

        for path in allowed_paths:
            with self.subTest(path=path):
                self.assertIsNone(forbidden_release_reason(path))

    def test_release_artifacts_directory_is_ignored(self):
        project_root = Path(settings.BASE_DIR)

        gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")

        liaraignore = (project_root / ".liaraignore").read_text(encoding="utf-8")

        self.assertIn(
            "/release_artifacts/",
            gitignore.splitlines(),
        )
        self.assertIn(
            "release_artifacts/",
            liaraignore.splitlines(),
        )
