from __future__ import annotations

import http.client
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    def __init__(self, message: str, *, provider: str = "", status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.detail = detail


@dataclass
class OpenAICompatibleProvider:
    provider_name: str
    endpoint: str
    api_key: str
    model: str
    timeout: int = 15
    extra_headers: dict | None = None
    extra_payload: dict | None = None

    @property
    def enabled(self) -> bool:
        return bool(
            getattr(settings, "HELP_AI_ENABLED", True)
            and self.api_key
            and self.model
            and self.endpoint
        )

    def complete(self, messages: list[dict]) -> str:
        if not self.enabled:
            raise AIProviderError(
                "AI provider is disabled or incomplete.",
                provider=self.provider_name,
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.15,
            "max_completion_tokens": int(
                getattr(settings, "HELP_AI_MAX_COMPLETION_TOKENS", 750) or 750
            ),
            **(self.extra_payload or {}),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(self.extra_headers or {}),
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            status = getattr(exc, "code", None)
            try:
                raw_detail = exc.read().decode("utf-8", errors="replace")[:1200]
            except Exception:
                raw_detail = ""
            logger.warning(
                "Help AI provider HTTP error | provider=%s status=%s detail=%s",
                self.provider_name,
                status,
                raw_detail[:500],
            )
            raise AIProviderError(
                f"{self.provider_name} request failed with HTTP {status}.",
                provider=self.provider_name,
                status=status,
                detail=raw_detail,
            ) from exc
        except (
            http.client.RemoteDisconnected,
            urllib.error.URLError,
            TimeoutError,
            ValueError,
        ) as exc:
            logger.warning(
                "Help AI provider request failed | provider=%s error=%s",
                self.provider_name,
                type(exc).__name__,
            )
            raise AIProviderError(
                f"{self.provider_name} request failed.",
                provider=self.provider_name,
            ) from exc

        try:
            answer = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "Unexpected AI provider response.",
                provider=self.provider_name,
            ) from exc

        answer = str(answer or "").strip()
        if not answer:
            raise AIProviderError(
                "Empty AI provider response.",
                provider=self.provider_name,
            )
        return answer


class GroqProvider(OpenAICompatibleProvider):
    """Compatibility wrapper; new code should use get_ai_provider()."""

    def __init__(self):
        super().__init__(
            provider_name="groq",
            endpoint="https://api.groq.com/openai/v1/chat/completions",
            api_key=str(getattr(settings, "GROQ_API_KEY", "") or "").strip(),
            model=str(getattr(settings, "HELP_AI_MODEL", "") or "").strip(),
            timeout=max(3, int(getattr(settings, "HELP_AI_TIMEOUT_SECONDS", 15) or 15)),
        )


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self):
        extra_headers = {}
        site_url = str(
            getattr(settings, "HELP_AI_SITE_URL", "")
            or getattr(settings, "PUBLIC_BASE_URL", "")
            or ""
        ).strip()
        app_name = str(getattr(settings, "BRAND_DISPLAY_NAME", "Loomera") or "Loomera").strip()
        if site_url:
            extra_headers["HTTP-Referer"] = site_url
        if app_name:
            extra_headers["X-Title"] = f"{app_name} Help Assistant"
        super().__init__(
            provider_name="openrouter",
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            api_key=str(getattr(settings, "OPENROUTER_API_KEY", "") or "").strip(),
            model=str(getattr(settings, "HELP_AI_MODEL", "") or "").strip(),
            timeout=max(3, int(getattr(settings, "HELP_AI_TIMEOUT_SECONDS", 15) or 15)),
            extra_headers=extra_headers,
            extra_payload={
                "provider": {
                    "zdr": True,
                    "data_collection": "deny",
                    "allow_fallbacks": True,
                }
            },
        )


class CustomProvider(OpenAICompatibleProvider):
    def __init__(self):
        base = str(getattr(settings, "HELP_AI_BASE_URL", "") or "").strip().rstrip("/")
        endpoint = base
        if endpoint and not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        super().__init__(
            provider_name="custom",
            endpoint=endpoint,
            api_key=str(getattr(settings, "HELP_AI_API_KEY", "") or "").strip(),
            model=str(getattr(settings, "HELP_AI_MODEL", "") or "").strip(),
            timeout=max(3, int(getattr(settings, "HELP_AI_TIMEOUT_SECONDS", 15) or 15)),
        )


class DisabledProvider:
    provider_name = "disabled"
    model = ""
    enabled = False

    def complete(self, messages: list[dict]) -> str:
        raise AIProviderError("AI provider is disabled.", provider=self.provider_name)


def get_ai_provider():
    provider = str(getattr(settings, "HELP_AI_PROVIDER", "groq") or "groq").strip().lower()
    if provider == "groq":
        return GroqProvider()
    if provider == "openrouter":
        return OpenRouterProvider()
    if provider in {"custom", "openai-compatible", "openai_compatible"}:
        return CustomProvider()
    return DisabledProvider()
