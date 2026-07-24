from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MessagingManagementCommandExceptionScopeTests(
    SimpleTestCase
):
    COMMANDS_DIR = (
        Path(settings.BASE_DIR)
        / "apps"
        / "messaging"
        / "management"
        / "commands"
    )

    EXPECTED_COMMAND_FILES = {
        "bale_account_link_check.py",
        "bale_delivery_queue_check.py",
        "bale_final_readiness_check.py",
        "bale_webhook_admin.py",
        "bale_webhook_event_check.py",
        "messaging_qa_check.py",
    }

    ALLOWED_EXCEPTION_NAMES = {
        "TypeError",
        "ValueError",
        "NoReverseMatch",
        "BaleBotApiError",
        "BaleWebhookIgnored",
    }

    @classmethod
    def _command_paths(cls):
        return sorted(
            path
            for path in cls.COMMANDS_DIR.glob("*.py")
            if path.name != "__init__.py"
        )

    @staticmethod
    def _exception_names(node):
        if node is None:
            return {"<bare>"}

        if isinstance(node, ast.Name):
            return {node.id}

        if isinstance(node, ast.Attribute):
            return {node.attr}

        if isinstance(node, ast.Tuple):
            names = set()

            for item in node.elts:
                names.update(
                    MessagingManagementCommandExceptionScopeTests
                    ._exception_names(item)
                )

            return names

        return {ast.unparse(node)}

    def test_expected_management_commands_are_scanned(self):
        discovered = {
            path.name
            for path in self._command_paths()
        }

        self.assertEqual(
            discovered,
            self.EXPECTED_COMMAND_FILES,
            msg=(
                "Messaging command inventory changed. "
                "Review the new or removed command before updating "
                "the exception-scope guard."
            ),
        )

    def test_commands_have_no_bare_or_broad_exception_handlers(
        self,
    ):
        violations = []

        for path in self._command_paths():
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

                names = self._exception_names(
                    node.type
                )

                forbidden = names.intersection(
                    {
                        "<bare>",
                        "Exception",
                        "BaseException",
                    }
                )

                if not forbidden:
                    continue

                violations.append(
                    (
                        f"{path.relative_to(settings.BASE_DIR)}:"
                        f"{node.lineno} "
                        f"({', '.join(sorted(forbidden))})"
                    )
                )

        self.assertEqual(
            violations,
            [],
            msg=(
                "Messaging management commands must not use "
                "bare except, Exception, or BaseException. "
                "Catch the expected parsing, routing, provider, "
                "or domain exception instead: "
                + ", ".join(violations)
            ),
        )

    def test_command_exception_handlers_are_domain_specific(
        self,
    ):
        violations = []

        for path in self._command_paths():
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

                names = self._exception_names(
                    node.type
                )
                unexpected = (
                    names
                    - self.ALLOWED_EXCEPTION_NAMES
                )

                if not unexpected:
                    continue

                violations.append(
                    (
                        f"{path.relative_to(settings.BASE_DIR)}:"
                        f"{node.lineno} "
                        f"({', '.join(sorted(unexpected))})"
                    )
                )

        self.assertEqual(
            violations,
            [],
            msg=(
                "An unreviewed exception type was added to a "
                "Messaging/Bale management command. Verify that "
                "the handler cannot hide database, network, or "
                "programming failures before allowing it: "
                + ", ".join(violations)
            ),
        )

    def test_current_command_exception_contract(self):
        expected = {
            "bale_account_link_check.py": [],
            "bale_delivery_queue_check.py": [],
            "bale_final_readiness_check.py": [],
            "bale_webhook_admin.py": [
                {"NoReverseMatch"},
                {"BaleBotApiError"},
                {"BaleBotApiError"},
                {"BaleBotApiError"},
            ],
            "bale_webhook_event_check.py": [
                {"BaleWebhookIgnored"},
            ],
            "messaging_qa_check.py": [
                {"TypeError", "ValueError"},
                {"NoReverseMatch"},
            ],
        }

        actual = {}

        for path in self._command_paths():
            source = path.read_text(
                encoding="utf-8"
            )
            tree = ast.parse(
                source,
                filename=str(path),
            )

            handlers = []

            for node in ast.walk(tree):
                if not isinstance(
                    node,
                    ast.ExceptHandler,
                ):
                    continue

                handlers.append(
                    (
                        node.lineno,
                        self._exception_names(
                            node.type
                        ),
                    )
                )

            handlers.sort(
                key=lambda item: item[0]
            )
            actual[path.name] = [
                names
                for _line_number, names in handlers
            ]

        self.assertEqual(
            actual,
            expected,
            msg=(
                "The management-command exception contract changed. "
                "Review whether the new handler is truly limited and "
                "does not hide provider, database, or programming "
                "errors."
            ),
        )
