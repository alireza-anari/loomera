from datetime import time
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.help_center.actions.customer_booking import (
    _period_matches,
    _positive_int,
)


class CustomerBookingPureTests(SimpleTestCase):
    def test_positive_int_rejects_invalid_ids(self):
        self.assertEqual(_positive_int("12"), 12)
        self.assertIsNone(_positive_int("0"))
        self.assertIsNone(_positive_int("-1"))
        self.assertIsNone(_positive_int("abc"))

    def test_period_windows_match_search_semantics(self):
        self.assertTrue(_period_matches(time(9, 0), "morning"))
        self.assertFalse(_period_matches(time(15, 0), "morning"))
        self.assertTrue(_period_matches(time(17, 30), "evening"))
        self.assertTrue(_period_matches(time(20, 0), "night"))


class CustomerBookingApiContractTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.help_center.action_views._consume_action_limit", return_value=True)
    @patch("apps.help_center.action_views.run_customer_booking_action")
    def test_booking_api_forwards_only_allowed_action(self, runner, _limit):
        from apps.help_center.action_views import customer_booking_api

        runner.return_value = {"handled": True, "kind": "booking_slots", "slots": []}
        request = self.factory.post(
            "/help/api/actions/customer-booking/",
            data='{"action":"select_stylist","action_state":{"mode":"customer_booking"}}',
            content_type="application/json",
        )
        request.user = Mock(is_authenticated=True, pk=10)
        response = customer_booking_api(request)
        self.assertEqual(response.status_code, 200)
        runner.assert_called_once()

    def test_booking_api_rejects_unknown_action(self):
        from apps.help_center.action_views import customer_booking_api

        request = self.factory.post(
            "/help/api/actions/customer-booking/",
            data='{"action":"delete_everything"}',
            content_type="application/json",
        )
        request.user = Mock(is_authenticated=True, pk=10)
        response = customer_booking_api(request)
        self.assertEqual(response.status_code, 400)
