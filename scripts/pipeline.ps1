# Step-by-step manual execution script for mangaEasy pipeline (Windows)
param(
    [string]$ProjectName = "sample_recap",
    [string]$MangaDexUrl = "",
    [string]$Chapters = "01-05"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "data/library/$ProjectName"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Starting mangaEasy Pipeline for: $ProjectName" -ForegroundColor Cyan
Write-Host " Project Root: $ProjectRoot" -ForegroundColor Cyan
Write-Host "============================================================"

if ($MangaDexUrl) {
    Write-Host "`n--- Step 1: Downloading MangaDex Chapters ---" -ForegroundColor Yellow
    uv run mangaeasy download --url "$MangaDexUrl" --name "$ProjectName" --chapters "$Chapters"
} else {
    Write-Host "`nNo URL provided; using existing images in $ProjectRoot" -ForegroundColor Gray
}

Write-Host "`n--- Step 2: Detecting Format ---" -ForegroundColor Yellow
uv run mangaeasy style-detect --project-root "$ProjectRoot" --json

Write-Host "`n--- Step 3: Cropping Panels ---" -ForegroundColor Yellow
uv run mangaeasy webtoon-split --project-root "$ProjectRoot" --item-range "$Chapters"

Write-Host "`n--- Step 4: Generating Reading Sheets ---" -ForegroundColor Yellow
uv run mangaeasy panel-reading-sheets --project-root "$ProjectRoot" --item-range "$Chapters"

Write-Host "`n--- Step 5: Packing Sheets into ZIPs (<= 1 GB each) ---" -ForegroundColor Yellow
uv run mangaeasy sheets-pack --project-root "$ProjectRoot"

Write-Host "`n--- Step 6: Validating Narration ---" -ForegroundColor Yellow
uv run mangaeasy narration-check --project-root "$ProjectRoot" --item-range "$Chapters" --json

Write-Host "`n--- Step 7: Generating Audio (TTS) ---" -ForegroundColor Yellow
uv run mangaeasy video-audio --project-root "$ProjectRoot" --item-range "$Chapters" --tts auto

Write-Host "`n--- Step 8: Generating Subtitles (Whisper large-v3-turbo) ---" -ForegroundColor Yellow
uv run mangaeasy video-subtitles --project-root "$ProjectRoot"

Write-Host "`n--- Step 9: Rendering & Joining Videos ---" -ForegroundColor Yellow
uv run mangaeasy video --project-root "$ProjectRoot" --item-range "$Chapters" --build-long-video --normalize-audio

Write-Host "`n--- Step 10: Running Video Quality Gate ---" -ForegroundColor Yellow
uv run mangaeasy video-quality --project-root "$ProjectRoot" --json

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " Pipeline Execution Finished Successfully!" -ForegroundColor Green
Write-Host " Outputs stored in: $ProjectRoot/output/" -ForegroundColor Green
Write-Host " Subtitles stored in: $ProjectRoot/subtitles/" -ForegroundColor Green
Write-Host " Zips stored in:      $ProjectRoot/zips/" -ForegroundColor Green
Write-Host "============================================================"