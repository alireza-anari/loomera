from django.test import SimpleTestCase

from apps.main.sentry_privacy import (
    REDACTED,
    sentry_before_breadcrumb,
    sentry_before_send,
)


class SentryPrivacyTests(SimpleTestCase):
    def test_sensitive_request_and_identity_data_are_removed(self):
        event = {
            "request": {
                "url": (
                    "https://loomera.ir/accounts/verify/"
                    "?otp=123456&token=very-secret"
                ),
                "method": "POST",
                "query_string": "otp=123456&token=very-secret",
                "data": {
                    "phone": "09121234567",
                    "otp": "123456",
                    "password": "my-password",
                },
                "cookies": {
                    "sessionid": "secret-session",
                },
                "env": {
                    "REMOTE_ADDR": "192.0.2.10",
                },
                "headers": {
                    "Authorization": "Bearer very-secret",
                    "Cookie": "sessionid=very-secret",
                    "X-CSRFToken": "very-secret",
                    "X-Forwarded-For": "192.0.2.10",
                    "User-Agent": "Loomera privacy test",
                    "Content-Type": "application/json",
                    "Host": "loomera.ir",
                },
            },
            "user": {
                "id": "23",
                "username": "09121234567",
                "email": "customer@example.com",
                "ip_address": "192.0.2.10",
            },
        }

        cleaned = sentry_before_send(event, None)

        self.assertNotIn("user", cleaned)

        request = cleaned["request"]

        self.assertNotIn("url", request)
        self.assertNotIn("query_string", request)
        self.assertNotIn("data", request)
        self.assertNotIn("cookies", request)
        self.assertNotIn("env", request)

        headers = request["headers"]

        self.assertNotIn("Authorization", headers)
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("X-CSRFToken", headers)
        self.assertNotIn("X-Forwarded-For", headers)

        self.assertEqual(
            headers["User-Agent"],
            "Loomera privacy test",
        )
        self.assertEqual(
            headers["Content-Type"],
            "application/json",
        )
        self.assertEqual(
            headers["Host"],
            "loomera.ir",
        )

    def test_nested_sensitive_values_are_redacted(self):
        event = {
            "message": ("Customer 09121234567 customer@example.com " "token=abcdef123"),
            "extra": {
                "api_key": "secret-api-key",
                "nested": {
                    "password": "secret-password",
                    "phone": "09121234567",
                    "safe_value": "booking_failed",
                },
            },
            "tags": {
                "safe_tag": "production",
            },
        }

        cleaned = sentry_before_send(event, None)

        self.assertNotIn("09121234567", cleaned["message"])
        self.assertNotIn(
            "customer@example.com",
            cleaned["message"],
        )
        self.assertNotIn(
            "abcdef123",
            cleaned["message"],
        )

        self.assertEqual(
            cleaned["extra"]["api_key"],
            REDACTED,
        )
        self.assertEqual(
            cleaned["extra"]["nested"]["password"],
            REDACTED,
        )
        self.assertEqual(
            cleaned["extra"]["nested"]["phone"],
            REDACTED,
        )

        self.assertEqual(
            cleaned["extra"]["nested"]["safe_value"],
            "booking_failed",
        )
        self.assertEqual(
            cleaned["tags"]["safe_tag"],
            "production",
        )

    def test_stack_frame_local_variables_are_removed(self):
        event = {
            "exception": {
                "values": [
                    {
                        "type": "RuntimeError",
                        "value": "booking failed",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "apps/orders/views.py",
                                    "function": "checkout",
                                    "vars": {
                                        "otp": "123456",
                                        "phone": "09121234567",
                                        "secret": "value",
                                    },
                                }
                            ]
                        },
                    }
                ]
            }
        }

        cleaned = sentry_before_send(event, None)

        frame = cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]

        self.assertNotIn("vars", frame)

    def test_breadcrumbs_are_scrubbed(self):
        breadcrumb = {
            "category": "loomera.test",
            "message": (
                "phone=09121234567 " "email customer@example.com " "token=secret-value"
            ),
            "data": {
                "otp": "123456",
                "safe_status": "failed",
            },
        }

        cleaned = sentry_before_breadcrumb(
            breadcrumb,
            None,
        )

        self.assertNotIn(
            "09121234567",
            cleaned["message"],
        )
        self.assertNotIn(
            "customer@example.com",
            cleaned["message"],
        )
        self.assertNotIn(
            "secret-value",
            cleaned["message"],
        )

        self.assertEqual(
            cleaned["data"]["otp"],
            REDACTED,
        )
        self.assertEqual(
            cleaned["data"]["safe_status"],
            "failed",
        )
