"""Render каждый экран как (текст, inline-клавиатура). Все кнопки здесь —
НАВИГАЦИЯ ТОЛЬКО (ТЗ §1.12): переключают callback_data на другой MenuRoute,
никогда не отправляют команду сами (кроме commands_inline_keyboard/execute —
см. flows/direct_execute.py и __init__.py's inline_mode branch).
"""
from __future__ import annotations

from ..registry.commands import ROOT_GRID, SCREEN_TITLES, commands_for_screen
from ..navigation.routes import MenuRoute, encode

_ROWS_PER_PAGE_SESSIONS = 8
_GRID_COLUMNS = 3  # ТЗ follow-up: compact long lists into a 3-column grid.


def _button(label: str, route: MenuRoute):
    from telegram import InlineKeyboardButton
    return InlineKeyboardButton(label, callback_data=encode(route))


def _grid(buttons, columns: int = _GRID_COLUMNS):
    """Chunk a flat button list into rows of *columns* each (last row may be shorter)."""
    rows = []
    for i in range(0, len(buttons), columns):
        rows.append(buttons[i:i + columns])
    return rows


def root_text(session_title: str | None, model_hint: str | None) -> str:
    lines = ["\U0001F916 *HERMES \u00b7 Управление*", ""]
    lines.append(f"Сессия: {session_title or '_без названия_'}")
    if model_hint:
        lines.append(f"Модель: {model_hint}")
    lines.append("")
    lines.append("Выберите раздел:")
    return "\n".join(lines)


def root_keyboard(*, inline_mode: bool = False):
    from telegram import InlineKeyboardMarkup

    target_kind = "cmdlist" if inline_mode else "screen"
    buttons = []
    for screen_id in ROOT_GRID:
        emoji, title = SCREEN_TITLES[screen_id]
        buttons.append(_button(f"{emoji} {title}", MenuRoute(kind=target_kind, screen=screen_id)))
    return InlineKeyboardMarkup(_grid(buttons))


def screen_text(screen_id: str) -> str:
    emoji, title = SCREEN_TITLES[screen_id]
    cmds = commands_for_screen(screen_id)
    lines = [f"{emoji} *{title}*", ""]
    for c in cmds:
        suffix = " \u2699" if c.needs_argument else ""
        lines.append(f"\u2022 {c.label}{suffix}")
    lines.append("")
    lines.append("Нажмите «Показать кнопки команд», чтобы отправить одну из них одним тапом.")
    return "\n".join(lines)


def screen_keyboard(screen_id: str):
    """Classic (non-inline-execute) mode only: bridge screen before showing
    the reply-keyboard command buttons (flows/execute.py)."""
    from telegram import InlineKeyboardMarkup

    rows = [
        [_button("\u25B6\uFE0F Показать кнопки команд", MenuRoute(kind="cmdlist", screen=screen_id))],
        [_button("\u2B05\uFE0F Назад", MenuRoute(kind="root"))],
        [_button("\U0001F3E0 Главная", MenuRoute(kind="root"))],
    ]
    return InlineKeyboardMarkup(rows)


def cmdlist_back_keyboard(screen_id: str, confirm_specs=None):
    """Inline nav + "Подтвердить" rows for destructive commands (ТЗ §4, §7):
    those never get a direct reply-keyboard send, only this inline gate
    that opens the Да/Отмена confirm screen."""
    from telegram import InlineKeyboardMarkup

    rows = []
    for spec in confirm_specs or []:
        rows.append([_button(f"\u26A0\uFE0F Подтвердить: {spec.label}",
                              MenuRoute(kind="confirm", command=spec.name))])
    rows.append([_button("\u2B05\uFE0F Назад к разделу", MenuRoute(kind="screen", screen=screen_id))])
    rows.append([_button("\U0001F3E0 Главная", MenuRoute(kind="root"))])
    return InlineKeyboardMarkup(rows)


def commands_inline_keyboard(screen_id: str):
    """All-inline command list (inline-execute mode, flows/direct_execute.py):
    safe commands become direct "execute" buttons in a compact 3-column
    grid; destructive ones still gate through "confirm" and get their own
    full-width row (longer label, needs the room, and stands out as risky)."""
    from telegram import InlineKeyboardMarkup

    specs = commands_for_screen(screen_id)
    safe_buttons = []
    risky_rows = []
    for c in specs:
        if c.destructive or c.confirm:
            risky_rows.append([_button(f"\u26A0\uFE0F {c.label}", MenuRoute(kind="confirm", command=c.name))])
        else:
            safe_buttons.append(_button(c.label, MenuRoute(kind="execute", command=c.name)))
    rows = _grid(safe_buttons) + risky_rows
    rows.append([_button("\u2B05\uFE0F Назад", MenuRoute(kind="root")),
                 _button("\U0001F3E0 Главная", MenuRoute(kind="root"))])
    return InlineKeyboardMarkup(rows)
