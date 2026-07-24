from __future__ import annotations

import ast
import copy
from hashlib import sha256
import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


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
    payload = ast.dump(
        clean,
        annotate_fields=True,
        include_attributes=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


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


class BookingCheckoutContractDocumentationTests(SimpleTestCase):
    source_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "orders"
        / "views.py"
    )
    manifest_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "orders"
        / "booking_checkout_contract_manifest.json"
    )

    def _state(self):
        source = self.source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(self.source_path))
        manifest = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )
        return manifest, _symbol_index(tree)

    def test_manifest_tracks_expected_contract_symbols(self):
        manifest, _ = self._state()
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["source"], "apps/orders/views.py")
        self.assertEqual(len(manifest["symbols"]), 10)
        self.assertEqual(
            {item["qualname"] for item in manifest["symbols"]},
            {
                "_clear_public_booking_session_state",
                "_validate_public_booking_stylist_selections",
                "_validate_public_booking_datetime_selections",
                "BookingStylistSelectPerService.post",
                "BookingDateTimeSelectPersian.post",
                "_get_session_booking_context",
                "_build_checkout_payload",
                "_build_checkout_submission_fingerprint",
                "_assert_checkout_slots_still_available",
                "AppointmentCheckoutView.post",
            },
        )

    def test_executable_contract_ast_matches_manifest(self):
        manifest, symbols = self._state()

        for item in manifest["symbols"]:
            with self.subTest(qualname=item["qualname"]):
                node = symbols[item["qualname"]]
                self.assertEqual(
                    _hash_node_without_docstrings(node),
                    item["executable_sha256"],
                )

    def test_documentation_hashes_match_manifest(self):
        manifest, symbols = self._state()

        for item in manifest["symbols"]:
            with self.subTest(qualname=item["qualname"]):
                doc = ast.get_docstring(symbols[item["qualname"]], clean=True)
                self.assertTrue(doc)
                self.assertEqual(
                    _doc_hash(doc),
                    item["documentation_sha256"],
                )

    def test_booking_session_contract_is_explicit(self):
        _, symbols = self._state()
        expected_phrases = {
            "_clear_public_booking_session_state": (
                "fail-closed reset",
                "partial selection cannot reach checkout",
            ),
            "_validate_public_booking_stylist_selections": (
                "client-supplied",
                "does not write the session",
                "does not reserve availability",
            ),
            "_validate_public_booking_datetime_selections": (
                "extra datetime keys are rejected",
                "final availability check",
            ),
            "BookingStylistSelectPerService.post": (
                "posted JSON is untrusted",
                "clears all public-booking session state",
                "datetime_selections",
            ),
            "BookingDateTimeSelectPersian.post": (
                "does not create an Order",
                "does not reserve a slot",
                "all three booking session keys",
            ),
            "_get_session_booking_context": (
                "Session data is input, not an authoritative reservation",
                "database locks",
            ),
        }

        for qualname, phrases in expected_phrases.items():
            doc = ast.get_docstring(symbols[qualname], clean=True) or ""
            normalized = " ".join(doc.split())
            for phrase in phrases:
                with self.subTest(qualname=qualname, phrase=phrase):
                    self.assertIn(phrase, normalized)

    def test_checkout_boundary_contract_is_explicit(self):
        _, symbols = self._state()
        expected_phrases = {
            "_build_checkout_payload": (
                "read-only checkout preview",
                "does not create an Order or Payment",
                "reserve a slot",
            ),
            "_build_checkout_submission_fingerprint": (
                "idempotency hint",
                "not authorization",
                "not a slot lock",
            ),
            "_assert_checkout_slots_still_available": (
                "transaction.atomic",
                "select_for_update",
                "Conflicts raise ValidationError",
            ),
            "AppointmentCheckoutView.post": (
                "transactional finalization boundary",
                "before creating Order and OrderDetail records",
                "not payment settlement",
            ),
        }

        for qualname, phrases in expected_phrases.items():
            doc = ast.get_docstring(symbols[qualname], clean=True) or ""
            normalized = " ".join(doc.split())
            for phrase in phrases:
                with self.subTest(qualname=qualname, phrase=phrase):
                    self.assertIn(phrase, normalized)
