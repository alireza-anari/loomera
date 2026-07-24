from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.api.v1.contract import (
    get_app_api_v1_contract,
    get_app_api_v1_endpoint,
)


class Command(BaseCommand):
    help = "Print Loomera App API v1 contract snapshot for app/frontend handoff."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Output machine-readable JSON.",
        )
        parser.add_argument(
            "--endpoint",
            dest="endpoint_id",
            default="",
            help="Print only one endpoint contract by endpoint id.",
        )

    def handle(self, *args, **options):
        endpoint_id = str(options.get("endpoint_id") or "").strip()

        if endpoint_id:
            endpoint = get_app_api_v1_endpoint(endpoint_id)
            if endpoint is None:
                raise CommandError(f"Unknown App API contract endpoint: {endpoint_id}")

            payload = {
                "contract_id": "loomera-app-api-v1-a7",
                "api_version": "v1",
                "endpoint": endpoint,
            }
        else:
            payload = get_app_api_v1_contract()

        if options["json_output"]:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        self._write_text(payload)

    def _write_text(self, payload):
        self.stdout.write(self.style.SUCCESS("Loomera App API v1 Contract Snapshot"))

        if "endpoint" in payload:
            endpoint = payload["endpoint"]
            self._write_endpoint(endpoint)
            return

        self.stdout.write(f"Contract ID: {payload['contract_id']}")
        self.stdout.write(f"API Version: {payload['api_version']}")
        self.stdout.write("")

        payment_policy = payload["payment_policy"]
        self.stdout.write("Payment Policy:")
        self.stdout.write(
            f"- Supported booking payment methods: "
            f"{', '.join(payment_policy['supported_booking_payment_methods'])}"
        )
        self.stdout.write(
            f"- Creates payment on confirm: "
            f"{payment_policy['creates_payment_on_confirm']}"
        )
        self.stdout.write(
            f"- Changes wallet on confirm: "
            f"{payment_policy['changes_wallet_on_confirm']}"
        )
        self.stdout.write("")

        self.stdout.write("Endpoints:")
        for endpoint in payload["endpoints"]:
            self._write_endpoint(endpoint)

    def _write_endpoint(self, endpoint):
        auth_label = "customer-session" if endpoint["auth_required"] else "public"
        self.stdout.write(
            f"- {endpoint['id']} | {endpoint['method']} {endpoint['path']} | "
            f"auth={auth_label} | success={endpoint['success_status']}"
        )
