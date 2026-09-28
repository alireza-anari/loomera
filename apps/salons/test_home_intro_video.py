from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse


class PublicHomeIntroVideoTests(TestCase):
    def test_home_contains_intro_video_trigger_and_dialog(self):
        response = self.client.get(reverse("salons:home"))

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "data-lm-intro-video-open",
        )
        self.assertContains(
            response,
            'id="loomera-intro-video-dialog"',
        )
        self.assertContains(
            response,
            "data-lm-intro-video",
        )
        self.assertContains(
            response,
            "videos/loomera-intro-web",
        )

    def test_intro_video_static_assets_exist(self):
        self.assertIsNotNone(finders.find("videos/loomera-intro-web.mp4"))
        self.assertIsNotNone(finders.find("videos/loomera-intro-poster.webp"))
