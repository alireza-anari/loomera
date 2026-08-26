from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .constants import (
    MessagingActionStatus,
    MessagingIdentityStatus,
    MessagingTokenPurpose,
)
from .models import (
    MessagingActionExecution,
    MessagingIdentity,
    MessagingProvider,
    MessagingToken,
)
from .services import hash_token, identity_has_active_connection, issue_messaging_token

ACTION_CALLBACK_PREFIX = "action:"


@dataclass(frozen=True)
class MessagingActionContext:
    provider: MessagingProvider
    identity: MessagingIdentity
    user: Any
    token: MessagingToken
    action_key: str
    related_object: Any = None
    salon_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    base_url: str = ""


@dataclass(frozen=True)
class MessagingActionResult:
    status: str = MessagingActionStatus.SUCCEEDED
    user_message: str = "عملیات با موفقیت انجام شد. ✅"
    result: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    reply_markup: dict[str, Any] | None = None


MessagingActionHandler = Callable[[MessagingActionContext], MessagingActionResult]
_ACTION_HANDLERS: dict[str, MessagingActionHandler] = {}


def action_token_ttl() -> timedelta:
    minutes = int(getattr(settings, "MESSAGING_ACTION_TOKEN_TTL_MINUTES", 60) or 60)
    return timedelta(minutes=max(minutes, 1))


def register_messaging_action(
    action_key: str, handler: MessagingActionHandler, *, replace: bool = False
) -> None:
    key = str(action_key or "").strip()
    if not key:
        raise ValueError("action_key_required")
    if key in _ACTION_HANDLERS and not replace:
        raise ValueError("action_handler_already_registered")
    _ACTION_HANDLERS[key] = handler


def get_messaging_action_handler(action_key: str) -> MessagingActionHandler | None:
    return _ACTION_HANDLERS.get(str(action_key or "").strip())


def clear_messaging_action_handlers_for_tests() -> None:
    _ACTION_HANDLERS.clear()
    register_default_messaging_actions()


def build_action_callback_data(raw_token: str) -> str:
    return f"{ACTION_CALLBACK_PREFIX}{str(raw_token or '').strip()}"


def extract_action_token(callback_data: str) -> str:
    value = str(callback_data or "").strip()
    if not value.startswith(ACTION_CALLBACK_PREFIX):
        return ""
    return value[len(ACTION_CALLBACK_PREFIX) :].strip()


def is_action_callback(callback_data: str) -> bool:
    return bool(extract_action_token(callback_data))


def mask_action_callback_data(callback_data: str) -> str:
    value = str(callback_data or "")
    raw = extract_action_token(value)
    if not raw:
        return value
    return f"{ACTION_CALLBACK_PREFIX}{raw[:6]}…"


def sanitize_reply_markup_for_log(
    reply_markup: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not reply_markup:
        return reply_markup

    def sanitize(value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                if key == "callback_data":
                    cleaned[key] = mask_action_callback_data(str(item or ""))
                else:
                    cleaned[key] = sanitize(item)
            return cleaned
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return sanitize(reply_markup)


def issue_action_token(
    *,
    provider: MessagingProvider,
    identity: MessagingIdentity,
    user,
    action_key: str,
    notification_delivery=None,
    related_object=None,
    audience_role: str = "",
    salon_id: int | None = None,
    expires_in: timedelta | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, MessagingToken]:
    """
    Issue a short-lived one-time token for a messaging callback action.

    Provider, identity, and action key are mandatory. The raw token is returned
    only so it can be embedded in callback data; storage uses its hash together
    with user, related object, audience role, salon scope, and metadata. Issuing a
    token is not authorization to mutate product state. The eventual handler must
    re-check user permissions, object state, ownership, and salon scope.
    """
    if provider is None:
        raise ValueError("provider_required")
    if identity is None:
        raise ValueError("identity_required")
    if not action_key:
        raise ValueError("action_key_required")
    return issue_messaging_token(
        purpose=MessagingTokenPurpose.ACTION,
        provider=provider,
        identity=identity,
        user=user,
        notification_delivery=notification_delivery,
        related_object=related_object,
        action_key=action_key,
        audience_role=audience_role,
        salon_id=salon_id,
        expires_in=expires_in or action_token_ttl(),
        metadata=metadata or {},
    )


def _execution_from_token(
    token: MessagingToken,
    *,
    identity: MessagingIdentity | None,
    provider: MessagingProvider | None,
) -> MessagingActionExecution:
    execution, _ = MessagingActionExecution.objects.get_or_create(
        token=token,
        defaults={
            "provider": provider or token.provider,
            "identity": identity or token.identity,
            "user": getattr(identity, "user", None) or token.user,
            "action_key": token.action_key or "unknown",
            "related_content_type": token.related_content_type,
            "related_object_id": token.related_object_id,
            "status": MessagingActionStatus.STARTED,
        },
    )
    return execution


def _audit_without_token(
    *,
    provider: MessagingProvider | None,
    identity: MessagingIdentity | None,
    user=None,
    action_key: str = "unknown",
    status: str,
    result: dict[str, Any] | None = None,
    error_message: str = "",
) -> None:
    execution = MessagingActionExecution.objects.create(
        provider=provider,
        identity=identity,
        user=user or getattr(identity, "user", None),
        token=None,
        action_key=action_key or "unknown",
        status=MessagingActionStatus.STARTED,
    )
    execution.mark_finished(
        status=status, result=result or {}, error_message=error_message
    )


def _message_for_error(error_code: str) -> str:
    messages = {
        "missing_identity_user": "برای استفاده از این دکمه، اول حساب Loomera را به ربات وصل کن.",
        "invalid_action_token": "این دکمه دیگر قابل استفاده نیست. منوی تازه را باز کن.",
        "token_revoked": "این دکمه دیگر فعال نیست. منوی تازه را باز کن.",
        "token_expired": "مهلت این دکمه تمام شده. منوی تازه را باز کن.",
        "token_already_used": "این کار قبلاً انجام شده است.",
        "token_provider_mismatch": "این دکمه برای پیام‌رسان دیگری ساخته شده است.",
        "token_identity_mismatch": "این دکمه برای حساب بله دیگری ساخته شده است.",
        "token_user_mismatch": "این دکمه برای کاربر دیگری ساخته شده است.",
        "related_object_missing": "مورد مرتبط با این دکمه دیگر در دسترس نیست.",
        "messaging_actions_disabled": "انجام این کار از داخل ربات موقتاً در دسترس نیست. از سایت اقدام کن.",
        "action_not_registered": "این کار از داخل ربات در دسترس نیست.",
        "action_handler_failed": "این کار انجام نشد. دوباره تلاش کن یا جزئیات را در سایت ببین.",
        "identity_not_linked": "برای استفاده از این دکمه، حساب بله را به Loomera وصل کن.",
        "identity_connection_inactive": "اتصال این حساب قطع شده. دوباره آن را از Loomera وصل کن.",
    }
    return messages.get(error_code, "اجرای اکشن ممکن نیست.")


def _blocked_result(
    status: str, error_code: str, *, result: dict[str, Any] | None = None
) -> MessagingActionResult:
    return MessagingActionResult(
        status=status,
        user_message=_message_for_error(error_code),
        result={"error_code": error_code, **(result or {})},
        error_message=error_code,
    )


@transaction.atomic
def dispatch_messaging_action_callback(
    *,
    provider: MessagingProvider,
    identity: MessagingIdentity,
    callback_data: str,
    base_url: str = "",
) -> MessagingActionResult:
    """
    Validate and execute one messaging action callback at most once.

    The transaction requires actions to be enabled, a linked identity with an
    active account connection, and an unused, unrevoked, unexpired action token
    bound to the current provider, identity, and user. The token row is locked and
    marked used before the registered handler runs, so callbacks are not retried
    automatically after a handler failure. Missing or denied tokens are audited,
    related objects and handlers are validated, and product handlers remain
    responsible for permission, lifecycle, ownership, and salon-scope checks.
    Unexpected handler errors are converted to a failed action result so one
    callback cannot crash the surrounding webhook workflow.
    """

    raw_token = extract_action_token(callback_data)
    user = getattr(identity, "user", None)
    if not raw_token:
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "invalid_action_token"},
            error_message="invalid_action_token",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "invalid_action_token")

    if not bool(getattr(settings, "MESSAGING_ACTIONS_ENABLED", False)):
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "messaging_actions_disabled"},
            error_message="messaging_actions_disabled",
        )
        return _blocked_result(
            MessagingActionStatus.DENIED,
            "messaging_actions_disabled",
        )

    if not getattr(identity, "user_id", None):
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=None,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "missing_identity_user"},
            error_message="missing_identity_user",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "missing_identity_user")

    if identity.status != MessagingIdentityStatus.LINKED:
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "identity_not_linked"},
            error_message="identity_not_linked",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "identity_not_linked")

    if not identity_has_active_connection(identity, user=identity.user):
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "identity_connection_inactive"},
            error_message="identity_connection_inactive",
        )
        return _blocked_result(
            MessagingActionStatus.DENIED, "identity_connection_inactive"
        )

    token = (
        MessagingToken.objects.filter(
            token_hash=hash_token(raw_token),
            purpose=MessagingTokenPurpose.ACTION,
        )
        .select_for_update(of=("self",))
        .select_related("provider", "identity", "user")
        .first()
    )
    if token is None:
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "invalid_action_token"},
            error_message="invalid_action_token",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "invalid_action_token")

    action_key = token.action_key or "unknown"

    if token.is_revoked:
        execution = _execution_from_token(token, identity=identity, provider=provider)
        execution.mark_finished(
            status=MessagingActionStatus.DENIED,
            result={"error_code": "token_revoked"},
            error_message="token_revoked",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "token_revoked")

    if token.is_expired:
        execution = _execution_from_token(token, identity=identity, provider=provider)
        execution.mark_finished(
            status=MessagingActionStatus.EXPIRED,
            result={"error_code": "token_expired"},
            error_message="token_expired",
        )
        return _blocked_result(MessagingActionStatus.EXPIRED, "token_expired")

    if token.is_used:
        return _blocked_result(MessagingActionStatus.ALREADY_USED, "token_already_used")

    if token.provider_id and token.provider_id != provider.pk:
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            action_key=action_key,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "token_provider_mismatch", "token_id": token.pk},
            error_message="token_provider_mismatch",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "token_provider_mismatch")

    if token.identity_id and token.identity_id != identity.pk:
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            action_key=action_key,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "token_identity_mismatch", "token_id": token.pk},
            error_message="token_identity_mismatch",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "token_identity_mismatch")

    if token.user_id and token.user_id != identity.user_id:
        _audit_without_token(
            provider=provider,
            identity=identity,
            user=user,
            action_key=action_key,
            status=MessagingActionStatus.DENIED,
            result={"error_code": "token_user_mismatch", "token_id": token.pk},
            error_message="token_user_mismatch",
        )
        return _blocked_result(MessagingActionStatus.DENIED, "token_user_mismatch")

    execution = _execution_from_token(token, identity=identity, provider=provider)
    token.mark_used()

    related_object = token.related_object
    if token.related_content_type_id and related_object is None:
        execution.mark_finished(
            status=MessagingActionStatus.FAILED,
            result={"error_code": "related_object_missing"},
            error_message="related_object_missing",
        )
        return _blocked_result(MessagingActionStatus.FAILED, "related_object_missing")

    handler = get_messaging_action_handler(action_key)
    if handler is None:
        execution.mark_finished(
            status=MessagingActionStatus.DENIED,
            result={"error_code": "action_not_registered", "action_key": action_key},
            error_message="action_not_registered",
        )
        return _blocked_result(
            MessagingActionStatus.DENIED,
            "action_not_registered",
            result={"action_key": action_key},
        )

    context = MessagingActionContext(
        provider=provider,
        identity=identity,
        user=identity.user,
        token=token,
        action_key=action_key,
        related_object=related_object,
        salon_id=token.salon_id,
        metadata=token.metadata or {},
        base_url=base_url,
    )

    try:
        result = handler(context)
    except (
        Exception
    ) as exc:  # product action errors must be logged, not crash webhook processing
        execution.mark_finished(
            status=MessagingActionStatus.FAILED,
            result={"error_code": "action_handler_failed", "action_key": action_key},
            error_message=str(exc) or "action_handler_failed",
        )
        return _blocked_result(
            MessagingActionStatus.FAILED,
            "action_handler_failed",
            result={"action_key": action_key},
        )

    status = result.status or MessagingActionStatus.SUCCEEDED
    execution.mark_finished(
        status=status,
        result=result.result or {},
        error_message=result.error_message or "",
    )
    return result


def acknowledge_action(context: MessagingActionContext) -> MessagingActionResult:
    """Safe built-in action for testing the secure callback rail.

    It does not modify any product object. Product actions are registered in
    later stages.
    """

    return MessagingActionResult(
        status=MessagingActionStatus.SUCCEEDED,
        user_message="انجام شد.",
        result={"action_key": context.action_key, "token_id": context.token.pk},
    )


def register_default_messaging_actions() -> None:
    _ACTION_HANDLERS.setdefault("messaging.acknowledge", acknowledge_action)

    # Product action handlers live in dedicated modules so provider adapters do
    # not know about appointment internals. Importing here keeps the registry
    # populated for webhook callbacks, tests and management commands.
    from .stylist_actions import register_stylist_messaging_actions
    from .manager_actions import register_manager_messaging_actions

    register_stylist_messaging_actions()
    register_manager_messaging_actions()


register_default_messaging_actions()
