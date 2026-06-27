@echo off
REM One-command launcher for mangaEasy from a source checkout (Windows).
REM Syncs Python deps, builds the desktop app if needed, then opens it.
REM
REM Usage: double-click run.bat, or run it from a terminal in the repo root.
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [FATAL] uv is not installed. Install it from https://docs.astral.sh/uv/ and re-run.
  exit /b 1
)

echo ==^> Syncing Python dependencies (uv sync)...
call uv sync
if errorlevel 1 exit /b 1

if not exist "desktop\out\main\index.js" goto build_desktop
if not exist "desktop\node_modules\electron" goto build_desktop
goto launch

:build_desktop
where npm >nul 2>nul
if errorlevel 1 (
  echo [FATAL] Node.js/npm is not installed. Install Node 22+ from https://nodejs.org/ and re-run.
  exit /b 1
)
echo ==^> Desktop app isn't built yet, building it (first run only)...
pushd desktop
call npm install
if errorlevel 1 (
  popd
  exit /b 1
)
call npm run build
if errorlevel 1 (
  popd
  exit /b 1
)
popd

:launch
echo ==^> Launching mangaEasy...
call uv run mangaeasy app
endlocal
