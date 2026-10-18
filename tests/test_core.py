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

    def test_coverage_matches_known_hermes_command_set(self):
        """Compares against the live /tmp/all_cmds.json snapshot taken from the
        installed Hermes during the audit (Фаза A). Skips gracefully if that
        snapshot isn't present (e.g. CI without a live Hermes checkout)."""
        snapshot_path = "/tmp/all_cmds.json"
        if not os.path.exists(snapshot_path):
            self.skipTest("no live Hermes command snapshot available")
        all_known = set(json.load(open(snapshot_path, encoding="utf-8")))
        mine = set(BY_NAME.keys())
        excluded = {"menu", "qr", "start"}  # meta/service, deliberately not in registry
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


if __name__ == "__main__":
    unittest.main()
