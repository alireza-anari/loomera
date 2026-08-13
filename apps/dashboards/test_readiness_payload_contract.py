from django.test import SimpleTestCase

from apps.dashboards.readiness import build_salon_readiness_checklist


class ReadinessPayloadContractTests(SimpleTestCase):
    def test_empty_salon_payload_does_not_claim_dashboard_contract(self):
        payload = build_salon_readiness_checklist(None)
        self.assertEqual(payload["items"], [])

    def test_source_exposes_dashboard_compatibility_keys(self):
        # Runtime regression guard for dashboard views/templates that consume
        # the richer canonical readiness payload.
        from pathlib import Path
        import apps.dashboards.readiness as readiness_module

        source = Path(readiness_module.__file__).read_text(encoding="utf-8")
        self.assertIn('"booking_items": booking_items', source)
        self.assertIn('"profile_quality_items": profile_quality_items', source)
        self.assertIn('"next_action": next_action', source)
