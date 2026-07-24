from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from apps.articles.forms import ArticleDraftForm, SalonStoryDraftForm
from apps.dashboards.content_views import ManagerArticleForm, ManagerStoryForm


def _image_upload(
    *,
    name="cover.jpg",
    size=(64, 64),
    image_format="JPEG",
    content_type="image/jpeg",
):
    buffer = BytesIO()
    image = Image.new("RGB", size, color=(240, 240, 240))
    image.save(buffer, format=image_format)
    buffer.seek(0)

    return SimpleUploadedFile(
        name,
        buffer.read(),
        content_type=content_type,
    )


def _animated_gif_upload(*, name="cover.gif", content_type="image/gif"):
    buffer = BytesIO()

    frame_one = Image.new("RGB", (32, 32), color=(255, 0, 0))
    frame_two = Image.new("RGB", (32, 32), color=(0, 255, 0))

    frame_one.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=[frame_two],
        duration=100,
        loop=0,
    )
    buffer.seek(0)

    return SimpleUploadedFile(
        name,
        buffer.read(),
        content_type=content_type,
    )


class ArticleCoverImageSecurityTests(TestCase):
    def _manager_article_form(self, uploaded_file):
        return ManagerArticleForm(
            data={
                "article-title": "مقاله تست",
                "article-summary": "خلاصه مقاله تست",
                "article-content": "متن مقاله تست برای بررسی تصویر شاخص",
                "article-content_type": "educational",
                "article-visibility": "public",
                "article-manager_approved_responsibility": "on",
            },
            files={
                "article-cover_image": uploaded_file,
            },
            prefix="article",
        )

    def _manager_story_form(self, uploaded_file):
        return ManagerStoryForm(
            data={
                "story-title": "استوری تست",
                "story-summary": "خلاصه استوری",
                "story-visibility": "public",
                "story-manager_approved_responsibility": "on",
            },
            files={
                "story-cover_image": uploaded_file,
            },
            prefix="story",
        )

    def test_manager_article_cover_rejects_gif_with_jpg_filename(self):
        form = self._manager_article_form(
            _animated_gif_upload(name="cover.jpg", content_type="image/jpeg")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_manager_article_cover_rejects_invalid_content_type(self):
        form = self._manager_article_form(
            _image_upload(
                name="cover.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_manager_article_cover_accepts_valid_jpeg_without_cover_error(self):
        form = self._manager_article_form(
            _image_upload(
                name="cover.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        form.is_valid()
        self.assertNotIn("cover_image", form.errors)

    def test_manager_story_cover_rejects_gif_with_jpg_filename(self):
        form = self._manager_story_form(
            _animated_gif_upload(name="story.jpg", content_type="image/jpeg")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_manager_story_cover_accepts_valid_jpeg_without_cover_error(self):
        form = self._manager_story_form(
            _image_upload(
                name="story.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        form.is_valid()
        self.assertNotIn("cover_image", form.errors)

    def _article_form(self, uploaded_file):
        return ArticleDraftForm(
            data={
                "title": "مقاله تست",
                "summary": "خلاصه مقاله تست",
                "content": "متن مقاله تست",
                "content_type": "educational",
                "professional_confirmed_responsibility": "on",
            },
            files={"cover_image": uploaded_file},
        )

    def _story_form(self, uploaded_file):
        return SalonStoryDraftForm(
            data={
                "title": "استوری تست",
                "summary": "خلاصه استوری",
                "visibility": "public",
                "professional_confirmed_responsibility": "on",
            },
            files={"cover_image": uploaded_file},
        )

    def assert_cover_image_invalid(self, form):
        self.assertFalse(form.is_valid())
        self.assertIn("cover_image", form.errors)

    def test_article_cover_accepts_valid_jpeg(self):
        form = self._article_form(
            _image_upload(
                name="cover.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertTrue(
            form.is_valid() or "cover_image" not in form.errors,
            form.errors,
        )

    def test_article_cover_rejects_gif_extension(self):
        form = self._article_form(
            _animated_gif_upload(name="cover.gif", content_type="image/gif")
        )

        self.assert_cover_image_invalid(form)

    def test_article_cover_rejects_gif_with_jpg_filename(self):
        form = self._article_form(
            _animated_gif_upload(name="cover.jpg", content_type="image/jpeg")
        )

        self.assert_cover_image_invalid(form)

    def test_article_cover_rejects_svg_extension(self):
        svg_file = SimpleUploadedFile(
            "cover.svg",
            b"<svg><script>alert(1)</script></svg>",
            content_type="image/svg+xml",
        )

        form = self._article_form(svg_file)

        self.assert_cover_image_invalid(form)

    def test_article_cover_rejects_invalid_content_type(self):
        form = self._article_form(
            _image_upload(
                name="cover.jpg",
                image_format="JPEG",
                content_type="text/plain",
            )
        )

        self.assert_cover_image_invalid(form)

    @override_settings(ARTICLE_COVER_IMAGE_MAX_DIMENSION=64)
    def test_article_cover_rejects_too_large_dimension(self):
        form = self._article_form(
            _image_upload(
                name="cover.jpg",
                size=(128, 32),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assert_cover_image_invalid(form)

    @override_settings(ARTICLE_COVER_IMAGE_MAX_PIXELS=1000)
    def test_article_cover_rejects_too_many_pixels(self):
        form = self._article_form(
            _image_upload(
                name="cover.jpg",
                size=(40, 40),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assert_cover_image_invalid(form)

    @override_settings(ARTICLE_COVER_IMAGE_MAX_SIZE_BYTES=100)
    def test_article_cover_rejects_too_large_file_size(self):
        form = self._article_form(
            _image_upload(
                name="cover.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assert_cover_image_invalid(form)

    def test_story_cover_accepts_valid_jpeg_without_cover_error(self):
        form = self._story_form(
            _image_upload(
                name="story.jpg",
                size=(64, 64),
                image_format="JPEG",
                content_type="image/jpeg",
            )
        )

        self.assertNotIn("cover_image", form.errors)

    def test_story_cover_rejects_gif_with_jpg_filename(self):
        form = self._story_form(
            _animated_gif_upload(name="story.jpg", content_type="image/jpeg")
        )

        self.assert_cover_image_invalid(form)
