@echo off
REM Pin every cache inside this install folder — the cmd.exe half of
REM mangaeasy/isolation.py. See scripts/isolate.sh for why this must be shell:
REM `uv sync` downloads the interpreter and every wheel before any of our
REM Python runs, so by the time isolation.py could act, uv has already written
REM to %LOCALAPPDATA%\uv\cache.
REM
REM Called by run.bat and bootstrap.ps1's cmd path. Do not run directly.
REM   MANGAEASY_INSTALL_ROOT must already be set.
REM
REM tests/test_isolation.py asserts this file and isolation.py agree on every
REM variable — if you add one here, add it there too.

if not defined MANGAEASY_INSTALL_ROOT (
  echo [FATAL] isolate.cmd: MANGAEASY_INSTALL_ROOT is not set. 1>&2
  exit /b 1
)

set "_ME_CACHE=%MANGAEASY_INSTALL_ROOT%\runtime\cache"

if /i "%MANGAEASY_SHARE_CACHES%"=="1" goto :share
if /i "%MANGAEASY_SHARE_CACHES%"=="true" goto :share

REM Default: force, so an ambient HF_HOME cannot redirect multi-GB downloads.
set "UV_CACHE_DIR=%_ME_CACHE%\uv"
set "UV_PYTHON_INSTALL_DIR=%_ME_CACHE%\uv_python"
set "HF_HOME=%_ME_CACHE%\hf"
set "HF_HUB_CACHE=%_ME_CACHE%\hf\hub"
set "TRANSFORMERS_CACHE=%_ME_CACHE%\hf\hub"
set "TORCH_HOME=%_ME_CACHE%\torch"
set "TORCH_EXTENSIONS_DIR=%_ME_CACHE%\torch_extensions"
set "TORCHINDUCTOR_CACHE_DIR=%_ME_CACHE%\torchinductor"
set "TRITON_CACHE_DIR=%_ME_CACHE%\triton"
set "XDG_CACHE_HOME=%_ME_CACHE%\xdg"
goto :common

:share
REM Deliberate opt-out: only fill in what is missing.
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=%_ME_CACHE%\uv"
if not defined UV_PYTHON_INSTALL_DIR set "UV_PYTHON_INSTALL_DIR=%_ME_CACHE%\uv_python"
if not defined HF_HOME set "HF_HOME=%_ME_CACHE%\hf"
if not defined HF_HUB_CACHE set "HF_HUB_CACHE=%_ME_CACHE%\hf\hub"
if not defined TRANSFORMERS_CACHE set "TRANSFORMERS_CACHE=%_ME_CACHE%\hf\hub"
if not defined TORCH_HOME set "TORCH_HOME=%_ME_CACHE%\torch"
if not defined TORCH_EXTENSIONS_DIR set "TORCH_EXTENSIONS_DIR=%_ME_CACHE%\torch_extensions"
if not defined TORCHINDUCTOR_CACHE_DIR set "TORCHINDUCTOR_CACHE_DIR=%_ME_CACHE%\torchinductor"
if not defined TRITON_CACHE_DIR set "TRITON_CACHE_DIR=%_ME_CACHE%\triton"
if not defined XDG_CACHE_HOME set "XDG_CACHE_HOME=%_ME_CACHE%\xdg"

:common
REM The venv itself — explicit so an inherited value cannot relocate it.
set "UV_PROJECT_ENVIRONMENT=%MANGAEASY_INSTALL_ROOT%\.venv"

if not defined HF_HUB_DISABLE_TELEMETRY set "HF_HUB_DISABLE_TELEMETRY=1"
if not defined HF_XET_HIGH_PERFORMANCE set "HF_XET_HIGH_PERFORMANCE=1"
if not defined TOKENIZERS_PARALLELISM set "TOKENIZERS_PARALLELISM=false"

if not exist "%_ME_CACHE%" mkdir "%_ME_CACHE%" >nul 2>nul

REM Prefer this install's own portable binaries over anything on the system PATH.
set "_ME_VENDOR=%MANGAEASY_INSTALL_ROOT%\runtime\tools\_vendor"
if exist "%_ME_VENDOR%\ffmpeg\bin"  set "PATH=%_ME_VENDOR%\ffmpeg\bin;%PATH%"
if exist "%_ME_VENDOR%\uv\bin"      set "PATH=%_ME_VENDOR%\uv\bin;%PATH%"
if exist "%_ME_VENDOR%\git-lfs\bin" set "PATH=%_ME_VENDOR%\git-lfs\bin;%PATH%"

set "_ME_CACHE="
set "_ME_VENDOR="
exit /b 0
