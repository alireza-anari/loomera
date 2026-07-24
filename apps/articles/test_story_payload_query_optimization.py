from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone

from apps.articles.models import (
    SalonStory,
    SalonStoryItem,
    SalonStoryView,
)
from apps.articles.services import (
    build_story_payload,
    published_stories_queryset,
)
from tests_stage1_helpers import Stage1DomainFactoryMixin


class StoryPayloadQueryOptimizationTests(
    Stage1DomainFactoryMixin,
    TestCase,
):
    def setUp(self):
        self.manager = self.make_salon_manager()
        self.salon = self.make_salon(manager=self.manager)

    def _make_story(self, *, index: int):
        story = SalonStory.objects.create(
            salon=self.salon,
            title=f"استوری تست {index}",
            summary=f"توضیح استوری {index}",
            status=SalonStory.Status.PUBLISHED,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=timezone.now() - timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(days=1),
        )

        first_item = SalonStoryItem.objects.create(
            story=story,
            media_type=SalonStoryItem.MediaType.IMAGE,
            image=f"images/articles/stories/items/story-{index}.jpg",
            caption=f"آیتم فعال {index}",
            sort_order=1,
            is_active=True,
        )

        SalonStoryItem.objects.create(
            story=story,
            media_type=SalonStoryItem.MediaType.IMAGE,
            image=f"images/articles/stories/items/inactive-{index}.jpg",
            caption=f"آیتم غیرفعال {index}",
            sort_order=0,
            is_active=False,
        )

        return story, first_item

    def _load_stories(self):
        return list(
            published_stories_queryset().filter(salon=self.salon).order_by("pk")
        )

    def test_story_queryset_loads_stories_and_active_items_in_two_queries(self):
        for index in range(3):
            self._make_story(index=index)

        with self.assertNumQueries(2):
            stories = self._load_stories()

        self.assertEqual(len(stories), 3)

    def test_anonymous_payload_runs_no_queries_after_prefetch(self):
        expected_items = {}

        for index in range(3):
            story, item = self._make_story(index=index)
            expected_items[story.pk] = item.pk

        stories = self._load_stories()

        with self.assertNumQueries(0):
            payload = build_story_payload(
                stories,
                user=AnonymousUser(),
                request=None,
            )

        self.assertEqual(len(payload), 3)

        for story_payload in payload:
            self.assertEqual(len(story_payload["items"]), 1)
            self.assertEqual(
                story_payload["items"][0]["id"],
                expected_items[story_payload["id"]],
            )
            self.assertIn(
                f"story-{story_payload['id'] - stories[0].pk}",
                story_payload["coverUrl"],
            )

    def test_query_count_does_not_grow_with_more_stories(self):
        for index in range(12):
            self._make_story(index=index)

        with self.assertNumQueries(2):
            stories = self._load_stories()

        with self.assertNumQueries(0):
            payload = build_story_payload(
                stories,
                user=AnonymousUser(),
                request=None,
            )

        self.assertEqual(len(payload), 12)

    def test_authenticated_payload_uses_one_view_state_query(self):
        customer = self.make_customer()

        first_story, _ = self._make_story(index=1)
        self._make_story(index=2)

        SalonStoryView.objects.create(
            user=customer.user,
            story=first_story,
            completed_at=timezone.now(),
        )

        stories = self._load_stories()

        with self.assertNumQueries(1):
            payload = build_story_payload(
                stories,
                user=customer.user,
                request=None,
            )

        by_id = {item["id"]: item for item in payload}

        self.assertTrue(by_id[first_story.pk]["isViewed"])

    def test_unprepared_story_call_remains_backward_compatible(self):
        story, active_item = self._make_story(index=20)

        payload = build_story_payload(
            [story],
            user=AnonymousUser(),
            request=None,
        )

        self.assertEqual(len(payload), 1)
        self.assertEqual(
            payload[0]["items"][0]["id"],
            active_item.pk,
        )
