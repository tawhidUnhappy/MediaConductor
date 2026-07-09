#!/usr/bin/env bash
# One-command bootstrap for mangaEasy from a source checkout (macOS / Linux).
# mangaEasy is a CLI + MCP tool for LLM agents -- there is no GUI. This syncs
# Python deps and shows the command list; drive it with `uv run mangaeasy ...`.
#
# Usage: ./run.sh        (from the repo root)
#        bash run.sh
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v uv >/dev/null 2>&1; then
  echo "[FATAL] uv is not installed. Install it from https://docs.astral.sh/uv/ and re-run." >&2
  exit 1
fi

echo "==> Syncing Python dependencies (uv sync)..."
uv sync

echo "==> mangaEasy is ready. Start with:"
echo "      uv run mangaeasy where --json      # resolved paths + version"
echo "      uv run mangaeasy commands          # the full command list"
echo "      uv run mangaeasy mcp               # run the MCP server for an agent host"
echo
uv run mangaeasy --help
