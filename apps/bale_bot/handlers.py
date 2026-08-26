from __future__ import annotations

from dataclasses import dataclass

from apps.messaging.services import (
    connect_identity_with_raw_token,
    disconnect_identity,
    identity_has_active_connection,
)
from apps.messaging.actions import (
    ACTION_CALLBACK_PREFIX,
    dispatch_messaging_action_callback,
)

from .client import BaleBotClient
from .constants import BaleUpdateType
from .menus import (
    MENU_CALLBACK_PREFIX,
    MENU_GUEST,
    MENU_HELP,
    MENU_MAIN,
    MENU_QUICK_LINKS,
    MENU_CUSTOMER_APPOINTMENTS,
    MENU_CUSTOMER_REVIEWS,
    MENU_CUSTOMER_SEARCH,
    MENU_CUSTOMER_SUPPORT,
    MENU_STYLIST_BOOKING_LINK,
    MENU_STYLIST_PROMOTION,
    MENU_STYLIST_SLOTS,
    MENU_STYLIST_TODAY,
    MENU_MANAGER_REQUESTS,
    MENU_MANAGER_PROMOTION,
    MENU_MANAGER_SHIFTS,
    MENU_MANAGER_SLOTS,
    MENU_MANAGER_SUMMARY,
    MENU_MANAGER_TODAY,
    connected_text,
    disconnected_required_text,
    guest_main_menu,
    guest_welcome_text,
    help_menu,
    help_text,
    menu_for_role,
    menu_for_user,
    quick_links_menu,
    quick_links_text,
    role_selector_menu,
    role_summary_text,
    token_error_text,
    unknown_start_payload_text,
    unsupported_action_text,
    already_disconnected_text,
    disconnected_text,
)
from .parser import ParsedBaleUpdate


@dataclass(frozen=True)
class BaleCommand:
    command: str
    payload: str = ""


def parse_command(text: str) -> BaleCommand | None:
    cleaned = (text or "").strip()
    if not cleaned.startswith("/"):
        return None
    first, _, rest = cleaned.partition(" ")
    command = first.split("@", 1)[0].lower()
    return BaleCommand(command=command, payload=rest.strip())


def extract_connect_token(payload: str) -> str:
    payload = (payload or "").strip()
    if payload.startswith("connect_"):
        return payload[len("connect_") :].strip()
    if payload.startswith("connect:"):
        return payload[len("connect:") :].strip()
    return ""


def _send(
    client: BaleBotClient,
    *,
    provider,
    identity,
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
):
    return client.send_message(
        provider=provider,
        identity=identity,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )


def _identity_is_connected(identity) -> bool:
    return identity_has_active_connection(
        identity, user=getattr(identity, "user", None)
    )


def _identity_user(identity):
    if not _identity_is_connected(identity):
        return None
    return getattr(identity, "user", None)


def _show_guest_menu(
    client: BaleBotClient,
    *,
    provider,
    identity,
    chat_id: str,
    base_url: str,
    display_name: str = "",
) -> str:
    _send(
        client,
        provider=provider,
        identity=identity,
        chat_id=chat_id,
        text=guest_welcome_text(display_name),
        reply_markup=guest_main_menu(base_url),
    )
    return "guest_menu"


def _show_connected_menu(
    client: BaleBotClient, *, provider, identity, chat_id: str, base_url: str
) -> str:
    user = _identity_user(identity)
    if not user:
        return _show_guest_menu(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
            display_name=getattr(identity, "display_name", ""),
        )

    text, markup = menu_for_user(base_url, user)
    _send(
        client,
        provider=provider,
        identity=identity,
        chat_id=chat_id,
        text=text,
        reply_markup=markup,
    )
    return "role_menu"


def _handle_menu_callback(
    *,
    client: BaleBotClient,
    parsed: ParsedBaleUpdate,
    identity,
    provider,
    base_url: str,
) -> str:
    chat_id = parsed.chat_id or getattr(identity, "chat_id", "")
    callback_data = parsed.callback_data or ""
    menu_key = callback_data[len(MENU_CALLBACK_PREFIX) :].strip()

    if parsed.callback_query_id:
        client.answer_callback_query(
            callback_query_id=parsed.callback_query_id,
            text="در حال آماده‌سازی…",
            show_alert=False,
        )

    if menu_key == MENU_GUEST:
        return _show_guest_menu(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
            display_name=getattr(identity, "display_name", ""),
        )

    if menu_key == MENU_CUSTOMER_SEARCH:
        from apps.messaging.customer_bot import render_customer_salon_search

        user = _identity_user(identity)
        text, markup = render_customer_salon_search(user, base_url)
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return "customer_search"

    if menu_key == MENU_HELP:
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=help_text(),
            reply_markup=help_menu(base_url),
        )
        return "help_menu"

    user = _identity_user(identity)
    if not user:
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=disconnected_required_text(),
            reply_markup=guest_main_menu(base_url),
        )
        return "menu_requires_connection"

    if menu_key == MENU_CUSTOMER_SUPPORT:
        from apps.messaging.customer_bot import render_customer_support

        user = getattr(identity, "user", None)
        text, markup = render_customer_support(user, base_url)
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return "customer_support"

    if not getattr(identity, "user_id", None):
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=disconnected_required_text(),
            reply_markup=guest_main_menu(base_url),
        )
        return "menu_requires_connection"

    user = identity.user
    if menu_key == MENU_MAIN:
        from apps.messaging.roles import detect_user_bot_roles

        context = detect_user_bot_roles(user)
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=role_summary_text(context),
            reply_markup=role_selector_menu(base_url, context),
        )
        return "role_selector"

    if menu_key == MENU_QUICK_LINKS:
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=quick_links_text(),
            reply_markup=quick_links_menu(base_url),
        )
        return "quick_links_menu"

    if menu_key in {MENU_CUSTOMER_APPOINTMENTS, MENU_CUSTOMER_REVIEWS}:
        from apps.messaging.customer_bot import (
            render_customer_appointments,
            render_customer_review_links,
        )

        if menu_key == MENU_CUSTOMER_APPOINTMENTS:
            text, markup = render_customer_appointments(user, base_url)
            result_key = "customer_appointments"
        else:
            text, markup = render_customer_review_links(user, base_url)
            result_key = "customer_reviews"
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return result_key

    if menu_key in {
        MENU_STYLIST_TODAY,
        MENU_STYLIST_SLOTS,
        MENU_STYLIST_BOOKING_LINK,
        MENU_STYLIST_PROMOTION,
    }:
        from apps.messaging.promotion_bot import render_stylist_promotion_pack
        from apps.messaging.stylist_bot import (
            render_stylist_available_slots,
            render_stylist_booking_link,
            render_stylist_today,
        )

        if menu_key == MENU_STYLIST_TODAY:
            text, markup = render_stylist_today(
                user, base_url, provider=provider, identity=identity
            )
            result_key = "stylist_today"
        elif menu_key == MENU_STYLIST_SLOTS:
            text, markup = render_stylist_available_slots(user, base_url)
            result_key = "stylist_slots"
        elif menu_key == MENU_STYLIST_PROMOTION:
            text, markup = render_stylist_promotion_pack(user, base_url)
            result_key = "stylist_promotion"
        else:
            text, markup = render_stylist_booking_link(user, base_url)
            result_key = "stylist_booking_link"
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return result_key

    if menu_key in {
        MENU_MANAGER_TODAY,
        MENU_MANAGER_SUMMARY,
        MENU_MANAGER_SHIFTS,
        MENU_MANAGER_SLOTS,
        MENU_MANAGER_REQUESTS,
        MENU_MANAGER_PROMOTION,
    }:
        from apps.messaging.manager_bot import (
            render_manager_available_slots,
            render_manager_pending_requests,
            render_manager_shifts_overview,
            render_manager_today_calendar,
            render_manager_today_summary,
        )
        from apps.messaging.promotion_bot import render_manager_promotion_pack

        if menu_key == MENU_MANAGER_TODAY:
            text, markup = render_manager_today_calendar(
                user, base_url, provider=provider, identity=identity
            )
            result_key = "manager_today"
        elif menu_key == MENU_MANAGER_SUMMARY:
            text, markup = render_manager_today_summary(
                user, base_url, provider=provider, identity=identity
            )
            result_key = "manager_summary"
        elif menu_key == MENU_MANAGER_SHIFTS:
            text, markup = render_manager_shifts_overview(
                user, base_url, provider=provider, identity=identity
            )
            result_key = "manager_shifts"
        elif menu_key == MENU_MANAGER_SLOTS:
            text, markup = render_manager_available_slots(
                user, base_url, provider=provider, identity=identity
            )
            result_key = "manager_slots"
        elif menu_key == MENU_MANAGER_PROMOTION:
            text, markup = render_manager_promotion_pack(user, base_url)
            result_key = "manager_promotion"
        else:
            text, markup = render_manager_pending_requests(
                user, base_url, provider=provider, identity=identity
            )
            result_key = "manager_requests"
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return result_key

    text, markup = menu_for_role(base_url, user, menu_key)
    _send(
        client,
        provider=provider,
        identity=identity,
        chat_id=chat_id,
        text=text,
        reply_markup=markup,
    )
    return f"role_menu:{menu_key}"


def _handle_action_callback(
    *,
    client: BaleBotClient,
    parsed: ParsedBaleUpdate,
    identity,
    provider,
    base_url: str,
) -> str:
    chat_id = parsed.chat_id or getattr(identity, "chat_id", "")
    result = dispatch_messaging_action_callback(
        provider=provider,
        identity=identity,
        callback_data=parsed.callback_data or "",
        base_url=base_url,
    )

    if parsed.callback_query_id:
        client.answer_callback_query(
            callback_query_id=parsed.callback_query_id,
            text=result.user_message,
            show_alert=result.status not in {"succeeded"},
        )

    _send(
        client,
        provider=provider,
        identity=identity,
        chat_id=chat_id,
        text=result.user_message,
        reply_markup=result.reply_markup,
    )
    return f"action_callback:{result.status}"


def _handle_disconnect_command(
    *, client: BaleBotClient, provider, identity, chat_id: str, base_url: str
) -> str:
    if not _identity_is_connected(identity):
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=already_disconnected_text(),
            reply_markup=guest_main_menu(base_url),
        )
        return "already_disconnected"

    disconnect_identity(identity)
    identity.refresh_from_db()

    _send(
        client,
        provider=provider,
        identity=identity,
        chat_id=chat_id,
        text=disconnected_text(),
        reply_markup=guest_main_menu(base_url),
    )
    return "disconnected"


def handle_bale_update_stage10(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    """
    Stage 10 dispatcher.

    Supported behaviour:
    - /start and /menu for guest or connected users
    - secure account-connect payload from stage 3
    - menu-only callback_data values with prefix menu:
    - one-time action callback tokens with prefix action:

    Customer menus/search, specialist/manager actions and promotion packs are now registered on the secure dispatcher.
    Every product-changing handler still re-checks object ownership, salon scope
    and permissions before changing anything.
    """
    client = BaleBotClient()
    chat_id = parsed.chat_id or getattr(identity, "chat_id", "")
    if not chat_id:
        return "ignored_missing_chat"

    if parsed.event_type == BaleUpdateType.CALLBACK_QUERY:
        callback_data = parsed.callback_data or ""
        if callback_data.startswith(MENU_CALLBACK_PREFIX):
            return _handle_menu_callback(
                client=client,
                parsed=parsed,
                identity=identity,
                provider=provider,
                base_url=base_url,
            )
        if callback_data.startswith(ACTION_CALLBACK_PREFIX):
            return _handle_action_callback(
                client=client,
                parsed=parsed,
                identity=identity,
                provider=provider,
                base_url=base_url,
            )
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=unsupported_action_text(),
            reply_markup=(
                guest_main_menu(base_url)
                if not getattr(identity, "user_id", None)
                else menu_for_user(base_url, identity.user)[1]
            ),
        )
        return "ignored_non_menu_callback"

    if parsed.event_type != BaleUpdateType.MESSAGE:
        return "ignored_non_message"

    command = parse_command(parsed.text)
    normalized_text = (parsed.text or "").strip().lower()

    if command and command.command in {"/stop", "/disconnect", "/logout"}:
        return _handle_disconnect_command(
            client=client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
        )

    if normalized_text in {
        "قطع اتصال",
        "لغو اتصال",
        "خروج",
        "توقف",
        "stop",
        "disconnect",
        "logout",
    }:
        return _handle_disconnect_command(
            client=client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
        )

    if command and command.command == "/start":
        payload = command.payload
        connect_token = extract_connect_token(payload)
        if connect_token:
            try:
                connection, token = connect_identity_with_raw_token(
                    identity=identity,
                    raw_token=connect_token,
                    metadata={"provider": "bale", "start_payload": payload},
                )
            except ValueError as exc:
                _send(
                    client,
                    provider=provider,
                    identity=identity,
                    chat_id=chat_id,
                    text=token_error_text(str(exc)),
                    reply_markup=guest_main_menu(base_url),
                )
                return f"connect_failed:{exc}"

            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=connected_text(connection.user),
                reply_markup=menu_for_user(base_url, connection.user)[1],
            )
            return "connected"

        if payload:
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=unknown_start_payload_text(),
                reply_markup=guest_main_menu(base_url),
            )
            return "unknown_payload"

        if getattr(identity, "user_id", None):
            return _show_connected_menu(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                base_url=base_url,
            )
        return _show_guest_menu(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
            display_name=getattr(identity, "display_name", ""),
        )

    if command and command.command in {"/search", "/salon"}:
        from apps.messaging.customer_bot import render_customer_salon_search

        text, markup = render_customer_salon_search(
            getattr(identity, "user", None), base_url, query=command.payload
        )
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return "customer_search_command"

    if command and command.command in {"/promo", "/story"}:
        user = _identity_user(identity)
        if not user:
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=disconnected_required_text(),
                reply_markup=guest_main_menu(base_url),
            )
            return "promotion_requires_connection"

        from apps.messaging.roles import BotRoleKey, detect_user_bot_roles
        from apps.messaging.promotion_bot import (
            render_manager_promotion_pack,
            render_stylist_promotion_pack,
        )

        context = detect_user_bot_roles(user)

        if context.has_role(BotRoleKey.STYLIST):
            text, markup = render_stylist_promotion_pack(identity.user, base_url)
            result_key = "stylist_promotion_command"
        elif context.has_role(BotRoleKey.MANAGER):
            text, markup = render_manager_promotion_pack(identity.user, base_url)
            result_key = "manager_promotion_command"
        else:
            text, markup = menu_for_user(base_url, identity.user)
            result_key = "promotion_no_role"
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return result_key

    if command and command.command in {"/menu", "/help"}:
        if command.command == "/help":
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=help_text(),
                reply_markup=help_menu(base_url),
            )
            return "help_menu"
        return _show_connected_menu(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
        )

    search_prefixes = ("جستجو ", "جستجوی ", "سالن ")
    for prefix in search_prefixes:
        if normalized_text.startswith(prefix):
            from apps.messaging.customer_bot import render_customer_salon_search

            query = (parsed.text or "").strip()[len(prefix) :].strip()
            text, markup = render_customer_salon_search(
                getattr(identity, "user", None), base_url, query=query
            )
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
            )
            return "customer_search_text"

    if normalized_text in {"جستجو", "جستجوی سالن", "سالن"}:
        from apps.messaging.customer_bot import render_customer_salon_search

        text, markup = render_customer_salon_search(
            getattr(identity, "user", None), base_url
        )
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return "customer_search_text"

    if normalized_text in {"نوبت های من", "نوبت‌های من", "نوبت من", "appointments"}:
        user = _identity_user(identity)
        if not user:
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=disconnected_required_text(),
                reply_markup=guest_main_menu(base_url),
            )
            return "appointments_requires_connection"

        from apps.messaging.customer_bot import render_customer_appointments

        text, markup = render_customer_appointments(user, base_url)
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return "customer_appointments_text"

    if normalized_text in {
        "تبلیغ",
        "استوری",
        "تبلیغ و لینک رزرو",
        "تبلیغ سالن",
        "محتوای آماده",
    }:
        user = _identity_user(identity)
        if not user:
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=disconnected_required_text(),
                reply_markup=guest_main_menu(base_url),
            )
            return "promotion_requires_connection"

        from apps.messaging.roles import BotRoleKey, detect_user_bot_roles
        from apps.messaging.promotion_bot import (
            render_manager_promotion_pack,
            render_stylist_promotion_pack,
        )

        context = detect_user_bot_roles(user)

        if context.has_role(BotRoleKey.STYLIST):
            text, markup = render_stylist_promotion_pack(identity.user, base_url)
            result_key = "stylist_promotion_text"
        elif context.has_role(BotRoleKey.MANAGER):
            text, markup = render_manager_promotion_pack(identity.user, base_url)
            result_key = "manager_promotion_text"
        else:
            text, markup = menu_for_user(base_url, identity.user)
            result_key = "promotion_no_role"
        _send(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            text=text,
            reply_markup=markup,
        )
        return result_key

    if normalized_text in {"منو", "menu", "راهنما", "help"}:
        if normalized_text in {"راهنما", "help"}:
            _send(
                client,
                provider=provider,
                identity=identity,
                chat_id=chat_id,
                text=help_text(),
                reply_markup=help_menu(base_url),
            )
            return "help_menu"
        return _show_connected_menu(
            client,
            provider=provider,
            identity=identity,
            chat_id=chat_id,
            base_url=base_url,
        )

    return "ignored_unknown_message"


def handle_bale_update_stage11(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )


# Backward-compatible aliases kept for imports created in previous stages.
def handle_bale_update_stage8(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )


def handle_bale_update_stage7(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )


def handle_bale_update_stage6(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )


def handle_bale_update_stage4(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )


def handle_bale_update_stage3(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )


def handle_bale_update_stage9(
    *, parsed: ParsedBaleUpdate, identity, provider, base_url: str = ""
) -> str:
    return handle_bale_update_stage10(
        parsed=parsed, identity=identity, provider=provider, base_url=base_url
    )
