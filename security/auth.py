"""Authorization checks for every callback and reply-keyboard tap.

Design constraint (see docs/menu-audit.md §1, §7): gateway/slash_access.py's
``SlashAccessPolicy`` is a core-internal module this plugin must NOT import
(catalog rule 9, "no core override" — a plugin may only use public ctx.*
surfaces). Hermes gives no ``ctx.get_slash_access_policy()`` equivalent, so
this plugin builds its OWN conservative check from data it legitimately can
read: the Telegram allowlist in ``.env`` (``TELEGRAM_ALLOWED_USERS``), read
the same way the gateway itself reads it at startup (environment variable,
never a direct file parse of someone else's secrets).

This is deliberately narrower than the full admin/user split Hermes's
gateway enforces for text commands — those rules still apply at dispatch
time regardless of what this plugin decides. What this module adds is a
SECOND, redundant check at the UI layer: never render or act on a button
for a user this plugin cannot positively verify is on the configured
allowlist. If the allowlist is unset (open gateway), every verified
Telegram user passes — matching the gateway's own "no admin list => gating
disabled" default (gateway/slash_access.py's documented behavior), so a
single-user personal bot is not locked out of its own menu.
"""
from __future__ import annotations

import os


def _allowed_user_ids() -> frozenset[str]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


def is_authorized(user_id: str | int | None) -> bool:
    """True when *user_id* may use this plugin's buttons.

    Mirrors the gateway's own fail-open-when-unconfigured default: an empty
    allowlist means every Telegram update that already reached this process
    (i.e. passed the gateway's own inbound authorization) is fine. A
    configured allowlist narrows that to exactly those IDs — this plugin
    never WIDENS access beyond what the gateway itself would allow.
    """
    allowed = _allowed_user_ids()
    if not allowed:
        return True
    return user_id is not None and str(user_id) in allowed


# Actions this plugin treats as "needs confirmation before sending" — chosen
# from Hermes's own command descriptions (destructive, irreversible, or
# costly). This list is advisory UI friction, NOT a replacement for
# Hermes's own approval system (ThisPlugin never bypasses /approve).
CONFIRM_BEFORE_SEND: frozenset[str] = frozenset({
    "restart", "update", "rollback", "undo", "stop", "platform",
})
