@echo off
REM One-command bootstrap for mangaEasy from a source checkout (Windows).
REM mangaEasy is a CLI + MCP server for LLM agents. This syncs Python
REM dependencies and shows the curated command list.
REM
REM Everything it downloads stays inside this folder — see scripts\isolate.cmd.
REM If you have no uv yet, use bootstrap.ps1 instead; it fetches a portable one.
REM
REM Usage: run it from a terminal in the repo root.
setlocal
title mangaEasy
cd /d "%~dp0"
set "MANGAEASY_INSTALL_ROOT=%CD%"

REM Pin every cache under .\runtime\cache BEFORE uv runs — uv sync is what
REM downloads the interpreter and the wheels, and it would otherwise fill
REM %LOCALAPPDATA%\uv\cache. Also puts .\runtime\tools\_vendor\*\bin on PATH.
call "%MANGAEASY_INSTALL_ROOT%\scripts\isolate.cmd"
if errorlevel 1 exit /b 1

REM uv's installer adds %USERPROFILE%\.local\bin to your user PATH, but a
REM shortcut/double-click launches through Explorer, which can be running
REM with a PATH cached from before that install. Fall back to the known
REM install location if a plain `where uv` can't find it.
where uv >nul 2>nul
if errorlevel 1 if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>nul
if errorlevel 1 (
  echo [FATAL] uv is not installed or not on PATH.
  echo         Run bootstrap.ps1 instead -- it downloads a portable uv into
  echo         this folder and needs nothing preinstalled:
  echo             powershell -ExecutionPolicy Bypass -File bootstrap.ps1
  echo.
  exit /b 1
)

echo ==^> Syncing Python dependencies (uv sync)...
echo     caches -^> %UV_CACHE_DIR%
call uv sync
if errorlevel 1 (
  echo.
  echo [FATAL] uv sync failed -- see the error above.
  exit /b 1
)

echo ==^> mangaEasy is ready. Start with:
echo       uv run mangaeasy modes        ^(show the manga-video catalog^)
echo       uv run mangaeasy where --json ^(resolved paths + version^)
echo       uv run mangaeasy env --check  ^(confirm nothing writes outside this folder^)
echo       uv run mangaeasy setup        ^(download portable ffmpeg + AI tools^)
echo       uv run mangaeasy mcp          ^(run the MCP server for an agent host^)
echo.
call uv run mangaeasy --help
endlocal
