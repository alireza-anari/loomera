from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.help_center.actions.common import (
    issue_confirmation,
    parse_time_range,
    parse_weekday_dates,
    read_confirmation,
)


class LumiActionCommonTests(SimpleTestCase):
    def test_parses_conversational_9_to_5_as_day_shift(self):
        start, end = parse_time_range("از ۹ صبح تا ۵ عصر")
        self.assertEqual(start, time(9, 0))
        self.assertEqual(end, time(17, 0))

    def test_parses_weekday_range_in_order(self):
        values = parse_weekday_dates("شنبه تا چهارشنبه", today=date(2026, 8, 28))
        self.assertEqual(len(values), 5)
        self.assertEqual([item.weekday() for item in values], [5, 6, 0, 1, 2])

    def test_signed_confirmation_is_bound_to_user(self):
        owner = SimpleNamespace(pk=10, is_authenticated=True)
        other = SimpleNamespace(pk=11, is_authenticated=True)
        token = issue_confirmation(user=owner, action="stylist_schedule_create", data={"x": 1})
        payload = read_confirmation(user=owner, token=token)
        self.assertEqual(payload["action"], "stylist_schedule_create")
        with self.assertRaises(ValidationError):
            read_confirmation(user=other, token=token)
    @patch("apps.help_center.actions.common.cache.add", return_value=False)
    def test_confirmation_replay_is_rejected(self, _cache_add):
        owner = SimpleNamespace(pk=10, is_authenticated=True)
        token = issue_confirmation(user=owner, action="stylist_schedule_create", data={"x": 1})
        with self.assertRaises(ValidationError):
            read_confirmation(user=owner, token=token, consume=True)

    @patch("apps.help_center.actions.common.cache.add", side_effect=RuntimeError("cache down"))
    def test_confirmation_replay_protection_fails_closed(self, _cache_add):
        owner = SimpleNamespace(pk=10, is_authenticated=True)
        token = issue_confirmation(user=owner, action="stylist_schedule_create", data={"x": 1})
        with self.assertRaisesMessage(ValidationError, "سامانه تأیید عملیات موقتاً در دسترس نیست"):
            read_confirmation(user=owner, token=token, consume=True)

