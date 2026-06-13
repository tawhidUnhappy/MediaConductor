"""mangaeasy.runtime — how this process re-invokes its own CLI.

Normal installs spawn subcommands as ``python -m mangaeasy.cli <command>``.
In a frozen (PyInstaller) build there is no ``python`` and no ``-m`` — the
executable *is* the CLI — so the prefix collapses to the exe itself.
Every place that spawns another mangaeasy command must build its argv via
:func:`cli_command` instead of hardcoding ``sys.executable -m ...``.
"""

from __future__ import annotations

import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def cli_command(command: str, *args: str) -> list[str]:
    """argv that runs ``mangaeasy <command> [args...]`` in a fresh process."""
    if is_frozen():
        return [sys.executable, command, *args]
    return [sys.executable, "-m", "mangaeasy.cli", command, *args]
