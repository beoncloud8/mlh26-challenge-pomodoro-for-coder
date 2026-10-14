import argparse
import math
import os
import select
import sys
import time
from dataclasses import dataclass

if os.name != "nt":
    import termios
    import tty


@dataclass(frozen=True)
class TimerConfig:
    focus_minutes: int
    break_minutes: int


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="poco",
        description="A focused Pomodoro timer for developers.",
        epilog="Examples: poco std    |    poco 50 10",
    )
    parser.add_argument(
        "durations",
        nargs="*",
        metavar="MINUTES",
        help="use 'std' for 25/5 minutes, or provide focus and break minutes",
    )
    args = parser.parse_args(argv)
    durations = args.durations

    if not durations or durations == ["std"]:
        return TimerConfig(focus_minutes=25, break_minutes=5)
    if len(durations) != 2:
        parser.error("provide 'std' or both focus and break minutes")

    values = []
    for duration in durations:
        if not duration.isascii() or not duration.isdigit() or int(duration) < 1:
            parser.error(f"duration must be a positive whole number of minutes: {duration!r}")
        values.append(int(duration))
    return TimerConfig(focus_minutes=values[0], break_minutes=values[1])


class KeyReader:
    def __init__(self, stream=sys.stdin):
        self.stream = stream
        self._original_terminal = None

    def __enter__(self):
        if os.name != "nt" and self.stream.isatty():
            self._original_terminal = termios.tcgetattr(self.stream.fileno())
            tty.setcbreak(self.stream.fileno())
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._original_terminal is not None:
            termios.tcsetattr(
                self.stream.fileno(), termios.TCSADRAIN, self._original_terminal
            )

    def read_key(self, timeout):
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if msvcrt.kbhit():
                    return msvcrt.getwch().lower()
                time.sleep(min(0.05, deadline - time.monotonic()))
            return None

        if not self.stream.isatty():
            time.sleep(timeout)
            return None
        ready, _, _ = select.select([self.stream], [], [], timeout)
        return self.stream.read(1).lower() if ready else None


def render_dashboard(label, remaining, elapsed, total, paused, output):
    width = 54
    bar_width = 30
    progress = min(1.0, max(0.0, elapsed / total))
    filled = round(progress * bar_width)
    bar = "#" * filled + "-" * (bar_width - filled)
    minutes, seconds = divmod(remaining, 60)
    clock = f"{minutes:02d}:{seconds:02d}"
    if remaining == 0:
        state = "PHASE COMPLETE"
    elif paused:
        state = "PAUSED - press r to resume"
    else:
        state = "press p to pause"
    title = f"  P O C O  ::  {label}".center(width)
    lines = [
        "+" + "-" * width + "+",
        "|" + title + "|",
        "|" + " " * width + "|",
        "|" + clock.center(width) + "|",
        "|" + f"  [{bar}]  {int(progress * 100):3d}%".ljust(width) + "|",
        "|" + " " * width + "|",
        "|" + f"  {state}  |  Ctrl+C: stop".ljust(width) + "|",
        "+" + "-" * width + "+",
    ]
    if output.isatty():
        output.write("\033[2J\033[H")
    output.write("\n".join(lines) + "\n")
    output.flush()


def run_phase(label, duration_seconds, keyboard, output, clock=time.monotonic):
    deadline = clock() + duration_seconds
    paused_remaining = None
    previous_remaining = None
    paused = False

    while True:
        now = clock()
        remaining = paused_remaining if paused else max(0, math.ceil(deadline - now))
        if remaining != previous_remaining:
            elapsed = duration_seconds - remaining
            render_dashboard(label, remaining, elapsed, duration_seconds, paused, output)
            previous_remaining = remaining
        if remaining == 0:
            return

        key = keyboard.read_key(timeout=min(0.1, remaining))
        if key == "p" and not paused:
            paused_remaining = max(1, math.ceil(deadline - clock()))
            paused = True
            previous_remaining = None
        elif key == "r" and paused:
            deadline = clock() + paused_remaining
            paused_remaining = None
            paused = False
            previous_remaining = None


def run_timer(config):
    phases = (
        ("FOCUS", config.focus_minutes * 60),
        ("BREAK", config.break_minutes * 60),
    )
    with KeyReader() as keyboard:
        for index, (label, seconds) in enumerate(phases):
            if index:
                print("\nFocus complete. Look away from your screen and move a little!")
            run_phase(label, seconds, keyboard, sys.stdout)
    print("\nBreak complete. Nice work - ready for another focus session!")


def main(argv=None):
    config = parse_args(argv)
    try:
        run_timer(config)
    except KeyboardInterrupt:
        print("\n\nTimer stopped. Take a break, stretch, and rest your eyes.")
    return 0
