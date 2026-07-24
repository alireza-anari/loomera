from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.articles.models import SalonStory


class MagazineHomeStoryParamSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _url(self):
        return reverse("articles:magazine_home")

    def _make_public_story(self, *, title="استوری public"):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        return SalonStory.objects.create(
            salon=salon,
            title=title,
            status=SalonStory.Status.PUBLISHED,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=timezone.now() - timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(days=1),
        )

    def _make_draft_story(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        return SalonStory.objects.create(
            salon=salon,
            title="استوری draft",
            status=SalonStory.Status.DRAFT,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=None,
            expires_at=timezone.now() + timedelta(days=1),
        )

    def test_magazine_home_allows_plain_get(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)

    def test_magazine_home_rejects_non_numeric_story_param(self):
        response = self.client.get(
            self._url(),
            {"story": "abc"},
        )

        self.assertEqual(response.status_code, 404)

    def test_magazine_home_rejects_non_numeric_story_id_param(self):
        response = self.client.get(
            self._url(),
            {"story_id": "abc"},
        )

        self.assertEqual(response.status_code, 404)

    def test_magazine_home_rejects_zero_story_param(self):
        response = self.client.get(
            self._url(),
            {"story": "0"},
        )

        self.assertEqual(response.status_code, 404)

    def test_magazine_home_accepts_accessible_public_story_param(self):
        story = self._make_public_story()

        response = self.client.get(
            self._url(),
            {"story": str(story.pk)},
        )

        self.assertEqual(response.status_code, 200)

        payload_ids = {
            item["id"] for item in response.context["magazine_stories_payload"]
        }
        self.assertIn(story.pk, payload_ids)

    def test_magazine_home_does_not_inject_inaccessible_draft_story(self):
        story = self._make_draft_story()

        response = self.client.get(
            self._url(),
            {"story": str(story.pk)},
        )

        self.assertEqual(response.status_code, 200)

        payload_ids = {
            item["id"] for item in response.context["magazine_stories_payload"]
        }
        self.assertNotIn(story.pk, payload_ids)
