from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from .subscriptions import (
    InstagramWebhookSubscriptionError,
    subscribe_professional_account,
    unsubscribe_professional_account,
)


SETTINGS = {
    "INSTAGRAM_GRAPH_BASE_URL": "https://graph.instagram.com",
    "INSTAGRAM_GRAPH_API_VERSION": "v24.0",
    "INSTAGRAM_REQUEST_TIMEOUT": 10,
    "INSTAGRAM_WEBHOOK_SUBSCRIBED_FIELDS": ["messages"],
}


@override_settings(**SETTINGS)
class InstagramWebhookSubscriptionTests(SimpleTestCase):
    @patch("apps.instagram_integration.subscriptions.requests.post")
    def test_subscribe_uses_account_endpoint_and_messages_field(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"success": True}
        post.return_value = response

        result = subscribe_professional_account(
            account_id="ig-123",
            access_token="secret-token",
        )

        self.assertTrue(result.success)
        args, kwargs = post.call_args
        self.assertEqual(
            args[0],
            "https://graph.instagram.com/v24.0/ig-123/subscribed_apps",
        )
        self.assertEqual(
            kwargs["json"],
            {"subscribed_fields": ["messages"]},
        )
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer secret-token",
        )
        self.assertNotIn("secret-token", args[0])

    @patch("apps.instagram_integration.subscriptions.requests.post")
    def test_subscribe_provider_failure_is_safe(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 403
        post.return_value = response

        with self.assertRaises(InstagramWebhookSubscriptionError):
            subscribe_professional_account(
                account_id="ig-123",
                access_token="secret-token",
            )

    @patch("apps.instagram_integration.subscriptions.requests.post")
    def test_subscribe_network_failure_is_safe(self, post):
        post.side_effect = requests.Timeout("timeout")

        with self.assertRaises(InstagramWebhookSubscriptionError):
            subscribe_professional_account(
                account_id="ig-123",
                access_token="secret-token",
            )

    @override_settings(INSTAGRAM_WEBHOOK_SUBSCRIBED_FIELDS=[])
    def test_messages_field_is_mandatory(self):
        with self.assertRaises(InstagramWebhookSubscriptionError):
            subscribe_professional_account(
                account_id="ig-123",
                access_token="secret-token",
            )

    @patch("apps.instagram_integration.subscriptions.requests.delete")
    def test_unsubscribe_uses_same_account_endpoint(self, delete):
        response = Mock()
        response.ok = True
        response.json.return_value = {"success": True}
        delete.return_value = response

        result = unsubscribe_professional_account(
            account_id="ig-123",
            access_token="secret-token",
        )

        self.assertTrue(result)
        args, kwargs = delete.call_args
        self.assertEqual(
            args[0],
            "https://graph.instagram.com/v24.0/ig-123/subscribed_apps",
        )
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer secret-token",
        )

    @patch("apps.instagram_integration.subscriptions.requests.delete")
    def test_unsubscribe_failure_never_raises(self, delete):
        delete.side_effect = requests.Timeout("timeout")

        self.assertFalse(
            unsubscribe_professional_account(
                account_id="ig-123",
                access_token="secret-token",
            )
        )
