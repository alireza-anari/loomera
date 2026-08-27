import json
from pathlib import Path
from django.test import SimpleTestCase

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "production_docs.json"

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


    def test_every_article_category_exists(self):
        category_slugs = {item["slug"] for item in self.payload["categories"]}
        for item in self.payload["articles"]:
            with self.subTest(key=item["key"]):
                self.assertIn(item["category"], category_slugs)

    def test_contexts_reference_existing_articles(self):
        keys = {item["key"] for item in self.payload["articles"]}
        for item in self.payload["contexts"]:
            with self.subTest(route=item.get("route_name")):
                self.assertIn(item["article_key"], keys)
