#!/usr/bin/env bash
# One-command launcher for mangaEasy from a source checkout (macOS / Linux).
# Syncs Python deps, builds the desktop app if needed, then opens it.
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

if [ ! -f desktop/out/main/index.js ] || [ ! -d desktop/node_modules/electron ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "[FATAL] Node.js/npm is not installed. Install Node 22+ from https://nodejs.org/ and re-run." >&2
    exit 1
  fi
  echo "==> Desktop app isn't built yet, building it (first run only)..."
  (cd desktop && npm install && npm run build)
fi

echo "==> Launching mangaEasy..."
uv run mangaeasy app
