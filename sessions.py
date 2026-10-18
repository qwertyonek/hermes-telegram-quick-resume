"""Read-only helpers for listing named Hermes sessions, reusing the public
``hermes sessions list`` CLI output (never touches state.db directly).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass
class SessionRow:
    index: int
    title: str
    preview: str
    last_active: str
    session_id: str = ""


_ROW_RE = re.compile(
    r"^(?P<title>.{1,33})\s{2,}(?P<preview>.{1,41})\s{2,}(?P<last_active>\S.{0,13}?)\s{2,}(?P<id>\S+)\s*$"
)


def list_telegram_sessions(limit: int = 10, timeout: float = 10.0) -> list[SessionRow]:
    """Shell out to ``hermes sessions list --source telegram`` (the same public CLI a
    user would run) and parse the fixed-width table into rows ordered like ``/resume``'s
    own numbered list. Returns [] on any failure — callers fall back to plain ``/resume``.
    """
    try:
        proc = subprocess.run(
            ["hermes", "sessions", "list", "--source", "telegram", "--limit", str(limit)],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    rows: list[SessionRow] = []
    for line in lines:
        if line.startswith("Title") or set(line.strip()) <= {"\u2500", "-"}:
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        title = m.group("title").strip()
        # "/resume" without args numbers only sessions that HAVE a title (gateway's
        # _list_titled_sessions filters `if s.get("title")`); "hermes sessions list"
        # shows every session, using an em-dash placeholder for untitled ones. Skipping
        # those here keeps our button numbering identical to what "/resume N" resolves.
        if not title or title == "\u2014":
            continue
        rows.append(SessionRow(
            index=len(rows) + 1,
            title=title,
            preview=m.group("preview").strip(),
            last_active=m.group("last_active").strip(),
            session_id=m.group("id").strip(),
        ))
    return rows


def format_session_label(row: SessionRow, max_len: int = 42) -> str:
    """Button label: ``N. Title — preview`` truncated for Telegram's button width."""
    base = f"{row.index}. {row.title}"
    if row.preview:
        base += f" — {row.preview}"
    if len(base) > max_len:
        base = base[: max_len - 1].rstrip() + "\u2026"
    return base


def delete_session(session_id: str, timeout: float = 10.0) -> bool:
    """Shell out to ``hermes sessions delete <id> --yes`` (same public CLI a
    user would run by hand). Returns True on success."""
    try:
        proc = subprocess.run(
            ["hermes", "sessions", "delete", session_id, "--yes"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def rename_session(session_id: str, new_title: str, timeout: float = 10.0) -> bool:
    """Shell out to ``hermes sessions rename <id> <title...>``. Returns True on success."""
    new_title = (new_title or "").strip()
    if not new_title:
        return False
    try:
        proc = subprocess.run(
            ["hermes", "sessions", "rename", session_id, new_title],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0
