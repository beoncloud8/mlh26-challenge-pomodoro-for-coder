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

LONG_BREAK_MINUTES = 20


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


def render_dashboard(
    label, remaining, elapsed, total, paused, output, refresh=False,
    animation_step=0, update_title=False, update_clock=True,
    update_progress=True, update_message=False, update_state=False,
    phase_message=""
):
    width = 54
    bar_width = 30
    progress = min(1.0, max(0.0, elapsed / total))
    filled = round(progress * bar_width)
    bar = ["="] * filled + ["-"] * (bar_width - filled)
    runner_width = 3
    runner_span = bar_width - runner_width
    runner_offset = animation_step % (runner_span * 2)
    runner_start = (
        runner_offset if runner_offset <= runner_span else runner_span * 2 - runner_offset
    )
    bar[runner_start : runner_start + runner_width] = "#" * runner_width
    bar = "".join(bar)
    minutes, seconds = divmod(remaining, 60)
    clock = f"{minutes:02d}:{seconds:02d}"
    if remaining == 0:
        state = "PHASE COMPLETE"
    elif paused:
        state = "PAUSED - press SPACE to resume"
    else:
        state = "press SPACE to pause"
    title = f"  P O C O  ::  {label}".center(width)
    lines = [
        "+" + "-" * width + "+",
        "|" + title + "|",
        "|" + " " * width + "|",
        "|" + clock.center(width) + "|",
        "|" + f"  [{bar}]  {int(progress * 100):3d}%".ljust(width) + "|",
        "|" + f"  {phase_message}".ljust(width) + "|",
        "|" + f"  {state}  |  Ctrl+C: stop".ljust(width) + "|",
        "+" + "-" * width + "+",
    ]
    if output.isatty() and refresh:
        if update_title:
            output.write("\033[2;1H" + lines[1])
        if update_clock:
            output.write("\033[4;1H" + lines[3])
        if update_progress:
            output.write("\033[5;1H" + lines[4])
        if update_message:
            output.write("\033[6;1H" + lines[5])
        if update_state:
            output.write("\033[7;1H" + lines[6])
        output.write("\033[9;1H")
    elif output.isatty():
        output.write("\033[2J\033[H")
        output.write("\n".join(lines) + "\n")
    elif not refresh:
        output.write("\n".join(lines) + "\n")
    output.flush()


def run_phase(
    label, duration_seconds, keyboard, output, clock=time.monotonic,
    reuse_dashboard=False, phase_message=""
):
    deadline = clock() + duration_seconds
    paused_remaining = None
    previous_remaining = None
    paused = False
    dashboard_initialized = reuse_dashboard
    state_changed = reuse_dashboard
    title_changed = reuse_dashboard
    previous_animation_step = None

    while True:
        now = clock()
        remaining = paused_remaining if paused else max(0, math.ceil(deadline - now))
        active_remaining = paused_remaining if paused else max(0, deadline - now)
        elapsed = duration_seconds - active_remaining
        animation_step = int(elapsed * 4)
        clock_changed = remaining != previous_remaining
        progress_changed = (
            clock_changed or animation_step != previous_animation_step
        )
        if not dashboard_initialized or clock_changed or progress_changed or state_changed:
            render_dashboard(
                label,
                remaining,
                elapsed,
                duration_seconds,
                paused,
                output,
                refresh=dashboard_initialized,
                animation_step=animation_step,
                update_title=title_changed,
                update_clock=clock_changed,
                update_progress=progress_changed,
                update_message=title_changed,
                update_state=state_changed or remaining == 0,
                phase_message=phase_message,
            )
            dashboard_initialized = True
            title_changed = False
            previous_remaining = remaining
            previous_animation_step = animation_step
            state_changed = False
        if remaining == 0:
            return

        key = keyboard.read_key(timeout=min(0.1, remaining))
        if key == " " and not paused:
            paused_remaining = max(1, math.ceil(deadline - clock()))
            paused = True
            previous_remaining = None
            state_changed = True
        elif key == " " and paused:
            deadline = clock() + paused_remaining
            paused_remaining = None
            paused = False
            previous_remaining = None
            state_changed = True


def timer_phases(config):
    focus_count = 0
    while True:
        yield "FOCUS", config.focus_minutes * 60
        focus_count += 1
        if focus_count % 4 == 0:
            yield "LONG BREAK", LONG_BREAK_MINUTES * 60
        else:
            yield "SHORT BREAK", config.break_minutes * 60


def run_timer(config):
    previous_phase = None
    dashboard_initialized = False
    with KeyReader() as keyboard:
        for label, seconds in timer_phases(config):
            if label == "SHORT BREAK":
                phase_message = "Focus complete. Short break - move a little!"
            elif label == "LONG BREAK":
                phase_message = "Four focus periods complete. Enjoy a longer break!"
            elif previous_phase is not None:
                phase_message = "Break complete. Back to focus!"
            else:
                phase_message = "Focus session started. Stay focused!"
            run_phase(
                label,
                seconds,
                keyboard,
                sys.stdout,
                reuse_dashboard=dashboard_initialized,
                phase_message=phase_message,
            )
            dashboard_initialized = True
            previous_phase = label


def main(argv=None):
    config = parse_args(argv)
    try:
        run_timer(config)
    except KeyboardInterrupt:
        pass
    return 0
