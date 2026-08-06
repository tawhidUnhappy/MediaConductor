"""mangaeasy.command_spec — declarative source for all command schemas."""

from __future__ import annotations

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_ITEMS = {"type": "array", "items": {"type": "string"}}
_PROJECT_ROOT = {"type": "string", "description": "Manga project directory (data/library/<MangaName>/)."}
_YOUTUBE_PROFILE = {
    "type": "string",
    "pattern": r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$",
    "default": "default",
    "description": "Isolated YouTube account profile.",
}

TOOLS: dict[str, tuple[str, str, dict, list[str], dict]] = {
    "modes": ("modes", "Show the manga-video production catalog.", {"mode": _STR}, [], {"mode": ("--mode", "value")}),
    "setup": ("setup", "Provision core tools and AI environments.", {"all": _BOOL, "minimal": _BOOL, "mode": _STR, "skip": _ITEMS, "dry_run": _BOOL}, [], {"all": ("--all", "flag"), "minimal": ("--minimal", "flag"), "mode": ("--mode", "value"), "skip": ("--skip", "repeat"), "dry_run": ("--dry-run", "flag")}),
    "download": ("download", "Download chapters from MangaDex.", {"url": _STR, "name": _STR, "chapters": _ITEMS, "all": _BOOL}, [], {"url": ("--url", "value"), "name": ("--name", "value"), "chapters": ("--chapters", "list"), "all": ("--all", "flag")}),
    "style_detect": ("style-detect", "Detect webtoon vs paged manga format.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "webtoon_split": ("webtoon-split", "Crop webtoon strips into panels.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "overrides": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "overrides": ("--overrides", "value")}),
    "webtoon_cutcheck": ("webtoon-cutcheck", "Review windows around forced cuts.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "webtoon_override": ("webtoon-override", "Add merge/split fixes to overrides file.", {"file": _STR, "project_root": _PROJECT_ROOT, "item": _STR}, ["file", "project_root"], {"file": ("--file", "value"), "project_root": ("--project-root", "value"), "item": ("--item", "value")}),
    "panels_remap": ("panels-remap", "Carry narration + audio across re-crop.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "apply": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "apply": ("--apply", "flag")}),
    "page_split": ("page-split", "Crop paged manga with MAGI v3.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "overrides": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "overrides": ("--overrides", "value")}),
    "panel_transcript": ("panel-transcript", "Run DeepSeek-OCR 2 on panel images.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "force": _BOOL, "seed_only": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "force": ("--force", "flag"), "seed_only": ("--seed-only", "flag")}),
    "narration_check": ("narration-check", "Validate narration.json structure.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "narration_edit": ("narration-edit", "Upsert/delete narration entries.", {"project_root": _PROJECT_ROOT, "item": _STR, "set_json": _STR}, ["project_root", "item"], {"project_root": ("--project-root", "value"), "item": ("--item", "value"), "set_json": ("--set-json", "value")}),
    "narration_review_sheets": ("narration-review-sheets", "Render panel + text + OCR review sheets.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "panel_reading_sheets": ("panel-reading-sheets", "Render multi-panel reading sheets.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "per_sheet": _INT}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "per_sheet": ("--per-sheet", "value")}),
    "sheets_pack": ("sheets-pack", "Pack contact/reading sheets into split ZIPs <= 1 GB stored in <project_root>/zips/.", {"project_root": _PROJECT_ROOT, "max_size_mb": _INT}, ["project_root"], {"project_root": ("--project-root", "value"), "max_size_mb": ("--max-size-mb", "value")}),
    "generate_audio": ("video-audio", "Generate narration audio with Kokoro TTS.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "overwrite": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "overwrite": ("--overwrite", "flag")}),
    "video_subtitles": ("video-subtitles", "Generate .ass/.srt subtitles using Whisper large-v3-turbo.", {"project_root": _PROJECT_ROOT, "model_repo": _STR, "device": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "model_repo": ("--model-repo", "value"), "device": ("--device", "value")}),
    "render_videos": ("video-render", "Render item videos from panels + audio.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "overwrite": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "overwrite": ("--overwrite", "flag")}),
    "build_long_video": ("video-join", "Join item videos into a full recap.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "allow_gaps": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "allow_gaps": ("--allow-gaps", "flag")}),
    "add_bgm": ("video-add-bgm", "Mix background music into video.", {"project_root": _PROJECT_ROOT, "background_music": _STR, "music_volume_db": _NUM}, ["project_root"], {"project_root": ("--project-root", "value"), "background_music": ("--background-music", "value"), "music_volume_db": ("--music-volume-db", "value")}),
    "run_full_pipeline": ("video", "Full pipeline execution.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "tts": _STR, "build_long_video": _BOOL, "normalize_audio": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "tts": ("--tts", "value"), "build_long_video": ("--build-long-video", "flag"), "normalize_audio": ("--normalize-audio", "flag")}),
    "video_validate": ("video-validate", "Validate generated outputs.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "video_chapters": ("video-chapters", "Generate YouTube chapter timestamps.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "video_quality": ("video-quality", "Measure deliverable quality & loudness.", {"project_root": _PROJECT_ROOT, "video": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "video": ("--video", "value")}),
    "audio_audit": ("video-audio-audit", "Verify narration audio files.", {"project_root": _PROJECT_ROOT, "fix": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "fix": ("--fix", "flag")}),
    "thumbnail_candidates": ("thumbnail-candidates", "Shortlist panels for thumbnail.", {"project_root": _PROJECT_ROOT, "top": _INT}, ["project_root"], {"project_root": ("--project-root", "value"), "top": ("--top", "value")}),
    "thumbnail_compose": ("thumbnail-compose", "Compose thumbnail from approved panels.", {"base": _ITEMS, "output": _STR, "text": _ITEMS, "preset": _STR}, ["base", "output"], {"base": ("--base", "repeat"), "output": ("--output", "value"), "text": ("--text", "repeat"), "preset": ("--preset", "value")}),
    "title_check": ("title-check", "Check recap titles against house pattern.", {"titles": _ITEMS, "pattern": _BOOL}, [], {"titles": ("", "positional-list"), "pattern": ("--pattern", "flag")}),
    "series_plan": ("series-plan", "Slice items into upload batches.", {"project_root": _PROJECT_ROOT, "batch_size": _INT}, ["project_root"], {"project_root": ("--project-root", "value"), "batch_size": ("--batch-size", "value")}),
    "series_mark_published": ("series-mark-published", "Record published batch.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "video_id": _STR}, ["project_root", "items", "video_id"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "video_id": ("--video-id", "value")}),
    "work_status": ("work-status", "Multi-agent dashboard & next tasks.", {"project_root": _PROJECT_ROOT, "next": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "next": ("--next", "flag")}),
    "work_claim": ("work-claim", "Claim an item+stage or shared resource.", {"project_root": _PROJECT_ROOT, "item": _STR, "stage": _STR, "agent": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "item": ("--item", "value"), "stage": ("--stage", "value"), "agent": ("--agent", "value")}),
    "work_note": ("work-note", "Append/read project shared notebook.", {"project_root": _PROJECT_ROOT, "add": _STR, "topic": _STR, "agent": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "add": ("--add", "value"), "topic": ("--topic", "value"), "agent": ("--agent", "value")}),
    "work_todo": ("work-todo", "Shared session todo list.", {"project_root": _PROJECT_ROOT, "add": _STR, "done": _INT}, ["project_root"], {"project_root": ("--project-root", "value"), "add": ("--add", "value"), "done": ("--done", "value")}),
    "work_qa": ("work-qa", "Machine-checkable QA gate.", {"project_root": _PROJECT_ROOT, "errors_only": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "errors_only": ("--errors-only", "flag")}),
    "work_artifacts": ("work-artifacts", "Inventory of generated artifacts.", {"project_root": _PROJECT_ROOT}, ["project_root"], {"project_root": ("--project-root", "value")}),
    "manga_review": ("manga-review", "Record/check hash-bound review approvals.", {"action": _STR, "project_root": _PROJECT_ROOT, "items": _ITEMS, "reviewer": _STR, "video": _STR}, ["action", "project_root"], {"action": (None, "positional"), "project_root": ("--project-root", "value"), "items": ("--items", "list"), "reviewer": ("--reviewer", "value"), "video": ("--video", "value")}),
    "panel_decisions": ("panel-decisions", "Legacy audit ledger for panel omissions.", {"project_root": _PROJECT_ROOT, "item": _STR, "panels": _ITEMS, "reason": _STR, "reviewer": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "item": ("--item", "value"), "panels": ("--panels", "list"), "reason": ("--reason", "value"), "reviewer": ("--reviewer", "value")}),
    "youtube_profiles": ("youtube-profiles", "List YouTube account profiles.", {}, [], {}),
    "youtube_status": ("youtube-status", "Status for one YouTube profile.", {"profile": _YOUTUBE_PROFILE, "verify": _BOOL}, [], {"profile": ("--profile", "value"), "verify": ("--verify", "flag")}),
    "youtube_upload": ("youtube-upload", "Upload video to YouTube.", {"profile": _YOUTUBE_PROFILE, "project_root": _PROJECT_ROOT, "video": _STR, "title": _STR, "privacy": _STR, "thumbnail": _STR}, ["project_root", "video", "title"], {"profile": ("--profile", "value"), "project_root": ("--project-root", "value"), "video": ("--video", "value"), "title": ("--title", "value"), "privacy": ("--privacy", "value"), "thumbnail": ("--thumbnail", "value")}),
    "youtube_list": ("youtube-list", "List profile's uploaded videos.", {"profile": _YOUTUBE_PROFILE, "limit": _INT}, [], {"profile": ("--profile", "value"), "limit": ("--limit", "value")}),
    "youtube_delete": ("youtube-delete", "Delete a video.", {"profile": _YOUTUBE_PROFILE, "video_id": _STR, "confirm": _BOOL}, [], {"profile": ("--profile", "value"), "video_id": ("--video-id", "value"), "confirm": ("--confirm", "flag")}),
    "youtube_thumbnail": ("youtube-thumbnail", "Set video thumbnail.", {"profile": _YOUTUBE_PROFILE, "video_id": _STR, "image": _STR}, ["video_id", "image"], {"profile": ("--profile", "value"), "video_id": ("--video-id", "value"), "image": ("--image", "value")}),
    "install_tool": ("install-tool", "Install external AI tool.", {"name": {"type": "string", "enum": ["kokoro-82m", "index-tts", "magi-v3", "deepseek-ocr2", "whisper-turbo"]}}, ["name"], {"name": (None, "positional")}),
    "job_start": ("job-start", "Start detached background job.", {"tool": _STR, "arguments": {"type": "object"}}, ["tool"], {"tool": ("--tool", "value"), "arguments": ("--arguments-json", "json")}),
    "job_status": ("job-status", "Status of background job.", {"job_id": _STR, "tail": _INT}, ["job_id"], {"job_id": (None, "positional"), "tail": ("--tail", "value")}),
    "job_list": ("jobs", "List all background jobs.", {}, [], {}),
    "doctor": ("doctor", "Check system prerequisites.", {}, [], {}),
    "where": ("where", "Show resolved paths.", {}, [], {}),
    "workspace_layout": ("workspace-layout", "Report persistent roots.", {"strict": _BOOL}, [], {"strict": ("--strict", "flag")}),
}

JSON_COMMANDS = {
    "modes", "doctor", "where", "library-list", "video-check", "video-validate",
    "video-chapters", "video-audio-audit", "youtube-profiles", "youtube-status",
    "youtube-upload", "style-detect", "narration-check", "series-plan",
    "workspace-layout", "panel-decisions", "panel-reading-sheets", "sheets-pack",
    "video-subtitles", "video-quality", "work-status", "work-claim", "work-note",
    "work-todo", "work-qa", "work-artifacts", "youtube-list", "youtube-delete",
    "youtube-thumbnail", "job-status", "jobs",
}

LONG_RUNNING = {
    "setup", "download", "webtoon-split", "page-split", "panel-transcript",
    "video", "video-audio", "video-audio-indextts", "video-render",
    "video-join", "video-normalize-audio", "install-tool", "bootstrap-tools",
    "youtube-upload", "smoke-test", "video-subtitles", "sheets-pack",
}

CLI_TO_TOOL = {cli: tool for tool, (cli, *_rest) in TOOLS.items()}


def cli_args_schema(cli_name: str, mode: str | None = None) -> dict | None:
    tool = CLI_TO_TOOL.get(cli_name)
    if tool is None:
        return None
    _cli, _desc, props, required, flags = TOOLS[tool]
    schema = {}
    for prop, prop_schema in props.items():
        flag, kind = flags.get(prop, (None, "value"))
        schema[prop] = {**prop_schema, "flag": flag, "kind": kind, "required": prop in required}
    return schema