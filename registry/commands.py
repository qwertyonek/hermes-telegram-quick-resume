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
    label_en: str = ""              # English button label; falls back to `label` if empty
    needs_argument: bool = False   # bare tap only shows usage; UI should say so
    argument_hint: str = ""        # Russian hint shown before tap for needs_argument=True
    argument_hint_en: str = ""     # English hint; falls back to argument_hint if empty
    confirm: bool = False          # ask "Точно?" before the reply-keyboard send
    destructive: bool = False      # irreversible/costly — drives confirm wording
    test_status: str = "manual"   # "verified_live" | "verified_unit" | "manual" | "core_only"

    def label_for(self, lang: str) -> str:
        return (self.label_en or self.label) if lang == "en" else self.label

    def argument_hint_for(self, lang: str) -> str:
        if lang == "en":
            return self.argument_hint_en or self.argument_hint
        return self.argument_hint


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

SCREEN_TITLES_EN: dict[str, tuple[str, str]] = {
    SCREEN_SESSIONS: ("\U0001F4AC", "Sessions"),
    SCREEN_RUN: ("\u26A1", "Run"),
    SCREEN_MODEL: ("\U0001F916", "Model"),
    SCREEN_STATUS: ("\U0001F4CA", "Status"),
    SCREEN_AUTOMATION: ("\U0001F3AF", "Automation"),
    SCREEN_TOOLS: ("\U0001F6E0", "Tools"),
    SCREEN_SETTINGS: ("\u2699\uFE0F", "Settings"),
    SCREEN_SYSTEM: ("\U0001F5A5", "System"),
}


def screen_title_for(screen: str, lang: str) -> tuple[str, str]:
    table = SCREEN_TITLES_EN if lang == "en" else SCREEN_TITLES
    return table[screen]

# Root screen's 2-per-row grid, in display order (ТЗ §2 root layout).
ROOT_GRID: list[str] = [
    SCREEN_SESSIONS, SCREEN_MODEL,
    SCREEN_RUN, SCREEN_STATUS,
    SCREEN_AUTOMATION, SCREEN_TOOLS,
    SCREEN_SETTINGS, SCREEN_SYSTEM,
]

COMMANDS: list[CommandSpec] = [
    # --- Сессии ---
    CommandSpec("new", "\u2728 Новая сессия", SCREEN_SESSIONS, label_en="\u2728 New session", test_status="verified_live"),
    CommandSpec("title", "\u270F\uFE0F Название", SCREEN_SESSIONS, label_en="\u270F\uFE0F Title", needs_argument=True,
                argument_hint="Допишите название после команды, например: /title Мой проект",
                argument_hint_en="Add the title after the command, e.g.: /title My Project",
                test_status="manual"),
    CommandSpec("branch", "\U0001F33F Ветка", SCREEN_SESSIONS, label_en="\U0001F33F Branch", test_status="manual"),
    CommandSpec("topic", "\U0001F9F5 Топики", SCREEN_SESSIONS, label_en="\U0001F9F5 Topics", test_status="manual"),
    CommandSpec("save", "\U0001F4BE Экспорт", SCREEN_SESSIONS, label_en="\U0001F4BE Export", test_status="manual"),
    CommandSpec("compress", "\U0001F5DC Сжать контекст", SCREEN_SESSIONS, label_en="\U0001F5DC Compress context",
                confirm=True, test_status="manual"),
    CommandSpec("rollback", "\u23EA Checkpoint'ы", SCREEN_SESSIONS, label_en="\u23EA Checkpoints", destructive=True,
                confirm=True, test_status="manual"),

    # --- Выполнение ---
    CommandSpec("stop", "\U0001F6D1 Остановить", SCREEN_RUN, label_en="\U0001F6D1 Stop", confirm=True,
                test_status="manual"),
    CommandSpec("pause", "\u23F8 Пауза/Снять", SCREEN_RUN, label_en="\u23F8 Pause/Resume", test_status="manual"),
    CommandSpec("retry", "\U0001F501 Повторить", SCREEN_RUN, label_en="\U0001F501 Retry", test_status="manual"),
    CommandSpec("undo", "\u21A9\uFE0F Отменить ход", SCREEN_RUN, label_en="\u21A9\uFE0F Undo turn", destructive=True,
                confirm=True, test_status="manual"),
    CommandSpec("bg", "\U0001F680 Фоновая задача", SCREEN_RUN, label_en="\U0001F680 Background task", needs_argument=True,
                argument_hint="Допишите задачу после команды, например: /bg проверь деплой",
                argument_hint_en="Add the task after the command, e.g.: /bg check the deploy",
                test_status="manual"),
    CommandSpec("btw", "\U0001F4AC Побочный вопрос", SCREEN_RUN, label_en="\U0001F4AC Side question", needs_argument=True,
                argument_hint="Допишите вопрос после команды, например: /btw а как там тест?",
                argument_hint_en="Add the question after the command, e.g.: /btw how's the test going?",
                test_status="manual"),
    CommandSpec("agents", "\U0001F916 Агенты и задачи", SCREEN_RUN, label_en="\U0001F916 Agents & tasks", test_status="manual"),
    CommandSpec("queue", "\U0001F4CB Очередь", SCREEN_RUN, label_en="\U0001F4CB Queue", test_status="manual"),
    CommandSpec("steer", "\U0001F3AE Направить", SCREEN_RUN, label_en="\U0001F3AE Steer", needs_argument=True,
                argument_hint="Допишите направление после команды, например: /steer используй другой подход",
                argument_hint_en="Add the direction after the command, e.g.: /steer try a different approach",
                test_status="manual"),
    CommandSpec("approve", "\u2705 Подтвердить", SCREEN_RUN, label_en="\u2705 Approve",
                test_status="core_only"),  # §3 of audit: no request-ID binding possible
    CommandSpec("deny", "\u274C Отклонить", SCREEN_RUN, label_en="\u274C Deny",
                test_status="core_only"),

    # --- Модель ---
    CommandSpec("model", "\U0001F916 Выбрать модель", SCREEN_MODEL, label_en="\U0001F916 Choose model", test_status="manual"),
    CommandSpec("personality", "\U0001F3AD Личность", SCREEN_MODEL, label_en="\U0001F3AD Personality", test_status="manual"),
    CommandSpec("reasoning", "\U0001F9E0 Размышление", SCREEN_MODEL, label_en="\U0001F9E0 Reasoning", test_status="manual"),
    CommandSpec("fast", "\u26A1 Быстрый режим", SCREEN_MODEL, label_en="\u26A1 Fast mode", test_status="manual"),

    # --- Статус ---
    CommandSpec("status", "\U0001F4CA Обзор", SCREEN_STATUS, label_en="\U0001F4CA Overview", test_status="verified_live"),
    CommandSpec("context", "\U0001F9E0 Контекст", SCREEN_STATUS, label_en="\U0001F9E0 Context", test_status="manual"),
    CommandSpec("usage", "\U0001FA99 Токены/лимиты", SCREEN_STATUS, label_en="\U0001FA99 Tokens/limits", test_status="manual"),
    CommandSpec("quota", "\U0001F4C9 Квоты", SCREEN_STATUS, label_en="\U0001F4C9 Quotas", test_status="manual"),
    CommandSpec("egress", "\U0001F310 Egress", SCREEN_STATUS, label_en="\U0001F310 Egress", test_status="manual"),
    CommandSpec("whoami", "\U0001F464 Права и профиль", SCREEN_STATUS, label_en="\U0001F464 Rights & profile", test_status="manual"),
    CommandSpec("profile", "\U0001F4C1 Профиль", SCREEN_STATUS, label_en="\U0001F4C1 Profile", test_status="manual"),
    CommandSpec("diff", "\U0001F4DD Git diff", SCREEN_STATUS, label_en="\U0001F4DD Git diff", test_status="manual"),
    CommandSpec("insights", "\U0001F4C8 Аналитика", SCREEN_STATUS, label_en="\U0001F4C8 Insights", test_status="manual"),

    # --- Автоматизация ---
    CommandSpec("goal", "\U0001F3AF Цель", SCREEN_AUTOMATION, label_en="\U0001F3AF Goal", needs_argument=True,
                argument_hint="Допишите цель после команды, например: /goal следи за ценами",
                argument_hint_en="Add the goal after the command, e.g.: /goal watch the prices",
                test_status="manual"),
    CommandSpec("subgoal", "\U0001F4CC Подцель", SCREEN_AUTOMATION, label_en="\U0001F4CC Subgoal", needs_argument=True,
                argument_hint="Допишите подцель после команды", argument_hint_en="Add the subgoal after the command",
                test_status="manual"),
    CommandSpec("heartbeat", "\U0001F493 Heartbeat", SCREEN_AUTOMATION, label_en="\U0001F493 Heartbeat", test_status="manual"),
    CommandSpec("loop", "\U0001F504 Повторение", SCREEN_AUTOMATION, label_en="\U0001F504 Loop", needs_argument=True,
                argument_hint="Допишите интервал и промпт после команды",
                argument_hint_en="Add the interval and prompt after the command", test_status="manual"),
    CommandSpec("blueprint", "\U0001F4D0 Шаблоны", SCREEN_AUTOMATION, label_en="\U0001F4D0 Blueprints", test_status="manual"),
    CommandSpec("suggestions", "\U0001F4A1 Предложения", SCREEN_AUTOMATION, label_en="\U0001F4A1 Suggestions", test_status="manual"),
    CommandSpec("kanban", "\U0001F4CB Kanban", SCREEN_AUTOMATION, label_en="\U0001F4CB Kanban", test_status="core_only"),
    CommandSpec("plan", "\U0001F5D2 План", SCREEN_AUTOMATION, label_en="\U0001F5D2 Plan", needs_argument=True,
                argument_hint="Допишите задачу для плана после команды",
                argument_hint_en="Add the plan task after the command", test_status="manual"),
    CommandSpec("moa", "\U0001F465 Mixture of Agents", SCREEN_AUTOMATION, label_en="\U0001F465 Mixture of Agents", needs_argument=True,
                argument_hint="Допишите промпт после команды", argument_hint_en="Add the prompt after the command",
                test_status="manual"),

    # --- Инструменты ---
    CommandSpec("learn", "\U0001F393 Обучить скиллу", SCREEN_TOOLS, label_en="\U0001F393 Learn a skill", needs_argument=True,
                argument_hint="Опишите, чему учиться, после команды",
                argument_hint_en="Describe what to learn after the command", test_status="manual"),
    CommandSpec("bundles", "\U0001F4E6 Бандлы", SCREEN_TOOLS, label_en="\U0001F4E6 Bundles", test_status="manual"),
    CommandSpec("reload_skills", "\U0001F504 Обновить скиллы", SCREEN_TOOLS, label_en="\U0001F504 Reload skills", test_status="manual"),
    CommandSpec("reload_mcp", "\U0001F50C Перезагрузить MCP", SCREEN_TOOLS, label_en="\U0001F50C Reload MCP", test_status="manual"),
    CommandSpec("curator", "\U0001F9F9 Куратор", SCREEN_TOOLS, label_en="\U0001F9F9 Curator", test_status="manual"),
    CommandSpec("memory", "\U0001F4DD Память", SCREEN_TOOLS, label_en="\U0001F4DD Memory", test_status="manual"),
    CommandSpec("commands", "\U0001F4D6 Все команды", SCREEN_TOOLS, label_en="\U0001F4D6 All commands", test_status="manual"),
    CommandSpec("help", "\u2753 Справка", SCREEN_TOOLS, label_en="\u2753 Help", test_status="verified_live"),
    CommandSpec("init", "\U0001F4C4 AGENTS.md", SCREEN_TOOLS, label_en="\U0001F4C4 AGENTS.md", test_status="manual"),
    CommandSpec("refine", "\u2728 Извлечь уроки", SCREEN_TOOLS, label_en="\u2728 Extract lessons", test_status="manual"),
    CommandSpec("review", "\U0001F50D Ревью субагентом", SCREEN_TOOLS, label_en="\U0001F50D Subagent review", test_status="manual"),

    # --- Настройки ---
    CommandSpec("approvals", "\U0001F6E1 Подтверждения", SCREEN_SETTINGS, label_en="\U0001F6E1 Approvals", test_status="verified_live"),
    CommandSpec("yolo", "\U0001F947 YOLO режим", SCREEN_SETTINGS, label_en="\U0001F947 YOLO mode", confirm=True,
                destructive=True, test_status="manual"),
    CommandSpec("voice", "\U0001F3A4 Голос", SCREEN_SETTINGS, label_en="\U0001F3A4 Voice", test_status="manual"),
    CommandSpec("footer", "\U0001F4CB Подпись", SCREEN_SETTINGS, label_en="\U0001F4CB Footer", test_status="manual"),
    CommandSpec("busy", "\u231B Пока занят", SCREEN_SETTINGS, label_en="\u231B While busy", test_status="manual"),
    CommandSpec("codex_runtime", "\U0001F527 Codex runtime", SCREEN_SETTINGS, label_en="\U0001F527 Codex runtime", test_status="manual"),

    # --- Система ---
    CommandSpec("version", "\U0001F3F7 Версия", SCREEN_SYSTEM, label_en="\U0001F3F7 Version", test_status="verified_live"),
    CommandSpec("restart", "\U0001F504 Перезапуск", SCREEN_SYSTEM, label_en="\U0001F504 Restart", destructive=True,
                confirm=True, test_status="manual"),
    CommandSpec("update", "\u2B06\uFE0F Обновление", SCREEN_SYSTEM, label_en="\u2B06\uFE0F Update", destructive=True,
                confirm=True, test_status="manual"),
    CommandSpec("debug", "\U0001F41B Диагностика", SCREEN_SYSTEM, label_en="\U0001F41B Diagnostics", test_status="manual"),
    CommandSpec("platform", "\U0001F310 Платформы", SCREEN_SYSTEM, label_en="\U0001F310 Platforms", confirm=True,
                test_status="manual"),
    CommandSpec("topup", "\U0001F4B3 Баланс Nous", SCREEN_SYSTEM, label_en="\U0001F4B3 Nous balance", test_status="manual"),
    CommandSpec("login", "\U0001F511 Вход Nous", SCREEN_SYSTEM, label_en="\U0001F511 Nous login", test_status="manual"),
    CommandSpec("sethome", "\U0001F3E0 Домашний чат", SCREEN_SYSTEM, label_en="\U0001F3E0 Home chat", test_status="manual"),
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
