from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse


ACTIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "workflow_actions.json"
DOCS_FILE = Path(__file__).resolve().parents[1] / "data" / "production_docs.json"


class WorkflowActionCatalogTests(SimpleTestCase):
    def setUp(self):
        self.actions = json.loads(ACTIONS_FILE.read_text(encoding="utf-8"))["articles"]
        self.docs = json.loads(DOCS_FILE.read_text(encoding="utf-8"))["articles"]

    def test_every_production_workflow_has_structured_steps(self):
        workflow_keys = {
            article["key"]
            for article in self.docs
            if article.get("article_type") == "workflow"
        }
        self.assertEqual(workflow_keys - set(self.actions), set())
        for key in workflow_keys:
            self.assertTrue(self.actions[key].get("steps"), key)

    def test_all_static_routes_are_reversible_without_entity_ids(self):
        broken = []
        for key, spec in self.actions.items():
            for index, step in enumerate(spec.get("steps", []), 1):
                route = str(step.get("route_name") or "").strip()
                if not route:
                    continue
                try:
                    reverse(route)
                except NoReverseMatch:
                    broken.append(f"{key}#{index}:{route}")
        self.assertEqual(broken, [])

    def test_priority_workflows_have_clickable_entry_points(self):
        priority = {
            "stylist.leave.request",
            "stylist.schedule.request",
            "manager.team.add-stylist",
            "manager.discounts.coupons",
            "customer.wallet.charge",
            "customer.account.address-add",
            "messaging.bale.connect",
        }
        for key in priority:
            self.assertTrue(
                any(step.get("route_name") for step in self.actions[key]["steps"]),
                key,
            )
