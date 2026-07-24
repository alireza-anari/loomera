from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.payments.gateways import (
    initiate_payment,
    verify_payment,
)
from apps.payments.models import Payment


class DummyRequest:
    def build_absolute_uri(self, path):
        return f"https://loomera.test{path}"


@override_settings(
    PAYMENT_MODE="sandbox",
    PAYMENT_PROVIDER="zibal",
    ZIBAL_SANDBOX_MERCHANT="zibal",
    PAYMENT_PUBLIC_BASE_URL="",
    PAYMENT_TIMEOUT_SECONDS=15,
)
class GatewayInitResponseParsingTests(SimpleTestCase):
    def make_payment(self):
        return SimpleNamespace(
            id=101,
            pk=101,
            order_id=501,
            callback_token="callback-token",
            purpose=Payment.Purpose.APPOINTMENT,
            Purpose=Payment.Purpose,
        )

    def call_initiate(self):
        return initiate_payment(
            request=DummyRequest(),
            payment=self.make_payment(),
            amount_toman=120_000,
            description="رزرو آزمایشی",
            mobile_number="09121234567",
        )

    @patch("apps.payments.gateways.requests.post")
    def test_valid_gateway_response_succeeds(
        self,
        mocked_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": 100,
            "trackId": 123456,
            "message": "success",
        }
        mocked_post.return_value = response

        result = self.call_initiate()

        self.assertTrue(result.success)
        self.assertEqual(result.code, 100)
        self.assertEqual(result.track_id, "123456")
        self.assertIn(
            "/start/123456",
            result.payment_url,
        )

    @patch("apps.payments.gateways.requests.post")
    def test_non_object_json_is_controlled_failure(
        self,
        mocked_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [
            {"result": 100},
        ]
        mocked_post.return_value = response

        result = self.call_initiate()

        self.assertFalse(result.success)
        self.assertIsNone(result.code)
        self.assertIsNone(result.track_id)
        self.assertEqual(
            result.message,
            "ساختار پاسخ درگاه معتبر نبود.",
        )

    @patch("apps.payments.gateways.requests.post")
    def test_invalid_result_code_is_controlled_failure(
        self,
        mocked_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "result": "not-a-number",
            "trackId": "track-101",
        }
        mocked_post.return_value = response

        result = self.call_initiate()

        self.assertFalse(result.success)
        self.assertIsNone(result.code)
        self.assertIsNone(result.track_id)
        self.assertEqual(
            result.message,
            "کد نتیجه درگاه معتبر نبود.",
        )

    @patch("apps.payments.gateways.requests.post")
    def test_missing_result_code_is_controlled_failure(
        self,
        mocked_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "trackId": "track-101",
        }
        mocked_post.return_value = response

        result = self.call_initiate()

        self.assertFalse(result.success)
        self.assertIsNone(result.code)
        self.assertEqual(
            result.message,
            "کد نتیجه درگاه معتبر نبود.",
        )

    @patch("apps.payments.gateways.requests.post")
    def test_invalid_json_keeps_existing_failure(
        self,
        mocked_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError(
            "invalid json"
        )
        mocked_post.return_value = response

        result = self.call_initiate()

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "\u067e\u0627\u0633\u062e \u062f\u0631\u06af\u0627\u0647 \u0642\u0627\u0628\u0644 \u067e\u0631\u062f\u0627\u0632\u0634 \u0646\u0628\u0648\u062f.",
        )

    @patch("apps.payments.gateways.requests.post")
    def test_unexpected_json_runtime_error_is_not_silenced(
        self,
        mocked_post,
    ):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = RuntimeError(
            "unexpected gateway parser failure"
        )
        mocked_post.return_value = response

        with self.assertRaises(RuntimeError):
            self.call_initiate()

    def test_gateway_core_has_no_broad_exception_handlers(
        self,
    ):
        for function in (
            initiate_payment,
            verify_payment,
        ):
            with self.subTest(function=function.__name__):
                source = textwrap.dedent(
                    inspect.getsource(function)
                )
                tree = ast.parse(source)
                violations = []

                for node in ast.walk(tree):
                    if not isinstance(
                        node,
                        ast.ExceptHandler,
                    ):
                        continue

                    if node.type is None:
                        violations.append(
                            f"bare except at line {node.lineno}"
                        )
                        continue

                    exception_name = ast.unparse(
                        node.type
                    )

                    if exception_name in {
                        "Exception",
                        "BaseException",
                    }:
                        violations.append(
                            f"{exception_name} at line "
                            f"{node.lineno}"
                        )

                self.assertEqual(
                    violations,
                    [],
                    msg=(
                        "Gateway core must not hide unexpected "
                        "programming failures: "
                        + ", ".join(violations)
                    ),
                )
