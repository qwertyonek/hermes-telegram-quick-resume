"""Static menu structure: groups Hermes's ~68 gateway slash commands into a
small set of categories for inline-button browsing. Pure data — no imports
from hermes_cli/gateway internals, so this file never breaks on a core update.
"""
from __future__ import annotations

# Each category: (emoji, title, [(command, short_label), ...])
# Only the most useful commands per category are surfaced as buttons; the rest
# stay reachable by typing them (Telegram's own /commands menu lists everything).
CATEGORIES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("\U0001F4C2", "Sessions", [
        ("new", "\u2728 New session"),
        ("resume", "\u21bb Resume (list)"),
        ("sessions", "\U0001F50D Browse sessions"),
        ("title", "\U0001F4DD Set title"),
        ("branch", "\U0001F500 Branch session"),
        ("save", "\U0001F4BE Export / save"),
        ("compress", "\U0001F5DC Compress context"),
        ("rollback", "\u23EA Rollback checkpoint"),
        ("topic", "\U0001F4CC Topic sessions"),
        ("sethome", "\U0001F3E0 Set home channel"),
    ]),
    ("\u26A1", "Run control", [
        ("stop", "\u23F9 Stop"),
        ("pause", "\u23F8 Pause (global)"),
        ("retry", "\U0001F501 Retry last"),
        ("undo", "\u21A9 Undo turn"),
        ("bg", "\U0001F3C3 Run in background"),
        ("agents", "\U0001F916 Active agents"),
        ("queue", "\U0001F4CB Queue"),
        ("steer", "\U0001F9ED Steer"),
        ("btw", "\U0001F4AC Side question"),
        ("busy", "\u231B Busy behavior"),
    ]),
    ("\U0001F9E0", "Model & behavior", [
        ("model", "\U0001F916 Switch model"),
        ("personality", "\U0001F3AD Personality"),
        ("reasoning", "\U0001F4A1 Reasoning effort"),
        ("fast", "\U0001F680 Fast mode"),
        ("yolo", "\U0001F947 YOLO mode"),
        ("approvals", "\u2705 Approval mode"),
        ("voice", "\U0001F3A4 Voice mode"),
        ("footer", "\U0001F9FE Runtime footer"),
        ("codex_runtime", "\U0001F4BB Codex runtime"),
    ]),
    ("\U0001F4CA", "Status & usage", [
        ("status", "\U0001F4CA Status"),
        ("context", "\U0001F4D0 Context window"),
        ("usage", "\U0001F4C8 Usage / limits"),
        ("quota", "\U0001F4B3 Quota"),
        ("egress", "\U0001F310 Egress proxy"),
        ("whoami", "\U0001F464 Whoami"),
        ("profile", "\U0001F4C1 Profile"),
        ("diff", "\U0001F4C4 Git diff"),
    ]),
    ("\U0001F3AF", "Automation", [
        ("goal", "\U0001F3AF Set goal"),
        ("subgoal", "\u2795 Add subgoal"),
        ("heartbeat", "\U0001F493 Heartbeat"),
        ("loop", "\U0001F501 Loop prompt"),
        ("blueprint", "\U0001F4D0 Blueprint"),
        ("suggestions", "\U0001F4A1 Suggestions"),
        ("kanban", "\U0001F4CB Kanban board"),
        ("plan", "\U0001F4DD Write plan"),
        ("moa", "\U0001F465 Mixture of Agents"),
    ]),
    ("\U0001F6E0", "Skills & maintenance", [
        ("learn", "\U0001F393 Learn skill"),
        ("bundles", "\U0001F4E6 Skill bundles"),
        ("reload_skills", "\U0001F504 Reload skills"),
        ("reload_mcp", "\U0001F50C Reload MCP"),
        ("curator", "\U0001F9F9 Curator"),
        ("memory", "\U0001F9E0 Memory review"),
        ("commands", "\U0001F4D6 Browse all commands"),
        ("help", "\u2753 Help"),
        ("refine", "\U0001F4A1 Refine (save lessons)"),
        ("review", "\U0001F50E Review (subagent)"),
        ("init", "\U0001F4C4 Init AGENTS.md"),
    ]),
    ("\u2699\uFE0F", "System", [
        ("restart", "\U0001F501 Restart gateway"),
        ("update", "\u2B06 Update Hermes"),
        ("version", "\u2139 Version"),
        ("debug", "\U0001F41E Debug report"),
        ("platform", "\U0001F4F1 Platform status"),
        ("insights", "\U0001F4C8 Insights"),
        ("topup", "\U0001F4B0 Balance / billing"),
        ("login", "\U0001F511 Nous login"),
    ]),
]

# Flat lookup: command name -> button label, built from CATEGORIES above.
COMMAND_LABELS: dict[str, str] = {
    cmd: label for _emoji, _title, cmds in CATEGORIES for cmd, label in cmds
}
