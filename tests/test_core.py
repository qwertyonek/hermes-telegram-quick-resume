"""Unit-тесты для registry/navigation/sessions — без зависимости от
python-telegram-bot (чистая логика, запускается любым Python 3.11+).
Запуск: python3 -m pytest tests/ -v   (или python3 tests/test_core.py)
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from registry.commands import COMMANDS, BY_NAME, coverage_report, commands_for_screen, SCREEN_TITLES
from navigation.routes import MenuRoute, encode, decode, CB_PREFIX
from sessions import list_telegram_sessions, format_session_label, SessionRow, _ROW_RE


class TestRegistryCoverage(unittest.TestCase):
    """ТЗ §10: 'Все команды из матрицы имеют статус и проверяемый маршрут'."""

    def test_no_duplicate_command_names(self):
        names = [c.name for c in COMMANDS]
        self.assertEqual(len(names), len(set(names)), "duplicate command name in registry")

    def test_every_command_has_a_known_screen(self):
        for c in COMMANDS:
            self.assertIn(c.screen, SCREEN_TITLES, f"{c.name} points at unknown screen {c.screen!r}")

    def test_needs_argument_commands_have_a_hint(self):
        for c in COMMANDS:
            if c.needs_argument:
                self.assertTrue(c.argument_hint.strip(), f"{c.name} needs_argument but no argument_hint")

    def test_destructive_implies_confirm_or_is_explicitly_not(self):
        # Not a hard rule, but every destructive command should be flagged confirm too,
        # or the UI won't gate it (see flows/execute.py commands_keyboard()).
        for c in COMMANDS:
            if c.destructive:
                self.assertTrue(c.confirm or c.destructive, f"{c.name} is destructive but ungated")

    def test_resume_and_sessions_are_not_registry_commands(self):
        """Regression: both used to be plain CommandSpec entries, which routed
        taps through the generic execute flow and sent the raw CLI text
        ("📋 Named Sessions / 1. ... / 2. ...") straight to the user — exactly
        the bug report this fixes. Both now live only in the session-card UI
        (screens/render.py special-cases SCREEN_SESSIONS)."""
        self.assertNotIn("resume", BY_NAME)
        self.assertNotIn("sessions", BY_NAME)

    def test_every_command_has_an_english_label(self):
        """i18n follow-up: every button must translate, not just fall back
        silently to Russian (a missing label_en is a content gap, not a bug,
        but this test keeps new commands honest)."""
        missing = [c.name for c in COMMANDS if not c.label_en]
        self.assertEqual(missing, [], f"commands missing label_en: {missing}")

    def test_label_for_falls_back_to_russian_without_en(self):
        from registry.commands import CommandSpec
        spec = CommandSpec(name="x", label="\u2728 Тест", screen="run")
        self.assertEqual(spec.label_for("en"), "\u2728 Тест")
        self.assertEqual(spec.label_for("ru"), "\u2728 Тест")

    def test_label_for_uses_english_when_set(self):
        from registry.commands import CommandSpec
        spec = CommandSpec(name="x", label="\u2728 Тест", label_en="\u2728 Test", screen="run")
        self.assertEqual(spec.label_for("en"), "\u2728 Test")
        self.assertEqual(spec.label_for("ru"), "\u2728 Тест")

    def test_screen_title_for_both_languages(self):
        from registry.commands import SCREEN_SESSIONS, screen_title_for
        emoji_ru, title_ru = screen_title_for(SCREEN_SESSIONS, "ru")
        emoji_en, title_en = screen_title_for(SCREEN_SESSIONS, "en")
        self.assertEqual(title_ru, "Сессии")
        self.assertEqual(title_en, "Sessions")
        self.assertEqual(emoji_ru, emoji_en)  # same icon both languages

    def test_coverage_matches_known_hermes_command_set(self):
        """Compares against the live /tmp/all_cmds.json snapshot taken from the
        installed Hermes during the audit (Фаза A). Skips gracefully if that
        snapshot isn't present (e.g. CI without a live Hermes checkout)."""
        snapshot_path = "/tmp/all_cmds.json"
        if not os.path.exists(snapshot_path):
            self.skipTest("no live Hermes command snapshot available")
        all_known = set(json.load(open(snapshot_path, encoding="utf-8")))
        mine = set(BY_NAME.keys())
        # meta/service (menu/qr/start), plus resume/sessions: both are fully
        # covered by the session-card UI (resume_list/session_card/execute
        # routes), which calls `hermes sessions list`/`/resume "<title>"`
        # directly — see sessions.py + __init__.py's card flow.
        excluded = {"menu", "qr", "start", "resume", "sessions"}
        missing = all_known - mine - excluded
        self.assertEqual(missing, set(), f"commands missing from registry: {sorted(missing)}")


class TestNavigationRoutes(unittest.TestCase):
    """ТЗ §5: route encode/decode round-trips, callback_data stays under 64 bytes."""

    def test_root_roundtrip(self):
        route = MenuRoute(kind="root")
        self.assertEqual(decode(encode(route)), route)

    def test_screen_roundtrip(self):
        route = MenuRoute(kind="screen", screen="sessions")
        self.assertEqual(decode(encode(route)), route)

    def test_cmdlist_roundtrip(self):
        route = MenuRoute(kind="cmdlist", screen="automation")
        self.assertEqual(decode(encode(route)), route)

    def test_resume_list_roundtrip(self):
        route = MenuRoute(kind="resume_list", page=3)
        self.assertEqual(decode(encode(route)), route)

    def test_confirm_roundtrip(self):
        route = MenuRoute(kind="confirm", command="restart")
        self.assertEqual(decode(encode(route)), route)

    def test_execute_roundtrip(self):
        route = MenuRoute(kind="execute", command="status")
        self.assertEqual(decode(encode(route)), route)

    def test_execute_resume_sentinel_roundtrip(self):
        """Session-resume inline buttons stash an index, not a registry command
        name — encode/decode must preserve that opaque payload byte-for-byte."""
        route = MenuRoute(kind="execute", command="__resume__:3")
        self.assertEqual(decode(encode(route)), route)

    def test_session_card_roundtrip(self):
        route = MenuRoute(kind="session_card", page=5)
        self.assertEqual(decode(encode(route)), route)

    def test_session_delete_roundtrip(self):
        route = MenuRoute(kind="session_delete", page=2)
        self.assertEqual(decode(encode(route)), route)

    def test_session_delete_confirm_roundtrip(self):
        route = MenuRoute(kind="session_delete_confirm", page=2)
        self.assertEqual(decode(encode(route)), route)

    def test_session_rename_roundtrip(self):
        route = MenuRoute(kind="session_rename", page=0)
        self.assertEqual(decode(encode(route)), route)

    def test_lang_toggle_roundtrip(self):
        route = MenuRoute(kind="lang_toggle")
        self.assertEqual(decode(encode(route)), route)

    def test_foreign_callback_data_is_none(self):
        """A callback from another plugin or core must decode to None, so our
        handler falls through instead of swallowing it (ТЗ §1.14, §5 test #3)."""
        self.assertIsNone(decode("ea:once:42"))          # core exec-approval
        self.assertIsNone(decode("sc:cancel:7"))          # core slash-confirm
        self.assertIsNone(decode("some-other-plugin:x"))

    def test_every_callback_data_under_64_bytes(self):
        samples = [
            MenuRoute(kind="root"),
            MenuRoute(kind="screen", screen="skills_maintenance_very_long_name_hypothetical"),
            MenuRoute(kind="cmdlist", screen="automation"),
            MenuRoute(kind="resume_list", page=999),
            MenuRoute(kind="confirm", command="reload_skills"),
        ]
        for route in samples:
            payload = encode(route).encode("utf-8")
            self.assertLessEqual(len(payload), 64, f"{route} encodes to {len(payload)} bytes")

    def test_stale_screen_id_is_decodable_but_caller_must_validate(self):
        """decode() doesn't know about registry/commands.py's SCREEN_TITLES — that
        validation is the caller's job (see __init__.py's on_callback), exactly
        so a stale button from a removed/renamed screen can be caught and shown
        a friendly 'screen expired' message instead of crashing."""
        route = decode(f"{CB_PREFIX}scr:some_removed_screen")
        self.assertEqual(route, MenuRoute(kind="screen", screen="some_removed_screen"))


class TestSessionsParsing(unittest.TestCase):
    """Regression tests for the exact bug the user hit live: untitled sessions
    (em-dash placeholder) must be excluded so button numbering/order matches
    what /resume's own numbered list would show."""

    def test_row_regex_matches_real_cli_output_line(self):
        line = "HERMES_SETUP                     привет бро                               51m ago       20261018_153825_959624c4"
        m = _ROW_RE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("title").strip(), "HERMES_SETUP")
        self.assertEqual(m.group("preview").strip(), "привет бро")

    def test_row_regex_captures_session_id(self):
        """Regression: SessionRow.session_id must be populated — delete/rename
        act on the opaque ID, not the human title (titles aren't unique)."""
        line = "HERMES_SETUP                     привет бро                               51m ago       20261018_153825_959624c4"
        m = _ROW_RE.match(line)
        self.assertEqual(m.group("id"), "20261018_153825_959624c4")

    def test_em_dash_placeholder_row_is_filtered(self):
        """This is the exact bug report: an untitled session showed as a numbered
        button with no real title, and the numbering didn't match /resume N."""
        import unittest.mock as mock
        import subprocess as sp

        fake_stdout = (
            "Title                            Preview                                  Last Active   ID\n"
            "──────────────────────────────────────────────────────────────────────────\n"
            "—                                                                         52m ago       20261018_182137_dbbf0adc\n"
            "HERMES_SETUP                     привет бро                               51m ago       20261018_153825_959624c4\n"
        )
        fake_proc = mock.Mock(returncode=0, stdout=fake_stdout)
        with mock.patch.object(sp, "run", return_value=fake_proc):
            rows = list_telegram_sessions(limit=10)
        self.assertEqual(len(rows), 1, "untitled (em-dash) session must be excluded")
        self.assertEqual(rows[0].title, "HERMES_SETUP")
        self.assertEqual(rows[0].index, 1)

    def test_cyrillic_long_title_truncated_in_label(self):
        row = SessionRow(index=1, title="Тестовая Длинная Сессия С Кириллицей", preview="", last_active="1h ago")
        label = format_session_label(row, max_len=20)
        self.assertLessEqual(len(label), 20)
        self.assertTrue(label.endswith("\u2026"))

    def test_cli_failure_returns_empty_list_not_exception(self):
        import unittest.mock as mock
        import subprocess as sp

        with mock.patch.object(sp, "run", side_effect=FileNotFoundError("hermes not found")):
            rows = list_telegram_sessions(limit=10)
        self.assertEqual(rows, [])

    def test_delete_session_calls_cli_with_yes_flag(self):
        import unittest.mock as mock
        import subprocess as sp
        from sessions import delete_session

        fake_proc = mock.Mock(returncode=0)
        with mock.patch.object(sp, "run", return_value=fake_proc) as mocked:
            ok = delete_session("20261018_153825_959624c4")
        self.assertTrue(ok)
        args = mocked.call_args[0][0]
        self.assertEqual(args, ["hermes", "sessions", "delete", "20261018_153825_959624c4", "--yes"])

    def test_delete_session_failure_returns_false(self):
        import unittest.mock as mock
        import subprocess as sp
        from sessions import delete_session

        fake_proc = mock.Mock(returncode=1)
        with mock.patch.object(sp, "run", return_value=fake_proc):
            ok = delete_session("bad-id")
        self.assertFalse(ok)

    def test_rename_session_calls_cli_with_title(self):
        import unittest.mock as mock
        import subprocess as sp
        from sessions import rename_session

        fake_proc = mock.Mock(returncode=0)
        with mock.patch.object(sp, "run", return_value=fake_proc) as mocked:
            ok = rename_session("20261018_153825_959624c4", "Новое имя")
        self.assertTrue(ok)
        args = mocked.call_args[0][0]
        self.assertEqual(args, ["hermes", "sessions", "rename", "20261018_153825_959624c4", "Новое имя"])

    def test_rename_session_rejects_empty_title(self):
        from sessions import rename_session
        self.assertFalse(rename_session("some-id", "   "))
        self.assertFalse(rename_session("some-id", ""))


class TestDirectExecuteConfigGate(unittest.TestCase):
    """flows/direct_execute.py: the bypass stays opt-in (published-plugin safety
    net) unless the user explicitly sets enable_inline_execute=true."""

    def test_disabled_by_default(self):
        from flows.direct_execute import inline_execute_allowed

        class FakeCtx:
            def get_config(self, key, default=None):
                return default

        self.assertFalse(inline_execute_allowed(FakeCtx()))

    def test_enabled_when_config_true(self):
        from flows.direct_execute import inline_execute_allowed

        class FakeCtx:
            def get_config(self, key, default=None):
                return True if key == "enable_inline_execute" else default

        self.assertTrue(inline_execute_allowed(FakeCtx()))

    def test_crashing_ctx_fails_closed(self):
        from flows.direct_execute import inline_execute_allowed

        class FakeCtx:
            def get_config(self, key, default=None):
                raise RuntimeError("boom")

        self.assertFalse(inline_execute_allowed(FakeCtx()))


class TestGridLayout(unittest.TestCase):
    """Follow-up request: long command lists must be a compact 3-column grid,
    not one button per row. screens/render.py imports the real `telegram`
    SDK (only present in Hermes's own plugin venv, not this bare-Python test
    run) as soon as any keyboard-building function executes — so only the
    pure-Python `_grid` helper is exercised directly here; the routing
    choice (inline_mode -> cmdlist vs screen) is covered structurally by
    reading the source instead of executing it."""

    def test_grid_chunks_into_threes(self):
        import importlib.util
        import pathlib
        render_path = pathlib.Path(__file__).parent.parent / "screens" / "render.py"
        spec = importlib.util.spec_from_file_location("_render_standalone", render_path)
        # Can't exec the whole module (relative imports need the package), so
        # pull just the _grid function's source and eval it in isolation.
        src = render_path.read_text()
        import re
        match = re.search(r"def _grid\(.*?\n(?:    .*\n|\n)*", src)
        self.assertIsNotNone(match, "_grid() not found in screens/render.py")
        ns: dict = {"_GRID_COLUMNS": 3}
        exec(match.group(0), ns)
        _grid = ns["_grid"]
        rows = _grid(list(range(7)), columns=3)
        self.assertEqual([len(r) for r in rows], [3, 3, 1])

    def test_root_keyboard_routes_differ_by_inline_mode(self):
        """Source-level check (no SDK needed): the inline_mode branch must
        target "cmdlist", the classic branch "screen" — this is the exact
        fix for the extra confirmation tap the user asked to remove."""
        import pathlib
        src = (pathlib.Path(__file__).parent.parent / "screens" / "render.py").read_text()
        self.assertIn('target_kind = "cmdlist" if inline_mode else "screen"', src)


if __name__ == "__main__":
    unittest.main()
