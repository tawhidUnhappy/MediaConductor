# Zero-prerequisite setup for mangaEasy (Windows).
#
# Needs only Windows PowerShell 5+ — everything else is downloaded as a
# portable binary INTO THIS FOLDER and nothing is installed on the system:
#
#   1. portable uv        -> .\runtime\tools\_vendor\uv\bin\
#   2. a private Python   -> .\runtime\cache\uv_python\
#   3. the mangaEasy venv -> .\.venv\
#   4. portable ffmpeg    -> .\runtime\tools\_vendor\ffmpeg\bin\
#      + git-lfs
#
# Delete this folder and the machine is exactly as it was. Nothing is written
# to %LOCALAPPDATA%, %APPDATA% or Program Files, and no PATH entry is added.
#
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 -WithTools
#
# Re-running is safe: each step is skipped when it is already done.

[CmdletBinding()]
param(
    # Also run `mangaeasy setup` (AI tool envs + model weights, several GB).
    [switch]$WithTools
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Keep in sync with UV_VERSION in mangaeasy/tools/vendored.py.
$UvVersion = '0.11.16'

$Root = $PSScriptRoot
Set-Location $Root
$env:MANGAEASY_INSTALL_ROOT = $Root

$PythonVersion = '3.12'
$pinFile = Join-Path $Root '.python-version'
if (Test-Path $pinFile) {
    $pinned = (Get-Content $pinFile -Raw).Trim()
    if ($pinned) { $PythonVersion = $pinned }
}

# ── Isolation: pin every cache inside this folder ─────────────────────────────
# This must happen before uv runs — uv sync downloads the interpreter and every
# wheel, and would otherwise fill %LOCALAPPDATA%\uv\cache. Mirrors
# scripts/isolate.cmd and mangaeasy/isolation.py (tests assert they agree).
$Cache = Join-Path $Root 'runtime\cache'
$share = $env:MANGAEASY_SHARE_CACHES -in @('1', 'true', 'True')

function Set-IsolatedVar([string]$Name, [string]$Value) {
    # Force by default; only fill gaps when sharing was explicitly requested.
    if ($share -and [Environment]::GetEnvironmentVariable($Name)) { return }
    Set-Item -Path "env:$Name" -Value $Value
}

Set-IsolatedVar 'UV_CACHE_DIR'             (Join-Path $Cache 'uv')
Set-IsolatedVar 'UV_PYTHON_INSTALL_DIR'    (Join-Path $Cache 'uv_python')
Set-IsolatedVar 'HF_HOME'                  (Join-Path $Cache 'hf')
Set-IsolatedVar 'HF_HUB_CACHE'             (Join-Path $Cache 'hf\hub')
Set-IsolatedVar 'TRANSFORMERS_CACHE'       (Join-Path $Cache 'hf\hub')
Set-IsolatedVar 'TORCH_HOME'               (Join-Path $Cache 'torch')
Set-IsolatedVar 'TORCH_EXTENSIONS_DIR'     (Join-Path $Cache 'torch_extensions')
Set-IsolatedVar 'TORCHINDUCTOR_CACHE_DIR'  (Join-Path $Cache 'torchinductor')
Set-IsolatedVar 'TRITON_CACHE_DIR'         (Join-Path $Cache 'triton')
Set-IsolatedVar 'XDG_CACHE_HOME'           (Join-Path $Cache 'xdg')
$env:UV_PROJECT_ENVIRONMENT = Join-Path $Root '.venv'
if (-not $env:HF_HUB_DISABLE_TELEMETRY) { $env:HF_HUB_DISABLE_TELEMETRY = '1' }
if (-not $env:HF_XET_HIGH_PERFORMANCE)  { $env:HF_XET_HIGH_PERFORMANCE  = '1' }
if (-not $env:TOKENIZERS_PARALLELISM)   { $env:TOKENIZERS_PARALLELISM   = 'false' }
New-Item -ItemType Directory -Force -Path $Cache | Out-Null

$Vendor = Join-Path $Root 'runtime\tools\_vendor'
$UvBin  = Join-Path $Vendor 'uv\bin'

# ── 0. Platform + the matching portable uv asset ──────────────────────────────
$arch = $env:PROCESSOR_ARCHITECTURE
if ($arch -notin @('AMD64', 'x86_64')) {
    throw "Only x64 Windows has a portable uv build here (found $arch). Install uv manually, then run run.bat."
}
$UvAsset = 'uv-x86_64-pc-windows-msvc.zip'
# The digest mangaeasy/tools/vendored.py verifies; a mismatch means a tampered
# or truncated download, so we refuse rather than execute it.
$UvSha   = 'dd9d6d6554bfab265bfa98aa8e8a406c5c3a7b97582f93de1f4d48d9154a0395'

Write-Host "mangaEasy bootstrap - windows/x64, Python $PythonVersion"
Write-Host "Install root: $Root"
Write-Host "Nothing is written outside it."
Write-Host ""

# ── 1. Portable uv ────────────────────────────────────────────────────────────
Write-Host "=== 1/4  portable uv ==="
$uvExe = Join-Path $UvBin 'uv.exe'
if (Test-Path $uvExe) {
    Write-Host "    already present: $uvExe"
} else {
    New-Item -ItemType Directory -Force -Path $UvBin | Out-Null
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("mangaeasy-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/$UvAsset"
        Write-Host "    downloading $url"
        $archive = Join-Path $tmp $UvAsset
        # TLS 1.2 for Windows PowerShell 5, whose default is often too old.
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing

        $got = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLower()
        if ($got -ne $UvSha) {
            throw "SHA-256 mismatch for $UvAsset`n        expected $UvSha`n        received $got`n        Refusing to run an unverified binary."
        }
        Write-Host "    sha256 ok"

        Expand-Archive -Path $archive -DestinationPath $tmp -Force
        foreach ($name in @('uv.exe', 'uvx.exe')) {
            $found = Get-ChildItem -Path $tmp -Filter $name -Recurse -File | Select-Object -First 1
            if (-not $found) { throw "$name not found inside $UvAsset" }
            Copy-Item $found.FullName (Join-Path $UvBin $name) -Force
        }
        Write-Host "    installed -> $UvBin"
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}
$env:PATH = "$UvBin;$env:PATH"
& $uvExe --version
Write-Host ""

# ── 2. A Python interpreter inside the folder ─────────────────────────────────
Write-Host "=== 2/4  private Python $PythonVersion ==="
Write-Host "    -> $env:UV_PYTHON_INSTALL_DIR"
& $uvExe python install $PythonVersion
if ($LASTEXITCODE -ne 0) { throw "uv python install failed" }
Write-Host ""

# ── 3. The mangaEasy environment ──────────────────────────────────────────────
Write-Host "=== 3/4  mangaEasy dependencies ==="
Write-Host "    wheel cache -> $env:UV_CACHE_DIR"
& $uvExe sync --python $PythonVersion
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
Write-Host ""

# ── 4. Portable ffmpeg / git-lfs ──────────────────────────────────────────────
Write-Host "=== 4/4  portable ffmpeg + git-lfs ==="
& $uvExe run --no-sync mangaeasy bootstrap-tools
Write-Host ""

if ($WithTools) {
    Write-Host "=== AI tool environments (this downloads several GB) ==="
    & $uvExe run --no-sync mangaeasy setup
    Write-Host ""
}

Write-Host "=== Verifying isolation ==="
& $uvExe run --no-sync mangaeasy env --check | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "    OK - every cache resolves inside $Root"
} else {
    Write-Host "    WARNING - something resolves outside the install folder (see above)"
}
Write-Host ""
Write-Host "Done. Use it with:"
Write-Host "    cd $Root"
Write-Host "    .\run.bat                      # re-sync and show the command list"
Write-Host "    uv run mangaeasy where --json  # resolved paths"
if (-not $WithTools) {
    Write-Host "    uv run mangaeasy setup         # AI tool envs + models (several GB)"
}
Write-Host "    uv run mangaeasy smoke-test    # prove it renders a real video"
