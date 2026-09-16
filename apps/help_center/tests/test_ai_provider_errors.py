import http.client
import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.help_center.ai import (
    AIProviderError,
    OpenAICompatibleProvider,
    OpenRouterProvider,
)


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@override_settings(
    HELP_AI_ENABLED=True,
    HELP_AI_MAX_COMPLETION_TOKENS=100,
)
class HelpAIProviderErrorTests(SimpleTestCase):
    def test_remote_disconnect_is_normalized_to_provider_error(self):
        provider = OpenAICompatibleProvider(
            provider_name="test",
            endpoint="https://example.invalid/chat/completions",
            api_key="test-key",
            model="test-model",
            timeout=3,
        )

        with patch(
            "apps.help_center.ai.urllib.request.urlopen",
            side_effect=http.client.RemoteDisconnected(
                "Remote end closed connection without response"
            ),
        ):
            with self.assertRaises(AIProviderError) as ctx:
                provider.complete(
                    [{"role": "user", "content": "test"}]
                )

        self.assertEqual(ctx.exception.provider, "test")
        self.assertEqual(
            str(ctx.exception),
            "test request failed.",
        )

    @override_settings(
        OPENROUTER_API_KEY="test-openrouter-key",
        HELP_AI_MODEL="openai/gpt-4.1-mini",
        HELP_AI_TIMEOUT_SECONDS=15,
    )
    def test_openrouter_enforces_privacy_routing_in_request_body(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["timeout"] = timeout
            captured["payload"] = json.loads(
                request.data.decode("utf-8")
            )
            return _FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "LUMI_OK"
                            }
                        }
                    ]
                }
            )

        provider = OpenRouterProvider()

        with patch(
            "apps.help_center.ai.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            answer = provider.complete(
                [{"role": "user", "content": "test"}]
            )

        self.assertEqual(answer, "LUMI_OK")
        self.assertEqual(captured["timeout"], 15)
        self.assertEqual(
            captured["payload"]["provider"],
            {
                "zdr": True,
                "data_collection": "deny",
                "allow_fallbacks": True,
            },
        )
