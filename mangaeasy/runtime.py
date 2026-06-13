"""mangaeasy.runtime — how this process re-invokes its own CLI.

Normal installs spawn subcommands as ``python -m mangaeasy.cli <command>``.
In a frozen (PyInstaller) build there is no ``python`` and no ``-m`` — the
executable *is* the CLI — so the prefix collapses to the exe itself.
Every place that spawns another mangaeasy command must build its argv via
:func:`cli_command` instead of hardcoding ``sys.executable -m ...``.
"""

from __future__ import annotations

import subprocess
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def cli_command(command: str, *args: str) -> list[str]:
    """argv that runs ``mangaeasy <command> [args...]`` in a fresh process."""
    if is_frozen():
        return [sys.executable, command, *args]
    return [sys.executable, "-m", "mangaeasy.cli", command, *args]


def popen_kwargs() -> dict:
    """Extra kwargs for subprocess.Popen/run that suppress console windows on Windows.

    A GUI-subsystem exe causes Windows to allocate a new console window for
    every child console process it spawns (ffmpeg, git, uv …). Adding
    CREATE_NO_WINDOW prevents that window from ever appearing.
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
