#!/usr/bin/env bash
# One-command bootstrap for mangaEasy from a source checkout (macOS/Linux).
# mangaEasy is a CLI + MCP server for LLM agents. This syncs Python
# dependencies and shows the curated command list.
#
# Everything it downloads stays inside this folder — see scripts/isolate.sh.
# If you have no uv yet, use ./bootstrap.sh instead; it fetches a portable one.
#
# Usage: ./run.sh        (from anywhere — it cd's to its own directory)
#        bash run.sh
set -euo pipefail

# BASH_SOURCE is unset when the script is piped into bash; fall back to $0.
cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
MANGAEASY_INSTALL_ROOT="$(pwd -P)"
export MANGAEASY_INSTALL_ROOT

# Pin every cache under ./runtime/cache BEFORE uv runs — uv sync is what
# downloads the interpreter and the wheels, and it would otherwise fill
# ~/.cache/uv. This also puts ./runtime/tools/_vendor/*/bin first on PATH.
# shellcheck source=scripts/isolate.sh
. "$MANGAEASY_INSTALL_ROOT/scripts/isolate.sh"

# uv's installer writes to ~/.local/bin (or ~/.cargo/bin on older versions) and
# appends it to a shell profile. A non-login shell, a Finder/GUI launch, or the
# very terminal that just ran the installer has a PATH from before that, so a
# bare `command -v uv` misses a perfectly good install. Check the known
# locations before giving up — same fallback run.bat does on Windows.
if ! command -v uv >/dev/null 2>&1; then
  for candidate in "$HOME/.local/bin" "$HOME/.cargo/bin" /opt/homebrew/bin /usr/local/bin; do
    if [ -x "$candidate/uv" ]; then
      PATH="$candidate:$PATH"
      export PATH
      break
    fi
  done
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[FATAL] uv is not installed or not on PATH." >&2
  echo "        Run ./bootstrap.sh instead — it downloads a portable uv into" >&2
  echo "        this folder and needs nothing preinstalled." >&2
  exit 1
fi

echo "==> Syncing Python dependencies (uv sync)..."
echo "    caches -> $UV_CACHE_DIR"
if ! uv sync; then
  echo >&2
  echo "[FATAL] uv sync failed -- see the error above." >&2
  exit 1
fi

echo "==> mangaEasy is ready. Start with:"
echo "      uv run mangaeasy modes        # show the manga-video catalog"
echo "      uv run mangaeasy where --json # resolved paths + version"
echo "      uv run mangaeasy env --check  # confirm nothing writes outside this folder"
echo "      uv run mangaeasy setup        # download portable ffmpeg + AI tools"
echo "      uv run mangaeasy mcp          # run the MCP server for an agent host"
echo
uv run mangaeasy --help
