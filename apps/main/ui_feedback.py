from __future__ import annotations

import ast
import re
from collections.abc import Iterable

from django.core.exceptions import ValidationError

DEFAULT_ERROR_MESSAGE = "انجام این عملیات با مشکل روبه‌رو شد. لطفاً دوباره تلاش کنید."
DEFAULT_FORM_ERROR_MESSAGE = "اطلاعات واردشده معتبر نیست. لطفاً موارد مشخص‌شده را اصلاح کنید."

_PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WHITESPACE_RE = re.compile(r"\s+")
_TECHNICAL_RE = re.compile(
    r"(?:traceback|exception|error\s*[:=]|sql|select\s+|insert\s+|update\s+|delete\s+|"
    r"django\.|python|keyerror|typeerror|valueerror|integrityerror|operationalerror|"
    r"object\s+at\s+0x|<[^>]+>|https?://)",
    re.IGNORECASE,
)

# Common technical acronyms that occasionally appear inside otherwise useful Persian
# validation messages. Replacing them keeps the visible sentence fully Persian.
_TERM_REPLACEMENTS = {
    "LOOMERA": "لومرا",
    "JPEG": "جی‌پی‌اِگ",
    "JPG": "جی‌پی‌جی",
    "PNG": "پی‌اِن‌جی",
    "WEBP": "وِب‌پی",
    "PDF": "پی‌دی‌اِف",
    "MP4": "اِم‌پی۴",
    "OTP": "کد تأیید",
    "SMS": "پیامک",
    "IR": "آی‌آر",
    "LIVE": "عملیاتی",
    "WORKFLOW": "فرایند",
    "SCOPE": "محدوده",
    "CHECKOUT": "تسویه",
    "COMMAND": "فرمان پردازش",
    "LEDGER": "دفتر مالی",
}


def _replace_known_terms(text: str) -> str:
    result = text
    for latin, persian in _TERM_REPLACEMENTS.items():
        result = re.sub(rf"\b{re.escape(latin)}\b", persian, result, flags=re.IGNORECASE)
    return result




def _join_ui_messages(messages: Iterable[str]) -> str:
    cleaned = [str(message or "").strip() for message in messages if str(message or "").strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    normalized = [message.rstrip(" .،؛") for message in cleaned]
    return "، ".join(normalized) + "."


def _unwrap_literal_collection(text: str) -> str:
    if not text:
        return ""
    if not (
        (text.startswith("[") and text.endswith("]"))
        or (text.startswith("(") and text.endswith(")"))
    ):
        return text
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text
    if isinstance(parsed, (list, tuple)) and parsed and all(isinstance(item, str) for item in parsed):
        items = [item.strip() for item in parsed if item.strip()]
        return _join_ui_messages(items)
    return text


def normalize_ui_text(value: object) -> str:
    text = _unwrap_literal_collection(str(value or "").strip())
    text = _replace_known_terms(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _validation_candidates(error: object) -> list[str]:
    if isinstance(error, ValidationError):
        message_dict = getattr(error, "message_dict", None)
        if isinstance(message_dict, dict):
            values: list[str] = []
            for messages in message_dict.values():
                if isinstance(messages, Iterable) and not isinstance(messages, (str, bytes)):
                    values.extend(str(item) for item in messages)
                elif messages:
                    values.append(str(messages))
            if values:
                return values
        messages = getattr(error, "messages", None)
        if messages:
            return [str(item) for item in messages]
    return [str(error or "")]


def is_safe_ui_text(value: object, *, allow_latin_data: bool = False) -> bool:
    text = normalize_ui_text(value)
    if not text or not _PERSIAN_RE.search(text):
        return False
    if _TECHNICAL_RE.search(text):
        return False
    # After replacing approved acronyms, remaining Latin characters indicate a raw
    # provider/framework/programming message and must not reach the user.
    if not allow_latin_data and _LATIN_RE.search(text):
        return False
    return True


def user_error_message(error: object, fallback: str = DEFAULT_ERROR_MESSAGE) -> str:
    """Return a Persian, non-technical message safe to expose to end users.

    Domain ``ValidationError`` messages are preserved when they are already suitable.
    Unexpected framework/provider exceptions are intentionally collapsed to a stable
    Persian fallback so class names, SQL, provider payloads and English internals are
    never leaked through flash messages or inline form errors.
    """

    safe_messages: list[str] = []
    for candidate in _validation_candidates(error):
        text = normalize_ui_text(candidate)
        if is_safe_ui_text(text) and text not in safe_messages:
            safe_messages.append(text)
    if safe_messages:
        return _join_ui_messages(safe_messages)

    normalized_fallback = normalize_ui_text(fallback)
    if is_safe_ui_text(normalized_fallback):
        return normalized_fallback
    return DEFAULT_ERROR_MESSAGE


def user_ui_message(
    value: object,
    fallback: str = "پیام قابل نمایش در دسترس نیست.",
    *,
    allow_latin_data: bool = False,
) -> str:
    """Normalize already-user-facing copy and suppress technical provider text.

    ``allow_latin_data`` is reserved for positive/informational copy where a user-
    supplied entity name (for example a salon name) can legitimately be Latin. The
    surrounding sentence must still contain Persian text and technical signatures
    are always rejected. Error paths keep this disabled.
    """

    text = normalize_ui_text(value)
    if is_safe_ui_text(text, allow_latin_data=allow_latin_data):
        return text
    normalized_fallback = normalize_ui_text(fallback)
    return (
        normalized_fallback
        if is_safe_ui_text(normalized_fallback, allow_latin_data=allow_latin_data)
        else DEFAULT_ERROR_MESSAGE
    )


def safe_form_errors(form) -> dict[str, list[str]]:
    """Serialize Django form errors without leaking raw/English validation copy."""

    payload: dict[str, list[str]] = {}
    for field_name, field_errors in form.errors.items():
        payload[str(field_name)] = [
            user_error_message(error, fallback=DEFAULT_FORM_ERROR_MESSAGE)
            for error in field_errors
        ]
    return payload


_REDIRECT_FORM_ERRORS_SESSION_KEY = "_lm_redirect_form_errors"


def stash_form_errors(request, form) -> None:
    """Persist bound form errors for the next redirected page render.

    Some POST endpoints intentionally redirect back to detail pages on invalid input.
    Keeping only the normalized, user-safe error contract lets the next page attach
    each error to the matching field without storing submitted values or raw
    exceptions in the session.
    """

    errors: list[dict[str, str]] = []
    for field_name, field_errors in form.errors.items():
        html_name = "" if field_name == "__all__" else form.add_prefix(field_name)
        for error in field_errors:
            errors.append(
                {
                    "field": html_name,
                    "message": user_error_message(
                        error, fallback=DEFAULT_FORM_ERROR_MESSAGE
                    ),
                }
            )

    if not errors:
        return

    request.session[_REDIRECT_FORM_ERRORS_SESSION_KEY] = {
        "action_path": request.path,
        "errors": errors,
    }


def pop_redirect_form_errors(request):
    """Return and consume the one-shot redirected-form error contract."""

    payload = request.session.pop(_REDIRECT_FORM_ERRORS_SESSION_KEY, None)
    if not isinstance(payload, dict):
        return None
    action_path = payload.get("action_path")
    errors = payload.get("errors")
    if not isinstance(action_path, str) or not isinstance(errors, list):
        return None
    return {"action_path": action_path, "errors": errors}
