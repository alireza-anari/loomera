from django.test import SimpleTestCase

from apps.help_center.content import article_to_dict
from apps.help_center.models import ArticleType, Audience, HelpArticle, HelpCategory


class HelpArticleContentTests(SimpleTestCase):
    def _article(self, *, steps):
        category = HelpCategory(slug="support", title="پشتیبانی", audience=Audience.ALL)
        return HelpArticle(
            category=category,
            key="test.article",
            slug="test-article",
            title="راهنمای تست",
            audience=Audience.ALL,
            article_type=ArticleType.WORKFLOW,
            summary="خلاصه تست",
            steps=steps,
        )

    def test_article_exposes_safe_static_workflow_links(self):
        article = self._article(
            steps=[
                {
                    "title": "باز کردن راهنما",
                    "body": "به مرکز راهنما برو.",
                    "route_name": "help_center:home",
                    "link_label": "مرکز راهنما",
                },
                {
                    "title": "مسیر نامعتبر",
                    "body": "نباید لینک خراب بسازد.",
                    "route_name": "help_center:not-a-real-route",
                },
            ]
        )

        payload = article_to_dict(article)

        self.assertEqual(payload["action_links"], [{"label": "مرکز راهنما", "url": "/help/"}])
        self.assertEqual(payload["steps"][0]["title"], "باز کردن راهنما")

    def test_article_deduplicates_workflow_links(self):
        article = self._article(
            steps=[
                {"title": "اول", "route_name": "help_center:home"},
                {"title": "دوم", "route_name": "help_center:home"},
            ]
        )

        payload = article_to_dict(article)

        self.assertEqual(len(payload["action_links"]), 1)
