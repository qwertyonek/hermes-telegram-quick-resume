"""Hermes Telegram Quick Resume — tap-to-resume menu for the Telegram gateway.

Design note on WHY this plugin never calls ``ctx.inject_message`` to run a
command: Hermes deliberately forces every plugin-injected message to
``allow_gateway_control=False`` (see gateway/run_plugin_injection.py and
gateway/platforms/event.py's ``get_command()``), so an injected "/status"
is never treated as a slash command — only as conversational text handed to
the LLM. That is a real security boundary (a plugin must never be able to
drive the gateway's control plane), not a bug to route around.

Instead, the final action on every button is a genuine Telegram message: a
``ReplyKeyboardMarkup`` button whose *text* is the exact command (e.g.
"/resume 3", "/status"). Tapping it sends that text as a real incoming
message from the user — indistinguishable from typing it by hand — so it
flows through Hermes's normal command dispatcher with full authorization.
Category navigation (no command execution) stays on cheap, UI-only inline
buttons that just edit the message in place.

Public-surface only: ctx.register_command, ctx.register_telegram_handler.
Never imports gateway/hermes_cli internals.
"""
from __future__ import annotations

import logging

from . import menu, sessions

logger = logging.getLogger(__name__)

# Telegram inline callback_data is capped at 64 bytes; keep every payload short and
# namespaced so this plugin's CallbackQueryHandler never fires for another plugin's
# or core's buttons.
_CB_PREFIX = "qr:"  # qr:cat:<idx> | qr:resume_refresh | qr:home


def _home_keyboard():
    """Pure navigation — inline buttons, no command ever executes from here."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    row: list = []
    for i, (emoji, title, _cmds) in enumerate(menu.CATEGORIES):
        row.append(InlineKeyboardButton(f"{emoji} {title}", callback_data=f"{_CB_PREFIX}cat:{i}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.insert(0, [InlineKeyboardButton("\U0001F4C2 Resume a session", callback_data=f"{_CB_PREFIX}resume_refresh")])
    return InlineKeyboardMarkup(rows)


def _category_keyboard(idx: int):
    """Navigation only: shows what's in a category, then hands off to a real
    ReplyKeyboardMarkup (via a follow-up message) for the actual command send."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [[InlineKeyboardButton("\u25B6 Show tappable commands", callback_data=f"{_CB_PREFIX}show:{idx}")]]
    rows.append([InlineKeyboardButton("\u2B05 Menu", callback_data=f"{_CB_PREFIX}home")])
    return InlineKeyboardMarkup(rows)


def _commands_reply_keyboard(cmds: list[tuple[str, str]]):
    """Real action buttons: each button's TEXT is the literal slash command, so tapping
    sends a genuine message that Hermes's own dispatcher recognizes and runs — no plugin
    injection involved. One-time: collapses back to the normal keyboard after a tap."""
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    rows = [[KeyboardButton(f"/{cmd}")] for cmd, _label in cmds]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _resume_reply_keyboard(rows: list[sessions.SessionRow]):
    from telegram import KeyboardButton, ReplyKeyboardMarkup

    def _cmd_for(row: sessions.SessionRow) -> str:
        # Quote the title so /resume's parser treats it as one argument even with
        # spaces; a literal " inside a title is escaped the same way the parser expects.
        safe_title = row.title.replace('"', '\\"')
        return f'/resume "{safe_title}"'

    buttons = [[KeyboardButton(_cmd_for(row))] for row in rows]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


def _handle_menu_command(raw_args: str, **kwargs):
    """``/menu`` body for non-Telegram surfaces (CLI, other gateways) where the live
    PTB ``Update`` isn't available — plain text fallback, no buttons."""
    lines = ["\U0001F916 Hermes — Quick Menu", ""]
    for emoji, title, cmds in menu.CATEGORIES:
        names = ", ".join(f"/{c}" for c, _label in cmds)
        lines.append(f"{emoji} {title}: {names}")
    lines.append("")
    lines.append("(Open this chat in Telegram for tap-to-run buttons.)")
    return "\n".join(lines)


def register(ctx):
    def _wire_telegram(native, adapter):
        """Factory invoked once at Telegram connect(): native is the PTB Application."""
        from telegram import Update
        from telegram.ext import CallbackQueryHandler, CommandHandler

        async def _send_home(update: Update):
            await update.effective_message.reply_text(
                "\U0001F916 *Hermes — Quick Menu*\n\nPick a category, or jump straight into a saved session.",
                parse_mode="Markdown", reply_markup=_home_keyboard(),
            )

        async def _send_resume_list(update: Update, edit: bool = False):
            rows = sessions.list_telegram_sessions(limit=10)
            if not rows:
                text = ("No named sessions found yet.\nUse /title to name your current "
                        "session, then come back here to resume it with one tap.")
                if edit and update.callback_query:
                    await update.callback_query.edit_message_text(
                        text, parse_mode="Markdown", reply_markup=_home_keyboard())
                else:
                    await update.effective_message.reply_text(text)
                return
            if edit and update.callback_query:
                await update.callback_query.edit_message_text(
                    "\U0001F4C2 *Saved sessions* — tap a button below to resume:", parse_mode="Markdown")
            # The actual resume buttons must be a NEW message: ReplyKeyboardMarkup is a
            # chat-wide keyboard, not something edit_message_text can attach.
            await update.effective_chat.send_message(
                "Tap a session \U0001F447", reply_markup=_resume_reply_keyboard(rows),
            )

        async def cmd_menu(update: Update, context):
            await _send_home(update)

        async def cmd_quick_resume(update: Update, context):
            await _send_resume_list(update, edit=False)

        async def on_callback(update: Update, context):
            query = update.callback_query
            data = query.data or ""
            if not data.startswith(_CB_PREFIX):
                return  # not ours — let core's catch-all handler see it
            await query.answer()
            action = data[len(_CB_PREFIX):]

            if action == "home":
                await query.edit_message_text(
                    "\U0001F916 *Hermes — Quick Menu*\n\nPick a category, or jump straight into a saved session.",
                    parse_mode="Markdown", reply_markup=_home_keyboard(),
                )
                return

            if action == "resume_refresh":
                await _send_resume_list(update, edit=True)
                return

            if action.startswith("cat:"):
                idx = int(action.split(":", 1)[1])
                emoji, title, cmds = menu.CATEGORIES[idx]
                names = "\n".join(f"\u2022 /{c} — {label}" for c, label in cmds)
                await query.edit_message_text(
                    f"{emoji} *{title}*\n\n{names}", parse_mode="Markdown",
                    reply_markup=_category_keyboard(idx),
                )
                return

            if action.startswith("show:"):
                idx = int(action.split(":", 1)[1])
                _emoji, _title, cmds = menu.CATEGORIES[idx]
                await update.effective_chat.send_message(
                    "Tap a command \U0001F447", reply_markup=_commands_reply_keyboard(cmds),
                )
                return

        native.add_handler(CommandHandler("menu", cmd_menu))
        native.add_handler(CommandHandler("qr", cmd_quick_resume))
        # Scoped to our prefix so core's own CallbackQueryHandler still gets everything else.
        native.add_handler(CallbackQueryHandler(on_callback, pattern=f"^{_CB_PREFIX}"))
        logger.info("hermes-telegram-quick-resume: /menu, /qr wired")

    ctx.register_telegram_handler(_wire_telegram)

    ctx.register_command(
        "menu", handler=_handle_menu_command,
        description="Open the tap-to-use Hermes menu (sessions + all commands)",
    )
    ctx.register_command(
        "qr", handler=lambda raw: "Use /menu or /qr in Telegram for the tap-to-resume list.",
        description="Quick session-resume button list (Telegram only)",
    )

    # Ship the companion skill so the agent can explain this plugin's commands to the user.
    from pathlib import Path
    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)
