from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from apps.orders.templatetags import jalali_filters


class SensitiveBareExceptionGuardTests(SimpleTestCase):
    SENSITIVE_APPS = (
        "payments",
        "orders",
        "api",
        "messaging",
        "bale_bot",
    )

    JALALI_PARSE_FILTERS = (
        jalali_filters.jalali,
        jalali_filters.jalali_long,
        jalali_filters.jalali_with_weekday,
        jalali_filters.jalali_short,
        jalali_filters.time_ago,
    )

    @classmethod
    def _production_python_files(cls):
        for app_name in cls.SENSITIVE_APPS:
            app_root = (
                Path(settings.BASE_DIR)
                / "apps"
                / app_name
            )

            for path in app_root.rglob("*.py"):
                relative_parts = path.relative_to(
                    settings.BASE_DIR
                ).parts
                filename = path.name

                if "migrations" in relative_parts:
                    continue
                if "__pycache__" in relative_parts:
                    continue
                if "tests" in relative_parts:
                    continue
                if filename == "tests.py":
                    continue
                if filename.startswith("test_"):
                    continue

                yield path

    def test_sensitive_production_code_has_no_bare_except(self):
        violations = []

        for path in self._production_python_files():
            source = path.read_text(
                encoding="utf-8"
            )
            tree = ast.parse(
                source,
                filename=str(path),
            )

            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    ast.ExceptHandler,
                ):
                    continue

                if node.type is not None:
                    continue

                violations.append(
                    (
                        f"{path.relative_to(settings.BASE_DIR)}:"
                        f"{node.lineno}"
                    )
                )

        self.assertEqual(
            violations,
            [],
            msg=(
                "Sensitive production code must not use bare "
                "except because it also catches SystemExit and "
                "KeyboardInterrupt: "
                + ", ".join(violations)
            ),
        )

    def test_sensitive_production_code_does_not_catch_base_exception(
        self,
    ):
        violations = []

        for path in self._production_python_files():
            source = path.read_text(
                encoding="utf-8"
            )
            tree = ast.parse(
                source,
                filename=str(path),
            )

            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    ast.ExceptHandler,
                ):
                    continue

                if (
                    isinstance(node.type, ast.Name)
                    and node.type.id == "BaseException"
                ):
                    violations.append(
                        (
                            f"{path.relative_to(settings.BASE_DIR)}:"
                            f"{node.lineno}"
                        )
                    )

        self.assertEqual(
            violations,
            [],
            msg=(
                "Sensitive production code must not catch "
                "BaseException: "
                + ", ".join(violations)
            ),
        )

    def test_invalid_date_strings_keep_existing_fallback(self):
        invalid_value = "not-a-gregorian-date"

        for filter_function in self.JALALI_PARSE_FILTERS:
            with self.subTest(
                filter=filter_function.__name__
            ):
                self.assertEqual(
                    filter_function(invalid_value),
                    invalid_value,
                )

    def test_system_exit_from_parser_is_not_swallowed(self):
        exploding_datetime = SimpleNamespace(
            strptime=lambda *_args, **_kwargs: (
                (_ for _ in ()).throw(
                    SystemExit("stop")
                )
            )
        )

        with patch.object(
            jalali_filters,
            "datetime",
            exploding_datetime,
        ):
            for filter_function in self.JALALI_PARSE_FILTERS:
                with self.subTest(
                    filter=filter_function.__name__
                ):
                    with self.assertRaises(SystemExit):
                        filter_function("2026-07-11")

    def test_jalali_string_parsers_catch_value_error_only(self):
        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "orders"
            / "templatetags"
            / "jalali_filters.py"
        )
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        target_names = {
            "jalali",
            "jalali_long",
            "jalali_with_weekday",
            "jalali_short",
            "time_ago",
        }
        actual = {}

        def is_datetime_strptime_call(candidate):
            if not isinstance(candidate, ast.Call):
                return False

            function = candidate.func

            return (
                isinstance(function, ast.Attribute)
                and function.attr == "strptime"
                and isinstance(function.value, ast.Name)
                and function.value.id == "datetime"
            )

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name not in target_names:
                continue

            strptime_calls = [
                candidate
                for candidate in ast.walk(node)
                if is_datetime_strptime_call(candidate)
            ]

            self.assertEqual(
                len(strptime_calls),
                1,
                msg=(
                    f"{node.name} must contain exactly one "
                    "datetime.strptime call."
                ),
            )

            strptime_call = strptime_calls[0]
            call_end_line = getattr(
                strptime_call,
                "end_lineno",
                strptime_call.lineno,
            )

            containing_tries = [
                candidate
                for candidate in ast.walk(node)
                if (
                    isinstance(candidate, ast.Try)
                    and candidate.lineno
                    <= strptime_call.lineno
                    and getattr(
                        candidate,
                        "end_lineno",
                        candidate.lineno,
                    )
                    >= call_end_line
                )
            ]

            self.assertTrue(
                containing_tries,
                msg=(
                    f"{node.name} datetime.strptime call "
                    "must be protected by a try block."
                ),
            )

            direct_parser_try = min(
                containing_tries,
                key=lambda candidate: (
                    getattr(
                        candidate,
                        "end_lineno",
                        candidate.lineno,
                    )
                    - candidate.lineno,
                    -candidate.lineno,
                ),
            )

            parser_handlers = [
                (
                    ast.unparse(handler.type)
                    if handler.type is not None
                    else "<bare>"
                )
                for handler in direct_parser_try.handlers
            ]

            actual[node.name] = parser_handlers

        expected = {
            name: ["ValueError"]
            for name in target_names
        }

        self.assertEqual(actual, expected)
