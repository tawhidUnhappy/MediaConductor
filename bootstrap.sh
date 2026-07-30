#!/usr/bin/env bash
# Zero-prerequisite setup for mangaEasy (Linux/macOS).
#
# Needs only bash, curl (or wget) and tar — everything else is downloaded as a
# portable binary INTO THIS FOLDER and nothing is installed on the system:
#
#   1. portable uv        -> ./runtime/tools/_vendor/uv/bin/
#   2. a private Python   -> ./runtime/cache/uv_python/
#   3. the mangaEasy venv -> ./.venv/
#   4. portable ffmpeg    -> ./runtime/tools/_vendor/ffmpeg/bin/
#      + git-lfs
#
# Delete this folder and the machine is exactly as it was. Nothing is written
# to ~/.cache, ~/.local or /usr.
#
#   ./bootstrap.sh                 core setup, no AI tool envs
#   ./bootstrap.sh --with-tools     also run `mangaeasy setup` (multi-GB models)
#
# Re-running is safe: each step is skipped when it is already done.
set -euo pipefail

UV_VERSION="0.11.16"   # keep in sync with UV_VERSION in mangaeasy/tools/vendored.py
PYTHON_VERSION="$(cat "$(dirname "${BASH_SOURCE[0]:-$0}")/.python-version" 2>/dev/null || echo 3.12)"

cd "$(dirname "${BASH_SOURCE[0]:-$0}")"
MANGAEASY_INSTALL_ROOT="$(pwd -P)"
export MANGAEASY_INSTALL_ROOT

WITH_TOOLS=0
for arg in "$@"; do
  case "$arg" in
    --with-tools) WITH_TOOLS=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "[FATAL] unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# shellcheck source=scripts/isolate.sh
. "$MANGAEASY_INSTALL_ROOT/scripts/isolate.sh"

VENDOR="$MANGAEASY_INSTALL_ROOT/runtime/tools/_vendor"
UV_BIN="$VENDOR/uv/bin"

say() { printf '%s\n' "$*"; }
die() { printf '[FATAL] %s\n' "$*" >&2; exit 1; }

# ── 0. Platform + the matching portable uv asset ──────────────────────────────
# Digests are the same ones mangaeasy/tools/vendored.py verifies; a mismatch
# here means a tampered or truncated download, so we refuse rather than run it.
case "$(uname -s)" in
  Linux)  OS=linux ;;
  Darwin) OS=darwin ;;
  *) die "unsupported OS: $(uname -s). Windows: use bootstrap.ps1." ;;
esac
case "$(uname -m)" in
  x86_64|amd64) ARCH=x64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) die "unsupported architecture: $(uname -m)" ;;
esac

case "$OS/$ARCH" in
  linux/x64)
    UV_ASSET="uv-x86_64-unknown-linux-gnu.tar.gz"
    UV_SHA="74947fe2c03315cf07e82ab3acc703eddef01aba4d5232a98e4c6825ec116131" ;;
  linux/arm64)
    UV_ASSET="uv-aarch64-unknown-linux-gnu.tar.gz"
    UV_SHA="8c9d0f0ee98166ae6ab198747519ba6f25db29d185bd2ae5960ecebc91a5c22a" ;;
  darwin/x64)
    UV_ASSET="uv-x86_64-apple-darwin.tar.gz"
    UV_SHA="6b91ae3de155f51bd1f5b74814821c79f016a176561f252cd9ddfb976939af2e" ;;
  darwin/arm64)
    UV_ASSET="uv-aarch64-apple-darwin.tar.gz"
    UV_SHA="2b25be1af546be330b340b0a76b99f989daa6d92678fdffb87438e661e9d88fb" ;;
  *) die "no portable uv build for $OS/$ARCH" ;;
esac

say "mangaEasy bootstrap — $OS/$ARCH, Python $PYTHON_VERSION"
say "Install root: $MANGAEASY_INSTALL_ROOT"
say "Nothing is written outside it."
say ""

fetch() {  # fetch <url> <dest>
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --proto '=https' --tlsv1.2 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --https-only -O "$2" "$1"
  else
    die "need curl or wget to download $1"
  fi
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else die "need sha256sum or shasum to verify downloads"
  fi
}

# ── 1. Portable uv ────────────────────────────────────────────────────────────
say "=== 1/4  portable uv ==="
if [ -x "$UV_BIN/uv" ]; then
  say "    already present: $UV_BIN/uv"
else
  mkdir -p "$UV_BIN"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$UV_ASSET"
  say "    downloading $url"
  fetch "$url" "$tmp/$UV_ASSET"
  got="$(sha256_of "$tmp/$UV_ASSET")"
  if [ "$got" != "$UV_SHA" ]; then
    die "SHA-256 mismatch for $UV_ASSET
        expected $UV_SHA
        received $got
        Refusing to run an unverified binary."
  fi
  say "    sha256 ok"
  tar -xzf "$tmp/$UV_ASSET" -C "$tmp"
  # The archive has one top-level dir containing uv and uvx.
  find "$tmp" -type f -name 'uv' -exec cp {} "$UV_BIN/uv" \;
  find "$tmp" -type f -name 'uvx' -exec cp {} "$UV_BIN/uvx" \;
  chmod +x "$UV_BIN/uv" "$UV_BIN/uvx"
  rm -rf "$tmp"
  trap - EXIT
  say "    installed -> $UV_BIN"
fi
PATH="$UV_BIN:$PATH"; export PATH
say "    $(uv --version)"
say ""

# ── 2. A Python interpreter inside the folder ─────────────────────────────────
say "=== 2/4  private Python $PYTHON_VERSION ==="
say "    -> $UV_PYTHON_INSTALL_DIR"
uv python install "$PYTHON_VERSION"
say ""

# ── 3. The mangaEasy environment ──────────────────────────────────────────────
say "=== 3/4  mangaEasy dependencies ==="
say "    wheel cache -> $UV_CACHE_DIR"
uv sync --python "$PYTHON_VERSION"
say ""

# ── 4. Portable ffmpeg / git-lfs ──────────────────────────────────────────────
say "=== 4/4  portable ffmpeg + git-lfs ==="
uv run --no-sync mangaeasy bootstrap-tools
say ""

if [ "$WITH_TOOLS" = "1" ]; then
  say "=== AI tool environments (this downloads several GB) ==="
  uv run --no-sync mangaeasy setup
  say ""
fi

say "=== Verifying isolation ==="
if uv run --no-sync mangaeasy env --check >/dev/null; then
  say "    OK — every cache resolves inside $MANGAEASY_INSTALL_ROOT"
else
  say "    WARNING — something resolves outside the install folder (see above)"
fi
say ""
say "Done. Use it with:"
say "    cd $MANGAEASY_INSTALL_ROOT"
say "    ./run.sh                      # re-sync and show the command list"
say "    uv run mangaeasy where --json # resolved paths"
if [ "$WITH_TOOLS" != "1" ]; then
  say "    uv run mangaeasy setup        # AI tool envs + models (several GB)"
fi
say "    uv run mangaeasy smoke-test    # prove it renders a real video"
