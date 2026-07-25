from __future__ import annotations

import ast
import copy
from hashlib import sha256
import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from apps.main.sensitive_exception_inventory import stable_ast_sha256


class PaymentGatewayContractDocumentationTests(SimpleTestCase):
    source_path = Path(settings.BASE_DIR) / "apps" / "payments" / "gateways.py"
    manifest_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "payments"
        / "payment_gateway_contract_manifest.json"
    )

    @staticmethod
    def _remove_docstrings(node):
        clean = copy.deepcopy(node)

        for candidate in ast.walk(clean):
            if not isinstance(
                candidate,
                (
                    ast.Module,
                    ast.ClassDef,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            body = getattr(candidate, "body", None)
            if not body:
                continue

            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                candidate.body = body[1:]

        return clean

    @classmethod
    def _source_and_tree(cls):
        source = cls.source_path.read_text(encoding="utf-8")
        return source, ast.parse(source, filename=str(cls.source_path))

    @classmethod
    def _manifest(cls):
        return json.loads(cls.manifest_path.read_text(encoding="utf-8"))

    @classmethod
    def _objects(cls):
        _source, tree = cls._source_and_tree()
        return {
            node.name: node
            for node in tree.body
            if isinstance(
                node,
                (
                    ast.ClassDef,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            )
        }

    def test_manifest_has_expected_documented_objects(self):
        manifest = self._manifest()

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["module"], "apps/payments/gateways.py")
        self.assertEqual(
            set(manifest["documented_objects"]),
            {
                "GatewayInitResult",
                "GatewayVerifyResult",
                "initiate_payment",
                "verify_payment",
            },
        )

    def test_executable_gateway_ast_matches_reviewed_manifest(self):
        _source, tree = self._source_and_tree()
        clean = self._remove_docstrings(tree)
        actual = stable_ast_sha256(clean)

        self.assertEqual(
            actual,
            self._manifest()["executable_ast_sha256"],
            msg=(
                "Executable gateway structure changed. Review initiation, "
                "verification, integrity checks, and payment state ownership "
                "before intentionally updating the contract manifest."
            ),
        )

    def test_contract_docstrings_match_reviewed_hashes(self):
        objects = self._objects()
        documented = self._manifest()["documented_objects"]

        for name, metadata in documented.items():
            with self.subTest(name=name):
                self.assertIn(name, objects)
                docstring = ast.get_docstring(objects[name], clean=True)
                self.assertIsNotNone(docstring)
                self.assertEqual(
                    sha256(docstring.encode("utf-8")).hexdigest(),
                    metadata["docstring_sha256"],
                )

    def test_initiation_contract_does_not_claim_settlement(self):
        objects = self._objects()
        init_result = ast.get_docstring(
            objects["GatewayInitResult"],
            clean=True,
        )
        initiate = ast.get_docstring(
            objects["initiate_payment"],
            clean=True,
        )
        combined = f"{init_result}\n{initiate}"
        normalized = " ".join(combined.split())

        for phrase in (
            "does not mean the payment is settled",
            "never marks the payment paid",
            "amount is received in tomans",
            "sent to Zibal in rials",
            "does not mutate Payment, Order, wallet, or ledger state",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

    def test_verification_contract_defines_all_outcome_classes(self):
        objects = self._objects()
        verify_result = ast.get_docstring(
            objects["GatewayVerifyResult"],
            clean=True,
        )
        verify = ast.get_docstring(
            objects["verify_payment"],
            clean=True,
        )
        combined = f"{verify_result}\n{verify}"

        for phrase in (
            "without mutating it",
            "gateway_track_id",
            "result code, status, amount, orderId, and refNumber",
            "retryable=True",
            "requires_review=True",
            "manual review",
            "definitive decline",
            "Callers own transitions",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, combined)
