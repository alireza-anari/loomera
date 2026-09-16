from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.help_center.action_views import (
    assistant_action_api,
    customer_booking_api,
    customer_discovery_api,
)


class LumiActionErrorBoundaryTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, pk=7)

    @patch("apps.help_center.action_views.logger.exception")
    @patch(
        "apps.help_center.action_views.run_customer_discovery",
        side_effect=RuntimeError("private discovery failure"),
    )
    @patch(
        "apps.help_center.action_views.is_customer_discovery_candidate",
        return_value=True,
    )
    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    def test_discovery_hides_unexpected_backend_error(
        self, _limit, _candidate, _run, log_exception
    ):
        request = self.factory.post(
            "/help/lumi/discovery/",
            data=json.dumps({"message": "یه آرایشگاه نزدیکم پیدا کن"}),
            content_type="application/json",
        )
        request.user = self.user

        response = customer_discovery_api(request)
        body = response.content.decode("utf-8")
        payload = json.loads(body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            payload["error"],
            "الان نتونستم این کار رو انجام بدم. دوباره امتحان کن.",
        )
        self.assertNotIn("private discovery failure", body)
        log_exception.assert_called_once()

    @patch("apps.help_center.action_views.logger.exception")
    @patch(
        "apps.help_center.action_views.run_customer_booking_action",
        side_effect=RuntimeError("database exploded"),
    )
    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    def test_booking_hides_unexpected_backend_error(
        self, _limit, _run, log_exception
    ):
        request = self.factory.post(
            "/help/lumi/booking/",
            data=json.dumps({"action": "select_salon"}),
            content_type="application/json",
        )
        request.user = self.user

        response = customer_booking_api(request)
        body = response.content.decode("utf-8")
        payload = json.loads(body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            payload["error"],
            "الان نتونستم این کار رو انجام بدم. دوباره امتحان کن.",
        )
        self.assertNotIn("database exploded", body)
        log_exception.assert_called_once()

    @patch("apps.help_center.action_views.logger.exception")
    @patch(
        "apps.help_center.action_views.run_assistant_action",
        side_effect=RuntimeError("ObjectDoesNotExist: private detail"),
    )
    @patch(
        "apps.help_center.action_views.is_assistant_action_candidate",
        return_value=True,
    )
    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    def test_assistant_message_hides_unexpected_backend_error(
        self, _limit, _candidate, _run, log_exception
    ):
        request = self.factory.post(
            "/help/lumi/action/",
            data=json.dumps(
                {"command": "message", "message": "نوبت‌های امروزم رو نشون بده"}
            ),
            content_type="application/json",
        )
        request.user = self.user

        response = assistant_action_api(request)
        body = response.content.decode("utf-8")
        payload = json.loads(body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            payload["error"],
            "الان نتونستم این کار رو انجام بدم. دوباره امتحان کن.",
        )
        self.assertNotIn("ObjectDoesNotExist", body)
        self.assertNotIn("private detail", body)
        log_exception.assert_called_once()

    @patch("apps.help_center.action_views.logger.exception")
    @patch(
        "apps.help_center.action_views.execute_assistant_confirmation",
        side_effect=RuntimeError("write result unknown"),
    )
    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    def test_execute_failure_never_claims_success(
        self, _limit, _execute, log_exception
    ):
        request = self.factory.post(
            "/help/lumi/action/",
            data=json.dumps(
                {
                    "command": "execute",
                    "confirmation_token": "signed-token-placeholder",
                }
            ),
            content_type="application/json",
        )
        request.user = self.user

        response = assistant_action_api(request)
        body = response.content.decode("utf-8")
        payload = json.loads(body)

        self.assertEqual(response.status_code, 500)
        self.assertIn("با اطمینان تأیید", payload["error"])
        self.assertNotIn("انجام شد", payload["error"])
        self.assertNotIn("write result unknown", body)
        log_exception.assert_called_once()
