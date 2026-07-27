"""mediaconductor.command_spec — the single declarative source for command schemas.

One table describes every agent-facing command: its MCP tool name, its CLI
name, a description, JSON-schema properties, required arguments, and how each
property maps onto CLI flags. Both consumers read from here:

- `mediaconductor mcp` (mediaconductor/mcp_server.py) serves these as MCP tool schemas
  and builds argv from the flag mappings.
- `mediaconductor commands --json --full` (mediaconductor/cli.py) publishes the same
  schemas so a shell agent can discover a command's arguments without running
  sixty separate `--help` calls.

Adding a flag to a subcommand's argparse? Add it here too — this table is
what agents see. (Historically the MCP server kept its own private copy of
all of this, which could silently drift from the real argparse; now there is
exactly one copy and two renderers.)

Flag spec kinds: "value" (--flag VALUE), "json" (--flag JSON_OBJECT), "flag" (--flag when true),
"no-flag" (--no-flag when false), "list" (--flag V1 V2 ...),
"repeat" (--flag V1 --flag V2 ..., for argparse action="append" flags),
"positional" (bare value).
"""

from __future__ import annotations

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_YOUTUBE_PROFILE = {
    "type": "string",
    "pattern": r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$",
    "default": "default",
    "description": "Isolated YouTube account profile (default: default; e.g. manga-main).",
}
_YOUTUBE_AUTO_AUTH = {
    "type": "boolean",
    "default": True,
    "description": "Open Google browser consent automatically when the selected profile has "
                   "no usable token. Set false for headless/noninteractive operation.",
}
_ITEMS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Item/chapter folder names or ranges, e.g. [\"01\", \"05-08\"]. "
                   "WARNING: omitting selects EVERY item in the project — for expensive "
                   "generation commands always pass the explicit batch.",
}
_PROJECT_ROOT = {
    "type": "string",
    "description": "Absolute path to the folder containing the item folders (usually data/library/<project>).",
}
# MCP tool name -> (cli command, description, {property: schema}, [required], {property: flag spec})
TOOLS: dict[str, tuple[str, str, dict, list[str], dict]] = {
    "modes": (
        "modes",
        "Show the manga-video production catalog, dependencies, and MCP restart command.",
        {"mode": {"type": "string", "enum": ["manga-video"]}},
        [], {"mode": ("--mode", "value")},
    ),
    "setup": (
        "setup",
        "One-command provisioning: core binaries (ffmpeg/uv/git-lfs) + AI tool envs + model "
        "downloads, GPU-aware. VERY LONG-RUNNING on first run (tens of GB with a GPU) — prefer "
        "job_start. Safe to re-run — updates/resumes instead of reinstalling. Set dry_run=true "
        "to preview the plan.",
        {"all": {**_BOOL, "description": "Install every tool regardless of hardware."},
         "minimal": {**_BOOL, "description": "Core binaries only; no AI tool envs."},
         "mode": {"type": "string", "enum": ["manga-video"],
                  "description": "Install the manga-video toolchain."},
         "skip": {"type": "array", "items": {"type": "string"},
                  "description": "Optional manga tool names to skip, e.g. [\"deepseek-ocr2\"]."},
         "skip_models": _BOOL, "cpu": _BOOL, "cuda": _BOOL, "dry_run": _BOOL},
        [],
        {"all": ("--all", "flag"), "minimal": ("--minimal", "flag"),
         "mode": ("--mode", "value"), "skip": ("--skip", "repeat"),
         "skip_models": ("--skip-models", "flag"), "cpu": ("--cpu", "flag"),
         "cuda": ("--cuda", "flag"), "dry_run": ("--dry-run", "flag")},
    ),
    "download": (
        "download",
        "Download chapters from MangaDex — politely (API spacing, 429 backoff, jittered delays) "
        "and resumable. Pass the title URL directly; all=true grabs the whole series start to "
        "end in English (LONG-RUNNING — prefer job_start; already-complete chapters are skipped).",
        {"url": {**_STR, "description": "MangaDex title URL or manga UUID."},
         "name": {**_STR, "description": "Library folder name; derived from the title if omitted."},
         "chapters": {"type": "array", "items": {"type": "string"},
                      "description": "Specific chapters/ranges, e.g. [\"0-12\", \"14\"]."},
         "all": {**_BOOL, "description": "Every chapter available in the language."},
         "from_chapter": {**_NUM, "description": "With all: skip chapters below this number."},
         "to_chapter": {**_NUM, "description": "With all: skip chapters above this number."},
         "fresh": {**_BOOL, "description": "Bypass the local metadata cache."}},
        [],
        {"url": ("--url", "value"), "name": ("--name", "value"),
         "chapters": ("--chapters", "list"), "all": ("--all", "flag"),
         "from_chapter": ("--from", "value"), "to_chapter": ("--to", "value"),
         "fresh": ("--fresh", "flag")},
    ),
    "style_detect": (
        "style-detect",
        "Detect webtoon (vertical strips -> webtoon_split) vs paged manga (-> page_split) from "
        "the downloaded page dimensions. Returns a verdict plus sample image paths to confirm "
        "visually before cropping.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "source_subdir": {**_STR, "description": "Page-image folder inside each item (default: download)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "source_subdir": ("--source-subdir", "value")},
    ),
    "webtoon_split": (
        "webtoon-split",
        "Crop webtoon items into panels (gutter detection + auto-split + gap rescue) and write "
        "verify sheets. Exit 3 means crops were generated but are NOT approved. A vision-capable "
        "reviewer must open every verify image and full-resolution crop, resolve suspects, "
        "forced cuts, content drops, and any withheld automatic full-source result against the "
        "source art, then re-split any fixes.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "source_subdir": {**_STR, "description": "Page-image folder inside each item (default: download)."},
         "work_dir": {**_STR, "description": "Work dir for verify sheets (default: data/work)."},
         "overrides": {**_STR, "description": "JSON file with per-item split_at/merge fixes."},
         "force_style": {**_BOOL, "description": "Bypass the webtoon-vs-paged pre-flight guard "
                                                 "(only for deliberate mixed-format items)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "source_subdir": ("--source-subdir", "value"),
         "work_dir": ("--work-dir", "value"), "overrides": ("--overrides", "value"),
         "force_style": ("--force-style", "flag")},
    ),
    "webtoon_cutcheck": (
        "webtoon-cutcheck",
        "Render full-resolution review windows around every forced auto-split cut and short "
        "panel from webtoon-split's ranges manifests, montaged into sheets. Exit 3 means the "
        "review artifacts are ready but not approved. Use sheets only as an index, then open "
        "EVERY image listed in emitted review_windows at full resolution and judge the art "
        "(FIX = cut through "
        "figure/speech bubble; ACCEPT = "
        "background/effect art, banners, bordered thin panels) before narrating.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "source_subdir": {**_STR, "description": "Page-image folder inside each item (default: download)."},
         "work_dir": {**_STR, "description": "Work dir holding webtoon_verify manifests (default: data/work)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "source_subdir": ("--source-subdir", "value"),
         "work_dir": ("--work-dir", "value")},
    ),
    "webtoon_override": (
        "webtoon-override",
        "Add merge/split fixes to a webtoon-split overrides file with indices resolved from "
        "the ranges manifest — never compute merge indices by hand. merge_at_cut undoes a bad "
        "auto-split cut at stitched y; merge_panels fuses current panels 'A,B' (1-based sheet "
        "numbers); split_at forces a cut at y. Re-run webtoon-split with the file after.",
        {"file": {**_STR, "description": "Overrides JSON to create/extend."},
         "project_root": _PROJECT_ROOT,
         "item": {**_STR, "description": "Item the fixes apply to, e.g. '01'."},
         "merge_at_cut": {"type": "array", "items": {"type": "string"},
                          "description": "Stitched y values of bad cuts to undo."},
         "merge_panels": {"type": "array", "items": {"type": "string"},
                          "description": "Panel pairs to fuse, each 'A,B' (1-based)."},
         "split_at": {"type": "array", "items": {"type": "string"},
                      "description": "Stitched y values to force cuts at."},
         "show": {**_BOOL, "description": "Print the resolved overrides file."}},
        ["file", "project_root"],
        {"file": ("--file", "value"), "project_root": ("--project-root", "value"),
         "item": ("--item", "value"), "merge_at_cut": ("--merge-at-cut", "repeat"),
         "merge_panels": ("--merge-panels", "repeat"), "split_at": ("--split-at", "repeat"),
         "show": ("--show", "flag")},
    ),
    "panels_remap": (
        "panels-remap",
        "After re-running webtoon-split, map the archived old panels to the new crops and carry "
        "narration + audio over (texts verbatim, WAVs copied/concatenated) instead of "
        "re-narrating. Dry run by default; set apply=true once the report shows zero orphans. "
        "Review every shift/merge panel with narration-review-sheets afterwards.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "source_subdir": {**_STR, "description": "Page-image folder inside each item (default: download)."},
         "audio_root": {**_STR, "description": "Audio root (default: data/audio)."},
         "old_run": {**_STR, "description": "Archive run (e.g. run_0002) the narration was written against."},
         "apply": {**_BOOL, "description": "Write narration.json + audio (default: dry-run report)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "source_subdir": ("--source-subdir", "value"),
         "audio_root": ("--audio-root", "value"), "old_run": ("--old-run", "value"),
         "apply": ("--apply", "flag")},
    ),
    "page_split": (
        "page-split",
        "Crop paged manga into panels with MAGI v3 detection (needs install-tool magi-v3; "
        "LONG-RUNNING — prefer job_start) and write verify overlays. MAGI boxes are proposals: "
        "automatic no-detection/full-page results are withheld for manual boxes. Exit 3 means "
        "a vision-capable reviewer must inspect every page overlay and every actual crop at "
        "full resolution, including full/tall boxes and reading-order numbers, before narration.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "source_subdir": {**_STR, "description": "Page-image folder inside each item (default: download)."},
         "work_dir": {**_STR, "description": "Work dir for verify sheets (default: data/work)."},
         "overrides": {**_STR, "description": "JSON file with per-page box fixes."},
         "device": {"type": "string", "enum": ["auto", "cuda", "cpu"]},
         "force_style": {**_BOOL, "description": "Bypass the webtoon-vs-paged pre-flight guard "
                                                 "(only for deliberate mixed-format items)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "source_subdir": ("--source-subdir", "value"),
         "work_dir": ("--work-dir", "value"), "overrides": ("--overrides", "value"),
         "device": ("--device", "value"), "force_style": ("--force-style", "flag")},
    ),
    "narration_check": (
        "narration-check",
        "Validate narration.json/intro.json structure per item: files parse, every entry's image "
        "exists, image/audio stems are unique, and no narration is empty. Deliberately omitted "
        "panels are warnings. Semantic accuracy and speaker attribution still require a "
        "vision-capable reviewer reading the original panels.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list")},
    ),
    "panel_transcript": (
        "panel-transcript",
        "Optionally OCR panels into <item>/transcript.json with DeepSeek-OCR 2 (needs "
        "install-tool deepseek-ocr2; LONG-RUNNING — prefer job_start). OCR is an untrusted "
        "cross-check, never a substitute for reading panel pixels/bubble tails. Values are "
        "SHA-256-bound to each crop so re-cropping invalidates stale text.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "force": {**_BOOL, "description": "Re-OCR panels that already have an ocr value."},
         "device": {"type": "string", "enum": ["auto", "cuda", "cpu"]},
         "seed_only": {**_BOOL, "description": "Write transcript skeletons without running OCR."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "force": ("--force", "flag"), "device": ("--device", "value"),
         "seed_only": ("--seed-only", "flag")},
    ),
    "narration_edit": (
        "narration-edit",
        "Upsert/delete/list narration.json (or intro.json) entries without hand-editing "
        "JSON. set_json takes a JSON array [{\"image\", \"narration\"}] inline; new images "
        "are inserted in name-sorted (reading) order; prune_audio deletes the WAVs of "
        "changed entries so the next audio run regenerates exactly those.",
        {"project_root": _PROJECT_ROOT,
         "item": {**_STR, "description": "Item folder, e.g. '01'."},
         "set_json": {**_STR, "description": "JSON array of entries to upsert."},
         "delete": {"type": "array", "items": {"type": "string"},
                    "description": "Image filenames whose entries to remove."},
         "intro": {**_BOOL, "description": "Edit intro.json instead of narration.json."},
         "prune_audio": {**_BOOL, "description": "Delete stale WAVs of changed entries."},
         "list": {**_BOOL, "description": "Print entries after any edits."}},
        ["project_root", "item"],
        {"project_root": ("--project-root", "value"), "item": ("--item", "value"),
         "set_json": ("--set-json", "value"), "delete": ("--delete", "repeat"),
         "intro": ("--intro", "flag"), "prune_audio": ("--prune-audio", "flag"),
         "list": ("--list", "flag")},
    ),
    "narration_review_sheets": (
        "narration-review-sheets",
        "Render sheets pairing every narration entry's panel image with the narration text and "
        "an optional UNVERIFIED OCR hint. Exit 3 means the review artifacts are ready but not "
        "approved. Read EVERY sheet and open every original panel: pixels, bubble tails, and "
        "sequence are authoritative. Verify one current beat, speaker attribution, factual "
        "grounding, natural causal prose, and spoken flow.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "work_dir": {**_STR, "description": "Scratch root (default: data/work)."},
         "output_root": {**_STR, "description": "Review-sheet output root."},
         "per_sheet": {**_INT, "description": "Entries per review sheet (default: 4)."},
         "only_images": {"type": "array", "items": {"type": "string"},
                         "description": "Limit to these image names (e.g. panels-remap's review list)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "work_dir": ("--work-dir", "value"), "output_root": ("--output-root", "value"),
         "per_sheet": ("--per-sheet", "value"),
         "only_images": ("--only-images", "list")},
    ),
    "thumbnail_candidates": (
        "thumbnail-candidates",
        "Shortlist the cropped panels worth using as a thumbnail base, and render numbered "
        "contact sheets of them. Scores each panel on detail, ink coverage, shape against "
        "16:9, and resolution. THE SCORE DOES NOT PICK THE THUMBNAIL: no pixel statistic "
        "knows which panel shows the reversal the title promises, or whether a composition "
        "reads as a sexualized minor. Open the shortlisted candidates at full resolution and "
        "choose by looking at them, exactly as with MAGI's panel proposals.",
        {"project_root": _PROJECT_ROOT,
         "items": _ITEMS,
         "item_range": {**_STR, "description": "Convenience range, e.g. 01-12."},
         "top": {**_INT, "description": "How many candidates to shortlist (default 20)."},
         "no_sheets": {**_BOOL, "description": "Score only; skip contact-sheet rendering."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "item_range": ("--item-range", "value"), "top": ("--top", "value"),
         "no_sheets": ("--no-sheets", "flag")},
    ),
    "thumbnail_compose": (
        "thumbnail-compose",
        "Compose a 1280x720 YouTube thumbnail from APPROVED SOURCE PANELS. There is no image "
        "generation in this path: the base pixels are always manga panels the crop review "
        "approved and rights.json lists under thumbnail_sources, because art the video does "
        "not contain is both a thumbnail-policy problem and a disappointment for whoever "
        "clicked. Four elements: 'blocks' (short ALL-CAPS hook words, yellow #FFE600, thick "
        "black stroke, -2..-5 degree rotate reads hand-placed), 'arrows' (fat block arrows "
        "pointing from a label to the character it names -- the most effective element in the "
        "reference set), 'bubbles' (a real line of dialogue in a dark bubble with white brush "
        "text, or a light bubble with black text), and 'badge' (the chapter range in a "
        "corner). Start from preset='label-arrow'|'bubble'|'split' and adjust. Pass check=true "
        "to get mechanical faults (off-canvas text, sub-44px text, collisions with each other "
        "or with YouTube's duration overlay) and exit 3. THEN OPEN THE IMAGE AND LOOK AT IT: "
        "the check knows nothing about whether the crop cuts a face, matches the title, or "
        "reads as explicit or minor-coded.",
        {"base": {"type": "array", "items": {"type": "string"},
                  "description": "Approved source panel path(s). Two or more = split layout."},
         "output": {**_STR, "description": "Absolute output PNG path."},
         "text": {"type": "array", "items": {"type": "string"},
                  "description": "Hook words (3-5 each). With preset, they fill its slots."},
         "preset": {**_STR, "enum": ["label-arrow", "bubble", "split"],
                    "description": "Worked starting layout to adjust."},
         "badge": {**_STR, "description": "Chapter-range stamp, e.g. '1-12'."},
         "badge_corner": {**_STR,
                          "enum": ["top-left", "top-right", "bottom-left", "top-center"],
                          "description": "Badge position (default top-left)."},
         "spec_json": {**_STR,
                       "description": "Inline JSON: layout/blocks/arrows/bubbles/badge/border."},
         "spec": {**_STR, "description": "Path to a JSON spec file."},
         "check": {**_BOOL, "description": "Report mechanical faults and exit 3 if any."}},
        ["base", "output"],
        {"base": ("--base", "repeat"), "output": ("--output", "value"),
         "text": ("--text", "repeat"), "preset": ("--preset", "value"),
         "badge": ("--badge", "value"), "badge_corner": ("--badge-corner", "value"),
         "spec_json": ("--spec-json", "value"), "spec": ("--spec", "value"),
         "check": ("--check", "flag")},
    ),
    "title_check": (
        "title-check",
        "Check recap title candidates against the house pattern: <STATUS or PREMISE> + "
        "<REVERSAL> [+ CONSEQUENCE] [(chapter range)] - <Manga|Manhwa> Recap. Reports length "
        "against YouTube's 100-character limit, the recap suffix a returning viewer scans "
        "for, all-caps shouting, emoji, punctuation spam, and a malformed chapter range. "
        "SHAPE ONLY -- a title that passes can still be a lie. Whether the reversal is the "
        "real turn of the story, and whether every claim is supported by a beat that appears "
        "in the video, is your judgement. Pass pattern=true for the formula and worked "
        "examples.",
        {"titles": {"type": "array", "items": {"type": "string"},
                    "description": "One or more candidate titles."},
         "pattern": {**_BOOL, "description": "Print the house pattern and examples instead."},
         "strict": {**_BOOL, "description": "Exit 1 on warnings as well as errors."}},
        [],
        {"titles": ("", "positional-list"), "pattern": ("--pattern", "flag"),
         "strict": ("--strict", "flag")},
    ),
    "series_plan": (
        "series-plan",
        "Slice a project's items into fixed upload batches (12 per video by default), report "
        "per-batch readiness and published state, and name the next batch to produce.",
        {"project_root": _PROJECT_ROOT,
         "batch_size": {**_INT, "description": "Items per video (default 12)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "batch_size": ("--batch-size", "value")},
    ),
    "series_mark_published": (
        "series-mark-published",
        "Record an uploaded batch in the project's publish.json (video id + timestamp) so "
        "series_plan advances to the next window. Call after a successful youtube_upload.",
        {"project_root": _PROJECT_ROOT,
         "items": {"type": "array", "items": {"type": "string"},
                   "description": "The batch's items, e.g. [\"01-12\"]."},
         "video_id": {**_STR, "description": "YouTube video id returned by youtube_upload."},
         "title": _STR,
         "url": {**_STR, "description": "Watch URL (derived from video_id when omitted)."},
         "profile": {**_YOUTUBE_PROFILE,
                     "description": "YouTube account profile used for the upload."},
         "channel_id": {**_STR, "description": "YouTube channel id that owns the upload."},
         "replaces_video_id": {**_STR,
                               "description": "Previous YouTube video id replaced by this upload."}},
        ["project_root", "items", "video_id"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "video_id": ("--video-id", "value"), "title": ("--title", "value"),
         "url": ("--url", "value"), "profile": ("--profile", "value"),
         "channel_id": ("--channel-id", "value"),
         "replaces_video_id": ("--replaces-video-id", "value")},
    ),
    "doctor": (
        "doctor",
        "Check this machine: ffmpeg/uv/git presence, GPU backend (cuda/mps/cpu), installed AI tools.",
        {"mode": {"type": "string", "enum": ["manga-video"],
                  "description": "Limit readiness output to one production mode."},
         "check_updates": {**_BOOL, "description": "Also check installed AI tools for upstream updates."}},
        [],
        {"mode": ("--mode", "value"), "check_updates": ("--check-updates", "flag")},
    ),
    "smoke_test": (
        "smoke-test",
        "Prove the install works end to end: builds a tiny throwaway project, renders a real "
        "MP4 through the pipeline and verifies its streams/duration, then cleans up. Run after "
        "`setup` — doctor says the parts are installed, this proves they work together. "
        "tts='kokoro' additionally exercises the real TTS toolchain (model download on first use).",
        {"tts": {"type": "string", "enum": ["silent", "kokoro"]},
         "keep": {**_BOOL, "description": "Keep <work-dir>/smoke_test/ for inspection."}},
        [],
        {"tts": ("--tts", "value"), "keep": ("--keep", "flag")},
    ),
    "where": (
        "where",
        "Show this install's resolved paths (data root, tools home) and version. Run this first.",
        {}, [], {},
    ),
    "library_list": (
        "library-list",
        "List projects and per-item readiness (panels/narration/intro) under a project root. Read-only.",
        {"project_root": {**_STR, "description": "Folder whose library/ gets scanned."}},
        ["project_root"],
        {"project_root": ("--project-root", "value")},
    ),
    "video_check": (
        "video-check",
        "Validate item inputs before generation: narration vs panels vs audio counts and name matches.",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "project_name": _STR, "items": _ITEMS},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "project_name": ("--project-name", "value"), "items": ("--items", "list")},
    ),
    "video_validate": (
        "video-validate",
        "Validate generated audio/videos against the inputs (stream formats, durations, counts).",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "output_root": _STR,
         "project_name": _STR, "items": _ITEMS,
         "require_long": {**_BOOL, "description": "Also require/validate the joined long video (default true)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "output_root": ("--output-root", "value"), "project_name": ("--project-name", "value"),
         "items": ("--items", "list"), "require_long": ("--no-require-long", "no-flag")},
    ),
    "video_chapters": (
        "video-chapters",
        "Probe rendered item videos and print cumulative, ready-to-paste YouTube chapter timestamps.",
        {"project_root": _PROJECT_ROOT, "output_root": _STR,
         "project_name": _STR, "items": _ITEMS,
         "item_range": {**_STR, "description": "Convenience range, e.g. 01-24."},
         "allow_gaps": {**_BOOL, "description": "Skip genuinely absent integer items, matching video-join."}},
        ["project_root", "output_root"],
        {"project_root": ("--project-root", "value"), "output_root": ("--output-root", "value"),
         "project_name": ("--project-name", "value"), "items": ("--items", "list"),
         "item_range": ("--item-range", "value"), "allow_gaps": ("--allow-gaps", "flag")},
    ),
    "video_quality": (
        "video-quality",
        "Measure the ENCODED deliverable, not the pre-encode filter: integrated loudness and "
        "true peak, audio/video drift, black and frozen frames, long silence, and stale item "
        "renders. Extracts evenly spaced full-resolution frames for the crop-readability and "
        "face/bubble-clipping pass no detector can perform. Exit 3 means machine-clean with "
        "review items outstanding. Passing is NOT a substitute for full video review.",
        {"project_root": _PROJECT_ROOT, "output_root": _STR, "project_name": _STR,
         "video": {**_STR, "description": "Exact MP4 to measure (default: latest joined long video)."},
         "items": _ITEMS,
         "review_frames": {**_INT, "description": "Frames to extract for the manual pass (0 to skip)."}},
        ["project_root", "output_root"],
        {"project_root": ("--project-root", "value"), "output_root": ("--output-root", "value"),
         "project_name": ("--project-name", "value"), "video": ("--video", "value"),
         "items": ("--items", "list"), "review_frames": ("--review-frames", "value")},
    ),
    "audio_audit": (
        "video-audio-audit",
        "ffprobe every expected narration audio file; report missing panels vs missing/corrupt audio. "
        "Set fix=true to delete bad audio so the next generation run recreates exactly those.",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "project_name": _STR, "items": _ITEMS,
         "fix": _BOOL},
        ["project_root", "audio_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "project_name": ("--project-name", "value"), "items": ("--items", "list"),
         "fix": ("--fix", "flag")},
    ),
    "generate_audio": (
        "video-audio",
        "Generate per-panel narration audio with Kokoro TTS (CPU-friendly). LONG-RUNNING — "
        "prefer job_start. Existing audio is skipped unless overwrite=true (old takes are "
        "archived, never lost). Blocked until manual crop/narration review is confirmed.",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "project_name": _STR, "items": _ITEMS,
         "overwrite": _BOOL},
        ["project_root", "audio_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "project_name": ("--project-name", "value"), "items": ("--items", "list"),
         "overwrite": ("--overwrite", "flag")},
    ),
    "render_videos": (
        "video-render",
        "Render one video per item from panels + audio after confirmed manual crop/narration "
        "review. Needs audio to exist (run generate_audio/audio_audit first).",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "output_root": _STR,
         "project_name": _STR, "items": _ITEMS, "overwrite": _BOOL},
        ["project_root", "audio_root", "output_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "output_root": ("--output-root", "value"), "project_name": ("--project-name", "value"),
         "items": ("--items", "list"), "overwrite": ("--overwrite", "flag")},
    ),
    "build_long_video": (
        "video-join",
        "Join manually reviewed item videos into one long video (no background music — use "
        "add_bgm afterward).",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "output_root": _STR,
         "project_name": _STR, "items": _ITEMS, "overwrite": _BOOL,
         "allow_gaps": {**_BOOL, "description": "Skip chapters genuinely missing from the source "
                        "instead of failing (never use it to paper over a failed render)."}},
        ["project_root", "output_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "output_root": ("--output-root", "value"), "project_name": ("--project-name", "value"),
         "items": ("--items", "list"), "overwrite": ("--overwrite", "flag"),
         "allow_gaps": ("--allow-gaps", "flag")},
    ),
    "add_bgm": (
        "video-add-bgm",
        "Mix background music into the already-joined long video (cheap — no re-join). "
        "Writes a new timestamped file unless replace=true.",
        {"project_root": _PROJECT_ROOT, "output_root": _STR,
         "background_music": {**_STR, "description": "Absolute path to the music file."},
         "music_volume_db": {**_NUM, "description": "Music loudness in dB, negative = quieter (default -30)."},
         "project_name": _STR, "replace": _BOOL},
        ["project_root", "output_root", "background_music"],
        {"project_root": ("--project-root", "value"), "output_root": ("--output-root", "value"),
         "background_music": ("--background-music", "value"),
         "music_volume_db": ("--music-volume-db", "value"), "project_name": ("--project-name", "value"),
         "replace": ("--replace", "flag")},
    ),
    "run_full_pipeline": (
        "video",
        "The all-in-one pipeline: audio -> fade -> render -> optional join/BGM/final normalize -> validate. VERY "
        "LONG-RUNNING — prefer job_start. Requires current crop/narration review records. "
        "Prefer the single-step tools when iterating.",
        {"project_root": _PROJECT_ROOT, "audio_root": _STR, "output_root": _STR, "items": _ITEMS,
         "tts": {"type": "string", "enum": ["auto", "kokoro", "indextts"]},
         "speaker_wav": {**_STR, "description": "IndexTTS speaker reference WAV (defaults to "
                         "config.system.json -> tts.speaker_wav)."},
         "skip_audio": {**_BOOL, "description": "Reuse existing narration WAVs instead of "
                        "running TTS; the selected audio_source is still prepared and rendered."},
         "audio_source": {"type": "string", "enum": ["raw", "faded"], "default": "faded",
                          "description": "Narration source for rendering. 'faded' prepares a "
                                         "separate edge-faded derivative; 'raw' preserves the "
                                         "original waveform."},
         "audio_fade_ms": {**_NUM, "exclusiveMinimum": 0, "default": 8.0,
                           "description": "Fade duration at both edges of each narration WAV, "
                                          "in milliseconds, when audio_source='faded'."},
         "build_long_video": _BOOL,
         "allow_gaps": {**_BOOL, "description": "Skip chapters genuinely missing from the source "
                        "when joining instead of failing."},
         "normalize_audio": {**_BOOL, "description": "Two-pass loudness-normalize the complete "
                             "long-video mix for YouTube (-14 LUFS) after background music is added."},
         "validate": {**_BOOL, "default": True,
                      "description": "Run structural audio/video validation as the final stage (default true)."},
         "overwrite_audio": {**_BOOL, "description": "Regenerate narration WAVs that already exist."},
         "overwrite_video": {**_BOOL, "description": "Re-render item videos that already exist — "
                             "REQUIRED after any panel/narration/audio change."},
         "no_background_music": _BOOL,
         "background_music": _STR,
         "music_volume_db": _NUM},
        ["project_root", "audio_root", "output_root"],
        {"project_root": ("--project-root", "value"), "audio_root": ("--audio-root", "value"),
         "output_root": ("--output-root", "value"), "items": ("--items", "list"),
         "tts": ("--tts", "value"), "speaker_wav": ("--speaker-wav", "value"),
         "skip_audio": ("--skip-audio", "flag"),
         "audio_source": ("--audio-source", "value"),
         "audio_fade_ms": ("--audio-fade-ms", "value"),
         "build_long_video": ("--build-long-video", "flag"),
         "allow_gaps": ("--allow-gaps", "flag"),
         "normalize_audio": ("--normalize-audio", "flag"),
         "validate": ("--no-validate", "no-flag"),
         "overwrite_audio": ("--overwrite-audio", "flag"),
         "overwrite_video": ("--overwrite-video", "flag"),
         "no_background_music": ("--no-background-music", "flag"),
         "background_music": ("--background-music", "value"),
         "music_volume_db": ("--music-volume-db", "value")},
    ),
    "youtube_profiles": (
        "youtube-profiles",
        "List isolated YouTube account profiles, connection state, and cached channel. Use this "
        "before publishing so the intended account is selected explicitly.",
        {}, [], {},
    ),
    "youtube_status": (
        "youtube-status",
        "Status for one YouTube account profile. Set verify=true for a live token refresh and "
        "channel query; missing/invalid authorization opens browser consent automatically unless "
        "auto_auth=false. Offline status (verify=false) never opens a browser.",
        {"profile": _YOUTUBE_PROFILE,
         "auto_auth": _YOUTUBE_AUTO_AUTH,
         "verify": {**_BOOL, "description": "Also verify the token works right now (network call)."}},
        [],
        {"profile": ("--profile", "value"), "auto_auth": ("--no-auto-auth", "no-flag"),
         "verify": ("--verify", "flag")},
    ),
    "youtube_upload": (
        "youtube-upload",
        "Upload through the selected YouTube account profile (resumable, LONG-RUNNING — prefer "
        "job_start). Missing/invalid authorization opens browser consent unless auto_auth=false. "
        "Default privacy is private; one upload costs 1,600 quota units.",
        {"profile": _YOUTUBE_PROFILE,
         "auto_auth": _YOUTUBE_AUTO_AUTH,
         "project_root": {**_PROJECT_ROOT, "description": "Manga project whose current final-video "
                          "review and rights record is bound to this exact file."},
         "video": {**_STR, "description": "Absolute path to the video file."},
         "title": {**_STR, "description": "Video title (max 100 chars)."},
         "description": _STR,
         "tags": {**_STR, "description": "Comma-separated tags, e.g. 'manga,recap'."},
         "privacy": {"type": "string", "enum": ["private", "unlisted", "public"]},
         "thumbnail": _STR, "made_for_kids": _BOOL, "contains_synthetic_media": _BOOL},
        ["project_root", "video", "title"],
        {"profile": ("--profile", "value"), "auto_auth": ("--no-auto-auth", "no-flag"),
         "project_root": ("--project-root", "value"),
         "video": ("--video", "value"), "title": ("--title", "value"),
         "description": ("--description", "value"), "tags": ("--tags", "value"),
         "privacy": ("--privacy", "value"), "thumbnail": ("--thumbnail", "value"),
         "made_for_kids": ("--made-for-kids", "flag"),
         "contains_synthetic_media": ("--contains-synthetic-media", "flag")},
    ),
    "youtube_list": (
        "youtube-list",
        "List the selected profile's uploads (video id, title, privacy, published date) — the "
        "IDs youtube_delete/youtube_thumbnail need. ~2 quota units.",
        {"profile": _YOUTUBE_PROFILE,
         "auto_auth": _YOUTUBE_AUTO_AUTH,
         "limit": {**_INT, "description": "Maximum videos to return (default 25)."}},
        [],
        {"profile": ("--profile", "value"), "auto_auth": ("--no-auto-auth", "no-flag"),
         "limit": ("--limit", "value")},
    ),
    "youtube_delete": (
        "youtube-delete",
        "Look up and irreversibly delete one video through the selected profile. Requires "
        "confirm=true; omit it for a confirmation preview.",
        {"profile": _YOUTUBE_PROFILE,
         "auto_auth": _YOUTUBE_AUTO_AUTH,
         "video_id": {**_STR, "description": "YouTube video id."},
         "url": {**_STR, "description": "YouTube URL; alternative to video_id."},
         "confirm": {**_BOOL, "description": "Actually delete the video (irreversible)."}},
        [],
        {"profile": ("--profile", "value"), "auto_auth": ("--no-auto-auth", "no-flag"),
         "video_id": ("--video-id", "value"),
         "url": ("--url", "value"), "confirm": ("--confirm", "flag")},
    ),
    "youtube_thumbnail": (
        "youtube-thumbnail",
        "Set/replace a thumbnail through the selected profile without re-uploading. Requires a "
        "verified YouTube account for custom thumbnails.",
        {"profile": _YOUTUBE_PROFILE,
         "auto_auth": _YOUTUBE_AUTO_AUTH,
         "video_id": {**_STR, "description": "Video id, e.g. dQw4w9WgXcQ."},
         "image": {**_STR, "description": "Absolute path to the PNG/JPG (max 2 MB)."}},
        ["video_id", "image"],
        {"profile": ("--profile", "value"), "auto_auth": ("--no-auto-auth", "no-flag"),
         "video_id": ("--video-id", "value"),
         "image": ("--image", "value")},
    ),
    "bootstrap_tools": (
        "bootstrap-tools",
        "Download ffmpeg/uv/git-lfs (~100 MB, one-time) into this install's own tools dir. LONG-RUNNING.",
        {}, [], {},
    ),
    "install_tool": (
        "install-tool",
        "Install an external AI tool env (multi-GB download). LONG-RUNNING — prefer job_start.",
        {"name": {"type": "string", "enum": ["kokoro-82m", "index-tts", "magi-v3",
                                              "deepseek-ocr2"]},
         "ref": _STR, "skip_model": _BOOL, "cpu": _BOOL, "cuda": _BOOL, "update": _BOOL},
        ["name"],
        {"name": (None, "positional"), "ref": ("--ref", "value"),
         "skip_model": ("--skip-model", "flag"), "cpu": ("--cpu", "flag"),
         "cuda": ("--cuda", "flag"), "update": ("--update", "flag")},
    ),
    "work_status": (
        "work-status",
        "Multi-agent dashboard + resume command: per-item pipeline stage derived from the "
        "filesystem, active claims, recent shared notes; next=true returns only the unclaimed "
        "actionable tasks. Run first in every session.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "next": {**_BOOL, "description": "Only the unclaimed actionable tasks."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "next": ("--next", "flag")},
    ),
    "work_claim": (
        "work-claim",
        "Atomically claim an item+stage (or a shared resource like 'gpu') with a TTL lease so "
        "concurrent agents never duplicate work. Non-zero result text means it is held by "
        "another live agent — pick a different task.",
        {"project_root": _PROJECT_ROOT,
         "item": {**_STR, "description": "Item folder, e.g. 05 (omit for --resource)."},
         "stage": {"type": "string", "enum": ["download", "crop", "transcribe", "narrate",
                                              "audio", "render", "join", "thumbnail", "upload"]},
         "resource": {**_STR, "description": "Shared resource name, e.g. gpu."},
         "agent": _STR, "ttl_minutes": _INT,
         "release": {**_BOOL, "description": "Release instead of acquire."},
         "renew": {**_BOOL, "description": "Extend an existing own claim."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "item": ("--item", "value"),
         "stage": ("--stage", "value"), "resource": ("--resource", "value"),
         "agent": ("--agent", "value"), "ttl_minutes": ("--ttl-minutes", "value"),
         "release": ("--release", "flag"), "renew": ("--renew", "flag")},
    ),
    "work_note": (
        "work-note",
        "Shared append-only project notebook for agent handoff (character names, speaker "
        "conventions, tone decisions, warnings). Omit 'add' to read.",
        {"project_root": _PROJECT_ROOT,
         "add": {**_STR, "description": "Note text to append."},
         "topic": {**_STR, "description": "characters / speakers / tone / decisions / warnings."},
         "agent": _STR, "limit": _INT},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "add": ("--add", "value"),
         "topic": ("--topic", "value"), "agent": ("--agent", "value"),
         "limit": ("--limit", "value")},
    ),
    "work_todo": (
        "work-todo",
        "Shared session todo list for agent handoff: plan-level next steps and decisions the "
        "filesystem can't derive on its own (batch scope, redo requests, things to confirm before "
        "publishing) — complements work_status, which only knows per-item pipeline stage. Survives "
        "a switch to a different LLM/vendor mid-project since it's a file, not chat state. Pass "
        "exactly one of add/start/done/reopen/remove to mutate; otherwise reads the list.",
        {"project_root": _PROJECT_ROOT,
         "add": {**_STR, "description": "Add a new pending todo with this text."},
         "topic": {**_STR, "description": "Topic tag for 'add', e.g. handoff/characters/publishing "
                                          "(default general)."},
         "start": {**_INT, "description": "Mark this todo id in_progress."},
         "done": {**_INT, "description": "Mark this todo id done."},
         "reopen": {**_INT, "description": "Reopen a done todo id back to pending."},
         "remove": {**_INT, "description": "Delete a todo id that is no longer relevant."},
         "agent": _STR,
         "pending_only": {**_BOOL, "description": "When reading: hide done todos."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "add": ("--add", "value"),
         "topic": ("--topic", "value"), "start": ("--start", "value"), "done": ("--done", "value"),
         "reopen": ("--reopen", "value"), "remove": ("--remove", "value"),
         "agent": ("--agent", "value"), "pending_only": ("--pending-only", "flag")},
    ),
    "work_qa": (
        "work-qa",
        "Aggregated machine-checkable QA gate over generated crops/narration/audio/renders. "
        "Each problem includes the exact fix command. ok=true means machine-clean only; "
        "manual_review_required and review-severity items identify original-page/crop/narration "
        "evidence a vision-capable reviewer must inspect before production approval.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "errors_only": {**_BOOL, "description": "Hide review/info items."},
         "max_problems": {**_INT, "description": "Cap list for small context windows (default 25)."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "errors_only": ("--errors-only", "flag"), "max_problems": ("--max-problems", "value")},
    ),
    "work_artifacts": (
        "work-artifacts",
        "Inventory of reusable generated artifacts (item renders, long-video takes, audio takes, "
        "transcripts, QA sheets, cached music beds) with a reuse hint each — check before "
        "regenerating anything expensive.",
        {"project_root": _PROJECT_ROOT},
        ["project_root"],
        {"project_root": ("--project-root", "value")},
    ),
    "manga_review": (
        "manga-review",
        "Record and check the hash-bound reviews that production depends on. 'crop' approves "
        "the exact source pages and panel crops, 'narration' approves the exact panels plus "
        "narration.json/intro.json, 'final-video' approves one exact MP4 together with the "
        "rights, voice-consent, and source-permission acknowledgements, and 'check' reports "
        "whether those records still match the current bytes. Any change to the inputs "
        "invalidates the approval — a boolean is never accepted as evidence that a review "
        "happened. Reviews can be recorded by a human or an LLM agent.",
        {"action": {"type": "string", "enum": ["crop", "narration", "final-video", "check"],
                    "description": "Which review to record, or 'check' to verify currency."},
         "project_root": _PROJECT_ROOT, "items": _ITEMS,
         "reviewer": {**_STR, "description": "Who performed the review (name or agent identity)."},
         "video": {**_STR, "description": "Absolute path to the final MP4 (final-video only)."},
         "source_subdir": {**_STR, "description": "Page-image folder inside each item (default: download)."},
         "stages": {"type": "array", "items": {"type": "string",
                                               "enum": ["crop", "narration", "final_video"]},
                    "description": "Stages to check (default: crop + narration)."},
         "rights_confirmed": {**_BOOL, "description": "Final-video: rights to the source art are confirmed."},
         "voice_consent_confirmed": {**_BOOL, "description": "Final-video: narrator voice consent/provenance is confirmed."},
         "source_permission_confirmed": {**_BOOL, "description": "Final-video: permission to use the source is confirmed."}},
        ["action", "project_root"],
        {"action": (None, "positional"), "project_root": ("--project-root", "value"),
         "items": ("--items", "list"), "reviewer": ("--reviewer", "value"),
         "video": ("--video", "value"), "source_subdir": ("--source-subdir", "value"),
         "stages": ("--stage", "repeat"),
         "rights_confirmed": ("--rights-confirmed", "flag"),
         "voice_consent_confirmed": ("--voice-consent-confirmed", "flag"),
         "source_permission_confirmed": ("--source-permission-confirmed", "flag")},
    ),
    "panel_decisions": (
        "panel-decisions",
        "Account for every cropped panel: narrated, or deliberately omitted for a stated "
        "reason bound to the panel's SHA-256. Called with panels+reason+reviewer it records "
        "omissions; called without them it audits which panels are still unaccounted for. "
        "Re-cropping invalidates a decision rather than silently inheriting it.",
        {"project_root": _PROJECT_ROOT, "items": _ITEMS,
         "item": {**_STR, "description": "Item folder the recorded decisions apply to, e.g. '01'."},
         "panels": {"type": "array", "items": {"type": "string"},
                    "description": "Panel filenames to mark as deliberately omitted."},
         "reason": {"type": "string",
                    "enum": ["credit", "scanlator_notice", "decorative", "duplicate",
                             "sfx_only", "platform_safety", "other"],
                    "description": "Why those panels carry no narration."},
         "note": {**_STR, "description": "Explanation; required when reason='other'."},
         "reviewer": {**_STR, "description": "Who made the decision."}},
        ["project_root"],
        {"project_root": ("--project-root", "value"), "items": ("--items", "list"),
         "item": ("--item", "value"), "panels": ("--panels", "list"),
         "reason": ("--reason", "value"), "note": ("--note", "value"),
         "reviewer": ("--reviewer", "value")},
    ),
    "manga_rights": (
        "manga-rights",
        "Create and verify the rights manifest that authorizes publication: source URL, "
        "edition, language, creator, publisher, permission basis, allowed chapters, "
        "attribution, translation provenance, voice consent, music licences, thumbnail "
        "source panels, and platform-safety scans. Fails closed — a reachable webtoon page "
        "is not permission, and neither is attribution or a disclaimer.",
        {"action": {"type": "string", "enum": ["init", "check", "show"]},
         "project_root": _PROJECT_ROOT,
         "force": {**_BOOL, "description": "init: overwrite an existing manifest."}},
        ["action", "project_root"],
        {"action": (None, "positional"), "project_root": ("--project-root", "value"),
         "force": ("--force", "flag")},
    ),
    "workspace_layout": (
        "workspace-layout",
        "Report every resolved persistent root and whether it landed in the right tree: "
        "everything downloaded or generated (items, audio, output, review, work, jobs) belongs "
        "under data/, and the re-downloadable machinery (tool envs, caches, state, OAuth "
        "tokens) under runtime/. Deleting data/ is the supported fresh start, so a production "
        "root outside it is a real defect. Read-only.",
        {"strict": {**_BOOL, "description": "Exit non-zero when a root lands outside its tree."}},
        [],
        {"strict": ("--strict", "flag")},
    ),
    "job_start": (
        "job-start",
        "Start one mode-visible MCP tool as a DETACHED background job and return a job id. "
        "Arguments are validated against that tool's typed schema; raw CLI argv is deliberately "
        "not accepted. Poll job_status for progress/result.",
        {"tool": {**_STR, "description": "A mode-visible MCP tool name, e.g. 'run_full_pipeline'."},
          "arguments": {"type": "object",
                        "description": "The target tool's normal typed arguments object."}},
        ["tool"],
        {"tool": ("--tool", "value"), "arguments": ("--arguments-json", "json")},
    ),
    "job_status": (
        "job-status",
        "Status of one background job: running/succeeded/review_required/failed/orphaned, exit "
        "code, progress markers, parsed MEDIACONDUCTOR_RESULT payload, and the tail of its log.",
        {"job_id": {**_STR, "description": "Id returned by job_start."},
         "tail": {**_INT, "description": "Log tail lines to include (default 20)."}},
        ["job_id"],
        {"job_id": (None, "positional"), "tail": ("--tail", "value")},
    ),
    "job_list": (
        "jobs",
        "List background jobs (running and finished) with their ids, commands, and states.",
        {}, [], {},
    ),
}

# Commands whose --json flag should be appended automatically by the MCP server.
# manga-review, panel-decisions and manga-rights always print one JSON object,
# so they are deliberately absent — appending --json would be an unknown flag.
JSON_COMMANDS = {"modes", "doctor", "where", "library-list", "video-check", "video-validate", "video-chapters",
                 "video-audio-audit", "youtube-profiles", "youtube-status", "youtube-upload",
                 "style-detect", "narration-check", "series-plan", "workspace-layout",
                 "panel-decisions", "video-quality",
                 "work-status", "work-claim", "work-note", "work-todo", "work-qa", "work-artifacts",
                 "youtube-list", "youtube-delete", "youtube-thumbnail",
                 "job-status", "jobs"}

# CLI commands that run for minutes to hours. Surfaced structurally so agents
# can decide to background them (job-start / harness background shells)
# without parsing prose.
LONG_RUNNING = {"setup", "download", "webtoon-split", "page-split", "panel-transcript",
                "video", "video-audio", "video-audio-indextts", "video-render",
                "video-join", "video-normalize-audio",
                "install-tool", "bootstrap-tools", "youtube-upload", "smoke-test",
                }

# cli command name -> mcp tool name (reverse index)
CLI_TO_TOOL: dict[str, str] = {cli: tool for tool, (cli, *_rest) in TOOLS.items()}


def cli_args_schema(cli_name: str, mode: str | None = None) -> dict | None:
    """The argument schema for one CLI command, flags included, or None.

    Shape (consumed by `mediaconductor commands --json --full`):
    {"<prop>": {"type": ..., "description": ..., "flag": "--project-root",
                "kind": "value", "required": true}, ...}
    """
    tool = CLI_TO_TOOL.get(cli_name)
    if tool is None:
        return None
    _cli, _desc, props, required, flags = TOOLS[tool]
    schema: dict = {}
    for prop, prop_schema in props.items():
        if prop_schema.get("x-mcp-only"):
            continue
        flag, kind = flags.get(prop, (None, "value"))
        schema[prop] = {
            **prop_schema,
            "flag": flag,
            "kind": kind,
            "required": prop in required,
        }
    if cli_name in JSON_COMMANDS:
        schema["json"] = {
            "type": "boolean", "flag": "--json", "kind": "flag",
            "required": False,
            "description": "Emit the machine-readable JSON report.",
        }
    if mode and cli_name in {"setup", "doctor"} and "mode" in schema:
        schema["mode"]["enum"] = [mode]
        schema["mode"]["default"] = mode
    if mode and cli_name == "install-tool" and "name" in schema:
        from mediaconductor.tools.setup import MODE_TOOLS
        schema["name"]["enum"] = list(MODE_TOOLS[mode])
    return schema
