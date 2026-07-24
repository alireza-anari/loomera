from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.articles.models import Article, ContentReport, SalonStory


class ContentReportSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _make_published_article(self, **kwargs):
        defaults = {
            "title": "مقاله تست امنیت",
            "slug": f"security-article-{timezone.now().timestamp()}",
            "summary": "خلاصه مقاله تست",
            "content": "متن مقاله تست",
            "status": Article.Status.PUBLISHED,
            "published_at": timezone.now() - timedelta(minutes=5),
        }
        defaults.update(kwargs)
        return Article.objects.create(**defaults)

    def _make_draft_article(self):
        return self._make_published_article(
            title="مقاله پیش‌نویس",
            slug=f"draft-article-{timezone.now().timestamp()}",
            status=Article.Status.DRAFT,
            published_at=None,
        )

    def _make_public_story(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        return SalonStory.objects.create(
            salon=salon,
            title="استوری تست گزارش",
            status=SalonStory.Status.PUBLISHED,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=timezone.now() - timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(days=1),
        )

    def _url(self, model_name, object_id):
        return reverse("articles:content_report", args=[model_name, object_id])

    def _valid_payload(self, **kwargs):
        payload = {
            "reason": ContentReport.Reason.INAPPROPRIATE,
            "description": "این محتوا نیازمند بررسی است.",
        }
        payload.update(kwargs)
        return payload

    def test_content_report_requires_login(self):
        article = self._make_published_article()

        response = self.client.post(
            self._url("article", article.pk),
            self._valid_payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])
        self.assertFalse(ContentReport.objects.exists())

    def test_content_report_rejects_get_method(self):
        customer = self.make_customer()
        article = self._make_published_article()

        self.client.force_login(customer.user)
        response = self.client.get(self._url("article", article.pk))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ContentReport.objects.exists())

    def test_content_report_rejects_invalid_model_name(self):
        customer = self.make_customer()

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("bad_model", 1),
            self._valid_payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_content_type")
        self.assertFalse(ContentReport.objects.exists())

    @override_settings(ARTICLE_CONTENT_REPORT_POST_MAX_BYTES=32)
    def test_content_report_rejects_oversized_payload(self):
        customer = self.make_customer()
        article = self._make_published_article()

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("article", article.pk),
            self._valid_payload(description="x" * 200),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")
        self.assertFalse(ContentReport.objects.exists())

    @override_settings(ARTICLE_CONTENT_REPORT_DESCRIPTION_MAX_CHARS=12)
    def test_content_report_rejects_too_long_description(self):
        customer = self.make_customer()
        article = self._make_published_article()

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("article", article.pk),
            self._valid_payload(description="این توضیح خیلی طولانی است"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "description_too_long")
        self.assertFalse(ContentReport.objects.exists())

    def test_content_report_rejects_unpublished_article(self):
        customer = self.make_customer()
        article = self._make_draft_article()

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("article", article.pk),
            self._valid_payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ContentReport.objects.exists())

    def test_content_report_accepts_published_article(self):
        customer = self.make_customer()
        article = self._make_published_article()

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("article", article.pk),
            self._valid_payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        report = ContentReport.objects.get()
        self.assertEqual(report.reported_by_id, customer.user_id)
        self.assertEqual(report.target_object_id, article.pk)

    def test_content_report_accepts_accessible_public_story(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("story", story.pk),
            self._valid_payload(reason=ContentReport.Reason.MISLEADING),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        report = ContentReport.objects.get()
        self.assertEqual(report.reported_by_id, customer.user_id)
        self.assertEqual(report.target_object_id, story.pk)

    def test_content_report_rejects_inaccessible_story(self):
        customer = self.make_customer()
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        story = SalonStory.objects.create(
            salon=salon,
            title="استوری خصوصی",
            status=SalonStory.Status.DRAFT,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=None,
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.client.force_login(customer.user)
        response = self.client.post(
            self._url("story", story.pk),
            self._valid_payload(),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ContentReport.objects.exists())
