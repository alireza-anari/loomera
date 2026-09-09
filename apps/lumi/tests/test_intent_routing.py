from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.lumi.context import build_lumi_context
from apps.lumi.orchestrator import DEFAULT_MODEL_ROUTABLE_TOOLS, LumiOrchestrator
from apps.lumi.providers.base import ModelProviderError
from apps.lumi.schemas.intents import StructuredIntent
from apps.lumi.tools import build_default_registry


class Guest:
    is_authenticated = False


class Customer:
    is_authenticated = True
    pk = 41
    is_admin = False
    is_superuser = False
    customer_profile = SimpleNamespace(pk=9)


class FakeDomain:
    def __init__(self):
        self.calls = []

    def get_services(self, *, salon_id=None, query="", limit=20):
        self.calls.append(("get_services", {"salon_id": salon_id, "query": query, "limit": limit}))
        if "رنگ" in query:
            return {"services": [{"id": 12, "salon_service_id": 112, "name": "رنگ مو"}]}
        if "مو" in query:
            return {
                "services": [
                    {"id": 12, "salon_service_id": 112, "name": "رنگ مو"},
                    {"id": 13, "salon_service_id": 113, "name": "کوتاهی مو"},
                ]
            }
        return {"services": []}

    def get_service_price(self, *, salon_id, service_id, stylist_id=None):
        self.calls.append(("get_service_price", {"salon_id": salon_id, "service_id": service_id, "stylist_id": stylist_id}))
        return {
            "salon_id": salon_id,
            "service_id": service_id,
            "service_name": "رنگ مو",
            "min_price": 320000,
            "max_price": 320000,
            "prices": [],
        }

    def get_contact(self, *, salon_id):
        self.calls.append(("get_contact", {"salon_id": salon_id}))
        return {"salon_id": salon_id, "name": "سالن تست", "address": "تهران", "phone": ""}

    def get_availability(self, *, salon_id, service_id, stylist_id=None, date="", period="", limit=18):
        self.calls.append(
            (
                "get_availability",
                {
                    "salon_id": salon_id,
                    "service_id": service_id,
                    "stylist_id": stylist_id,
                    "date": date,
                    "period": period,
                    "limit": limit,
                },
            )
        )
        return {
            "salon_id": salon_id,
            "service_id": service_id,
            "service_name": "رنگ مو",
            "options": [{"date": date, "time": "17:00", "stylist_name": "سارا"}],
        }

    def prepare_booking(self, *, context, arguments):
        raise AssertionError("prepare_booking must never be model-routed in Phase C")


class FakeModel:
    enabled = True

    def __init__(self, intent):
        self.intent = intent
        self.seen_context = None
        self.seen_tools = None

    def extract_intent(self, *, message, context, tools):
        self.seen_context = context
        self.seen_tools = tools
        return self.intent


class FailingModel:
    enabled = True

    def extract_intent(self, **kwargs):
        raise ModelProviderError("provider unavailable")


class IntentRoutingTests(unittest.TestCase):
    def _context(self, user=None):
        return build_lumi_context(
            user=user or Guest(),
            channel="telegram",
            session_id="secret-session-id",
            metadata={
                "scope_type": "salon",
                "salon_id": 4,
                "reference_date": "2026-09-09",
                "private_note": "must-not-leak",
            },
        )

    def _orchestrator(self, model, domain=None):
        domain = domain or FakeDomain()
        return LumiOrchestrator(
            registry=build_default_registry(domain=domain),
            model=model,
            model_allowed_tools=DEFAULT_MODEL_ROUTABLE_TOOLS,
            min_confidence=0.65,
        ), domain

    def test_persian_entities_are_resolved_server_side(self):
        model = FakeModel(
            StructuredIntent(
                intent="get_availability",
                arguments={
                    "service_query": "رنگ مو",
                    "date": "فردا",
                    "time_preference": "عصر",
                    "salon_id": 999,
                    "service_id": 999,
                    "stylist_id": 999,
                },
                confidence=0.94,
            )
        )
        orchestrator, domain = self._orchestrator(model)
        result = orchestrator.route_message(context=self._context(), message="فردا عصر برای رنگ مو جا دارید؟")
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(result.tool, "get_availability")
        availability_call = [item for item in domain.calls if item[0] == "get_availability"][-1][1]
        self.assertEqual(availability_call["salon_id"], 4)
        self.assertEqual(availability_call["service_id"], 12)
        self.assertIsNone(availability_call["stylist_id"])
        self.assertEqual(availability_call["date"], "2026-09-10")
        self.assertEqual(availability_call["period"], "evening")

    def test_model_never_receives_user_or_scope_ids(self):
        model = FakeModel(StructuredIntent(intent="get_contact", arguments={}, confidence=0.9))
        orchestrator, _ = self._orchestrator(model)
        result = orchestrator.route_message(context=self._context(Customer()), message="راه ارتباطی چیه؟")
        self.assertTrue(result.ok)
        self.assertNotIn("user_id", model.seen_context)
        self.assertNotIn("session_id", model.seen_context)
        self.assertNotIn("salon_id", model.seen_context)
        self.assertNotIn("private_note", model.seen_context)
        self.assertEqual(model.seen_context["scope_type"], "salon")

    def test_sensitive_tool_suggestion_is_rejected(self):
        model = FakeModel(StructuredIntent(intent="prepare_booking", arguments={}, confidence=0.99))
        orchestrator, domain = self._orchestrator(model)
        result = orchestrator.route_message(context=self._context(Customer()), message="رزروش کن")
        self.assertIsNone(result)
        self.assertFalse(any(name == "prepare_booking" for name, _args in domain.calls))
        advertised = {item["name"] for item in model.seen_tools}
        self.assertNotIn("prepare_booking", advertised)
        self.assertNotIn("confirm_booking", advertised)
        self.assertNotIn("cancel_booking", advertised)

    def test_provider_failure_falls_back_without_tool_execution(self):
        orchestrator, domain = self._orchestrator(FailingModel())
        result = orchestrator.route_message(context=self._context(), message="یه سوال عجیب")
        self.assertIsNone(result)
        self.assertEqual(domain.calls, [])

    def test_low_confidence_falls_back(self):
        model = FakeModel(StructuredIntent(intent="get_contact", arguments={}, confidence=0.31))
        orchestrator, domain = self._orchestrator(model)
        self.assertIsNone(orchestrator.route_message(context=self._context(), message="شاید آدرسه"))
        self.assertEqual(domain.calls, [])

    def test_ambiguous_service_does_not_guess(self):
        model = FakeModel(
            StructuredIntent(intent="get_service_price", arguments={"service_query": "مو"}, confidence=0.9)
        )
        orchestrator, domain = self._orchestrator(model)
        result = orchestrator.route_message(context=self._context(), message="قیمت کارهای مو چنده؟")
        self.assertTrue(result.ok)
        self.assertTrue(result.data["needs_clarification"])
        self.assertEqual(len(result.data["services"]), 2)
        self.assertFalse(any(name == "get_service_price" for name, _args in domain.calls))


if __name__ == "__main__":
    unittest.main()
