from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class RuntimeDebugOutputSecurityTests(SimpleTestCase):
    def _runtime_python_files(self):
        roots = [
            Path(settings.BASE_DIR) / "apps",
            Path(settings.BASE_DIR) / "loomera",
            Path(settings.BASE_DIR) / "middlewares",
        ]

        for root in roots:
            for path in root.rglob("*.py"):
                relative_parts = path.relative_to(settings.BASE_DIR).parts

                if "migrations" in relative_parts:
                    continue
                if "__pycache__" in relative_parts:
                    continue
                if "tests" in relative_parts:
                    continue
                if path.name == "tests.py":
                    continue
                if path.name.startswith("test_"):
                    continue

                yield path

    def test_runtime_python_code_does_not_call_builtin_print(self):
        violations = []

        for path in self._runtime_python_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name):
                    continue
                if node.func.id != "print":
                    continue

                violations.append(
                    f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}"
                )

        self.assertEqual(
            violations,
            [],
            msg=(
                "Runtime print() calls are not allowed. "
                "Use a configured logger instead: " + ", ".join(violations)
            ),
        )

    def test_celery_debug_task_does_not_dump_request_representation(self):
        celery_path = Path(settings.BASE_DIR) / "loomera" / "celery.py"
        source = celery_path.read_text(encoding="utf-8")

        self.assertNotIn("self.request!r", source)
        self.assertNotIn("print(", source)

    def test_new_runtime_loggers_use_masked_console_handler(self):
        logging_config = settings.LOGGING

        console_filters = logging_config["handlers"]["console"].get("filters", [])
        self.assertIn("mask_sensitive", console_filters)

        for logger_name in ["apps.salons", "loomera.celery"]:
            logger_config = logging_config["loggers"][logger_name]

            self.assertEqual(logger_config["handlers"], ["console"])
            self.assertFalse(logger_config["propagate"])
