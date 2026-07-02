#!/usr/bin/env bash
# Launches the Electron app in dev mode — same as the manual 3-line Git Bash
# sequence used throughout this session, just packaged so it doesn't need
# retyping. Run from anywhere: `bash desktop/run.sh` or `./run.sh` from
# inside desktop/.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Portable Node is vendored at .mangaeasy/tools/_vendor/node (Windows: node.exe
# etc. live at the top level; macOS/Linux nest under bin/) by `mangaeasy
# ensure-node` -- same self-contained dir ffmpeg/uv/git-lfs use. Prefer a
# system npm if one's already on PATH, else fall back to the vendored copy,
# fetching it first if this is the very first run.
if ! command -v npm >/dev/null 2>&1; then
  if [ ! -e .mangaeasy/tools/_vendor/node/npm.cmd ] && [ ! -e .mangaeasy/tools/_vendor/node/bin/npm ]; then
    echo "==> No npm found, fetching a portable Node.js for this install..."
    uv run mangaeasy ensure-node
  fi
  export PATH="$(pwd)/.mangaeasy/tools/_vendor/node:$(pwd)/.mangaeasy/tools/_vendor/node/bin:$PATH"
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "[FATAL] Node.js/npm still not found after fetching it -- see the error above." >&2
  exit 1
fi

cd desktop
unset ELECTRON_RUN_AS_NODE
npm run dev
