"""mangaeasy.command_spec — single declarative source for command schemas."""

from __future__ import annotations

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_ITEMS = {"type": "array", "items": {"type": "string"}}
_PROJECT_ROOT = {"type": "string", "description": "Manga project directory (data/library/<MangaName>/)."}

TOOLS: dict[str, tuple[str, str, dict, list[str], dict]] = {
    "modes": ("modes", "Show the manga-video production catalog.", {}, [], {}),
    "setup": ("setup", "Provision core tools and AI environments.", {}, [], {}),
    "download": ("download", "Download chapters from MangaDex.", {"url": _STR, "name": _STR, "chapters": _ITEMS}, [], {"url": ("--url", "value"), "name": ("--name", "value"), "chapters": ("--chapters", "list")}),
    "style_detect": ("style-detect", "Detect webtoon vs paged manga format.", {"project_root": _PROJECT_ROOT}, ["project_root"], {"project_root": ("--project-root", "value")}),
    "webtoon_split": ("webtoon-split", "Crop webtoon strips into panels.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "page_split": ("page-split", "Crop paged manga with MAGI v3.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "panel_reading_sheets": ("panel-reading-sheets", "Render bounded multi-panel reading sheets.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "sheets_pack": ("sheets-pack", "Pack contact/reading sheets into split ZIPs <= 1 GB stored in <project_root>/zips/.", {"project_root": _PROJECT_ROOT, "max_size_mb": _INT}, ["project_root"], {"project_root": ("--project-root", "value"), "max_size_mb": ("--max-size-mb", "value")}),
    "narration_check": ("narration-check", "Validate narration.json/intro.json structure.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "panel_transcript": ("panel-transcript", "Run DeepSeek-OCR 2 on panel images.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "generate_audio": ("video-audio", "Generate narration audio via Kokoro TTS.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "tts": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "tts": ("--tts", "value")}),
    "video_subtitles": ("video-subtitles", "Generate .ass/.srt subtitles using Whisper large-v3-turbo.", {"project_root": _PROJECT_ROOT, "model_repo": _STR, "device": _STR}, ["project_root"], {"project_root": ("--project-root", "value"), "model_repo": ("--model-repo", "value"), "device": ("--device", "value")}),
    "render_videos": ("video-render", "Render item videos from panels + audio.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "build_long_video": ("video-join", "Join item videos into a full recap.", {"project_root": _PROJECT_ROOT, "items": _ITEMS}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list")}),
    "run_full_pipeline": ("video", "Full pipeline execution.", {"project_root": _PROJECT_ROOT, "items": _ITEMS, "build_long_video": _BOOL, "normalize_audio": _BOOL}, ["project_root"], {"project_root": ("--project-root", "value"), "items": ("--items", "list"), "build_long_video": ("--build-long-video", "flag"), "normalize_audio": ("--normalize-audio", "flag")}),
    "video_quality": ("video-quality", "Run quality measurement gate.", {"project_root": _PROJECT_ROOT}, ["project_root"], {"project_root": ("--project-root", "value")}),
    "install_tool": ("install-tool", "Install external AI tool.", {"name": {"type": "string", "enum": ["kokoro-82m", "index-tts", "magi-v3", "deepseek-ocr2", "whisper-turbo"]}}, ["name"], {"name": (None, "positional")}),
    "doctor": ("doctor", "Check environment readiness.", {}, [], {}),
    "where": ("where", "Show resolved paths.", {}, [], {}),
}

JSON_COMMANDS = {"modes", "doctor", "where", "library-list", "video-check", "video-validate", "sheets-pack", "video-subtitles", "video-quality"}
LONG_RUNNING = {"setup", "download", "webtoon-split", "page-split", "panel-transcript", "video", "video-audio", "video-subtitles", "sheets-pack"}
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