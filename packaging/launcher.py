"""PyInstaller entry point for the standalone mangaEasy executable.

The frozen exe *is* the CLI: ``mangaEasy.exe <command> [args...]`` behaves
exactly like ``mangaeasy <command>``. Double-clicking it (no arguments)
opens the control center instead of dumping CLI help into a console.
"""

import multiprocessing
import sys

from mangaeasy.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    if not argv:
        argv = ["app"]
    sys.exit(main(argv))
