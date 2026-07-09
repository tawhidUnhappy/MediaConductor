"""PyInstaller entry point for the standalone mangaEasy backend executable.

The frozen exe *is* the CLI: ``mangaeasy.exe <command> [args...]`` behaves
exactly like ``mangaeasy <command>``. mangaEasy is a CLI + MCP tool for LLM
agents — there is no GUI. This build is invoked with explicit args (a
command); with no args it just prints ``--help``.
"""

import multiprocessing
import sys

from mangaeasy.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
