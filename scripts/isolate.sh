#!/usr/bin/env bash
# Pin every cache inside this install folder — the shell-side half of
# mangaeasy/isolation.py.
#
# Why this exists as shell at all: `uv sync` is what downloads the Python
# interpreter and every wheel, and it runs *before* any of our Python does.
# By the time mangaeasy/isolation.py could set UV_CACHE_DIR, uv has already
# written ~200 MB to ~/.cache/uv. So the launchers export these first.
#
# Sourced by run.sh and bootstrap.sh. Do not run directly.
#
#   MANGAEASY_INSTALL_ROOT must already be set to the install directory.
#
# tests/test_isolation.py asserts this file and isolation.py agree on every
# variable and path — if you add one here, add it there (and vice versa).

if [ -z "${MANGAEASY_INSTALL_ROOT:-}" ]; then
  echo "[FATAL] isolate.sh: MANGAEASY_INSTALL_ROOT is not set." >&2
  return 1 2>/dev/null || exit 1
fi

_me_cache="$MANGAEASY_INSTALL_ROOT/runtime/cache"

if [ "${MANGAEASY_SHARE_CACHES:-}" = "1" ] || [ "${MANGAEASY_SHARE_CACHES:-}" = "true" ]; then
  # Deliberate opt-out: keep whatever the environment already says, and only
  # fill in the gaps. For someone sharing one model cache across checkouts.
  : "${UV_CACHE_DIR:=$_me_cache/uv}"
  : "${UV_PYTHON_INSTALL_DIR:=$_me_cache/uv_python}"
  : "${HF_HOME:=$_me_cache/hf}"
  : "${HF_HUB_CACHE:=$_me_cache/hf/hub}"
  : "${TRANSFORMERS_CACHE:=$_me_cache/hf/hub}"
  : "${TORCH_HOME:=$_me_cache/torch}"
  : "${TORCH_EXTENSIONS_DIR:=$_me_cache/torch_extensions}"
  : "${TORCHINDUCTOR_CACHE_DIR:=$_me_cache/torchinductor}"
  : "${TRITON_CACHE_DIR:=$_me_cache/triton}"
  : "${XDG_CACHE_HOME:=$_me_cache/xdg}"
else
  # Default: force. An ambient HF_HOME the user exported for another project
  # would otherwise silently redirect this install's multi-GB downloads.
  UV_CACHE_DIR="$_me_cache/uv"
  UV_PYTHON_INSTALL_DIR="$_me_cache/uv_python"
  HF_HOME="$_me_cache/hf"
  HF_HUB_CACHE="$_me_cache/hf/hub"
  TRANSFORMERS_CACHE="$_me_cache/hf/hub"
  TORCH_HOME="$_me_cache/torch"
  TORCH_EXTENSIONS_DIR="$_me_cache/torch_extensions"
  TORCHINDUCTOR_CACHE_DIR="$_me_cache/torchinductor"
  TRITON_CACHE_DIR="$_me_cache/triton"
  XDG_CACHE_HOME="$_me_cache/xdg"
fi

export UV_CACHE_DIR UV_PYTHON_INSTALL_DIR HF_HOME HF_HUB_CACHE TRANSFORMERS_CACHE
export TORCH_HOME TORCH_EXTENSIONS_DIR TORCHINDUCTOR_CACHE_DIR TRITON_CACHE_DIR
export XDG_CACHE_HOME

# The venv itself. uv defaults to <project>/.venv, which is already inside the
# folder — set it explicitly so an inherited UV_PROJECT_ENVIRONMENT cannot
# place it elsewhere.
export UV_PROJECT_ENVIRONMENT="$MANGAEASY_INSTALL_ROOT/.venv"

: "${HF_HUB_DISABLE_TELEMETRY:=1}";  export HF_HUB_DISABLE_TELEMETRY
: "${HF_XET_HIGH_PERFORMANCE:=1}";   export HF_XET_HIGH_PERFORMANCE
: "${TOKENIZERS_PARALLELISM:=false}"; export TOKENIZERS_PARALLELISM

mkdir -p "$_me_cache" 2>/dev/null || true

# Prefer this install's own portable binaries (ffmpeg, uv, git-lfs) over
# anything on the system PATH.
for _me_tool in ffmpeg uv git-lfs; do
  _me_bin="$MANGAEASY_INSTALL_ROOT/runtime/tools/_vendor/$_me_tool/bin"
  if [ -d "$_me_bin" ]; then
    PATH="$_me_bin:$PATH"
  fi
done
export PATH
unset _me_cache _me_tool _me_bin
