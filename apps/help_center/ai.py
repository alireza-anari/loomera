from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings


class AIProviderError(RuntimeError):
    pass


class GroqProvider:
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self.api_key = str(getattr(settings, "GROQ_API_KEY", "") or "").strip()
        self.model = str(
            getattr(settings, "HELP_AI_MODEL", "qwen/qwen3-32b") or "qwen/qwen3-32b"
        ).strip()
        self.timeout = max(3, int(getattr(settings, "HELP_AI_TIMEOUT_SECONDS", 12) or 12))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and bool(getattr(settings, "HELP_AI_ENABLED", True))

    def complete(self, messages: list[dict]) -> str:
        if not self.enabled:
            raise AIProviderError("AI provider is disabled or GROQ_API_KEY is missing.")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_completion_tokens": 650,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            raise AIProviderError("Groq request failed.") from exc

        try:
            answer = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Unexpected Groq response.") from exc

        answer = str(answer or "").strip()
        if not answer:
            raise AIProviderError("Empty Groq response.")
        return answer
