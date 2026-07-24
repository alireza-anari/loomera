from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.urls import NoReverseMatch

from apps.messaging import promotion_bot


class PromotionBotUrlExceptionScopeTests(
    SimpleTestCase
):
    base_url = "https://loomera.test"

    def test_safe_url_falls_back_on_no_reverse_match(self):
        with patch(
            "apps.messaging.promotion_bot.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            result = promotion_bot._safe_url(
                self.base_url,
                "missing:view",
                fallback_path="/fallback/",
            )

        self.assertEqual(
            result,
            f"{self.base_url}/fallback/",
        )

    def test_quick_link_url_falls_back_on_no_reverse_match(
        self,
    ):
        quick_link = SimpleNamespace(
            token="secure-token",
        )

        with patch(
            "apps.messaging.promotion_bot.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            result = (
                promotion_bot._booking_quick_link_url(
                    self.base_url,
                    quick_link,
                )
            )

        self.assertEqual(
            result,
            (
                f"{self.base_url}"
                "/orders/quick-booking/secure-token/"
            ),
        )

    def test_salon_url_falls_back_on_no_reverse_match(self):
        salon = SimpleNamespace(
            pk=11,
            slug="salon-test",
        )

        with patch(
            "apps.messaging.promotion_bot.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            result = promotion_bot._salon_url(
                self.base_url,
                salon,
            )

        self.assertEqual(
            result,
            f"{self.base_url}/detail_salon/11/",
        )

    def test_article_url_falls_back_on_no_reverse_match(self):
        article = SimpleNamespace(
            get_absolute_url=Mock(
                side_effect=NoReverseMatch("missing")
            ),
        )

        with patch(
            "apps.messaging.promotion_bot.reverse",
            return_value="/magazine/",
        ):
            result = promotion_bot._article_url(
                self.base_url,
                article,
            )

        self.assertEqual(
            result,
            f"{self.base_url}/magazine/",
        )

    def test_story_url_falls_back_on_no_reverse_match(self):
        story = SimpleNamespace(pk=21)

        with patch(
            "apps.messaging.promotion_bot.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            result = promotion_bot._story_url(
                self.base_url,
                story,
            )

        self.assertEqual(
            result,
            (
                f"{self.base_url}"
                "/magazine/stories/"
            ),
        )

    def test_unexpected_reverse_errors_are_not_silenced(
        self,
    ):
        salon = SimpleNamespace(
            pk=11,
            slug="salon-test",
        )
        quick_link = SimpleNamespace(
            token="secure-token",
        )
        story = SimpleNamespace(pk=21)

        callbacks = (
            lambda: promotion_bot._safe_url(
                self.base_url,
                "missing:view",
                fallback_path="/fallback/",
            ),
            lambda: (
                promotion_bot._booking_quick_link_url(
                    self.base_url,
                    quick_link,
                )
            ),
            lambda: promotion_bot._salon_url(
                self.base_url,
                salon,
            ),
            lambda: promotion_bot._story_url(
                self.base_url,
                story,
            ),
        )

        with patch(
            "apps.messaging.promotion_bot.reverse",
            side_effect=RuntimeError(
                "unexpected URL failure"
            ),
        ):
            for callback in callbacks:
                with self.subTest(callback=callback):
                    with self.assertRaises(RuntimeError):
                        callback()

    def test_article_runtime_error_is_not_silenced(self):
        article = SimpleNamespace(
            get_absolute_url=Mock(
                side_effect=RuntimeError(
                    "unexpected article URL failure"
                )
            ),
        )

        with self.assertRaises(RuntimeError):
            promotion_bot._article_url(
                self.base_url,
                article,
            )

    def test_promotion_url_helpers_have_no_broad_handler(
        self,
    ):
        helpers = (
            promotion_bot._safe_url,
            promotion_bot._booking_quick_link_url,
            promotion_bot._salon_url,
            promotion_bot._article_url,
            promotion_bot._story_url,
        )

        for helper in helpers:
            with self.subTest(
                helper=helper.__name__
            ):
                source = inspect.getsource(helper)

                self.assertIn(
                    "except NoReverseMatch:",
                    source,
                )
                self.assertNotIn(
                    "except Exception",
                    source,
                )
