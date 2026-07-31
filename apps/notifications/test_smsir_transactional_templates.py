from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.notifications.smsir_transactional import (
    build_booking_parameters,
    send_smsir_transactional,
    template_setting_name,
)


class SMSIRTransactionalTemplateTests(SimpleTestCase):
    def _detail(self):
        salon = SimpleNamespace(salon_name="سالن آزمایشی لومرا")
        service = SimpleNamespace(service_name="کوتاهی و براشینگ")
        return SimpleNamespace(
            salon=salon,
            service=service,
            date=date(2026, 7, 31),
            time=time(16, 30),
        )

    def test_template_mapping(self):
        self.assertEqual(
            template_setting_name(
                event_type="booking_created",
                audience_role="customer",
            ),
            "SMSIR_BOOKING_CREATED_TEMPLATE_ID",
        )
        self.assertEqual(
            template_setting_name(
                event_type="booking_created",
                audience_role="stylist",
            ),
            "SMSIR_STYLIST_NEW_BOOKING_TEMPLATE_ID",
        )
        self.assertEqual(
            template_setting_name(
                event_type="stylist_confirmed",
                audience_role="customer",
            ),
            "SMSIR_BOOKING_CONFIRMED_TEMPLATE_ID",
        )

    def test_booking_parameters_match_approved_template_names(self):
        parameters = build_booking_parameters(
            order_detail=self._detail(),
        )

        self.assertEqual(
            [item["name"] for item in parameters],
            ["SALON", "SERVICE", "DATE", "TIME"],
        )
        self.assertEqual(parameters[0]["value"], "سالن آزمایشی لومرا")
        self.assertEqual(parameters[1]["value"], "کوتاهی و براشینگ")
        self.assertTrue(parameters[2]["value"])
        self.assertEqual(parameters[3]["value"], "۱۶:۳۰")

    @override_settings(
        SMSIR_TRANSACTIONAL_TEMPLATES_ENABLED=True,
        SMSIR_USE_SANDBOX=False,
        SMSIR_API_KEY="test-api-key",
        SMSIR_VERIFY_URL="https://api.sms.ir/v1/send/verify",
        SMSIR_BOOKING_CREATED_TEMPLATE_ID="572553",
        SMSIR_TIMEOUT_SECONDS=10,
    )
    @patch("apps.notifications.smsir_transactional.requests.post")
    def test_send_booking_created_uses_verify_template(
        self,
        mocked_post,
    ):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "status": 1,
            "message": "موفق",
            "data": {"messageId": 123456789},
        }
        mocked_post.return_value = response

        result = send_smsir_transactional(
            event_type="booking_created",
            audience_role="customer",
            mobile="09121234567",
            order_detail=self._detail(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "sent")
        self.assertEqual(result.response["template_id"], 572553)
        self.assertEqual(result.response["message_id"], "123456789")

        request_payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(request_payload["mobile"], "9121234567")
        self.assertEqual(request_payload["templateId"], 572553)
        self.assertEqual(
            [item["name"] for item in request_payload["parameters"]],
            ["SALON", "SERVICE", "DATE", "TIME"],
        )

    @override_settings(
        SMSIR_TRANSACTIONAL_TEMPLATES_ENABLED=True,
        SMSIR_USE_SANDBOX=False,
        SMSIR_API_KEY="test-api-key",
        SMSIR_BOOKING_CONFIRMED_TEMPLATE_ID="",
    )
    def test_mapped_event_without_template_is_pending_setup(self):
        result = send_smsir_transactional(
            event_type="stylist_confirmed",
            audience_role="customer",
            mobile="09121234567",
            order_detail=self._detail(),
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "pending_setup")
        self.assertIn(
            "SMSIR_BOOKING_CONFIRMED_TEMPLATE_ID",
            result.error,
        )

    @override_settings(
        SMSIR_TRANSACTIONAL_TEMPLATES_ENABLED=True,
        SMSIR_USE_SANDBOX=False,
        SMSIR_API_KEY="test-api-key",
    )
    def test_unmapped_event_can_fall_back_to_bulk(self):
        result = send_smsir_transactional(
            event_type="marketing_campaign",
            audience_role="customer",
            mobile="09121234567",
            order_detail=self._detail(),
        )

        self.assertIsNone(result)
