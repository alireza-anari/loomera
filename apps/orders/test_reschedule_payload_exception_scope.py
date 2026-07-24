from __future__ import annotations

import json as stdlib_json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser


class ReschedulePayloadExceptionScopeTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(
            mobile_number="09124567891",
            name="کاربر",
            family="تست",
            is_active=True,
        )
        self.client.force_login(self.user)
        self.url = reverse("orders:reschedule_confirm")

    def test_malformed_json_keeps_existing_user_facing_fallback(self):
        response = self.client.post(
            self.url,
            data={"booking_data": "{invalid-json"},
        )

        self.assertRedirects(
            response,
            reverse("orders:appointments"),
            fetch_redirect_response=False,
        )

    def test_type_error_is_treated_as_invalid_payload(self):
        isolated_json = SimpleNamespace(
            JSONDecodeError=stdlib_json.JSONDecodeError,
            loads=Mock(
                side_effect=TypeError("invalid input type")
            ),
        )

        with patch("apps.orders.views.json", isolated_json):
            response = self.client.post(
                self.url,
                data={"booking_data": "{}"},
            )

        self.assertRedirects(
            response,
            reverse("orders:appointments"),
            fetch_redirect_response=False,
        )

    def test_unexpected_json_loader_error_is_not_silenced(self):
        isolated_json = SimpleNamespace(
            JSONDecodeError=stdlib_json.JSONDecodeError,
            loads=Mock(
                side_effect=RuntimeError(
                    "unexpected JSON loader failure"
                )
            ),
        )

        with patch("apps.orders.views.json", isolated_json):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.url,
                    data={"booking_data": "{}"},
                )
