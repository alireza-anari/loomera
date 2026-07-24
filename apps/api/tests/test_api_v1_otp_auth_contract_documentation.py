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


class OtpAuthContractDocumentationTests(SimpleTestCase):
    manifest_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "api"
        / "otp_auth_contract_manifest.json"
    )

    expected_symbols = {
        ("apps/api/v1/auth_otp.py", "api_otp_fail_closed"),
        ("apps/api/v1/auth_otp.py", "_cache_get"),
        ("apps/api/v1/auth_otp.py", "_cache_set"),
        ("apps/api/v1/auth_otp.py", "_cache_delete"),
        ("apps/api/v1/auth_otp.py", "_increment_hour_rate"),
        ("apps/api/v1/auth_otp.py", "_check_resend_cooldown"),
        ("apps/api/v1/auth_otp.py", "create_api_otp_request"),
        ("apps/api/v1/auth_otp.py", "verify_api_otp_code"),
        ("apps/api/v1/auth_views.py", "_parse_content_length"),
        ("apps/api/v1/auth_views.py", "_load_auth_json_object_payload"),
        ("apps/api/v1/auth_views.py", "ApiOtpRequestAPIView.post"),
        ("apps/api/v1/auth_views.py", "ApiOtpVerifyAPIView.post"),
    }

    def _state(self):
        manifest = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )
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
        self.assertEqual(
            manifest["sources"],
            [
                "apps/api/v1/auth_otp.py",
                "apps/api/v1/auth_views.py",
            ],
        )
        self.assertEqual(len(manifest["symbols"]), 12)
        self.assertEqual(
            {
                (item["source"], item["qualname"])
                for item in manifest["symbols"]
            },
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

    def test_payload_and_request_contract_is_explicit(self):
        _, sources = self._state()
        symbols = sources["apps/api/v1/auth_views.py"]
        expected_phrases = {
            "_parse_content_length": (
                "non-negative integers",
                "sole body-size check",
            ),
            "_load_auth_json_object_payload": (
                "declared Content-Length",
                "actual request body",
                "non-object JSON",
                "untrusted input",
            ),
            "ApiOtpRequestAPIView.post": (
                "masked mobile number",
                "never returns the OTP code",
                "does not authenticate a session",
            ),
        }

        for qualname, phrases in expected_phrases.items():
            doc = ast.get_docstring(symbols[qualname], clean=True) or ""
            normalized = " ".join(doc.split())

            for phrase in phrases:
                with self.subTest(qualname=qualname, phrase=phrase):
                    self.assertIn(phrase, normalized)

    def test_cache_rate_limit_and_creation_contract_is_explicit(self):
        _, sources = self._state()
        symbols = sources["apps/api/v1/auth_otp.py"]
        expected_phrases = {
            "api_otp_fail_closed": (
                "blocks OTP request or verification",
                "cannot be trusted",
            ),
            "_cache_delete": (
                "best-effort cleanup",
                "may still be replayable",
            ),
            "_increment_hour_rate": (
                "mobile or IP scope",
                "does not create or deliver an OTP",
            ),
            "_check_resend_cooldown": (
                "mobile_resend",
                "does not mutate the OTP record",
            ),
            "create_api_otp_request": (
                "Only a salted code hash is stored",
                "plaintext code is never placed in cache",
                "does not create a user",
            ),
        }

        for qualname, phrases in expected_phrases.items():
            doc = ast.get_docstring(symbols[qualname], clean=True) or ""
            normalized = " ".join(doc.split())

            for phrase in phrases:
                with self.subTest(qualname=qualname, phrase=phrase):
                    self.assertIn(phrase, normalized)

    def test_verification_and_login_boundary_is_explicit(self):
        _, sources = self._state()
        otp_symbols = sources["apps/api/v1/auth_otp.py"]
        view_symbols = sources["apps/api/v1/auth_views.py"]

        verify_doc = " ".join(
            (
                ast.get_docstring(
                    otp_symbols["verify_api_otp_code"],
                    clean=True,
                )
                or ""
            ).split()
        )
        view_doc = " ".join(
            (
                ast.get_docstring(
                    view_symbols["ApiOtpVerifyAPIView.post"],
                    clean=True,
                )
                or ""
            ).split()
        )

        for phrase in (
            "secrets.compare_digest",
            "preserve the remaining TTL",
            "requires deletion of the cache record",
            "does not authenticate a Django user session",
        ):
            with self.subTest(contract="verify", phrase=phrase):
                self.assertIn(phrase, verify_doc)

        for phrase in (
            "Only after the challenge succeeds",
            "required cache delete completes",
            "call Django login",
            "missing user is not created automatically",
        ):
            with self.subTest(contract="view", phrase=phrase):
                self.assertIn(phrase, view_doc)
