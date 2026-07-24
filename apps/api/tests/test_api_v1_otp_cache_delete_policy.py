from __future__ import annotations

import inspect
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.api.v1.auth_otp import (
    ApiOtpRateLimitUnavailable,
    _cache_delete,
    verify_api_otp_code,
)


class ApiOtpCacheDeletePolicyTests(SimpleTestCase):
    @patch(
        "apps.api.v1.auth_otp.cache.delete",
        return_value=True,
    )
    def test_successful_delete_returns_true(
        self,
        mocked_delete,
    ):
        result = _cache_delete(
            "loomera:test:record:app_login:masked",
            context="verified",
            required=True,
        )

        self.assertTrue(result)
        mocked_delete.assert_called_once()

    @override_settings(
        LOOMERA_API_AUTH_OTP_FAIL_CLOSED=True
    )
    @patch(
        "apps.api.v1.auth_otp.cache.delete",
        side_effect=RuntimeError("cache unavailable"),
    )
    def test_best_effort_delete_does_not_raise(
        self,
        mocked_delete,
    ):
        result = _cache_delete(
            "loomera:test:record:app_login:masked",
            context="expired",
            required=False,
        )

        self.assertFalse(result)
        mocked_delete.assert_called_once()

    @override_settings(
        LOOMERA_API_AUTH_OTP_FAIL_CLOSED=True
    )
    @patch(
        "apps.api.v1.auth_otp.cache.delete",
        side_effect=RuntimeError("cache unavailable"),
    )
    def test_required_delete_fails_closed(
        self,
        mocked_delete,
    ):
        with self.assertRaises(
            ApiOtpRateLimitUnavailable
        ):
            _cache_delete(
                "loomera:test:record:app_login:masked",
                context="verified",
                required=True,
            )

        mocked_delete.assert_called_once()

    @override_settings(
        LOOMERA_API_AUTH_OTP_FAIL_CLOSED=False
    )
    @patch(
        "apps.api.v1.auth_otp.cache.delete",
        side_effect=RuntimeError("cache unavailable"),
    )
    def test_required_delete_can_follow_local_open_policy(
        self,
        mocked_delete,
    ):
        result = _cache_delete(
            "loomera:test:record:app_login:masked",
            context="verified",
            required=True,
        )

        self.assertFalse(result)
        mocked_delete.assert_called_once()

    def test_verify_flow_has_no_direct_cache_delete_catch(self):
        source = inspect.getsource(
            verify_api_otp_code
        )

        self.assertNotIn(
            "cache.delete(",
            source,
        )
        self.assertNotIn(
            "except Exception",
            source,
        )
