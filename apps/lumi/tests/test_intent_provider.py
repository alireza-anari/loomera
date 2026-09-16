from __future__ import annotations

import unittest

from apps.lumi.providers.base import ModelProviderError
from apps.lumi.providers.staging import HelpCenterIntentProvider


class FakeCompletionProvider:
    enabled = True
    model = "free-model"

    def __init__(self, response):
        self.response = response
        self.messages = None

    def complete(self, messages):
        self.messages = messages
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ProviderHTTPFailure(RuntimeError):
    def __init__(self, status):
        super().__init__("provider failed")
        self.status = status


class ProviderNetworkFailure(RuntimeError):
    pass


TOOLS = [
    {
        "name": "get_availability",
        "description": "read slots",
        "input_schema": {"type": "object"},
        "policy": {"allowed_roles": ["guest"]},
    }
]


class IntentProviderTests(unittest.TestCase):
    def test_extracts_json_from_code_fence(self):
        backend = FakeCompletionProvider(
            '```json\n{"intent":"get_availability","arguments":{"service_query":"رنگ مو","date":"فردا"},"confidence":0.91}\n```'
        )
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        intent = provider.extract_intent(
            message="رنگ مو فردا",
            context={"scope_type": "salon"},
            tools=TOOLS,
        )
        self.assertEqual(intent.intent, "get_availability")
        self.assertEqual(intent.arguments["service_query"], "رنگ مو")
        self.assertEqual(intent.confidence, 0.91)
        # Only safe tool metadata is serialized to the model payload.
        user_payload = backend.messages[-1]["content"]
        self.assertNotIn("allowed_roles", user_payload)

    def test_malformed_json_raises_provider_error(self):
        backend = FakeCompletionProvider("intent=get_availability")
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        with self.assertRaises(ModelProviderError):
            provider.extract_intent(message="x", context={}, tools=TOOLS)

    def test_hallucinated_tool_becomes_fallback(self):
        backend = FakeCompletionProvider(
            '{"intent":"confirm_booking","arguments":{"booking_id":1},"confidence":1}'
        )
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        intent = provider.extract_intent(message="رزرو کن", context={}, tools=TOOLS)
        self.assertEqual(intent.intent, "fallback")
        self.assertEqual(intent.arguments, {})
        self.assertEqual(intent.confidence, 0.0)

    def test_backend_exception_is_wrapped(self):
        backend = FakeCompletionProvider(RuntimeError("secret provider detail"))
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        with self.assertRaises(ModelProviderError) as caught:
            provider.extract_intent(message="x", context={}, tools=TOOLS)
        self.assertNotIn("secret provider detail", str(caught.exception))
        self.assertEqual(provider.last_error_kind, "provider_unavailable")

    def test_timeout_cause_is_classified_as_network_without_leaking_detail(self):
        outer = ProviderNetworkFailure("outer")
        outer.__cause__ = TimeoutError("tls handshake secret detail")
        backend = FakeCompletionProvider(outer)
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        with self.assertRaises(ModelProviderError) as caught:
            provider.extract_intent(message="x", context={}, tools=TOOLS)
        self.assertEqual(provider.last_error_kind, "provider_network")
        self.assertNotIn("tls handshake", str(caught.exception))

    def test_rate_limit_is_classified_for_cooldown(self):
        backend = FakeCompletionProvider(ProviderHTTPFailure(429))
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        with self.assertRaises(ModelProviderError):
            provider.extract_intent(message="x", context={}, tools=TOOLS)
        self.assertEqual(provider.last_error_kind, "provider_rate_limited")

    def test_malformed_response_sets_invalid_response_kind(self):
        backend = FakeCompletionProvider("not json")
        provider = HelpCenterIntentProvider(provider_factory=lambda: backend)
        with self.assertRaises(ModelProviderError):
            provider.extract_intent(message="x", context={}, tools=TOOLS)
        self.assertEqual(provider.last_error_kind, "provider_invalid_response")


if __name__ == "__main__":
    unittest.main()
