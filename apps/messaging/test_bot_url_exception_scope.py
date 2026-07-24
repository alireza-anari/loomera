from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import NoReverseMatch

# Bootstrap the messaging action registry before importing action modules.
# Importing manager_actions directly first creates a circular import because
# actions.py registers the default manager/stylist handlers at module load.
from apps.messaging import actions as _messaging_actions  # noqa: F401
from apps.messaging import (
    customer_bot,
    manager_actions,
    manager_bot,
    stylist_actions,
    stylist_bot,
)


class BotUrlExceptionScopeTests(SimpleTestCase):
    base_url = "https://loomera.test"

    def test_customer_helpers_fall_back_on_no_reverse_match(self):
        salon = SimpleNamespace(pk=11, slug="salon-test")
        detail = SimpleNamespace(pk=21)
        order = SimpleNamespace(pk=31)

        cases = (
            (
                "safe_url",
                patch(
                    "apps.messaging.customer_bot.reverse",
                    side_effect=NoReverseMatch("missing"),
                ),
                lambda: customer_bot._safe_url(
                    self.base_url,
                    "missing:view",
                    fallback_path="/fallback/",
                ),
                f"{self.base_url}/fallback/",
            ),
            (
                "salon_url",
                patch(
                    "apps.messaging.customer_bot.reverse",
                    side_effect=NoReverseMatch("missing"),
                ),
                lambda: customer_bot._salon_url(
                    self.base_url,
                    salon,
                ),
                f"{self.base_url}/detail_salon/11/",
            ),
            (
                "appointment_url",
                patch(
                    "apps.messaging.customer_bot.reverse",
                    side_effect=NoReverseMatch("missing"),
                ),
                lambda: customer_bot._appointment_detail_url(
                    self.base_url,
                    detail,
                ),
                (
                    f"{self.base_url}"
                    "/orders/appointment_detail/21/"
                ),
            ),
            (
                "rebook_url",
                patch(
                    "apps.messaging.customer_bot.reverse",
                    side_effect=NoReverseMatch("missing"),
                ),
                lambda: customer_bot._rebook_url(
                    self.base_url,
                    order,
                ),
                f"{self.base_url}/orders/rebook/31/",
            ),
        )

        for name, reverse_patch, callback, expected in cases:
            with self.subTest(helper=name):
                with reverse_patch:
                    self.assertEqual(
                        callback(),
                        expected,
                    )

    def test_stylist_helpers_fall_back_on_no_reverse_match(self):
        detail = SimpleNamespace(pk=41)
        quick_link = SimpleNamespace(token="secure-token")

        cases = (
            (
                "dashboard_url",
                lambda: stylist_bot._safe_dashboard_url(
                    self.base_url,
                    "missing:view",
                ),
                f"{self.base_url}/dashboards/stylist/",
            ),
            (
                "appointment_url",
                lambda: stylist_bot._appointment_detail_url(
                    self.base_url,
                    detail,
                ),
                (
                    f"{self.base_url}"
                    "/dashboards/stylist/appointments/41/"
                ),
            ),
            (
                "quick_link_url",
                lambda: stylist_bot._booking_quick_link_url(
                    self.base_url,
                    quick_link,
                ),
                (
                    f"{self.base_url}"
                    "/orders/quick-booking/secure-token/"
                ),
            ),
        )

        for name, callback, expected in cases:
            with self.subTest(helper=name):
                with patch(
                    "apps.messaging.stylist_bot.reverse",
                    side_effect=NoReverseMatch("missing"),
                ):
                    self.assertEqual(
                        callback(),
                        expected,
                    )

    def test_action_helpers_fall_back_on_no_reverse_match(self):
        context = SimpleNamespace(
            base_url=self.base_url,
        )
        detail = SimpleNamespace(pk=51)

        with patch(
            "apps.messaging.stylist_actions.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            self.assertEqual(
                stylist_actions._appointment_url(
                    context,
                    detail,
                ),
                (
                    f"{self.base_url}"
                    "/dashboards/stylist/appointments/51/"
                ),
            )

        with patch(
            "apps.messaging.manager_actions.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            self.assertEqual(
                manager_actions._detail_url(
                    context,
                    "missing:view",
                    fallback="/dashboards/fallback/",
                    object_id=61,
                ),
                (
                    f"{self.base_url}"
                    "/dashboards/fallback/"
                ),
            )

    def test_manager_bot_url_falls_back_on_no_reverse_match(self):
        with patch(
            "apps.messaging.manager_bot.reverse",
            side_effect=NoReverseMatch("missing"),
        ):
            self.assertEqual(
                manager_bot._url(
                    self.base_url,
                    "missing:view",
                    fallback="/dashboards/",
                ),
                f"{self.base_url}/dashboards/",
            )

    def test_customer_unexpected_reverse_error_is_not_silenced(self):
        salon = SimpleNamespace(pk=11, slug="salon-test")
        detail = SimpleNamespace(pk=21)
        order = SimpleNamespace(pk=31)

        callbacks = (
            lambda: customer_bot._safe_url(
                self.base_url,
                "missing:view",
                fallback_path="/fallback/",
            ),
            lambda: customer_bot._salon_url(
                self.base_url,
                salon,
            ),
            lambda: customer_bot._appointment_detail_url(
                self.base_url,
                detail,
            ),
            lambda: customer_bot._rebook_url(
                self.base_url,
                order,
            ),
        )

        with patch(
            "apps.messaging.customer_bot.reverse",
            side_effect=RuntimeError(
                "unexpected URL failure"
            ),
        ):
            for callback in callbacks:
                with self.subTest(callback=callback):
                    with self.assertRaises(RuntimeError):
                        callback()

    def test_stylist_unexpected_reverse_error_is_not_silenced(self):
        detail = SimpleNamespace(pk=41)
        quick_link = SimpleNamespace(token="secure-token")

        callbacks = (
            lambda: stylist_bot._safe_dashboard_url(
                self.base_url,
                "missing:view",
            ),
            lambda: stylist_bot._appointment_detail_url(
                self.base_url,
                detail,
            ),
            lambda: stylist_bot._booking_quick_link_url(
                self.base_url,
                quick_link,
            ),
        )

        with patch(
            "apps.messaging.stylist_bot.reverse",
            side_effect=RuntimeError(
                "unexpected URL failure"
            ),
        ):
            for callback in callbacks:
                with self.subTest(callback=callback):
                    with self.assertRaises(RuntimeError):
                        callback()

    def test_action_unexpected_reverse_errors_are_not_silenced(self):
        context = SimpleNamespace(
            base_url=self.base_url,
        )
        detail = SimpleNamespace(pk=51)

        with patch(
            "apps.messaging.stylist_actions.reverse",
            side_effect=RuntimeError(
                "unexpected URL failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                stylist_actions._appointment_url(
                    context,
                    detail,
                )

        with patch(
            "apps.messaging.manager_actions.reverse",
            side_effect=RuntimeError(
                "unexpected URL failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                manager_actions._detail_url(
                    context,
                    "missing:view",
                    fallback="/dashboards/fallback/",
                    object_id=61,
                )

        with patch(
            "apps.messaging.manager_bot.reverse",
            side_effect=RuntimeError(
                "unexpected URL failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                manager_bot._url(
                    self.base_url,
                    "missing:view",
                    fallback="/dashboards/",
                )

    def test_url_helpers_have_no_broad_exception_handler(self):
        helpers = (
            customer_bot._safe_url,
            customer_bot._salon_url,
            customer_bot._appointment_detail_url,
            customer_bot._rebook_url,
            stylist_bot._safe_dashboard_url,
            stylist_bot._appointment_detail_url,
            stylist_bot._booking_quick_link_url,
            stylist_actions._appointment_url,
            manager_actions._detail_url,
            manager_bot._url,
        )

        for helper in helpers:
            with self.subTest(helper=helper.__name__):
                source = inspect.getsource(helper)

                self.assertIn(
                    "except NoReverseMatch:",
                    source,
                )
                self.assertNotIn(
                    "except Exception",
                    source,
                )
