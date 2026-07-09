@echo off
REM One-command bootstrap for mangaEasy from a source checkout (Windows).
REM mangaEasy is a CLI + MCP tool for LLM agents -- there is no GUI. This syncs
REM Python deps and shows the command list; drive it with `uv run mangaeasy ...`.
REM
REM Usage: run it from a terminal in the repo root.
setlocal
title mangaEasy
cd /d "%~dp0"

REM uv's installer adds %USERPROFILE%\.local\bin to your user PATH, but a
REM shortcut/double-click launches through Explorer, which can be running
REM with a PATH cached from before that install. Fall back to the known
REM install location if a plain `where uv` can't find it.
where uv >nul 2>nul
if errorlevel 1 if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"

where uv >nul 2>nul
if errorlevel 1 (
  echo [FATAL] uv is not installed or not on PATH.
  echo         Install it from https://docs.astral.sh/uv/ and re-run.
  echo.
  exit /b 1
)

echo ==^> Syncing Python dependencies (uv sync)...
call uv sync
if errorlevel 1 (
  echo.
  echo [FATAL] uv sync failed -- see the error above.
  exit /b 1
)

echo ==^> mangaEasy is ready. Start with:
echo       uv run mangaeasy where --json      ^(resolved paths + version^)
echo       uv run mangaeasy commands          ^(the full command list^)
echo       uv run mangaeasy mcp               ^(run the MCP server for an agent host^)
echo.
call uv run mangaeasy --help
endlocal
