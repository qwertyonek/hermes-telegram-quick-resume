"""DELIBERATE BYPASS of Hermes's plugin-injection safety boundary.

Hermes's ONLY public API for a plugin to "send a message as the user" is
``PluginContext.inject_message()``. Core forces ``allow_gateway_control=False``
on every event it produces (gateway/run_plugin_injection.py:148,236) —
by design, so an installed plugin can never silently fire a slash command
(``/restart``, ``/rollback``, ``/approve``...) on the user's behalf without
a real message appearing in the chat.

This module deliberately does NOT use that API. Instead it calls the
Telegram adapter's own ``handle_message()`` directly — the exact same
entrypoint PTB uses for a real typed message — with a MessageEvent built
from the REAL update that carried the inline-button tap (same chat, same
Telegram user_id, same authorization path: ``_is_user_authorized_from_message``
runs downstream exactly as it would for typed text). The only thing that
differs from a typed command is that no visible text message appears in
the chat history before the agent's reply.

Accepted explicitly by the user (QWERTYONEK) after being shown the
alternative (honest reply-keyboard) and the exact mechanism being bypassed.
If this plugin is ever published for other people's bots, this module
must ship disabled by default — see EXECUTE_INLINE_ENABLED below.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Published-plugin safety net: inline-execute is OFF unless explicitly turned
# on via the plugin's own settings subtree:
#   plugins:
#     entries:
#       hermes-telegram-quick-resume:
#         settings:
#           enable_inline_execute: true
# Read through ctx.get_config() — the documented, public per-plugin settings
# API — not any internal config module. Keeps the bypass opt-in for anyone
# who installs this from the catalog.
_CONFIG_FLAG = "enable_inline_execute"


def inline_execute_allowed(ctx) -> bool:
    try:
        return ctx.get_config(_CONFIG_FLAG, False) is True
    except Exception:
        logger.debug("inline_execute_allowed: config lookup failed", exc_info=True)
        return False


async def execute_as_if_typed(adapter, update, command_text: str) -> bool:
    """Run *command_text* (e.g. "/restart") through the SAME path a real typed
    Telegram message would take, using the chat/user identity from *update*
    (the update that carried the inline-button tap).

    Returns True if dispatched, False if the adapter/message shape didn't
    match what we expect (caller should fall back to showing the reply-
    keyboard button instead of silently doing nothing).
    """
    from gateway.platforms.event import MessageType

    msg = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if msg is None:
        return False
    try:
        event = adapter._build_message_event(msg, MessageType.COMMAND, update_id=update.update_id)
    except Exception:
        logger.warning("execute_as_if_typed: _build_message_event failed", exc_info=True)
        return False

    # _build_message_event() takes the text from the ORIGINAL update (the
    # callback's message, not the command) — override it with the command
    # we actually want to run. allow_gateway_control defaults True on a
    # fresh MessageEvent, which is exactly the bypass: this is what makes
    # Hermes treat it as a real command instead of inert chat text.
    event.text = command_text

    # Re-run the same authorization check _handle_command() would have run
    # on a typed message, using the real update's user — belt-and-braces,
    # since _build_message_event() already derived identity from it, but an
    # explicit recheck here keeps this module auditable on its own.
    try:
        if not adapter._is_user_authorized_from_message(msg):
            logger.warning("execute_as_if_typed: blocked unauthorized user for %r", command_text)
            return False
    except Exception:
        logger.warning("execute_as_if_typed: authorization check failed, refusing", exc_info=True)
        return False

    try:
        await adapter.handle_message(event)
    except Exception:
        logger.warning("execute_as_if_typed: handle_message failed for %r", command_text, exc_info=True)
        return False
    return True
