"""Declarative command registry: single source of truth for every Hermes
slash command this plugin surfaces, which screen it lives on, whether it
needs an argument (so the UI can tell the user what to type instead of
pretending a bare tap is enough), and whether it should ask for
confirmation before the reply-keyboard button sends it.

This is the ``command -> screen -> handler -> arguments -> permissions ->
test`` matrix the spec (§3) asks for, as data — not scattered across
screen-rendering code. ``docs/menu-audit.md`` records per-command
verification status; this file only records what the UI needs to render
correctly.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandSpec:
    name: str                      # canonical command, no leading slash
    label: str                     # short Russian button label (with emoji)
    screen: str                    # which Screen id this command's button lives on
    needs_argument: bool = False   # bare tap only shows usage; UI should say so
    argument_hint: str = ""        # Russian hint shown before tap for needs_argument=True
    confirm: bool = False          # ask "Точно?" before the reply-keyboard send
    destructive: bool = False      # irreversible/costly — drives confirm wording
    test_status: str = "manual"   # "verified_live" | "verified_unit" | "manual" | "core_only"


# Screens — one entry per ТЗ §2.1-2.8 section, "root" is the home screen.
SCREEN_SESSIONS = "sessions"
SCREEN_RUN = "run"
SCREEN_MODEL = "model"
SCREEN_STATUS = "status"
SCREEN_AUTOMATION = "automation"
SCREEN_TOOLS = "tools"
SCREEN_SETTINGS = "settings"
SCREEN_SYSTEM = "system"

SCREEN_TITLES: dict[str, tuple[str, str]] = {
    SCREEN_SESSIONS: ("\U0001F4AC", "Сессии"),
    SCREEN_RUN: ("\u26A1", "Выполнение"),
    SCREEN_MODEL: ("\U0001F916", "Модель"),
    SCREEN_STATUS: ("\U0001F4CA", "Статус"),
    SCREEN_AUTOMATION: ("\U0001F3AF", "Автоматизация"),
    SCREEN_TOOLS: ("\U0001F6E0", "Инструменты"),
    SCREEN_SETTINGS: ("\u2699\uFE0F", "Настройки"),
    SCREEN_SYSTEM: ("\U0001F5A5", "Система"),
}

# Root screen's 2-per-row grid, in display order (ТЗ §2 root layout).
ROOT_GRID: list[str] = [
    SCREEN_SESSIONS, SCREEN_MODEL,
    SCREEN_RUN, SCREEN_STATUS,
    SCREEN_AUTOMATION, SCREEN_TOOLS,
    SCREEN_SETTINGS, SCREEN_SYSTEM,
]

COMMANDS: list[CommandSpec] = [
    # --- Сессии ---
    CommandSpec("new", "\u2728 Новая сессия", SCREEN_SESSIONS, test_status="verified_live"),
    CommandSpec("resume", "\u21bb Возобновить", SCREEN_SESSIONS, needs_argument=False,
                test_status="verified_live"),
    CommandSpec("sessions", "\U0001F4DA Список сессий", SCREEN_SESSIONS, test_status="manual"),
    CommandSpec("title", "\u270F\uFE0F Название", SCREEN_SESSIONS, needs_argument=True,
                argument_hint="Допишите название после команды, например: /title Мой проект",
                test_status="manual"),
    CommandSpec("branch", "\U0001F33F Ветка", SCREEN_SESSIONS, test_status="manual"),
    CommandSpec("topic", "\U0001F9F5 Топики", SCREEN_SESSIONS, test_status="manual"),
    CommandSpec("save", "\U0001F4BE Экспорт", SCREEN_SESSIONS, test_status="manual"),
    CommandSpec("compress", "\U0001F5DC Сжать контекст", SCREEN_SESSIONS, confirm=True,
                test_status="manual"),
    CommandSpec("rollback", "\u23EA Checkpoint'ы", SCREEN_SESSIONS, destructive=True,
                confirm=True, test_status="manual"),

    # --- Выполнение ---
    CommandSpec("stop", "\U0001F6D1 Остановить", SCREEN_RUN, confirm=True,
                test_status="manual"),
    CommandSpec("pause", "\u23F8 Пауза/Снять", SCREEN_RUN, test_status="manual"),
    CommandSpec("retry", "\U0001F501 Повторить", SCREEN_RUN, test_status="manual"),
    CommandSpec("undo", "\u21A9\uFE0F Отменить ход", SCREEN_RUN, destructive=True,
                confirm=True, test_status="manual"),
    CommandSpec("bg", "\U0001F680 Фоновая задача", SCREEN_RUN, needs_argument=True,
                argument_hint="Допишите задачу после команды, например: /bg проверь деплой",
                test_status="manual"),
    CommandSpec("btw", "\U0001F4AC Побочный вопрос", SCREEN_RUN, needs_argument=True,
                argument_hint="Допишите вопрос после команды, например: /btw а как там тест?",
                test_status="manual"),
    CommandSpec("agents", "\U0001F916 Агенты и задачи", SCREEN_RUN, test_status="manual"),
    CommandSpec("queue", "\U0001F4CB Очередь", SCREEN_RUN, test_status="manual"),
    CommandSpec("steer", "\U0001F3AE Направить", SCREEN_RUN, needs_argument=True,
                argument_hint="Допишите направление после команды, например: /steer используй другой подход",
                test_status="manual"),
    CommandSpec("approve", "\u2705 Подтвердить", SCREEN_RUN,
                test_status="core_only"),  # §3 of audit: no request-ID binding possible
    CommandSpec("deny", "\u274C Отклонить", SCREEN_RUN,
                test_status="core_only"),

    # --- Модель ---
    CommandSpec("model", "\U0001F916 Выбрать модель", SCREEN_MODEL, test_status="manual"),
    CommandSpec("personality", "\U0001F3AD Личность", SCREEN_MODEL, test_status="manual"),
    CommandSpec("reasoning", "\U0001F9E0 Размышление", SCREEN_MODEL, test_status="manual"),
    CommandSpec("fast", "\u26A1 Быстрый режим", SCREEN_MODEL, test_status="manual"),

    # --- Статус ---
    CommandSpec("status", "\U0001F4CA Обзор", SCREEN_STATUS, test_status="verified_live"),
    CommandSpec("context", "\U0001F9E0 Контекст", SCREEN_STATUS, test_status="manual"),
    CommandSpec("usage", "\U0001FA99 Токены/лимиты", SCREEN_STATUS, test_status="manual"),
    CommandSpec("quota", "\U0001F4C9 Квоты", SCREEN_STATUS, test_status="manual"),
    CommandSpec("egress", "\U0001F310 Egress", SCREEN_STATUS, test_status="manual"),
    CommandSpec("whoami", "\U0001F464 Права и профиль", SCREEN_STATUS, test_status="manual"),
    CommandSpec("profile", "\U0001F4C1 Профиль", SCREEN_STATUS, test_status="manual"),
    CommandSpec("diff", "\U0001F4DD Git diff", SCREEN_STATUS, test_status="manual"),
    CommandSpec("insights", "\U0001F4C8 Аналитика", SCREEN_STATUS, test_status="manual"),

    # --- Автоматизация ---
    CommandSpec("goal", "\U0001F3AF Цель", SCREEN_AUTOMATION, needs_argument=True,
                argument_hint="Допишите цель после команды, например: /goal следи за ценами",
                test_status="manual"),
    CommandSpec("subgoal", "\U0001F4CC Подцель", SCREEN_AUTOMATION, needs_argument=True,
                argument_hint="Допишите подцель после команды", test_status="manual"),
    CommandSpec("heartbeat", "\U0001F493 Heartbeat", SCREEN_AUTOMATION, test_status="manual"),
    CommandSpec("loop", "\U0001F504 Повторение", SCREEN_AUTOMATION, needs_argument=True,
                argument_hint="Допишите интервал и промпт после команды", test_status="manual"),
    CommandSpec("blueprint", "\U0001F4D0 Шаблоны", SCREEN_AUTOMATION, test_status="manual"),
    CommandSpec("suggestions", "\U0001F4A1 Предложения", SCREEN_AUTOMATION, test_status="manual"),
    CommandSpec("kanban", "\U0001F4CB Kanban", SCREEN_AUTOMATION, test_status="core_only"),
    CommandSpec("plan", "\U0001F5D2 План", SCREEN_AUTOMATION, needs_argument=True,
                argument_hint="Допишите задачу для плана после команды", test_status="manual"),
    CommandSpec("moa", "\U0001F465 Mixture of Agents", SCREEN_AUTOMATION, needs_argument=True,
                argument_hint="Допишите промпт после команды", test_status="manual"),

    # --- Инструменты ---
    CommandSpec("learn", "\U0001F393 Обучить скиллу", SCREEN_TOOLS, needs_argument=True,
                argument_hint="Опишите, чему учиться, после команды", test_status="manual"),
    CommandSpec("bundles", "\U0001F4E6 Бандлы", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("reload_skills", "\U0001F504 Обновить скиллы", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("reload_mcp", "\U0001F50C Перезагрузить MCP", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("curator", "\U0001F9F9 Куратор", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("memory", "\U0001F4DD Память", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("commands", "\U0001F4D6 Все команды", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("help", "\u2753 Справка", SCREEN_TOOLS, test_status="verified_live"),
    CommandSpec("init", "\U0001F4C4 AGENTS.md", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("refine", "\u2728 Извлечь уроки", SCREEN_TOOLS, test_status="manual"),
    CommandSpec("review", "\U0001F50D Ревью субагентом", SCREEN_TOOLS, test_status="manual"),

    # --- Настройки ---
    CommandSpec("approvals", "\U0001F6E1 Подтверждения", SCREEN_SETTINGS, test_status="verified_live"),
    CommandSpec("yolo", "\U0001F947 YOLO режим", SCREEN_SETTINGS, confirm=True,
                destructive=True, test_status="manual"),
    CommandSpec("voice", "\U0001F3A4 Голос", SCREEN_SETTINGS, test_status="manual"),
    CommandSpec("footer", "\U0001F4CB Подпись", SCREEN_SETTINGS, test_status="manual"),
    CommandSpec("busy", "\u231B Пока занят", SCREEN_SETTINGS, test_status="manual"),
    CommandSpec("codex_runtime", "\U0001F527 Codex runtime", SCREEN_SETTINGS, test_status="manual"),

    # --- Система ---
    CommandSpec("version", "\U0001F3F7 Версия", SCREEN_SYSTEM, test_status="verified_live"),
    CommandSpec("restart", "\U0001F504 Перезапуск", SCREEN_SYSTEM, destructive=True,
                confirm=True, test_status="manual"),
    CommandSpec("update", "\u2B06\uFE0F Обновление", SCREEN_SYSTEM, destructive=True,
                confirm=True, test_status="manual"),
    CommandSpec("debug", "\U0001F41B Диагностика", SCREEN_SYSTEM, test_status="manual"),
    CommandSpec("platform", "\U0001F310 Платформы", SCREEN_SYSTEM, confirm=True,
                test_status="manual"),
    CommandSpec("topup", "\U0001F4B3 Баланс Nous", SCREEN_SYSTEM, test_status="manual"),
    CommandSpec("login", "\U0001F511 Вход Nous", SCREEN_SYSTEM, test_status="manual"),
    CommandSpec("sethome", "\U0001F3E0 Домашний чат", SCREEN_SYSTEM, test_status="manual"),
]

BY_NAME: dict[str, CommandSpec] = {c.name: c for c in COMMANDS}


def commands_for_screen(screen: str) -> list[CommandSpec]:
    return [c for c in COMMANDS if c.screen == screen]


def coverage_report() -> dict[str, int]:
    """Counts by test_status, for the audit/acceptance report."""
    out: dict[str, int] = {}
    for c in COMMANDS:
        out[c.test_status] = out.get(c.test_status, 0) + 1
    return out
