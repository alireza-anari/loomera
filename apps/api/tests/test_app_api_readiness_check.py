import json
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

API_TEST_REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-readiness-check-tests",
        }
    },
    REST_FRAMEWORK=API_TEST_REST_FRAMEWORK,
    ONLINE_PAYMENT_ENABLED=False,
    LOOMERA_API_VERSION="v1",
    LOOMERA_PUBLIC_APP_VERSION="beta",
    LOOMERA_API_PUBLIC_QUERY_MAX_CHARS=256,
    LOOMERA_API_PUBLIC_LIST_MAX_LIMIT=50,
    LOOMERA_API_AVAILABILITY_MAX_DAYS_AHEAD=45,
    LOOMERA_API_AVAILABILITY_MAX_SLOTS_PER_STYLIST=40,
    LOOMERA_API_NEXT_AVAILABLE_MAX_DAYS=14,
    LOOMERA_API_AUTH_OTP_LENGTH=6,
    LOOMERA_API_AUTH_OTP_TTL_SECONDS=120,
    LOOMERA_API_AUTH_OTP_RESEND_SECONDS=60,
    LOOMERA_API_AUTH_MAX_VERIFY_ATTEMPTS=5,
    LOOMERA_API_AUTH_OTP_REQUEST_MAX_BYTES=2 * 1024,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_MOBILE_HOUR=5,
    LOOMERA_API_AUTH_OTP_REQUEST_RATE_PER_IP_HOUR=30,
    LOOMERA_API_AUTH_OTP_CACHE_PREFIX="loomera:test-api-auth-otp",
    LOOMERA_API_AUTH_OTP_FAIL_CLOSED=True,
    LOOMERA_API_BOOKING_DRAFT_MAX_BYTES=4 * 1024,
)
class AppApiReadinessCheckCommandTests(TestCase):
    def test_app_api_readiness_check_passes_in_local_mode(self):
        out = StringIO()

        call_command("app_api_readiness_check", stdout=out)

        output = out.getvalue()
        self.assertIn("App API readiness: OK", output)
        self.assertIn("route_booking_confirm", output)
        self.assertIn("route_my_appointments", output)
        self.assertIn("cache_remote_backend", output)

    def test_app_api_readiness_check_json_output_is_machine_readable(self):
        out = StringIO()

        call_command("app_api_readiness_check", json_output=True, stdout=out)

        payload = json.loads(out.getvalue())

        self.assertTrue(payload["ok"])
        self.assertIn("summary", payload)
        self.assertIn("checks", payload)

        codes = {check["code"] for check in payload["checks"]}
        self.assertIn("route_health", codes)
        self.assertIn("route_booking_draft_validate", codes)
        self.assertIn("route_booking_confirm", codes)
        self.assertIn("route_my_appointments", codes)
        self.assertIn("setting_otp_fail_closed", codes)
        self.assertIn("payment_online_policy_visible", codes)

    def test_strict_does_not_fail_on_local_cache_unless_remote_cache_required(self):
        out = StringIO()

        call_command("app_api_readiness_check", strict=True, stdout=out)

        output = out.getvalue()
        self.assertIn("App API readiness: OK", output)
        self.assertIn("[WARN] cache_remote_backend", output)

    def test_strict_can_require_remote_cache_for_staging_or_production(self):
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "app_api_readiness_check",
                strict=True,
                require_remote_cache=True,
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("[FAIL] cache_remote_backend", output)

    @override_settings(ONLINE_PAYMENT_ENABLED=True)
    def test_strict_can_require_online_payment_disabled(self):
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "app_api_readiness_check",
                strict=True,
                require_online_payment_disabled=True,
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("[FAIL] payment_online_disabled", output)

    @override_settings(LOOMERA_API_AUTH_OTP_FAIL_CLOSED=False)
    def test_strict_fails_when_otp_policy_is_not_fail_closed(self):
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command("app_api_readiness_check", strict=True, stdout=out)

        output = out.getvalue()
        self.assertIn("[FAIL] setting_otp_fail_closed", output)
