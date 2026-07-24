from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.articles.models import SalonStory
from apps.services.models import GroupServices


class StoryExploreFilterSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _url(self):
        return reverse("articles:story_explore")

    def _make_group(self, title):
        return GroupServices.objects.create(
            group_title=title,
            is_active=True,
        )

    def _make_public_story(self, *, title="استوری تست", service_group=None):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        return SalonStory.objects.create(
            salon=salon,
            title=title,
            status=SalonStory.Status.PUBLISHED,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=timezone.now() - timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(days=1),
            related_service_group=service_group,
        )

    def test_story_explore_allows_plain_get(self):
        self._make_public_story()

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "newest")
        self.assertEqual(response.context["current_scope"], "all")

    def test_story_explore_rejects_invalid_service_group_id(self):
        response = self.client.get(
            self._url(),
            {"service_group": "abc"},
        )

        self.assertEqual(response.status_code, 404)

    def test_story_explore_filters_valid_service_group_id(self):
        group_one = self._make_group("گروه یک")
        group_two = self._make_group("گروه دو")

        story_one = self._make_public_story(
            title="استوری گروه یک",
            service_group=group_one,
        )
        story_two = self._make_public_story(
            title="استوری گروه دو",
            service_group=group_two,
        )

        response = self.client.get(
            self._url(),
            {"service_group": str(group_one.pk)},
        )

        self.assertEqual(response.status_code, 200)

        story_ids = {story.pk for story in response.context["stories"]}
        self.assertIn(story_one.pk, story_ids)
        self.assertNotIn(story_two.pk, story_ids)
        self.assertEqual(response.context["current_service_group"], str(group_one.pk))

    def test_story_explore_defaults_invalid_sort_to_newest(self):
        self._make_public_story()

        response = self.client.get(
            self._url(),
            {"sort": "popular;DROP"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "newest")

    def test_story_explore_defaults_invalid_scope_to_all(self):
        self._make_public_story()

        response = self.client.get(
            self._url(),
            {"scope": "favorites;DROP"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_scope"], "all")

    @override_settings(ARTICLE_STORY_EXPLORE_TEXT_MAX_CHARS=12)
    def test_story_explore_truncates_long_query_text(self):
        self._make_public_story()

        response = self.client.get(
            self._url(),
            {"q": "x" * 200},
        )

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.context["current_q"]), 12)

    @override_settings(ARTICLE_STORY_EXPLORE_TEXT_MAX_CHARS=12)
    def test_story_explore_truncates_long_topic_slug(self):
        self._make_public_story()

        response = self.client.get(
            self._url(),
            {"topic": "x" * 200},
        )

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.context["current_topic"]), 12)
