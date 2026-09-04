import ast
import json
import re
from pathlib import Path

from django.test import SimpleTestCase

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "production_docs.json"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _python_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.add(f"{node.name}.{child.name}")
    return symbols


class HelpProductionDocsFixtureTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    def test_fixture_has_broad_production_coverage(self):
        self.assertGreaterEqual(len(self.payload["articles"]), 95)
        article_types = {item["article_type"] for item in self.payload["articles"]}
        self.assertTrue({"guide", "workflow", "troubleshooting", "faq"} <= article_types)

    def test_keys_and_slugs_are_unique(self):
        keys = [item["key"] for item in self.payload["articles"]]
        slugs = [item["slug"] for item in self.payload["articles"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_every_article_has_internal_sources_and_search_terms(self):
        for item in self.payload["articles"]:
            with self.subTest(key=item["key"]):
                self.assertTrue(item.get("source_refs"))
                self.assertTrue((item.get("keywords") or "").strip())
                self.assertTrue((item.get("summary") or "").strip())

    def test_every_source_ref_points_to_existing_source(self):
        symbol_cache = {}
        for item in self.payload["articles"]:
            for source_ref in item.get("source_refs") or []:
                with self.subTest(key=item["key"], source_ref=source_ref):
                    relative_path, separator, locator = str(source_ref).partition(":")
                    source_path = PROJECT_ROOT / relative_path
                    self.assertTrue(source_path.is_file(), f"Missing source file: {relative_path}")
                    if not separator or not locator:
                        continue

                    if source_path.suffix == ".py" and source_path.name == "urls.py" and ":" in locator:
                        route_name = locator.rsplit(":", 1)[-1]
                        source_text = source_path.read_text(encoding="utf-8")
                        self.assertRegex(
                            source_text,
                            rf"name\s*=\s*['\"]{re.escape(route_name)}['\"]",
                            f"Missing URL name {locator} in {relative_path}",
                        )
                        continue

                    if source_path.suffix == ".py":
                        symbols = symbol_cache.setdefault(source_path, _python_symbols(source_path))
                        self.assertIn(locator, symbols, f"Missing Python symbol {locator} in {relative_path}")
                        continue

                    source_text = source_path.read_text(encoding="utf-8")
                    self.assertIn(locator, source_text, f"Missing locator {locator} in {relative_path}")

    def test_every_article_category_exists(self):
        category_slugs = {item["slug"] for item in self.payload["categories"]}
        for item in self.payload["articles"]:
            with self.subTest(key=item["key"]):
                self.assertIn(item["category"], category_slugs)

    def test_getting_started_is_manager_setup_only(self):
        category = next(item for item in self.payload["categories"] if item["slug"] == "getting-started")
        self.assertEqual(category["audience"], "manager")
        articles = [item for item in self.payload["articles"] if item["category"] == "getting-started"]
        self.assertTrue(articles)
        self.assertTrue(all(item["audience"] == "manager" for item in articles))

    def test_customer_notes_privacy_guidance_exists(self):
        article = next(
            item
            for item in self.payload["articles"]
            if item["key"] == "manager.customers.notes-privacy"
        )
        self.assertEqual(article["audience"], "manager")
        self.assertIn("رضایت", article["body"])
        self.assertIn("اطلاعات حساس", article["body"])

    def test_contexts_reference_existing_articles(self):
        keys = {item["key"] for item in self.payload["articles"]}
        for item in self.payload["contexts"]:
            with self.subTest(route=item.get("route_name")):
                self.assertIn(item["article_key"], keys)
