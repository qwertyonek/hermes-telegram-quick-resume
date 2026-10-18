"""Navigation state machine (ТЗ §5): stable route identity encoded directly
in Telegram callback_data, so no server-side session store is required for
simple screen<->screen moves — only wizards (flows/) need persisted state.

A MenuRoute is reconstructed FROM callback_data on every tap; there is no
mutable global "current screen" anywhere in this process (multiple chats,
topics and users navigate independently and safely because nothing is
shared). This directly satisfies ТЗ §5's isolation requirement: a stale
button from another session can only ever re-render A SCREEN, never run a
privileged action (actions live on ReplyKeyboardMarkup, never on inline
callback_data at all — see registry/commands.py and screens/render.py).
"""
from __future__ import annotations

from dataclasses import dataclass

# Telegram inline callback_data hard cap is 64 BYTES, not characters. Every
# route below stays well under that: "qr:root", "qr:scr:sessions:0",
# "qr:cmdlist:automation" are all < 30 bytes even with Cyrillic-free ASCII
# command/screen ids (deliberately ASCII-only ids for this reason).
CB_PREFIX = "qr:"


@dataclass(frozen=True)
class MenuRoute:
    """One navigable screen. ``page`` doubles as: pagination page number for
    "resume_list"; the FLAT session index (not page-relative) for every
    "session_*" card-flow route below — see __init__.py's _render_session_card
    for why a flat index instead of a per-page one."""
    kind: str                 # "root"|"screen"|"cmdlist"|"resume_list"|"confirm"|"execute"
                               # |"session_card"|"session_delete"|"session_delete_confirm"|"session_rename"
    screen: str = ""           # registry screen id, empty for root
    page: int = 0
    command: str = ""          # for "confirm": which command needs Да/Отмена


def encode(route: MenuRoute) -> str:
    if route.kind == "root":
        return f"{CB_PREFIX}root"
    if route.kind == "screen":
        return f"{CB_PREFIX}scr:{route.screen}"
    if route.kind == "cmdlist":
        return f"{CB_PREFIX}cmdlist:{route.screen}"
    if route.kind == "resume_list":
        return f"{CB_PREFIX}resume:{route.page}"
    if route.kind == "confirm":
        return f"{CB_PREFIX}confirm:{route.command}"
    if route.kind == "execute":
        return f"{CB_PREFIX}x:{route.command}"
    if route.kind == "session_card":
        return f"{CB_PREFIX}card:{route.page}"
    if route.kind == "session_delete":
        return f"{CB_PREFIX}del:{route.page}"
    if route.kind == "session_delete_confirm":
        return f"{CB_PREFIX}delok:{route.page}"
    if route.kind == "session_rename":
        return f"{CB_PREFIX}ren:{route.page}"
    raise ValueError(f"unknown route kind: {route.kind!r}")


def decode(data: str) -> MenuRoute | None:
    """Parse callback_data back into a MenuRoute, or None if it's not ours
    (lets the handler fall through to core's own CallbackQueryHandler)."""
    if not data.startswith(CB_PREFIX):
        return None
    body = data[len(CB_PREFIX):]
    if body == "root":
        return MenuRoute(kind="root")
    if body.startswith("scr:"):
        return MenuRoute(kind="screen", screen=body[4:])
    if body.startswith("cmdlist:"):
        return MenuRoute(kind="cmdlist", screen=body[8:])
    if body.startswith("resume:"):
        page_s = body[7:]
        try:
            return MenuRoute(kind="resume_list", page=int(page_s))
        except ValueError:
            return MenuRoute(kind="resume_list", page=0)
    if body.startswith("confirm:"):
        return MenuRoute(kind="confirm", command=body[8:])
    if body.startswith("x:"):
        return MenuRoute(kind="execute", command=body[2:])
    if body.startswith("card:"):
        try:
            return MenuRoute(kind="session_card", page=int(body[5:]))
        except ValueError:
            return None
    if body.startswith("delok:"):
        try:
            return MenuRoute(kind="session_delete_confirm", page=int(body[6:]))
        except ValueError:
            return None
    if body.startswith("del:"):
        try:
            return MenuRoute(kind="session_delete", page=int(body[4:]))
        except ValueError:
            return None
    if body.startswith("ren:"):
        try:
            return MenuRoute(kind="session_rename", page=int(body[4:]))
        except ValueError:
            return None
    return None
