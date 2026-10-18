---
name: quick-resume-tips
description: "Explain the hermes-telegram-quick-resume plugin's /menu, /qr commands and reply-keyboard buttons when the user asks about them in Telegram."
version: 1.0.0
---

# Quick Resume — Telegram tap menu

This plugin adds a tap-to-use menu on top of Hermes's existing Telegram gateway
commands. It never replaces `/resume` or any built-in command — it just adds
buttons that send the same commands for you.

## Commands it adds

- `/menu` — opens the main menu: category buttons (Sessions, Run
  control, Model & behavior, Status & usage, Automation, Skills &
  maintenance, System) plus a direct "Resume a session" shortcut.
- `/qr` — jumps straight to the tap-to-resume session list (same as tapping
  "Resume a session" from `/menu`).

## How tapping actually runs a command

Category and navigation buttons are Telegram inline buttons — they just edit
the menu message, nothing executes. The final command buttons (session
numbers, `/status`, `/model`, ...) are Telegram **reply-keyboard** buttons:
tapping one sends that exact text as a genuine incoming message, exactly as
if the user had typed `/resume 3` themselves. Hermes's normal command
dispatcher authorizes and runs it — nothing is bypassed.

This two-tier design exists because Hermes's plugin API deliberately
refuses to let a plugin execute a slash command programmatically
(`ctx.inject_message` always sets `allow_gateway_control=False`) — a real
security boundary, not a missing feature. Reply keyboards get the same
one-tap feel without needing that permission at all.

## Category buttons are shortcuts, not new behavior

Every reply-keyboard button sends the bare slash command (e.g. tapping
"/model" sends `/model`). Commands that need arguments still show their
normal usage/picker after the tap — the button only saves typing the
command name.
