import io
import itertools
import unittest
from unittest.mock import patch

from poco.cli import (
    LONG_BREAK_MINUTES,
    TimerConfig,
    main,
    parse_args,
    render_dashboard,
    run_phase,
    run_timer,
    timer_phases,
)


class ParseArgsTests(unittest.TestCase):
    def test_standard_timer(self):
        self.assertEqual(parse_args(["std"]), TimerConfig(25, 5))

    def test_defaults_to_standard_timer(self):
        self.assertEqual(parse_args([]), TimerConfig(25, 5))

    def test_custom_timer(self):
        self.assertEqual(parse_args(["50", "10"]), TimerConfig(50, 10))

    def test_rejects_invalid_durations(self):
        for arguments in (["0", "5"], ["1.5", "5"], ["10"], ["10", "5", "2"]):
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as error:
                    parse_args(arguments)
                self.assertEqual(error.exception.code, 2)


class TimerPhaseTests(unittest.TestCase):
    def test_repeats_focus_cycles_and_takes_long_break_after_four(self):
        phases = list(itertools.islice(timer_phases(TimerConfig(25, 5)), 10))

        self.assertEqual(
            phases,
            [
                ("FOCUS", 25 * 60),
                ("SHORT BREAK", 5 * 60),
                ("FOCUS", 25 * 60),
                ("SHORT BREAK", 5 * 60),
                ("FOCUS", 25 * 60),
                ("SHORT BREAK", 5 * 60),
                ("FOCUS", 25 * 60),
                ("LONG BREAK", LONG_BREAK_MINUTES * 60),
                ("FOCUS", 25 * 60),
                ("SHORT BREAK", 5 * 60),
            ],
        )

    def test_short_break_uses_custom_duration(self):
        phases = list(itertools.islice(timer_phases(TimerConfig(50, 10)), 2))

        self.assertEqual(phases, [("FOCUS", 50 * 60), ("SHORT BREAK", 10 * 60)])

    def test_run_timer_continues_dispatching_phases(self):
        class FakeKeyboard:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        phases = []

        def record_phase(label, seconds, keyboard, output):
            if len(phases) == 10:
                raise KeyboardInterrupt
            phases.append((label, seconds))

        with patch("poco.cli.KeyReader", FakeKeyboard):
            with patch("poco.cli.run_phase", side_effect=record_phase):
                with patch("sys.stdout", io.StringIO()):
                    with self.assertRaises(KeyboardInterrupt):
                        run_timer(TimerConfig(25, 5))

        self.assertEqual(
            [label for label, _ in phases],
            [
                "FOCUS",
                "SHORT BREAK",
                "FOCUS",
                "SHORT BREAK",
                "FOCUS",
                "SHORT BREAK",
                "FOCUS",
                "LONG BREAK",
                "FOCUS",
                "SHORT BREAK",
            ],
        )


class DashboardTests(unittest.TestCase):
    def test_dashboard_shows_countdown_progress_and_controls(self):
        output = io.StringIO()
        render_dashboard("FOCUS", 1500, 0, 1500, False, output)

        screen = output.getvalue()
        self.assertIn("25:00", screen)
        self.assertIn("[###---------------------------]", screen)
        self.assertIn("press p to pause", screen)
        self.assertIn("Ctrl+C: stop", screen)
        self.assertTrue(all(len(line) == 56 for line in screen.splitlines()))

    def test_dashboard_shows_paused_state(self):
        output = io.StringIO()
        render_dashboard("BREAK", 60, 30, 90, True, output)

        self.assertIn("PAUSED - press r to resume", output.getvalue())

    def test_terminal_dashboard_refresh_updates_in_place(self):
        class TerminalOutput(io.StringIO):
            def isatty(self):
                return True

        output = TerminalOutput()
        render_dashboard("FOCUS", 60, 0, 120, False, output)
        render_dashboard("FOCUS", 59, 1, 120, False, output, refresh=True, animation_step=1)

        screen = output.getvalue()
        self.assertEqual(screen.count("\033[2J"), 1)
        self.assertIn("\033[4;1H", screen)
        self.assertIn("\033[5;1H", screen)
        self.assertNotIn("\033[7;1H", screen)
        self.assertIn("\033[9;1H", screen)
        self.assertEqual(screen.count("+------------------------------------------------------+\n"), 2)
        self.assertEqual(screen.count("P O C O  ::  FOCUS"), 1)

    def test_countdown_does_not_redraw_or_clear_terminal_each_second(self):
        class FakeClock:
            now = 0

            def __call__(self):
                return self.now

        class FakeKeyboard:
            def __init__(self, clock):
                self.clock = clock

            def read_key(self, timeout):
                self.clock.now += 1
                return None

        class TerminalOutput(io.StringIO):
            def isatty(self):
                return True

        clock = FakeClock()
        output = TerminalOutput()
        run_phase("FOCUS", 3, FakeKeyboard(clock), output, clock=clock)

        screen = output.getvalue()
        self.assertEqual(screen.count("\033[2J"), 1)
        self.assertEqual(screen.count("+------------------------------------------------------+\n"), 2)
        self.assertEqual(screen.count("\033[4;1H"), 3)
        self.assertEqual(screen.count("\033[5;1H"), 3)
        self.assertEqual(screen.count("\033[7;1H"), 1)
        self.assertEqual(screen.count("P O C O  ::  FOCUS"), 1)
        self.assertEqual(screen.count("###"), 4)
        self.assertIn("PHASE COMPLETE", screen)

    def test_nonterminal_output_does_not_repeat_dashboard(self):
        class FakeClock:
            now = 0

            def __call__(self):
                return self.now

        class FakeKeyboard:
            def __init__(self, clock):
                self.clock = clock

            def read_key(self, timeout):
                self.clock.now += 1
                return None

        clock = FakeClock()
        output = io.StringIO()
        run_phase("FOCUS", 3, FakeKeyboard(clock), output, clock=clock)

        screen = output.getvalue()
        self.assertEqual(screen.count("+------------------------------------------------------+\n"), 2)
        self.assertEqual(screen.count("P O C O  ::  FOCUS"), 1)

    def test_progress_animation_updates_more_often_than_clock(self):
        class TerminalOutput(io.StringIO):
            def isatty(self):
                return True

        class FakeClock:
            now = 0

            def __call__(self):
                return self.now

        class FakeKeyboard:
            def __init__(self, clock):
                self.clock = clock

            def read_key(self, timeout):
                self.clock.now += 0.1
                return None

        clock = FakeClock()
        output = TerminalOutput()
        run_phase("FOCUS", 2, FakeKeyboard(clock), output, clock=clock)

        screen = output.getvalue()
        self.assertEqual(screen.count("P O C O  ::  FOCUS"), 1)
        self.assertEqual(screen.count("\033[4;1H"), 2)
        self.assertGreater(screen.count("\033[5;1H"), screen.count("\033[4;1H"))

    def test_pause_and_resume_controls(self):
        class TerminalOutput(io.StringIO):
            def isatty(self):
                return True

        class FakeClock:
            now = 0

            def __call__(self):
                return self.now

        clock = FakeClock()

        class FakeKeyboard:
            calls = 0

            def read_key(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    return "p"
                if self.calls == 2:
                    clock.now += 30
                    return "r"
                if self.calls == 3:
                    clock.now += 3
                return None

        output = TerminalOutput()
        run_phase("FOCUS", 3, FakeKeyboard(), output, clock=clock)

        screen = output.getvalue()
        self.assertIn("PAUSED - press r to resume", screen)
        self.assertIn("PHASE COMPLETE", screen)
        self.assertEqual(screen.count("press p to pause"), 2)


class InterruptTests(unittest.TestCase):
    def test_ctrl_c_stops_with_break_reminder(self):
        output = io.StringIO()
        with patch("poco.cli.run_timer", side_effect=KeyboardInterrupt):
            with patch("sys.stdout", output):
                self.assertEqual(main(["std"]), 0)

        self.assertIn("Timer stopped. Take a break", output.getvalue())


if __name__ == "__main__":
    unittest.main()
