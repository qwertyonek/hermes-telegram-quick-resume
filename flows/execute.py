"""The ONLY place actual commands get sent: ReplyKeyboardMarkup buttons whose
label IS the literal slash command. Tapping one is indistinguishable from
the user typing it (see docs/menu-audit.md §1.2 for why this is the correct
and only honest mechanism).

Destructive/confirm-flagged commands (ТЗ §4, §7) never get a direct
reply-keyboard button here — a reply-keyboard button sends on a single tap
with no interception point, so it is the wrong tool for anything that
needs a confirmation step. Those commands instead get an INLINE "Подтвердить"
button (navigation/routes.py's "confirm" route) that opens a dedicated
Да/Отмена screen; see __init__.py's confirm rendering.
"""
from __future__ import annotations

from ..registry.commands import CommandSpec, commands_for_screen

# Sentinel text for the "Отмена" button, intercepted by our own MessageHandler
# before it can reach the LLM as a stray chat message (see __init__.py).
CANCEL_TEXT = "\u274C Отмена"


def commands_keyboard(screen_id: str) -> tuple[list[CommandSpec], list[CommandSpec], object]:
    """Returns (destructive_specs, arg_specs, reply_markup). ``destructive_specs``
    needs the confirm flow; ``arg_specs`` needs a ForceReply argument prompt
    (see __init__.py's _render_arg_prompt) — neither gets a direct
    reply-keyboard button, since a bare tap on either would either skip
    confirmation or silently send the command with no argument at all (the
    ORIGINAL bug report this fixes: "Название" button fired bare /title).
    The caller renders inline rows for both alongside this reply keyboard,
    since both can't live on one message (reply keyboards attach to
    messages, inline keyboards too, but a single Telegram message carries
    only ONE of the two kinds at once)."""
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    specs = commands_for_screen(screen_id)
    direct = [c for c in specs if not (c.destructive or c.confirm or c.needs_argument)]
    needs_confirm = [c for c in specs if c.destructive or c.confirm]
    needs_arg = [c for c in specs if c.needs_argument and not (c.destructive or c.confirm)]

    rows = [[KeyboardButton(f"/{c.name}")] for c in direct]
    rows.append([KeyboardButton("/menu")])
    return needs_confirm, needs_arg, ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def confirm_keyboard(command_name: str):
    """Да/Отмена for one destructive command. "Да" sends the REAL command;
    "Отмена" sends a fixed sentinel text (CANCEL_TEXT) that this plugin's
    own MessageHandler intercepts BEFORE core's catch-all text handler
    (same hoisting mechanism as the callback handler — see
    gateway/platforms/base.py::_wire_plugin_handlers), so it never reaches
    the LLM as a stray chat message."""
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    rows = [
        [KeyboardButton(f"/{command_name}")],
        [KeyboardButton(CANCEL_TEXT)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def confirm_prompt_text(spec: CommandSpec) -> str:
    risk = "НЕОБРАТИМО" if spec.destructive else "требует внимания"
    return (
        f"\u26A0\uFE0F *{spec.label}* \u2014 {risk}.\n\n"
        f"Нажмите /{spec.name} ниже, чтобы подтвердить, или «{CANCEL_TEXT}»."
    )


def needs_argument_text(spec: CommandSpec) -> str:
    return (
        f"*{spec.label}* требует аргумент.\n\n"
        f"{spec.argument_hint}\n\n"
        f"Можно также нажать /{spec.name} без аргумента \u2014 бот покажет, что делать дальше."
    )
