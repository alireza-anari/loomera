import json
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import Resolver404, resolve

from apps.api.v1.contract import (
    get_app_api_v1_contract,
    get_app_api_v1_endpoint,
)


class AppApiContractSnapshotTests(TestCase):
    def test_contract_contains_required_app_api_endpoints(self):
        contract = get_app_api_v1_contract()
        endpoint_ids = {endpoint["id"] for endpoint in contract["endpoints"]}

        required_endpoint_ids = {
            "health",
            "meta",
            "public_salons",
            "public_salon_detail",
            "public_salon_services",
            "public_salon_stylists",
            "public_services",
            "availability",
            "next_available",
            "auth_status",
            "auth_me",
            "auth_policy",
            "otp_request",
            "otp_verify",
            "auth_logout",
            "booking_draft_validate",
            "booking_draft_summary",
            "booking_confirm",
            "my_appointments",
            "my_appointment_detail",
        }

        self.assertTrue(required_endpoint_ids.issubset(endpoint_ids))

    def test_contract_path_examples_resolve(self):
        contract = get_app_api_v1_contract()

        unresolved = []
        for endpoint in contract["endpoints"]:
            try:
                resolve(endpoint["path_example"])
            except Resolver404:
                unresolved.append(endpoint["id"])

        self.assertEqual(unresolved, [])

    def test_contract_locks_booking_payment_policy(self):
        contract = get_app_api_v1_contract()
        policy = contract["payment_policy"]

        self.assertFalse(policy["online_payment_enabled_for_booking_api"])
        self.assertEqual(policy["supported_booking_payment_methods"], ["pay_in_salon"])
        self.assertFalse(policy["creates_payment_on_confirm"])
        self.assertFalse(policy["changes_wallet_on_confirm"])
        self.assertFalse(policy["sends_notification_on_confirm"])

        booking_confirm = get_app_api_v1_endpoint("booking_confirm")
        self.assertIsNotNone(booking_confirm)
        self.assertEqual(
            booking_confirm["request_body"]["payment_method"],
            "pay_in_salon",
        )
        self.assertFalse(booking_confirm["side_effects"]["creates_payment"])
        self.assertFalse(booking_confirm["side_effects"]["changes_wallet"])
        self.assertFalse(booking_confirm["side_effects"]["sends_notification"])

    def test_contract_marks_customer_only_endpoints_as_auth_required(self):
        contract = get_app_api_v1_contract()
        endpoints = {endpoint["id"]: endpoint for endpoint in contract["endpoints"]}

        for endpoint_id in contract["auth_policy"]["customer_only_endpoints"]:
            self.assertTrue(endpoints[endpoint_id]["auth_required"])

    def test_contract_keeps_public_catalog_endpoints_public(self):
        endpoints = {
            endpoint["id"]: endpoint
            for endpoint in get_app_api_v1_contract()["endpoints"]
        }

        public_endpoint_ids = {
            "health",
            "meta",
            "public_salons",
            "public_salon_detail",
            "public_salon_services",
            "public_salon_stylists",
            "public_services",
            "availability",
            "next_available",
            "auth_status",
            "auth_policy",
            "otp_request",
            "otp_verify",
            "auth_logout",
        }

        for endpoint_id in public_endpoint_ids:
            self.assertFalse(endpoints[endpoint_id]["auth_required"])

    def test_contract_snapshot_command_text_output(self):
        out = StringIO()

        call_command("app_api_contract_snapshot", stdout=out)

        output = out.getvalue()
        self.assertIn("Loomera App API v1 Contract Snapshot", output)
        self.assertIn("booking_confirm", output)
        self.assertIn("my_appointments", output)
        self.assertIn("pay_in_salon", output)

    def test_contract_snapshot_command_json_output(self):
        out = StringIO()

        call_command("app_api_contract_snapshot", json_output=True, stdout=out)

        payload = json.loads(out.getvalue())
        endpoint_ids = {endpoint["id"] for endpoint in payload["endpoints"]}

        self.assertEqual(payload["contract_id"], "loomera-app-api-v1-a7")
        self.assertEqual(payload["api_version"], "v1")
        self.assertIn("booking_confirm", endpoint_ids)
        self.assertIn("my_appointment_detail", endpoint_ids)

    def test_contract_snapshot_command_can_filter_one_endpoint(self):
        out = StringIO()

        call_command(
            "app_api_contract_snapshot",
            endpoint_id="booking_confirm",
            json_output=True,
            stdout=out,
        )

        payload = json.loads(out.getvalue())

        self.assertEqual(payload["endpoint"]["id"], "booking_confirm")
        self.assertEqual(payload["endpoint"]["method"], "POST")
        self.assertEqual(payload["endpoint"]["success_status"], 201)

    def test_contract_snapshot_command_rejects_unknown_endpoint(self):
        out = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "app_api_contract_snapshot",
                endpoint_id="does_not_exist",
                stdout=out,
            )
