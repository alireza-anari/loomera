from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.messaging.constants import (
    MessagingMessageDirection,
    MessagingMessageStatus,
    MessagingProviderKey,
)
from apps.messaging.models import MessagingIdentity, MessagingProvider
from apps.messaging.services import (
    log_message,
    messaging_outbound_enabled,
    provider_allowed,
)
from apps.messaging.actions import sanitize_reply_markup_for_log


class BaleBotApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class BaleBotClient:
    """
    Thin HTTP client for Bale Bot API.

    This client is intentionally not wired into notifications yet. It is safe for
    stage 2 because every outbound call is blocked unless both messaging and Bale
    outbound flags are enabled and the Bale provider is explicitly active/allowed.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        api_base_url: str | None = None,
        timeout: int | None = None,
    ):
        self.token = (
            token if token is not None else getattr(settings, "BALE_BOT_TOKEN", "")
        ).strip()
        self.api_base_url = (
            api_base_url
            or getattr(settings, "BALE_BOT_API_BASE_URL", "https://tapi.bale.ai/bot")
        ).rstrip("/")
        self.timeout = timeout or int(getattr(settings, "BALE_BOT_REQUEST_TIMEOUT", 10))

    def _method_url(self, method_name: str) -> str:
        if not self.token:
            raise ImproperlyConfigured("BALE_BOT_TOKEN is not configured.")
        return f"{self.api_base_url}{self.token}/{method_name}"

    def request(
        self, method_name: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Call one Bale Bot API method through the configured HTTP boundary.
        
        The bot token is required to construct the first-party provider URL. HTTP,
        transport, malformed response, and provider-level ``ok=false`` outcomes are
        translated to ``BaleBotApiError`` with bounded response context. A successful
        call returns the decoded provider dictionary. This low-level method does not
        create message logs, alter notification delivery state, or decide whether
        outbound messaging is enabled.
        """
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self._method_url(method_name),
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(
                req, timeout=self.timeout
            ) as response:  # nosec B310 - configured first-party API endpoint
                response_body = response.read().decode("utf-8")
                data = json.loads(response_body or "{}")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(response_body or "{}")
            except json.JSONDecodeError:
                data = {"raw": response_body}
            raise BaleBotApiError(
                "bale_api_http_error", status_code=exc.code, response=data
            ) from exc
        except (
            Exception
        ) as exc:  # network/provider errors must not crash caller workflows
            raise BaleBotApiError(
                "bale_api_request_failed", response={"error": str(exc)}
            ) from exc

        if not data.get("ok", False):
            raise BaleBotApiError("bale_api_not_ok", response=data)
        return data

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        provider: MessagingProvider | None = None,
        identity: MessagingIdentity | None = None,
        notification_delivery=None,
        reply_markup: dict[str, Any] | None = None,
    ):
        """
        Attempt one Bale outbound message and always express the result as an audit log.
        
        Outbound sending requires all messaging and Bale feature flags, an active and
        allowed provider, outbound enablement, and a configured bot token. Disabled
        sending is logged as skipped; a missing token after all other gates pass is
        logged as failed. Callback tokens in reply markup are masked in the logged
        payload. Provider success and ``BaleBotApiError`` outcomes become sent or
        failed message logs. The method returns the log, or None when no provider exists,
        and does not directly update NotificationDelivery status.
        """
        provider = (
            provider
            or MessagingProvider.objects.filter(key=MessagingProviderKey.BALE).first()
        )
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        log_payload = {**payload}
        if reply_markup:
            log_payload["reply_markup"] = sanitize_reply_markup_for_log(reply_markup)

        outbound_allowed = (
            bool(getattr(settings, "MESSAGING_ENABLED", False))
            and bool(getattr(settings, "BALE_BOT_ENABLED", False))
            and messaging_outbound_enabled()
            and provider is not None
            and provider.is_active
            and provider_allowed(MessagingProviderKey.BALE)
        )

        if not outbound_allowed or not self.token:
            token_missing = bool(outbound_allowed and not self.token)
            return (
                log_message(
                    provider=provider,
                    identity=identity,
                    notification_delivery=notification_delivery,
                    direction=MessagingMessageDirection.OUTBOUND,
                    status=(
                        MessagingMessageStatus.FAILED
                        if token_missing
                        else MessagingMessageStatus.SKIPPED
                    ),
                    text=text,
                    payload=log_payload,
                    error_message=(
                        "bale_bot_token_missing"
                        if token_missing
                        else "bale_outbound_disabled"
                    ),
                )
                if provider
                else None
            )

        try:
            response = self.request("sendMessage", payload)
            result = response.get("result") or {}
            return log_message(
                provider=provider,
                identity=identity,
                notification_delivery=notification_delivery,
                direction=MessagingMessageDirection.OUTBOUND,
                status=MessagingMessageStatus.SENT,
                text=text,
                payload=log_payload,
                provider_response=response,
                external_message_id=str(result.get("message_id") or ""),
            )
        except BaleBotApiError as exc:
            return log_message(
                provider=provider,
                identity=identity,
                notification_delivery=notification_delivery,
                direction=MessagingMessageDirection.OUTBOUND,
                status=MessagingMessageStatus.FAILED,
                text=text,
                payload=log_payload,
                provider_response=exc.response,
                error_message=str(exc),
            )

    def answer_callback_query(
        self, *, callback_query_id: str, text: str = "", show_alert: bool = False
    ) -> dict[str, Any]:
        if not callback_query_id:
            return {"ok": False, "skipped": True, "reason": "missing_callback_query_id"}
        outbound_allowed = (
            bool(getattr(settings, "MESSAGING_ENABLED", False))
            and bool(getattr(settings, "BALE_BOT_ENABLED", False))
            and messaging_outbound_enabled()
            and provider_allowed(MessagingProviderKey.BALE)
        )
        if not outbound_allowed or not self.token:
            return {
                "ok": False,
                "skipped": True,
                "reason": (
                    "bale_bot_token_missing"
                    if outbound_allowed and not self.token
                    else "bale_outbound_disabled"
                ),
            }
        payload = {
            "callback_query_id": callback_query_id,
            "text": str(text or "")[:180],
            "show_alert": bool(show_alert),
        }
        try:
            return self.request("answerCallbackQuery", payload)
        except BaleBotApiError as exc:
            return {"ok": False, "error": str(exc), "response": exc.response}

    def get_me(self) -> dict[str, Any]:
        return self.request("getMe", {})

    def get_webhook_info(self) -> dict[str, Any]:
        return self.request("getWebhookInfo", {})

    def set_webhook(
        self,
        webhook_url: str,
        *,
        secret_token: str = "",
        drop_pending_updates: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        if drop_pending_updates:
            payload["drop_pending_updates"] = True
        return self.request("setWebhook", payload)

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if drop_pending_updates:
            payload["drop_pending_updates"] = True
        return self.request("deleteWebhook", payload)
