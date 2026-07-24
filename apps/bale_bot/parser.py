from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import BaleUpdateType


@dataclass(frozen=True)
class ParsedBaleUpdate:
    update_id: str
    event_id: str
    event_type: str
    user_id: str
    chat_id: str
    username: str = ""
    display_name: str = ""
    language_code: str = ""
    text: str = ""
    callback_data: str = ""
    callback_query_id: str = ""
    raw_user: dict[str, Any] = field(default_factory=dict)
    raw_chat: dict[str, Any] = field(default_factory=dict)

    @property
    def inbound_text(self) -> str:
        if self.event_type == BaleUpdateType.CALLBACK_QUERY:
            return self.callback_data or ""
        return self.text or ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _display_name(user: dict[str, Any]) -> str:
    first_name = str(user.get("first_name") or "").strip()
    last_name = str(user.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or str(user.get("username") or "").strip()


def detect_update_type(payload: dict[str, Any]) -> str:
    for key in [
        BaleUpdateType.MESSAGE,
        BaleUpdateType.EDITED_MESSAGE,
        BaleUpdateType.CALLBACK_QUERY,
        BaleUpdateType.PRE_CHECKOUT_QUERY,
    ]:
        if isinstance(payload.get(key), dict):
            return key
    return BaleUpdateType.UNKNOWN


def parse_bale_update(payload: dict[str, Any]) -> ParsedBaleUpdate:
    payload = _as_dict(payload)
    event_type = detect_update_type(payload)
    update_id = _as_str(payload.get("update_id"))

    message = _as_dict(payload.get("message"))
    edited_message = _as_dict(payload.get("edited_message"))
    callback_query = _as_dict(payload.get("callback_query"))
    pre_checkout_query = _as_dict(payload.get("pre_checkout_query"))

    raw_user: dict[str, Any] = {}
    raw_chat: dict[str, Any] = {}
    text = ""
    callback_data = ""
    event_id = ""

    if event_type == BaleUpdateType.MESSAGE:
        raw_user = _as_dict(message.get("from"))
        raw_chat = _as_dict(message.get("chat"))
        text = _as_str(message.get("text"))
        message_id = _as_str(message.get("message_id"))
        if message_id and raw_chat.get("id") is not None:
            event_id = f"message:{raw_chat.get('id')}:{message_id}"
    elif event_type == BaleUpdateType.EDITED_MESSAGE:
        raw_user = _as_dict(edited_message.get("from"))
        raw_chat = _as_dict(edited_message.get("chat"))
        text = _as_str(edited_message.get("text"))
        message_id = _as_str(edited_message.get("message_id"))
        if message_id and raw_chat.get("id") is not None:
            event_id = f"edited_message:{raw_chat.get('id')}:{message_id}"
    elif event_type == BaleUpdateType.CALLBACK_QUERY:
        raw_user = _as_dict(callback_query.get("from"))
        callback_message = _as_dict(callback_query.get("message"))
        raw_chat = _as_dict(callback_message.get("chat"))
        callback_data = _as_str(callback_query.get("data"))
        callback_id = _as_str(callback_query.get("id"))
        if callback_id:
            event_id = f"callback:{callback_id}"
    elif event_type == BaleUpdateType.PRE_CHECKOUT_QUERY:
        raw_user = _as_dict(pre_checkout_query.get("from"))
        event_id = f"pre_checkout:{_as_str(pre_checkout_query.get('id'))}"

    provider_user_id = _as_str(raw_user.get("id"))
    chat_id = _as_str(raw_chat.get("id"))
    if not chat_id and provider_user_id:
        # Private-message callback payloads may omit message.chat in some edge cases.
        chat_id = provider_user_id

    return ParsedBaleUpdate(
        update_id=update_id,
        event_id=event_id,
        event_type=event_type,
        user_id=provider_user_id,
        chat_id=chat_id,
        username=_as_str(raw_user.get("username")),
        display_name=_display_name(raw_user),
        language_code=_as_str(raw_user.get("language_code")),
        text=text,
        callback_data=callback_data,
        callback_query_id=_as_str(callback_query.get("id")) if event_type == BaleUpdateType.CALLBACK_QUERY else "",
        raw_user=raw_user,
        raw_chat=raw_chat,
    )
