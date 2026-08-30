from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.messaging.actions import sanitize_reply_markup_for_log
from apps.messaging.constants import (
    MessagingMessageDirection, MessagingMessageStatus, MessagingProviderKey,
)
from apps.messaging.models import MessagingIdentity, MessagingProvider
from apps.messaging.services import log_message, messaging_outbound_enabled, provider_allowed


class TelegramBotApiError(RuntimeError):
    def __init__(self, message: str, *, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class TelegramBotClient:
    """Thin Telegram Bot API adapter; Loomera domain logic stays in apps.messaging."""

    def __init__(self, *, token=None, api_base_url=None, timeout=None):
        self.token = (
            token if token is not None else getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        ).strip()
        self.api_base_url = (
            api_base_url
            or getattr(settings, "TELEGRAM_BOT_API_BASE_URL", "https://api.telegram.org/bot")
        ).rstrip("/")
        self.timeout = timeout or int(getattr(settings, "TELEGRAM_BOT_REQUEST_TIMEOUT", 10))

    def _method_url(self, method_name: str) -> str:
        if not self.token:
            raise ImproperlyConfigured("TELEGRAM_BOT_TOKEN is not configured.")
        return f"{self.api_base_url}{self.token}/{method_name}"

    def request(self, method_name: str, payload: dict[str, Any] | None = None):
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self._method_url(method_name),
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8") or "{}")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw or "{}")
            except json.JSONDecodeError:
                data = {"raw": raw[:2000]}
            raise TelegramBotApiError(
                "telegram_api_http_error", status_code=exc.code, response=data
            ) from exc
        except Exception as exc:
            # urllib exception strings can contain the tokenized request URL.
            raise TelegramBotApiError(
                "telegram_api_request_failed",
                response={"error_type": type(exc).__name__},
            ) from exc
        if not data.get("ok", False):
            raise TelegramBotApiError("telegram_api_not_ok", response=data)
        return data

    def _outbound_allowed(self, provider=None):
        return bool(
            getattr(settings, "MESSAGING_ENABLED", False)
            and getattr(settings, "TELEGRAM_BOT_ENABLED", False)
            and messaging_outbound_enabled()
            and (provider is None or provider.is_active)
            and provider_allowed(MessagingProviderKey.TELEGRAM)
        )

    def send_message(
        self, *, chat_id, text, provider=None, identity=None,
        notification_delivery=None, reply_markup=None
    ):
        provider = provider or MessagingProvider.objects.filter(
            key=MessagingProviderKey.TELEGRAM
        ).first()
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        log_payload = dict(payload)
        if reply_markup:
            log_payload["reply_markup"] = sanitize_reply_markup_for_log(reply_markup)
        outbound_allowed = self._outbound_allowed(provider)
        if not outbound_allowed or not self.token:
            token_missing = bool(outbound_allowed and not self.token)
            return (
                log_message(
                    provider=provider, identity=identity,
                    notification_delivery=notification_delivery,
                    direction=MessagingMessageDirection.OUTBOUND,
                    status=(MessagingMessageStatus.FAILED if token_missing else MessagingMessageStatus.SKIPPED),
                    text=text, payload=log_payload,
                    error_message=("telegram_bot_token_missing" if token_missing else "telegram_outbound_disabled"),
                ) if provider else None
            )
        try:
            response = self.request("sendMessage", payload)
            result = response.get("result") or {}
            return log_message(
                provider=provider, identity=identity,
                notification_delivery=notification_delivery,
                direction=MessagingMessageDirection.OUTBOUND,
                status=MessagingMessageStatus.SENT, text=text, payload=log_payload,
                provider_response=response,
                external_message_id=str(result.get("message_id") or ""),
            )
        except TelegramBotApiError as exc:
            return log_message(
                provider=provider, identity=identity,
                notification_delivery=notification_delivery,
                direction=MessagingMessageDirection.OUTBOUND,
                status=MessagingMessageStatus.FAILED, text=text, payload=log_payload,
                provider_response=exc.response, error_message=str(exc),
            )

    def answer_callback_query(self, *, callback_query_id, text="", show_alert=False):
        if not callback_query_id:
            return {"ok": False, "skipped": True, "reason": "missing_callback_query_id"}
        allowed = self._outbound_allowed()
        if not allowed or not self.token:
            return {
                "ok": False, "skipped": True,
                "reason": "telegram_bot_token_missing" if allowed and not self.token else "telegram_outbound_disabled",
            }
        try:
            return self.request(
                "answerCallbackQuery",
                {"callback_query_id": callback_query_id, "text": str(text or "")[:180], "show_alert": bool(show_alert)},
            )
        except TelegramBotApiError as exc:
            return {"ok": False, "error": str(exc), "response": exc.response}

    def get_me(self):
        return self.request("getMe", {})

    def get_webhook_info(self):
        return self.request("getWebhookInfo", {})

    def set_webhook(self, webhook_url, *, secret_token="", drop_pending_updates=False):
        payload = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        if drop_pending_updates:
            payload["drop_pending_updates"] = True
        return self.request("setWebhook", payload)

    def delete_webhook(self, *, drop_pending_updates=False):
        payload = {"drop_pending_updates": True} if drop_pending_updates else {}
        return self.request("deleteWebhook", payload)
