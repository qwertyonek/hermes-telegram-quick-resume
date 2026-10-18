"""Render каждый экран как (текст, inline-клавиатура). Все кнопки здесь —
НАВИГАЦИЯ ТОЛЬКО (ТЗ §1.12): переключают callback_data на другой MenuRoute,
никогда не отправляют команду сами (кроме commands_inline_keyboard/execute —
см. flows/direct_execute.py и __init__.py's inline_mode branch).

i18n: every render function takes ``lang`` ("ru" | "en"); CommandSpec.label_for
and registry.commands.screen_title_for resolve the actual string. The per-chat
language choice is read/written in __init__.py via ctx.state (PluginState).
"""
from __future__ import annotations

from ..registry.commands import ROOT_GRID, SCREEN_SESSIONS, commands_for_screen, screen_title_for
from ..navigation.routes import MenuRoute, encode

_ROWS_PER_PAGE_SESSIONS = 8
_GRID_COLUMNS = 3  # ТЗ follow-up: compact long lists into a 3-column grid.

_STRINGS = {
    "ru": {
        "root_header": "\U0001F916 *HERMES \u00b7 Управление*",
        "root_session": "Сессия",
        "root_model": "Модель",
        "root_choose": "Выберите раздел:",
        "root_untitled": "_без названия_",
        "show_cmd_buttons": "\u25B6\uFE0F Показать кнопки команд",
        "back": "\u2B05\uFE0F Назад",
        "home": "\U0001F3E0 Главная",
        "confirm_prefix": "\u26A0\uFE0F Подтвердить",
        "back_to_section": "\u2B05\uFE0F Назад к разделу",
        "tap_a_command": "Нажмите «Показать кнопки команд», чтобы отправить одну из них одним тапом.",
        "sessions_list_btn": "\U0001F4DA Список сессий",
        "sessions_list_hint": "\u2022 \U0001F4DA Список сессий (карточки, без команд)",
        "lang_toggle": "\U0001F310 EN",
    },
    "en": {
        "root_header": "\U0001F916 *HERMES \u00b7 Control Panel*",
        "root_session": "Session",
        "root_model": "Model",
        "root_choose": "Choose a section:",
        "root_untitled": "_untitled_",
        "show_cmd_buttons": "\u25B6\uFE0F Show command buttons",
        "back": "\u2B05\uFE0F Back",
        "home": "\U0001F3E0 Home",
        "confirm_prefix": "\u26A0\uFE0F Confirm",
        "back_to_section": "\u2B05\uFE0F Back to section",
        "tap_a_command": "Tap «Show command buttons» to send one with a single tap.",
        "sessions_list_btn": "\U0001F4DA Session list",
        "sessions_list_hint": "\u2022 \U0001F4DA Session list (cards, not a command)",
        "lang_toggle": "\U0001F310 RU",
    },
}


def _s(lang: str, key: str) -> str:
    return _STRINGS.get(lang, _STRINGS["ru"])[key]


def _button(label: str, route: MenuRoute):
    from telegram import InlineKeyboardButton
    return InlineKeyboardButton(label, callback_data=encode(route))


def _grid(buttons, columns: int = _GRID_COLUMNS):
    """Chunk a flat button list into rows of *columns* each (last row may be shorter)."""
    rows = []
    for i in range(0, len(buttons), columns):
        rows.append(buttons[i:i + columns])
    return rows


def root_text(session_title: str | None, model_hint: str | None, *, lang: str = "ru") -> str:
    lines = [_s(lang, "root_header"), ""]
    lines.append(f"{_s(lang, 'root_session')}: {session_title or _s(lang, 'root_untitled')}")
    if model_hint:
        lines.append(f"{_s(lang, 'root_model')}: {model_hint}")
    lines.append("")
    lines.append(_s(lang, "root_choose"))
    return "\n".join(lines)


def root_keyboard(*, inline_mode: bool = False, lang: str = "ru"):
    """Root grid (3-column) plus a trailing row with a language toggle on
    the far right, as requested — tapping it flips the WHOLE menu's language
    for this chat (persisted via ctx.state, see __init__.py's _toggle_lang)."""
    from telegram import InlineKeyboardMarkup

    target_kind = "cmdlist" if inline_mode else "screen"
    buttons = []
    for screen_id in ROOT_GRID:
        emoji, title = screen_title_for(screen_id, lang)
        buttons.append(_button(f"{emoji} {title}", MenuRoute(kind=target_kind, screen=screen_id)))
    rows = _grid(buttons)
    rows.append([_button(_s(lang, "lang_toggle"), MenuRoute(kind="lang_toggle"))])
    return InlineKeyboardMarkup(rows)


def screen_text(screen_id: str, *, lang: str = "ru") -> str:
    emoji, title = screen_title_for(screen_id, lang)
    cmds = commands_for_screen(screen_id)
    lines = [f"{emoji} *{title}*", ""]
    if screen_id == SCREEN_SESSIONS:
        lines.append(_s(lang, "sessions_list_hint"))
    for c in cmds:
        suffix = " \u2699" if c.needs_argument else ""
        lines.append(f"\u2022 {c.label_for(lang)}{suffix}")
    lines.append("")
    lines.append(_s(lang, "tap_a_command"))
    return "\n".join(lines)


def screen_keyboard(screen_id: str, *, lang: str = "ru"):
    """Classic (non-inline-execute) mode only: bridge screen before showing
    the reply-keyboard command buttons (flows/execute.py)."""
    from telegram import InlineKeyboardMarkup

    rows = []
    if screen_id == SCREEN_SESSIONS:
        # "Список сессий"/"Session list" is NOT a registry command — it opens
        # the card UI (resume_list route) directly, same in classic and inline mode.
        rows.append([_button(_s(lang, "sessions_list_btn"), MenuRoute(kind="resume_list", page=0))])
    rows.append([_button(_s(lang, "show_cmd_buttons"), MenuRoute(kind="cmdlist", screen=screen_id))])
    rows.append([_button(_s(lang, "back"), MenuRoute(kind="root"))])
    rows.append([_button(_s(lang, "home"), MenuRoute(kind="root"))])
    return InlineKeyboardMarkup(rows)


def cmdlist_back_keyboard(screen_id: str, confirm_specs=None, arg_specs=None, *, lang: str = "ru"):
    """Inline nav + "Подтвердить"/"Confirm" rows for destructive commands
    (ТЗ §4, §7), plus argument-prompt rows for needs_argument commands
    (fixes: a bare reply-keyboard tap used to send e.g. "/title" with no
    argument at all) — both gate through inline buttons, never a direct
    reply-keyboard send."""
    from telegram import InlineKeyboardMarkup

    rows = []
    for spec in confirm_specs or []:
        rows.append([_button(f"{_s(lang, 'confirm_prefix')}: {spec.label_for(lang)}",
                              MenuRoute(kind="confirm", command=spec.name))])
    for spec in arg_specs or []:
        rows.append([_button(spec.label_for(lang), MenuRoute(kind="arg_prompt", command=spec.name))])
    rows.append([_button(_s(lang, "back_to_section"), MenuRoute(kind="screen", screen=screen_id))])
    rows.append([_button(_s(lang, "home"), MenuRoute(kind="root"))])
    return InlineKeyboardMarkup(rows)


def commands_inline_keyboard(screen_id: str, *, lang: str = "ru"):
    """All-inline command list (inline-execute mode, flows/direct_execute.py):
    safe commands become direct "execute" buttons in a compact 3-column
    grid; destructive ones still gate through "confirm" and get their own
    full-width row (longer label, needs the room, and stands out as risky).
    "Список сессий"/"Session list" on the Sessions screen is special-cased:
    it is NOT a registry command (there's no slash command to execute) — it
    opens the session-card UI directly via the resume_list route."""
    from telegram import InlineKeyboardMarkup

    specs = commands_for_screen(screen_id)
    safe_buttons = []
    risky_rows = []
    if screen_id == SCREEN_SESSIONS:
        safe_buttons.append(_button(_s(lang, "sessions_list_btn"), MenuRoute(kind="resume_list", page=0)))
    for c in specs:
        if c.destructive or c.confirm:
            risky_rows.append([_button(f"\u26A0\uFE0F {c.label_for(lang)}", MenuRoute(kind="confirm", command=c.name))])
        elif c.needs_argument:
            # Needs a text argument (/title <name>, /bg <task>, ...) — can't be
            # a direct execute button (there's nothing to send yet). Opens a
            # ForceReply prompt instead (see __init__.py's _render_arg_prompt).
            safe_buttons.append(_button(c.label_for(lang), MenuRoute(kind="arg_prompt", command=c.name)))
        else:
            safe_buttons.append(_button(c.label_for(lang), MenuRoute(kind="execute", command=c.name)))
    rows = _grid(safe_buttons) + risky_rows
    rows.append([_button(_s(lang, "back"), MenuRoute(kind="root")),
                 _button(_s(lang, "home"), MenuRoute(kind="root"))])
    return InlineKeyboardMarkup(rows)
