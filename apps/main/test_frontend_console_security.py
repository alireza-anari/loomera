from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class FrontendConsoleSecurityTests(SimpleTestCase):
    FORBIDDEN_CONSOLE_PATTERN = re.compile(r"\bconsole\.(?:log|debug|info|trace)\s*\(")

    def _project_frontend_files(self):
        roots = [
            Path(settings.BASE_DIR) / "static",
            Path(settings.BASE_DIR) / "templates",
        ]

        for root in roots:
            if not root.exists():
                continue

            for path in root.rglob("*"):
                if path.suffix not in {".js", ".html"}:
                    continue

                relative_parts = path.relative_to(settings.BASE_DIR).parts

                if "vendor" in relative_parts:
                    continue
                if "node_modules" in relative_parts:
                    continue
                if "__pycache__" in relative_parts:
                    continue

                yield path

    def test_project_frontend_has_no_debug_console_calls(self):
        violations = []

        for path in self._project_frontend_files():
            source = path.read_text(encoding="utf-8", errors="ignore")

            for line_number, line in enumerate(source.splitlines(), start=1):
                if not self.FORBIDDEN_CONSOLE_PATTERN.search(line):
                    continue

                violations.append(
                    f"{path.relative_to(settings.BASE_DIR)}:{line_number}"
                )

        self.assertEqual(
            violations,
            [],
            msg=(
                "Frontend runtime must not contain console.log/debug/info/trace. "
                "Remove the debug output or use an approved diagnostic path: "
                + ", ".join(violations)
            ),
        )

    def test_vendor_files_are_not_part_of_project_console_policy(self):
        inspected_paths = {
            path.relative_to(settings.BASE_DIR)
            for path in self._project_frontend_files()
        }

        self.assertFalse(any("vendor" in path.parts for path in inspected_paths))
