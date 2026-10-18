"""Hermes Telegram Control — полноценная русскоязычная (+EN) панель управления.

Архитектура (см. docs/menu-audit.md для полного разбора ограничений API):

- navigation/routes.py: callback_data <-> MenuRoute, без серверного state.
- screens/render.py: текст+inline-клавиатура для каждого экрана — ТОЛЬКО
  навигация, никогда не выполняет команду. Содержит i18n-строки (ru/en).
- registry/commands.py: единый реестр command -> screen -> metadata, с
  CommandSpec.label_for(lang) для перевода подписей кнопок.
- flows/execute.py: ReplyKeyboardMarkup — единственное место, где тап
  реально ОТПРАВЛЯЕТ команду (как настоящее сообщение пользователя), для
  классического (не inline-execute) режима.
- flows/direct_execute.py: опциональный байпас allow_gateway_control для
  инлайн-исполнения (см. модуль за полный разбор механизма и рисков).
- security/auth.py: проверка допуска при каждом callback/сообщении.
- sessions.py: чтение/удаление/переименование сессий через публичный
  `hermes sessions` CLI (list/delete/rename) — никогда не трогает state.db.

i18n: язык хранится per-chat в ctx.state (PluginState, профильный JSON,
публичный API плагина) под ключом f"lang:{chat_id}". Кнопка "🌐 EN"/"🌐 RU"
в правом нижнем углу главного меню переключает её для текущего чата; весь
рендер экранов — screens/render.py — принимает lang="ru"|"en".

Почему команды не выполняются из инлайн-кнопок по умолчанию — см.
docs/menu-audit.md §1.2: Hermes принудительно ставит
allow_gateway_control=False для любого ctx.inject_message, поэтому
программный вызов slash-команды плагином архитектурно невозможен
(осознанная граница безопасности). Честный способ — ReplyKeyboardMarkup,
где подпись кнопки = текст команды. Опциональный byпасс — flows/direct_execute.py.

Public-surface only: ctx.register_command, ctx.register_telegram_handler,
ctx.state, ctx.get_config. Никогда не импортирует gateway/hermes_cli internals
(кроме flows/direct_execute.py's deliberate, documented, opt-in bypass).
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
_NOT_AUTHORIZED_TEXT = "\u26D4 У вас нет доступа к этой панели. / No access to this panel."
_DEFAULT_LANG = "ru"
# chat_id -> session_id awaiting a ForceReply rename answer. Module-level
# (not per-handler-closure) since on_rename_reply and _render_session_rename_prompt
# both need it; process-local and ephemeral by design — a restart just drops
# any in-flight rename wizard, which is harmless (nothing destructive pending).
_pending_rename: dict[int, str] = {}


async def _safe_edit(query, text: str, **kwargs):
    """edit_message_text wrapper: Telegram raises BadRequest("Message is not
    modified") when the new text+markup are byte-identical to the current
    message (e.g. tapping the same screen twice) — harmless, not a real
    error, but an uncaught raise crashes the whole callback handler. Swallow
    only that exact case; anything else re-raises."""
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception as exc:
        if "not modified" in str(exc).lower():
            return
        raise


def _session_list_keyboard(rows: list[SessionRow], *, lang: str):
    """Flat list of session-title buttons — PURE NAVIGATION (ТЗ §1.12): each
    tap opens that session's card (session_card route), never resumes
    directly. Works identically in classic and inline-execute mode since
    this is navigation, not execution — no reply-keyboard needed here."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    home_label = "\U0001F3E0 Главная" if lang != "en" else "\U0001F3E0 Home"
    rows_kb = []
    for idx, row in enumerate(rows):
        rows_kb.append([InlineKeyboardButton(
            f"{idx + 1}. {row.title}", callback_data=encode(MenuRoute(kind="session_card", page=idx)))])
    rows_kb.append([InlineKeyboardButton(home_label, callback_data=encode(MenuRoute(kind="root")))])
    return InlineKeyboardMarkup(rows_kb)


def _session_list_text(rows: list[SessionRow], *, lang: str) -> str:
    if lang == "en":
        if not rows:
            return ("\U0001F4AC *Sessions*\n\nNo named sessions yet.\n"
                    "Use /title to name the current session, then come back here.")
        return "\U0001F4AC *Saved sessions*\n\nPick a session \U0001F447"
    if not rows:
        return ("\U0001F4AC *Сессии*\n\nНазванных сессий пока нет.\n"
                "Используйте /title, чтобы назвать текущую сессию, потом возвращайтесь сюда.")
    return "\U0001F4AC *Сохранённые сессии*\n\nВыберите сессию \U0001F447"


def _session_card_text(row: SessionRow, *, lang: str) -> str:
    if lang == "en":
        lines = [f"\U0001F4AC *{row.title}*", ""]
        if row.preview:
            lines.append(f"_{row.preview}_")
            lines.append("")
        lines.append(f"Last active: {row.last_active}")
        lines.append(f"ID: `{row.session_id}`")
        return "\n".join(lines)
    lines = [f"\U0001F4AC *{row.title}*", ""]
    if row.preview:
        lines.append(f"_{row.preview}_")
        lines.append("")
    lines.append(f"Последняя активность: {row.last_active}")
    lines.append(f"ID: `{row.session_id}`")
    return "\n".join(lines)


def _session_card_keyboard(idx: int, *, inline_mode: bool, lang: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    en = lang == "en"
    enter_label = "\u25B6\uFE0F Enter" if en else "\u25B6\uFE0F Войти"
    rename_label = "\u270F\uFE0F Rename" if en else "\u270F\uFE0F Переименовать"
    delete_label = "\U0001F5D1 Delete" if en else "\U0001F5D1 Удалить"
    back_label = "\u2B05\uFE0F To list" if en else "\u2B05\uFE0F К списку"
    home_label = "\U0001F3E0 Home" if en else "\U0001F3E0 Главная"

    top_row = []
    if inline_mode:
        # Resume needs the handle_message() bypass (flows/direct_execute.py) —
        # only available in inline-execute mode. Classic mode's enter button
        # is a real reply-keyboard /resume button instead (see _render_session_card).
        top_row.append(InlineKeyboardButton(enter_label, callback_data=encode(MenuRoute(kind="execute", command=f"__resume__:{idx}"))))
    top_row.append(InlineKeyboardButton(rename_label, callback_data=encode(MenuRoute(kind="session_rename", page=idx))))
    rows = [
        top_row,
        [InlineKeyboardButton(delete_label, callback_data=encode(MenuRoute(kind="session_delete", page=idx)))],
        [InlineKeyboardButton(back_label, callback_data=encode(MenuRoute(kind="resume_list", page=0))),
         InlineKeyboardButton(home_label, callback_data=encode(MenuRoute(kind="root")))],
    ]
    return InlineKeyboardMarkup(rows)


def _session_delete_confirm_keyboard(idx: int, *, lang: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    yes_label = "\u2705 Yes, delete" if lang == "en" else "\u2705 Да, удалить"
    cancel_label = "\u274C Cancel" if lang == "en" else "\u274C Отмена"
    rows = [
        [InlineKeyboardButton(yes_label, callback_data=encode(MenuRoute(kind="session_delete_confirm", page=idx))),
         InlineKeyboardButton(cancel_label, callback_data=encode(MenuRoute(kind="session_card", page=idx)))],
    ]
    return InlineKeyboardMarkup(rows)


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

    def _lang_for(chat_id: int) -> str:
        try:
            return ctx.state.get(f"lang:{chat_id}", _DEFAULT_LANG) or _DEFAULT_LANG
        except Exception:
            return _DEFAULT_LANG

    def _toggle_lang(chat_id: int) -> str:
        current = _lang_for(chat_id)
        new_lang = "en" if current != "en" else "ru"
        try:
            ctx.state.set(f"lang:{chat_id}", new_lang)
        except Exception:
            logger.debug("lang_toggle: ctx.state.set failed", exc_info=True)
        return new_lang

    def _wire_telegram(native, adapter):
        """Фабрика, вызываемая один раз при connect(): native — живое PTB Application."""
        from telegram import Update
        from telegram.ext import CallbackQueryHandler, CommandHandler, filters
        from telegram.ext import MessageHandler as TgMessageHandler

        def _user_id(update: Update) -> str | None:
            user = update.effective_user
            return str(user.id) if user else None

        async def _render_root(update: Update, *, edit: bool):
            lang = _lang_for(update.effective_chat.id)
            text = root_text(session_title=None, model_hint=None, lang=lang)
            kb = root_keyboard(inline_mode=inline_mode, lang=lang)
            if edit and update.callback_query:
                await _safe_edit(update.callback_query, text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

        async def _render_screen(update: Update, screen_id: str, *, edit: bool):
            lang = _lang_for(update.effective_chat.id)
            text = screen_text(screen_id, lang=lang)
            kb = screen_keyboard(screen_id, lang=lang)
            if edit and update.callback_query:
                await _safe_edit(update.callback_query, text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

        async def _render_cmdlist(update: Update, screen_id: str):
            lang = _lang_for(update.effective_chat.id)
            emoji, title = SCREEN_TITLES[screen_id]
            if inline_mode:
                # All-inline: safe commands execute directly via adapter.handle_message()
                # bypass (flows/direct_execute.py); destructive ones still gate through confirm.
                if update.callback_query:
                    await _safe_edit(update.callback_query,
                        f"{emoji} *{title}*", parse_mode="Markdown",
                        reply_markup=commands_inline_keyboard(screen_id, lang=lang),
                    )
                return
            confirm_specs, reply_kb = commands_keyboard(screen_id)
            # Inline part: edit the panel message — nav back + "Подтвердить" gates
            # for any destructive command on this screen.
            if update.callback_query:
                await _safe_edit(update.callback_query,
                    f"{emoji} *{title}* \u2014 кнопки команд ниже \U0001F447",
                    parse_mode="Markdown", reply_markup=cmdlist_back_keyboard(screen_id, confirm_specs, lang=lang),
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
            lang = _lang_for(update.effective_chat.id)
            query = update.callback_query
            if command_name.startswith("__resume__:"):
                try:
                    idx = int(command_name.split(":", 1)[1])
                except ValueError:
                    idx = -1
                rows = list_telegram_sessions(limit=50)
                if idx < 0 or idx >= len(rows):
                    await _safe_edit(query, "\u26A0\uFE0F Сессия устарела.", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
                    return
                safe_title = rows[idx].title.replace('"', '\\"')
                ok = await execute_as_if_typed(adapter, update, f'/resume "{safe_title}"')
                label = rows[idx].title
                if not ok:
                    await _safe_edit(query, f"\u26A0\uFE0F Не удалось открыть «{label}».",
                                      reply_markup=_session_card_keyboard(idx, inline_mode=inline_mode, lang=lang))
                    return
                await _safe_edit(query, f"\u2705 Открываю: {label}", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
                return
            spec = BY_NAME.get(command_name)
            if spec is None:
                await _safe_edit(query, "\u26A0\uFE0F Команда устарела.", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
                return
            ok = await execute_as_if_typed(adapter, update, f"/{spec.name}")
            if not ok:
                await _safe_edit(query,
                    f"\u26A0\uFE0F Не удалось выполнить /{spec.name}. Попробуйте ещё раз.",
                    reply_markup=commands_inline_keyboard(spec.screen, lang=lang),
                )
                return
            # The agent's own reply arrives as a normal new message; leave the panel
            # message showing where we are, with nav back to the same command list.
            await _safe_edit(query,
                f"\u2705 Отправлено: /{spec.name}", reply_markup=commands_inline_keyboard(spec.screen, lang=lang),
            )

        async def _render_confirm(update: Update, command_name: str):
            lang = _lang_for(update.effective_chat.id)
            spec = BY_NAME.get(command_name)
            if spec is None:
                await _safe_edit(update.callback_query,
                    "\u26A0\uFE0F Команда устарела.", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
                return
            if inline_mode:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                yes_label = f"\u2705 Yes, {spec.label_for(lang)}" if lang == "en" else f"\u2705 Да, {spec.label_for(lang)}"
                cancel_label = "\u274C Cancel" if lang == "en" else "\u274C Отмена"
                rows = [
                    [InlineKeyboardButton(yes_label, callback_data=encode(MenuRoute(kind="execute", command=spec.name)))],
                    [InlineKeyboardButton(cancel_label, callback_data=encode(MenuRoute(kind="cmdlist", screen=spec.screen)))],
                ]
                await _safe_edit(update.callback_query,
                    confirm_prompt_text(spec), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows),
                )
                return
            await _safe_edit(update.callback_query,
                confirm_prompt_text(spec), parse_mode="Markdown",
                reply_markup=cmdlist_back_keyboard(spec.screen, [], lang=lang),
            )
            await update.effective_chat.send_message(
                "Подтвердите \U0001F447", reply_markup=confirm_keyboard(spec.name),
            )

        async def _render_resume(update: Update, page: int, *, edit: bool):
            lang = _lang_for(update.effective_chat.id)
            rows = list_telegram_sessions(limit=50)
            kb = _session_list_keyboard(rows, lang=lang)
            text = _session_list_text(rows, lang=lang)
            if edit and update.callback_query:
                await _safe_edit(update.callback_query, text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

        async def _render_session_card(update: Update, idx: int):
            lang = _lang_for(update.effective_chat.id)
            query = update.callback_query
            rows = list_telegram_sessions(limit=50)
            if idx < 0 or idx >= len(rows):
                await _safe_edit(query, "\u26A0\uFE0F Сессия устарела.", reply_markup=_session_list_keyboard(rows, lang=lang))
                return
            row = rows[idx]
            await _safe_edit(query, _session_card_text(row, lang=lang), parse_mode="Markdown",
                              reply_markup=_session_card_keyboard(idx, inline_mode=inline_mode, lang=lang))
            if not inline_mode:
                # Classic mode: "Войти"/"Enter" has to be a real reply-keyboard
                # button (same honesty contract as commands_keyboard) since
                # there is no handle_message() bypass available here.
                from telegram import KeyboardButton, ReplyKeyboardMarkup
                safe_title = row.title.replace('"', '\\"')
                reply_kb = ReplyKeyboardMarkup(
                    [[KeyboardButton(f'/resume "{safe_title}"')], [KeyboardButton("/menu")]],
                    resize_keyboard=True, one_time_keyboard=True,
                )
                prompt = f"\u25B6\uFE0F Tap to enter «{row.title}»" if lang == "en" else f"\u25B6\uFE0F Нажмите, чтобы войти в «{row.title}»"
                await update.effective_chat.send_message(prompt, reply_markup=reply_kb)

        async def _render_session_delete(update: Update, idx: int):
            lang = _lang_for(update.effective_chat.id)
            query = update.callback_query
            rows = list_telegram_sessions(limit=50)
            if idx < 0 or idx >= len(rows):
                await _safe_edit(query, "\u26A0\uFE0F Сессия устарела.", reply_markup=_session_list_keyboard(rows, lang=lang))
                return
            row = rows[idx]
            prompt = (f"\u26A0\uFE0F Delete «{row.title}»? This is IRREVERSIBLE."
                      if lang == "en" else f"\u26A0\uFE0F Удалить «{row.title}»? Это действие НЕОБРАТИМО.")
            await _safe_edit(query, prompt, reply_markup=_session_delete_confirm_keyboard(idx, lang=lang))

        async def _render_session_delete_confirm(update: Update, idx: int):
            from .sessions import delete_session
            lang = _lang_for(update.effective_chat.id)
            query = update.callback_query
            rows = list_telegram_sessions(limit=50)
            if idx < 0 or idx >= len(rows):
                await _safe_edit(query, "\u26A0\uFE0F Сессия устарела.", reply_markup=_session_list_keyboard(rows, lang=lang))
                return
            row = rows[idx]
            ok = delete_session(row.session_id)
            if not ok:
                fail = f"\u26A0\uFE0F Could not delete «{row.title}»." if lang == "en" else f"\u26A0\uFE0F Не удалось удалить «{row.title}»."
                await _safe_edit(query, fail, reply_markup=_session_card_keyboard(idx, inline_mode=inline_mode, lang=lang))
                return
            rows_after = list_telegram_sessions(limit=50)
            done = f"\u2705 Deleted: «{row.title}»" if lang == "en" else f"\u2705 Удалено: «{row.title}»"
            await _safe_edit(query, done + "\n\n" + _session_list_text(rows_after, lang=lang),
                              parse_mode="Markdown", reply_markup=_session_list_keyboard(rows_after, lang=lang))

        async def _render_session_rename_prompt(update: Update, idx: int):
            from telegram import ForceReply
            lang = _lang_for(update.effective_chat.id)
            query = update.callback_query
            rows = list_telegram_sessions(limit=50)
            if idx < 0 or idx >= len(rows):
                await _safe_edit(query, "\u26A0\uFE0F Сессия устарела.", reply_markup=_session_list_keyboard(rows, lang=lang))
                return
            row = rows[idx]
            chat_id = update.effective_chat.id
            _pending_rename[chat_id] = row.session_id
            prompt = (f"\u270F\uFE0F Enter a new title for «{row.title}»:"
                      if lang == "en" else f"\u270F\uFE0F Введите новое название для «{row.title}»:")
            placeholder = "New title" if lang == "en" else "Новое название"
            await update.effective_chat.send_message(
                prompt, reply_markup=ForceReply(selective=True, input_field_placeholder=placeholder),
            )

        async def on_rename_reply(update: Update, context):
            from telegram.ext import ApplicationHandlerStop
            from .sessions import rename_session
            chat_id = update.effective_chat.id
            if chat_id not in _pending_rename:
                return  # not a rename reply — not ours, let it fall through
            if not is_authorized(_user_id(update)):
                return  # fail closed; don't consume someone else's pending state
            lang = _lang_for(chat_id)
            session_id = _pending_rename.pop(chat_id)
            new_title = (update.effective_message.text or "").strip()
            if not new_title:
                empty_msg = "\u26A0\uFE0F Title cannot be empty." if lang == "en" else "\u26A0\uFE0F Название не может быть пустым."
                await update.effective_message.reply_text(empty_msg)
                # STOP here too: this text answered our ForceReply prompt, it
                # must never also reach core's catch-all as ordinary chat input.
                raise ApplicationHandlerStop
            ok = rename_session(session_id, new_title)
            if ok:
                done = f"\u2705 Renamed: «{new_title}»" if lang == "en" else f"\u2705 Переименовано: «{new_title}»"
                await update.effective_message.reply_text(done, reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
            else:
                fail = "\u26A0\uFE0F Rename failed." if lang == "en" else "\u26A0\uFE0F Не удалось переименовать."
                await update.effective_message.reply_text(fail)
            # CRITICAL: without this, PTB still runs group=0 handlers (core's
            # catch-all text handler) on the SAME update — the rename reply
            # text would also be dispatched as if the user had typed it as a
            # normal chat message (visible symptom: it looked exactly like
            # typing "/title <text>" straight into the agent). Raising here
            # is the only way to stop cross-group dispatch in PTB.
            raise ApplicationHandlerStop

        async def on_lang_toggle(update: Update):
            new_lang = _toggle_lang(update.effective_chat.id)
            await _render_root(update, edit=True)
            return new_lang

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
                await query.answer(text="Нет доступа / No access", show_alert=True)
                return
            try:
                await query.answer()
            except Exception:
                pass  # устаревший/дважды отвеченный callback — не фатально (ТЗ §7)

            lang = _lang_for(update.effective_chat.id)
            if route.kind == "root":
                await _render_root(update, edit=True)
            elif route.kind == "lang_toggle":
                await on_lang_toggle(update)
            elif route.kind == "screen":
                if route.screen not in SCREEN_TITLES:
                    await _safe_edit(query, "\u26A0\uFE0F Экран устарел.", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
                    return
                await _render_screen(update, route.screen, edit=True)
            elif route.kind == "cmdlist":
                if route.screen not in SCREEN_TITLES:
                    await _safe_edit(query, "\u26A0\uFE0F Экран устарел.", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang))
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
            elif route.kind == "session_card":
                await _render_session_card(update, route.page)
            elif route.kind == "session_delete":
                await _render_session_delete(update, route.page)
            elif route.kind == "session_delete_confirm":
                await _render_session_delete_confirm(update, route.page)
            elif route.kind == "session_rename":
                await _render_session_rename_prompt(update, route.page)

        async def on_cancel_text(update: Update, context):
            """Перехватывает кнопку CANCEL_TEXT до того, как она дойдёт до LLM как
            обычное сообщение (тот же hoisting-механизм, что и у CallbackQueryHandler)."""
            from telegram.ext import ApplicationHandlerStop
            lang = _lang_for(update.effective_chat.id)
            await update.effective_message.reply_text(
                "Отменено. Ничего не выполнено.", reply_markup=root_keyboard(inline_mode=inline_mode, lang=lang),
            )
            raise ApplicationHandlerStop  # same cross-group leak this fixes for on_rename_reply

        native.add_handler(CommandHandler("menu", cmd_menu))
        native.add_handler(CallbackQueryHandler(on_callback, pattern="^qr:"))
        native.add_handler(TgMessageHandler(filters.Regex(f"^{CANCEL_TEXT}$"), on_cancel_text))
        # Reply to a ForceReply rename prompt (group=-1-equivalent: registered
        # before the Regex handler so a "^{CANCEL_TEXT}$" collision is impossible
        # — the rename text can never equal CANCEL_TEXT since they're disjoint
        # UI flows). on_rename_reply no-ops (falls through) when chat_id isn't
        # in _pending_rename, so it never swallows ordinary chat text.
        native.add_handler(TgMessageHandler(filters.TEXT & ~filters.COMMAND, on_rename_reply), group=-1)
        logger.info("hermes-telegram-control: /menu wired (navigation+execution split, i18n ru/en)")

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
