from pathlib import Path
import json

from django.test import TestCase

from apps.help_center.product_truth import BETA_INACTIVE_HELP_ARTICLE_KEYS
from apps.help_center.retrieval import retrieve_help_chunks


class BetaPaymentTruthFixtureTests(TestCase):
    def test_active_fixture_contains_pay_at_salon_truth_and_archives_future_customer_payment_sources(self):
        payload = json.loads(
            (Path(__file__).resolve().parents[1] / "data" / "production_docs.json").read_text(encoding="utf-8")
        )
        articles = {item["key"]: item for item in payload["articles"]}
        truth = articles["customer.payment.beta-pay-at-salon-only"]
        self.assertIn("فقط در مجموعه", truth["summary"])
        self.assertIn("کیف پول مشتری", truth["body"])
        self.assertTrue(BETA_INACTIVE_HELP_ARTICLE_KEYS.issubset(articles.keys()))

    def test_retrieval_does_not_return_inactive_beta_payment_articles(self):
        hits = retrieve_help_chunks("کیف پول و پرداخت آنلاین رزرو", role="customer", limit=8)
        self.assertTrue(all(hit.article_key not in BETA_INACTIVE_HELP_ARTICLE_KEYS for hit in hits))
