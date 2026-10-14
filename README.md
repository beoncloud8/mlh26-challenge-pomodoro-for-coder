# Poco - Pomodoro Timer for Coder

Poco is a small terminal Pomodoro timer that reminds developers to step away
from the screen and move during breaks.

## Install

Requires Python 3.9 or newer.

```bash
python -m pip install .
```

## Run

```bash
poco std       # 25 minutes of focus, then a 5-minute break
poco 50 10     # 50 minutes of focus, then a 10-minute break
poco           # same as "poco std"
```

Poco keeps repeating focus and break periods until you stop it. After each
focus period it starts the configured short break; after every fourth focus
period, it starts a 20-minute long break instead. The terminal display includes
an ASCII countdown and progress bar for every phase. The dashboard stays in
place while an animated `###` marker moves only inside the progress bar.

## Controls

- Press `p` to pause the timer.
- Press `r` to resume.
- Press `Ctrl+C` to stop Poco, restore the terminal, and exit with a break
  reminder. It does not close other applications.

The timer uses only the Python standard library.
