from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.articles.models import SalonStory, SalonStoryItem, SalonStoryView


class StoryTrackingSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _make_public_story(self):
        manager = self.make_salon_manager()
        salon = self.make_salon(manager=manager)

        return SalonStory.objects.create(
            salon=salon,
            title="استوری تست امنیت",
            status=SalonStory.Status.PUBLISHED,
            visibility=SalonStory.Visibility.PUBLIC,
            published_at=timezone.now() - timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(days=1),
        )

    def test_story_view_tracking_requires_login(self):
        story = self._make_public_story()

        response = self.client.post(reverse("articles:story_view", args=[story.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response["Location"])

        story.refresh_from_db()
        self.assertEqual(story.view_count, 0)

    def test_story_view_tracking_rejects_get_method(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.get(reverse("articles:story_view", args=[story.pk]))

        self.assertEqual(response.status_code, 405)

        story.refresh_from_db()
        self.assertEqual(story.view_count, 0)

    def test_story_view_tracking_rejects_invalid_item_id(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("articles:story_view", args=[story.pk]),
            {
                "item_id": "abc",
                "completed": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_payload")
        self.assertFalse(
            SalonStoryView.objects.filter(user=customer.user, story=story).exists()
        )

        story.refresh_from_db()
        self.assertEqual(story.view_count, 0)

    def test_story_view_tracking_rejects_invalid_completed_value(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("articles:story_view", args=[story.pk]),
            {
                "completed": "maybe",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_payload")
        self.assertFalse(
            SalonStoryView.objects.filter(user=customer.user, story=story).exists()
        )

        story.refresh_from_db()
        self.assertEqual(story.view_count, 0)

    @override_settings(ARTICLE_STORY_TRACK_POST_MAX_BYTES=32)
    def test_story_view_tracking_rejects_oversized_payload(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("articles:story_view", args=[story.pk]),
            {
                "item_id": "1",
                "payload": "x" * 200,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")
        self.assertFalse(
            SalonStoryView.objects.filter(user=customer.user, story=story).exists()
        )

        story.refresh_from_db()
        self.assertEqual(story.view_count, 0)

    def test_story_view_tracking_accepts_valid_item_and_completed(self):
        customer = self.make_customer()
        story = self._make_public_story()
        item = SalonStoryItem.objects.create(
            story=story,
            sort_order=1,
            is_active=True,
        )

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("articles:story_view", args=[story.pk]),
            {
                "item_id": str(item.pk),
                "completed": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        view = SalonStoryView.objects.get(user=customer.user, story=story)
        self.assertEqual(view.last_item_seen_id, item.pk)
        self.assertIsNotNone(view.completed_at)

        story.refresh_from_db()
        self.assertEqual(story.view_count, 1)

    def test_story_click_tracking_rejects_get_method(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.get(reverse("articles:story_click", args=[story.pk]))

        self.assertEqual(response.status_code, 405)

        story.refresh_from_db()
        self.assertEqual(story.click_count, 0)

    @override_settings(ARTICLE_STORY_TRACK_POST_MAX_BYTES=32)
    def test_story_click_tracking_rejects_oversized_payload(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("articles:story_click", args=[story.pk]),
            {
                "payload": "x" * 200,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"], "payload_too_large")

        story.refresh_from_db()
        self.assertEqual(story.click_count, 0)

    def test_story_click_tracking_accepts_valid_post(self):
        customer = self.make_customer()
        story = self._make_public_story()

        self.client.force_login(customer.user)
        response = self.client.post(
            reverse("articles:story_click", args=[story.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

        story.refresh_from_db()
        self.assertEqual(story.click_count, 1)
