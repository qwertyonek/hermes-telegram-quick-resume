"""Render каждый экран как (текст, inline-клавиатура). Все кнопки здесь —
НАВИГАЦИЯ ТОЛЬКО (ТЗ §1.12): переключают callback_data на другой MenuRoute,
никогда не отправляют команду сами. Реальное выполнение — отдельная
ReplyKeyboardMarkup, построенная в flows/execute.py.
"""
from __future__ import annotations

from ..registry.commands import ROOT_GRID, SCREEN_TITLES, commands_for_screen
from ..navigation.routes import MenuRoute, encode

_ROWS_PER_PAGE_SESSIONS = 8


def _button(label: str, route: MenuRoute):
    from telegram import InlineKeyboardButton
    return InlineKeyboardButton(label, callback_data=encode(route))


def root_text(session_title: str | None, model_hint: str | None) -> str:
    lines = ["\U0001F916 *HERMES \u00b7 Управление*", ""]
    lines.append(f"Сессия: {session_title or '_без названия_'}")
    if model_hint:
        lines.append(f"Модель: {model_hint}")
    lines.append("")
    lines.append("Выберите раздел:")
    return "\n".join(lines)


def root_keyboard():
    from telegram import InlineKeyboardMarkup

    rows = []
    row = []
    for screen_id in ROOT_GRID:
        emoji, title = SCREEN_TITLES[screen_id]
        row.append(_button(f"{emoji} {title}", MenuRoute(kind="screen", screen=screen_id)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


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
    """All-inline command list (used only when inline-execute is enabled, see
    flows/direct_execute.py): safe commands become direct "execute" buttons,
    destructive ones still gate through "confirm". No reply-keyboard at all."""
    from telegram import InlineKeyboardMarkup

    specs = commands_for_screen(screen_id)
    rows = []
    for c in specs:
        if c.destructive or c.confirm:
            rows.append([_button(f"\u26A0\uFE0F {c.label}", MenuRoute(kind="confirm", command=c.name))])
        else:
            rows.append([_button(c.label, MenuRoute(kind="execute", command=c.name))])
    rows.append([_button("\u2B05\uFE0F Назад к разделу", MenuRoute(kind="screen", screen=screen_id))])
    rows.append([_button("\U0001F3E0 Главная", MenuRoute(kind="root"))])
    return InlineKeyboardMarkup(rows)
