from __future__ import annotations

import ast
import copy
from hashlib import sha256
import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from apps.main.sensitive_exception_inventory import stable_ast_sha256


class _DocstringStripper(ast.NodeTransformer):
    @staticmethod
    def _strip(body):
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            return body[1:]
        return body

    def visit_Module(self, node):
        node = self.generic_visit(node)
        node.body = self._strip(node.body)
        return node

    def visit_ClassDef(self, node):
        node = self.generic_visit(node)
        node.body = self._strip(node.body)
        return node

    def visit_FunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = self._strip(node.body)
        return node

    def visit_AsyncFunctionDef(self, node):
        node = self.generic_visit(node)
        node.body = self._strip(node.body)
        return node


def _hash_node_without_docstrings(node):
    clean = _DocstringStripper().visit(copy.deepcopy(node))
    ast.fix_missing_locations(clean)
    return stable_ast_sha256(clean)


def _doc_hash(doc):
    return sha256(doc.encode("utf-8")).hexdigest()


def _symbol_index(tree):
    result = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = node
            continue

        if not isinstance(node, ast.ClassDef):
            continue

        result[node.name] = node

        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[f"{node.name}.{child.name}"] = child

    return result


class MessagingBaleContractDocumentationTests(SimpleTestCase):
    manifest_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "messaging"
        / "messaging_bale_contract_manifest.json"
    )

    expected_symbols = {
        ("apps/bale_bot/views.py", "BaleWebhookView.post"),
        ("apps/bale_bot/services.py", "record_bale_webhook_update"),
        ("apps/bale_bot/services.py", "reprocess_bale_webhook_event"),
        ("apps/messaging/services.py", "connect_identity_with_raw_token"),
        ("apps/messaging/services.py", "record_webhook_event"),
        ("apps/messaging/services.py", "log_message"),
        ("apps/messaging/actions.py", "issue_action_token"),
        ("apps/messaging/actions.py", "dispatch_messaging_action_callback"),
        ("apps/bale_bot/client.py", "BaleBotClient.request"),
        ("apps/bale_bot/client.py", "BaleBotClient.send_message"),
        (
            "apps/messaging/notification_delivery.py",
            "build_actionable_reply_markup",
        ),
        (
            "apps/messaging/notification_delivery.py",
            "messaging_delivery_preference_enabled",
        ),
        (
            "apps/messaging/notification_delivery.py",
            "deliver_simple_notification",
        ),
    }

    def _state(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        sources = {}

        for relative_path in manifest["sources"]:
            path = Path(settings.BASE_DIR) / relative_path
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            sources[relative_path] = _symbol_index(tree)

        return manifest, sources

    def test_manifest_tracks_expected_contract_symbols(self):
        manifest, _ = self._state()

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(len(manifest["symbols"]), 13)
        self.assertEqual(
            {(item["source"], item["qualname"]) for item in manifest["symbols"]},
            self.expected_symbols,
        )

    def test_executable_contract_ast_matches_manifest(self):
        manifest, sources = self._state()

        for item in manifest["symbols"]:
            with self.subTest(
                source=item["source"],
                qualname=item["qualname"],
            ):
                node = sources[item["source"]][item["qualname"]]
                self.assertEqual(
                    _hash_node_without_docstrings(node),
                    item["executable_sha256"],
                )

    def test_documentation_hashes_match_manifest(self):
        manifest, sources = self._state()

        for item in manifest["symbols"]:
            with self.subTest(
                source=item["source"],
                qualname=item["qualname"],
            ):
                node = sources[item["source"]][item["qualname"]]
                doc = ast.get_docstring(node, clean=True)
                self.assertTrue(doc)
                self.assertEqual(
                    _doc_hash(doc),
                    item["documentation_sha256"],
                )

    def test_webhook_and_idempotency_contract_is_explicit(self):
        _, sources = self._state()
        expected_phrases = {
            ("apps/bale_bot/views.py", "BaleWebhookView.post"): (
                "compare_digest",
                "raw body size",
                "not dispatched again",
                "do not expose internal exception text",
            ),
            (
                "apps/bale_bot/services.py",
                "record_bale_webhook_update",
            ): (
                "provider-scoped event or update identifiers",
                "without a second inbound message log",
                "marked processed after successful handling",
            ),
            (
                "apps/bale_bot/services.py",
                "reprocess_bale_webhook_event",
            ): (
                "event row is locked",
                "bypasses duplicate detection",
                "does not create a second inbound message log",
                "administrative recovery",
            ),
            (
                "apps/messaging/services.py",
                "record_webhook_event",
            ): (
                "no stable deduplication key exists",
                "IntegrityError",
                "created flag",
            ),
        }

        for (source, qualname), phrases in expected_phrases.items():
            doc = ast.get_docstring(sources[source][qualname], clean=True) or ""
            normalized = " ".join(doc.replace("``", "").split())

            for phrase in phrases:
                with self.subTest(
                    source=source,
                    qualname=qualname,
                    phrase=phrase,
                ):
                    self.assertIn(phrase, normalized)

    def test_identity_and_action_callback_contract_is_explicit(self):
        _, sources = self._state()
        expected_phrases = {
            (
                "apps/messaging/services.py",
                "connect_identity_with_raw_token",
            ): (
                "token row is locked",
                "marked used in the same transaction",
                "does not authenticate a web session",
            ),
            (
                "apps/messaging/actions.py",
                "issue_action_token",
            ): (
                "storage uses its hash",
                "is not authorization",
                "salon scope",
            ),
            (
                "apps/messaging/actions.py",
                "dispatch_messaging_action_callback",
            ): (
                "at most once",
                "token row is locked",
                "marked used before the registered handler runs",
                "not retried automatically",
                "cannot crash the surrounding webhook workflow",
            ),
        }

        for (source, qualname), phrases in expected_phrases.items():
            doc = ast.get_docstring(sources[source][qualname], clean=True) or ""
            normalized = " ".join(doc.replace("``", "").split())

            for phrase in phrases:
                with self.subTest(
                    source=source,
                    qualname=qualname,
                    phrase=phrase,
                ):
                    self.assertIn(phrase, normalized)

    def test_delivery_and_failure_isolation_contract_is_explicit(self):
        _, sources = self._state()
        expected_phrases = {
            ("apps/bale_bot/client.py", "BaleBotClient.request"): (
                "translated to BaleBotApiError",
                "does not create message logs",
                "decide whether outbound messaging is enabled",
            ),
            ("apps/bale_bot/client.py", "BaleBotClient.send_message"): (
                "logged as skipped",
                "Callback tokens in reply markup are masked",
                "does not directly update NotificationDelivery status",
            ),
            (
                "apps/messaging/notification_delivery.py",
                "build_actionable_reply_markup",
            ): (
                "one-time action tokens",
                "persistent storage keeps its hash",
                "rows of at most two",
            ),
            (
                "apps/messaging/notification_delivery.py",
                "messaging_delivery_preference_enabled",
            ): (
                "Preferences may change",
                "Critical notifications bypass opt-out",
                "most specific",
            ),
            (
                "apps/messaging/notification_delivery.py",
                "deliver_simple_notification",
            ): (
                "before any API call",
                "pending-setup",
                "does not itself persist the queue row transition",
            ),
            ("apps/messaging/services.py", "log_message"): (
                "does not perform network I/O",
                "update a NotificationDelivery row",
                "execute a messaging action",
            ),
        }

        for (source, qualname), phrases in expected_phrases.items():
            doc = ast.get_docstring(sources[source][qualname], clean=True) or ""
            normalized = " ".join(doc.replace("``", "").split())

            for phrase in phrases:
                with self.subTest(
                    source=source,
                    qualname=qualname,
                    phrase=phrase,
                ):
                    self.assertIn(phrase, normalized)
