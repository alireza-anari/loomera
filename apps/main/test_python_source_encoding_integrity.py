from __future__ import annotations

import ast
import io
from pathlib import Path
import re
import tokenize

from django.conf import settings
from django.test import SimpleTestCase


class PythonSourceEncodingIntegrityTests(SimpleTestCase):
    target_files = (
        "apps/payments/gateways.py",
        "apps/payments/test_gateway_init_response_parsing.py",
        "apps/orders/test_reschedule_payload_exception_scope.py",
        "apps/api/v1/auth_otp.py",
        "apps/orders/views.py",
    )

    def test_python_strings_and_comments_have_no_question_mark_runs(self):
        violations = []
        apps_root = Path(settings.BASE_DIR) / "apps"

        for path in apps_root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            source = path.read_text(encoding="utf-8")
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)

            for token in tokens:
                if token.type not in {tokenize.STRING, tokenize.COMMENT}:
                    continue
                if re.search(r"\?{3,}", token.string):
                    violations.append(
                        f"{path.relative_to(settings.BASE_DIR)}:{token.start[0]}"
                    )

        self.assertEqual(violations, [])

    def test_recovered_sources_are_valid_utf8_and_compile(self):
        for relative_path in self.target_files:
            with self.subTest(path=relative_path):
                path = Path(settings.BASE_DIR) / relative_path
                source = path.read_bytes().decode("utf-8")
                compile(source, str(path), "exec")

    def test_gateway_recovery_messages_are_readable(self):
        path = Path(settings.BASE_DIR) / "apps/payments/gateways.py"
        source = path.read_text(encoding="utf-8")

        self.assertIn(
            "ساختار پاسخ درگاه معتبر نبود.",
            source,
        )
        self.assertIn(
            "کد نتیجه درگاه معتبر نبود.",
            source,
        )

    def test_recovered_internal_docstrings_are_readable(self):
        checks = (
            (
                "apps/api/v1/auth_otp.py",
                "_cache_delete",
            ),
            (
                "apps/orders/views.py",
                "_order_detail_date_field_kind",
            ),
        )

        for relative_path, function_name in checks:
            with self.subTest(function=function_name):
                path = Path(settings.BASE_DIR) / relative_path
                tree = ast.parse(path.read_text(encoding="utf-8"))
                function = next(
                    node
                    for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == function_name
                )
                docstring = ast.get_docstring(function) or ""
                self.assertTrue(docstring.strip())
                self.assertNotRegex(docstring, r"\?{3,}")
