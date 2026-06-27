@echo off
REM One-command launcher for mangaEasy from a source checkout (Windows).
REM Syncs Python deps, builds the desktop app if needed, then opens it.
REM
REM Usage: double-click run.bat (or a shortcut to it), or run it from a
REM terminal in the repo root.
setlocal
title mangaEasy launcher
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
  pause
  exit /b 1
)

echo ==^> Syncing Python dependencies (uv sync)...
call uv sync
if errorlevel 1 (
  echo.
  echo [FATAL] uv sync failed -- see the error above.
  pause
  exit /b 1
)

if not exist "desktop\out\main\index.js" goto build_desktop
if not exist "desktop\node_modules\electron" goto build_desktop
goto launch

:build_desktop
where npm >nul 2>nul
if not errorlevel 1 goto have_npm

REM No system Node -- vendor a portable copy into .mangaeasy\tools (same
REM self-contained dir ffmpeg/uv/git-lfs use) instead of requiring a real
REM install. Nothing is committed to the repo; this only runs once.
echo ==^> No npm found, fetching a portable Node.js for this install...
call uv run mangaeasy ensure-node
if errorlevel 1 (
  echo.
  echo [FATAL] Could not fetch a portable Node.js automatically.
  echo         Install Node 22+ yourself from https://nodejs.org/ and re-run.
  echo.
  pause
  exit /b 1
)
set "PATH=%~dp0.mangaeasy\tools\_vendor\node;%PATH%"

where npm >nul 2>nul
if errorlevel 1 (
  echo [FATAL] Node.js/npm still not found after fetching it -- see the error above.
  echo.
  pause
  exit /b 1
)

:have_npm
echo ==^> Desktop app isn't built yet, building it (first run only)...
pushd desktop
call npm install
if errorlevel 1 (
  popd
  echo.
  echo [FATAL] npm install failed -- see the error above.
  pause
  exit /b 1
)
call npm run build
if errorlevel 1 (
  popd
  echo.
  echo [FATAL] npm run build failed -- see the error above.
  pause
  exit /b 1
)
popd

:launch
echo ==^> Launching mangaEasy...
call uv run mangaeasy app
if errorlevel 1 (
  echo.
  echo [FATAL] mangaeasy app exited with an error -- see above.
  pause
  exit /b 1
)
endlocal
