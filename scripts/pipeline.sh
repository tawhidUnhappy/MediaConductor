#!/usr/bin/env bash
# Step-by-step manual execution script for mangaEasy pipeline
set -e

PROJECT_NAME="${1:-sample_recap}"
MANGADEX_URL="${2}"
CHAPTERS="${3:-01-05}"
PROJECT_ROOT="data/library/${PROJECT_NAME}"

echo "============================================================"
echo " Starting mangaEasy Pipeline for: ${PROJECT_NAME}"
echo " Project Root: ${PROJECT_ROOT}"
echo "============================================================"

echo ""
echo "--- Step 1: Downloading MangaDex Chapters ---"
if [ -n "$MANGADEX_URL" ]; then
    uv run mangaeasy download --url "$MANGADEX_URL" --name "$PROJECT_NAME" --chapters "$CHAPTERS"
else
    echo "No URL provided; skipping download (using existing images)."
fi

echo ""
echo "--- Step 2: Detecting Format (Webtoon vs Paged) ---"
uv run mangaeasy style-detect --project-root "$PROJECT_ROOT" --json

echo ""
echo "--- Step 3: Cropping Panels ---"
uv run mangaeasy webtoon-split --project-root "$PROJECT_ROOT" --item-range "$CHAPTERS"

echo ""
echo "--- Step 4: Generating Reading Sheets ---"
uv run mangaeasy panel-reading-sheets --project-root "$PROJECT_ROOT" --item-range "$CHAPTERS"

echo ""
echo "--- Step 5: Packing Sheets into ZIPs (<= 1 GB each) ---"
uv run mangaeasy sheets-pack --project-root "$PROJECT_ROOT"

echo ""
echo "--- Step 6: Validating Narration Structure ---"
uv run mangaeasy narration-check --project-root "$PROJECT_ROOT" --item-range "$CHAPTERS" --json

echo ""
echo "--- Step 7: Generating Audio (TTS) ---"
uv run mangaeasy video-audio --project-root "$PROJECT_ROOT" --item-range "$CHAPTERS" --tts auto

echo ""
echo "--- Step 8: Generating Subtitles (Whisper large-v3-turbo) ---"
uv run mangaeasy video-subtitles --project-root "$PROJECT_ROOT"

echo ""
echo "--- Step 9: Rendering & Joining Videos ---"
uv run mangaeasy video --project-root "$PROJECT_ROOT" --item-range "$CHAPTERS" --build-long-video --normalize-audio

echo ""
echo "--- Step 10: Running Video Quality Gate ---"
uv run mangaeasy video-quality --project-root "$PROJECT_ROOT" --json

echo ""
echo "============================================================"
echo " Pipeline Execution Finished Successfully!"
echo " Outputs stored in: ${PROJECT_ROOT}/output/"
echo " Subtitles stored in: ${PROJECT_ROOT}/subtitles/"
echo " Zips stored in:      ${PROJECT_ROOT}/zips/"
echo "============================================================"