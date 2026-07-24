from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.main.sensitive_exception_inventory import (
    ALLOWED_CATEGORIES,
    ALLOWED_REVIEW_STATUSES,
    collect_broad_exception_inventory,
    collect_forbidden_exception_handlers,
)


class SensitiveBroadExceptionAllowlistTests(SimpleTestCase):
    manifest_path = (
        Path(settings.BASE_DIR)
        / "apps"
        / "main"
        / "sensitive_broad_exception_allowlist.json"
    )

    def _manifest(self):
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    @staticmethod
    def _identity(item):
        return (
            item["path"],
            item["qualname"],
            item["ordinal"],
        )

    def test_sensitive_code_has_no_bare_or_base_exception_handlers(
        self,
    ):
        self.assertEqual(
            collect_forbidden_exception_handlers(Path(settings.BASE_DIR)),
            [],
        )

    def test_allowlist_metadata_is_explicit_and_reviewed(
        self,
    ):
        manifest = self._manifest()

        self.assertEqual(
            len(manifest),
            88,
        )

        self.assertEqual(
            Counter(item["review_status"] for item in manifest),
            Counter(
                {
                    "approved_boundary": 32,
                    "tracked_legacy": 56,
                }
            ),
        )

        for item in manifest:
            with self.subTest(
                path=item["path"],
                qualname=item["qualname"],
                ordinal=item["ordinal"],
            ):
                self.assertIn(
                    item["category"],
                    ALLOWED_CATEGORIES,
                )
                self.assertIn(
                    item["review_status"],
                    ALLOWED_REVIEW_STATUSES,
                )
                self.assertTrue(item["note"].strip())
                self.assertEqual(
                    len(item["try_sha256"]),
                    64,
                )
                self.assertEqual(
                    len(item["handler_sha256"]),
                    64,
                )

    def test_no_new_removed_moved_or_modified_broad_handler(
        self,
    ):
        self.maxDiff = None
        manifest = self._manifest()
        actual = collect_broad_exception_inventory(Path(settings.BASE_DIR))

        expected_by_identity = {self._identity(item): item for item in manifest}
        actual_by_identity = {self._identity(item): item for item in actual}

        missing = sorted(set(expected_by_identity) - set(actual_by_identity))
        added = sorted(set(actual_by_identity) - set(expected_by_identity))
        changed = sorted(
            identity
            for identity in (set(expected_by_identity) & set(actual_by_identity))
            if (expected_by_identity[identity] != actual_by_identity[identity])
        )

        self.assertEqual(
            {
                "missing": missing,
                "added": added,
                "changed": changed,
            },
            {
                "missing": [],
                "added": [],
                "changed": [],
            },
            msg=(
                "The sensitive broad-exception inventory "
                "changed. Review the handler boundary and "
                "its regression tests before intentionally "
                "updating the allowlist."
            ),
        )

    def test_manifest_has_unique_handler_identities(
        self,
    ):
        manifest = self._manifest()
        identities = [self._identity(item) for item in manifest]

        self.assertEqual(
            len(identities),
            len(set(identities)),
        )
