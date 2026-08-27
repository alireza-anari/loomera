from django.test import TestCase

from apps.help_center.chunking import article_chunk_specs
from apps.help_center.models import Audience, HelpArticle, HelpCategory


class HelpChunkingTests(TestCase):
    def test_body_headings_become_separate_chunks(self):
        category = HelpCategory.objects.create(slug="chunk-test", title="آزمایش", audience=Audience.ALL)
        article = HelpArticle(
            category=category,
            key="test.chunking",
            slug="test-chunking",
            title="راهنمای آزمایشی",
            audience=Audience.ALL,
            summary="خلاصه مقاله",
            body="## پیش‌نیازها\nیک مورد لازم است.\n\n## مراحل\nمرحله اصلی را انجام بده.",
        )
        specs = article_chunk_specs(article)
        headings = [item.heading for item in specs]
        self.assertIn("خلاصه", headings)
        self.assertIn("پیش‌نیازها", headings)
        self.assertIn("مراحل", headings)
