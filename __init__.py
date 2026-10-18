"""Hermes Telegram Control — полноценная русскоязычная панель управления.

Архитектура (см. docs/menu-audit.md для полного разбора ограничений API):

- navigation/routes.py: callback_data <-> MenuRoute, без серверного state.
- screens/render.py: текст+inline-клавиатура для каждого экрана — ТОЛЬКО
  навигация, никогда не выполняет команду.
- registry/commands.py: единый реестр command -> screen -> metadata.
- flows/execute.py: ReplyKeyboardMarkup — единственное место, где тап
  реально ОТПРАВЛЯЕТ команду (как настоящее сообщение пользователя).
- security/auth.py: проверка допуска при каждом callback/сообщении.
- sessions.py: чтение списка сессий через публичный `hermes sessions list`.

Почему команды не выполняются из инлайн-кнопок — см. docs/menu-audit.md §1.2:
Hermes принудительно ставит allow_gateway_control=False для любого
ctx.inject_message, поэтому программный вызов slash-команды плагином
архитектурно невозможен (осознанная граница безопасности). Единственный
честный способ — ReplyKeyboardMarkup, где подпись кнопки = текст команды,
и тап отправляет его как настоящее сообщение, проходящее штатный диспетчер.

Public-surface only: ctx.register_command, ctx.register_telegram_handler.
Никогда не импортирует gateway/hermes_cli internals.
"""
from __future__ import annotations

import logging

from .flows.direct_execute import execute_as_if_typed, inline_execute_allowed
from .flows.execute import CANCEL_TEXT, commands_keyboard, confirm_keyboard, confirm_prompt_text
from .navigation.routes import MenuRoute, decode, encode
from .registry.commands import BY_NAME, SCREEN_TITLES, commands_for_screen
from .screens.render import (cmdlist_back_keyboard, commands_inline_keyboard, root_keyboard, root_text,
                              screen_keyboard, screen_text)
from .security.auth import is_authorized
from .sessions import SessionRow, list_telegram_sessions

logger = logging.getLogger(__name__)

_RESUME_PAGE_SIZE = 8
_NOT_AUTHORIZED_TEXT = "\u26D4 У вас нет доступа к этой панели."


async def _safe_edit(query, text: str, **kwargs):
    """edit_message_text wrapper: Telegram raises BadRequest("Message is not
    modified") when the new text+markup are byte-identical to the current
    message (e.g. tapping the same screen twice, or a "Отправлено: /status"
    confirmation re-shown after a second tap) — harmless, not a real error,
    but an uncaught raise crashes the whole callback handler. Swallow only
    that exact case; anything else re-raises."""
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception as exc:
        if "not modified" in str(exc).lower():
            return
        raise


def _resume_page_keyboard(rows: list[SessionRow], page: int, *, inline_mode: bool = False):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

    start = page * _RESUME_PAGE_SIZE
    page_rows = rows[start:start + _RESUME_PAGE_SIZE]
    total_pages = max(1, (len(rows) + _RESUME_PAGE_SIZE - 1) // _RESUME_PAGE_SIZE)

    def _cmd_for(row: SessionRow) -> str:
        safe_title = row.title.replace('"', '\\"')
        return f'/resume "{safe_title}"'

    if inline_mode:
        # No ReplyKeyboardMarkup at all: each session is its own inline "execute"
        # button (command stashed in callback_data, resolved to the real /resume
        # text only inside _render_execute's lookup via BY_NAME... but /resume
        # needs an arbitrary title, not a registry command name, so we encode
        # the session index instead and resolve the title at dispatch time).
        inline_rows = []
        for idx, row in enumerate(page_rows):
            inline_rows.append([InlineKeyboardButton(
                row.title, callback_data=encode(MenuRoute(kind="execute", command=f"__resume__:{start + idx}")))])
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("\u2B05\uFE0F", callback_data=encode(MenuRoute(kind="resume_list", page=page - 1))))
        nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=encode(MenuRoute(kind="resume_list", page=page))))
        if start + _RESUME_PAGE_SIZE < len(rows):
            nav_row.append(InlineKeyboardButton("\u27A1\uFE0F", callback_data=encode(MenuRoute(kind="resume_list", page=page + 1))))
        inline_rows.append(nav_row)
        inline_rows.append([InlineKeyboardButton("\U0001F3E0 Главная", callback_data=encode(MenuRoute(kind="root")))])
        return InlineKeyboardMarkup(inline_rows), None

    # Navigation (inline, edits the panel message).
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("\u2B05\uFE0F", callback_data=encode(MenuRoute(kind="resume_list", page=page - 1))))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=encode(MenuRoute(kind="resume_list", page=page))))
    if start + _RESUME_PAGE_SIZE < len(rows):
        nav_row.append(InlineKeyboardButton("\u27A1\uFE0F", callback_data=encode(MenuRoute(kind="resume_list", page=page + 1))))
    inline_rows = [nav_row, [InlineKeyboardButton("\U0001F3E0 Главная", callback_data=encode(MenuRoute(kind="root")))]]

    # Execution (real reply-keyboard, one tap = real "/resume "<title>"" message).
    reply_rows = [[KeyboardButton(_cmd_for(row))] for row in page_rows]
    reply_rows.append([KeyboardButton("/menu")])

    return InlineKeyboardMarkup(inline_rows), ReplyKeyboardMarkup(reply_rows, resize_keyboard=True, one_time_keyboard=True)


def _resume_page_text(rows: list[SessionRow], page: int) -> str:
    if not rows:
        return ("\U0001F4AC *Сессии*\n\nНазванных сессий пока нет.\n"
                "Используйте /title, чтобы назвать текущую сессию, потом возвращайтесь сюда.")
    start = page * _RESUME_PAGE_SIZE
    page_rows = rows[start:start + _RESUME_PAGE_SIZE]
    lines = ["\U0001F4AC *Сохранённые сессии*", ""]
    for row in page_rows:
        preview = f" \u2014 _{row.preview}_" if row.preview else ""
        lines.append(f"\u2022 {row.title}{preview} ({row.last_active})")
    lines.append("")
    lines.append("Нажмите кнопку снизу, чтобы вернуться в сессию \U0001F447")
    return "\n".join(lines)


def _handle_menu_command(raw_args: str, **kwargs):
    """``/menu`` для не-Telegram поверхностей (CLI, другие гейтвеи) —
    текстовый fallback без кнопок, т.к. живого PTB Update там нет."""
    lines = ["\U0001F916 Hermes \u2014 Управление", ""]
    for screen_id, (emoji, title) in SCREEN_TITLES.items():
        names = ", ".join(f"/{c.name}" for c in commands_for_screen(screen_id))
        lines.append(f"{emoji} {title}: {names}")
    lines.append("")
    lines.append("(Откройте этот чат в Telegram для панели с кнопками.)")
    return "\n".join(lines)


def register(ctx):
    inline_mode = inline_execute_allowed(ctx)
    if inline_mode:
        logger.warning(
            "hermes-telegram-control: INLINE EXECUTE ENABLED — bypassing "
            "allow_gateway_control via adapter.handle_message(); see "
            "flows/direct_execute.py for the exact mechanism and why."
        )

    def _wire_telegram(native, adapter):
        """Фабрика, вызываемая один раз при connect(): native — живое PTB Application."""
        from telegram import Update
        from telegram.ext import CallbackQueryHandler, CommandHandler, filters
        from telegram.ext import MessageHandler as TgMessageHandler

        def _user_id(update: Update) -> str | None:
            user = update.effective_user
            return str(user.id) if user else None

        async def _render_root(update: Update, *, edit: bool):
            text = root_text(session_title=None, model_hint=None)
            kb = root_keyboard(inline_mode=inline_mode)
            if edit and update.callback_query:
                await _safe_edit(update.callback_query, text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

        async def _render_screen(update: Update, screen_id: str, *, edit: bool):
            text = screen_text(screen_id)
            kb = screen_keyboard(screen_id)
            if edit and update.callback_query:
                await _safe_edit(update.callback_query, text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

        async def _render_cmdlist(update: Update, screen_id: str):
            emoji, title = SCREEN_TITLES[screen_id]
            if inline_mode:
                # All-inline: safe commands execute directly via adapter.handle_message()
                # bypass (flows/direct_execute.py); destructive ones still gate through confirm.
                if update.callback_query:
                    await _safe_edit(update.callback_query, 
                        f"{emoji} *{title}*", parse_mode="Markdown",
                        reply_markup=commands_inline_keyboard(screen_id),
                    )
                return
            confirm_specs, reply_kb = commands_keyboard(screen_id)
            # Inline part: edit the panel message — nav back + "Подтвердить" gates
            # for any destructive command on this screen.
            if update.callback_query:
                await _safe_edit(update.callback_query, 
                    f"{emoji} *{title}* \u2014 кнопки команд ниже \U0001F447",
                    parse_mode="Markdown", reply_markup=cmdlist_back_keyboard(screen_id, confirm_specs),
                )
            # Reply-keyboard part: a NEW message, since ReplyKeyboardMarkup cannot
            # attach to edit_message_text (Telegram Bot API constraint). Only
            # non-destructive commands are real buttons here.
            await update.effective_chat.send_message(
                "Нажмите команду \U0001F447", reply_markup=reply_kb,
            )

        async def _render_execute(update: Update, command_name: str):
            """Inline-mode only: run *command_name* through the handle_message()
            bypass using the SAME update that carried this callback tap."""
            query = update.callback_query
            if command_name.startswith("__resume__:"):
                try:
                    idx = int(command_name.split(":", 1)[1])
                except ValueError:
                    idx = -1
                rows = list_telegram_sessions(limit=50)
                if idx < 0 or idx >= len(rows):
                    await _safe_edit(query, "\u26A0\uFE0F Сессия устарела.", reply_markup=root_keyboard(inline_mode=inline_mode))
                    return
                safe_title = rows[idx].title.replace('"', '\\"')
                ok = await execute_as_if_typed(adapter, update, f'/resume "{safe_title}"')
                label = rows[idx].title
                if not ok:
                    await _safe_edit(query, f"\u26A0\uFE0F Не удалось открыть «{label}».", reply_markup=root_keyboard(inline_mode=inline_mode))
                    return
                await _safe_edit(query, f"\u2705 Открываю: {label}", reply_markup=root_keyboard(inline_mode=inline_mode))
                return
            spec = BY_NAME.get(command_name)
            if spec is None:
                await _safe_edit(query, "\u26A0\uFE0F Команда устарела.", reply_markup=root_keyboard(inline_mode=inline_mode))
                return
            ok = await execute_as_if_typed(adapter, update, f"/{spec.name}")
            if not ok:
                await _safe_edit(query, 
                    f"\u26A0\uFE0F Не удалось выполнить /{spec.name}. Попробуйте ещё раз.",
                    reply_markup=commands_inline_keyboard(spec.screen),
                )
                return
            # The agent's own reply arrives as a normal new message; leave the panel
            # message showing where we are, with nav back to the same command list.
            await _safe_edit(query, 
                f"\u2705 Отправлено: /{spec.name}", reply_markup=commands_inline_keyboard(spec.screen),
            )

        async def _render_confirm(update: Update, command_name: str):
            spec = BY_NAME.get(command_name)
            if spec is None:
                await _safe_edit(update.callback_query, 
                    "\u26A0\uFE0F Команда устарела.", reply_markup=root_keyboard(inline_mode=inline_mode))
                return
            if inline_mode:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                rows = [
                    [InlineKeyboardButton(f"\u2705 Да, {spec.label}", callback_data=encode(MenuRoute(kind="execute", command=spec.name)))],
                    [InlineKeyboardButton("\u274C Отмена", callback_data=encode(MenuRoute(kind="cmdlist", screen=spec.screen)))],
                ]
                await _safe_edit(update.callback_query, 
                    confirm_prompt_text(spec), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows),
                )
                return
            await _safe_edit(update.callback_query, 
                confirm_prompt_text(spec), parse_mode="Markdown",
                reply_markup=cmdlist_back_keyboard(spec.screen, []),
            )
            await update.effective_chat.send_message(
                "Подтвердите \U0001F447", reply_markup=confirm_keyboard(spec.name),
            )

        async def _render_resume(update: Update, page: int, *, edit: bool):
            rows = list_telegram_sessions(limit=50)
            inline_kb, reply_kb = _resume_page_keyboard(rows, page, inline_mode=inline_mode)
            text = _resume_page_text(rows, page)
            if edit and update.callback_query:
                await _safe_edit(update.callback_query, text, parse_mode="Markdown", reply_markup=inline_kb)
            else:
                await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=inline_kb)
            if rows and reply_kb is not None:
                await update.effective_chat.send_message("Нажмите сессию \U0001F447", reply_markup=reply_kb)

        async def cmd_menu(update: Update, context):
            if not is_authorized(_user_id(update)):
                await update.effective_message.reply_text(_NOT_AUTHORIZED_TEXT)
                return
            await _render_root(update, edit=False)

        async def on_callback(update: Update, context):
            query = update.callback_query
            data = query.data or ""
            route = decode(data)
            if route is None:
                return  # не наш callback — пусть core обработает своим catch-all
            # ТЗ §1.8 + §7: авторизация и answer() на КАЖДЫЙ callback, не только на рендер.
            if not is_authorized(_user_id(update)):
                await query.answer(text="Нет доступа", show_alert=True)
                return
            try:
                await query.answer()
            except Exception:
                pass  # устаревший/дважды отвеченный callback — не фатально (ТЗ §7)

            if route.kind == "root":
                await _render_root(update, edit=True)
            elif route.kind == "screen":
                if route.screen not in SCREEN_TITLES:
                    await _safe_edit(query, "\u26A0\uFE0F Экран устарел.", reply_markup=root_keyboard(inline_mode=inline_mode))
                    return
                await _render_screen(update, route.screen, edit=True)
            elif route.kind == "cmdlist":
                if route.screen not in SCREEN_TITLES:
                    await _safe_edit(query, "\u26A0\uFE0F Экран устарел.", reply_markup=root_keyboard(inline_mode=inline_mode))
                    return
                await _render_cmdlist(update, route.screen)
            elif route.kind == "resume_list":
                await _render_resume(update, route.page, edit=True)
            elif route.kind == "confirm":
                await _render_confirm(update, route.command)
            elif route.kind == "execute":
                if not inline_mode:
                    return  # execute routes only exist when inline-execute is on
                await _render_execute(update, route.command)

        async def on_cancel_text(update: Update, context):
            """Перехватывает кнопку CANCEL_TEXT до того, как она дойдёт до LLM как
            обычное сообщение (тот же hoisting-механизм, что и у CallbackQueryHandler)."""
            await update.effective_message.reply_text(
                "Отменено. Ничего не выполнено.", reply_markup=root_keyboard(inline_mode=inline_mode),
            )

        native.add_handler(CommandHandler("menu", cmd_menu))
        native.add_handler(CallbackQueryHandler(on_callback, pattern="^qr:"))
        native.add_handler(TgMessageHandler(filters.Regex(f"^{CANCEL_TEXT}$"), on_cancel_text))
        logger.info("hermes-telegram-control: /menu wired (navigation+execution split)")

    ctx.register_telegram_handler(_wire_telegram)

    ctx.register_command(
        "menu", handler=_handle_menu_command,
        description="Открыть панель управления Hermes (все разделы и команды)",
    )

    from pathlib import Path
    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)
