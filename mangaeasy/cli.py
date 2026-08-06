"""mangaeasy.cli — the single `mangaeasy` entry point."""

from __future__ import annotations

import difflib
import importlib
import sys

from mangaeasy import __version__
from mangaeasy.brand import CLI_NAME, LEGACY_CLI_NAME, PRODUCT_NAME, mirror_legacy_environment
from mangaeasy.isolation import apply as apply_isolation
from mangaeasy.tools.vendored import ensure_vendored_path

mirror_legacy_environment()
ensure_vendored_path()
apply_isolation()


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


_force_utf8_stdio()

COMMANDS: dict[str, tuple[str, str, str, str]] = {
    # ── Setup & Core ──────────────────────────────────────────────────────────
    "commands":             ("mangaeasy.cli", "commands_main", "Setup", "List every command or emit JSON catalog."),
    "modes":                ("mangaeasy.modes", "main", "Setup", "Show available production catalog."),
    "where":                ("mangaeasy.tools.external", "where_main", "Setup", "Show resolved environment & data paths."),
    "workspace-layout":     ("mangaeasy.workspace", "main", "Setup", "Report layout structure."),
    "workspace-reset":      ("mangaeasy.workspace", "reset_main", "Setup", "Reset data folder."),
    "library-list":         ("mangaeasy.library_scan", "main", "Setup", "List manga projects."),
    "series-plan":          ("mangaeasy.series_plan", "plan_main", "Setup", "Plan upload batches."),
    "series-mark-published":("mangaeasy.series_plan", "mark_main", "Setup", "Mark batch published."),
    "mcp":                  ("mangaeasy.mcp_server", "main", "Setup", "Run MCP stdio server."),
    "doctor":               ("mangaeasy.tools.install", "doctor_main", "Setup", "Check environment readiness."),
    "setup":                ("mangaeasy.tools.setup", "main", "Setup", "Provision environment & tool binaries."),
    "smoke-test":           ("mangaeasy.tools.smoke", "main", "Setup", "Run pipeline smoke test."),
    "install-tool":         ("mangaeasy.tools.install", "main", "Setup", "Install external AI tool."),
    "bootstrap-tools":      ("mangaeasy.tools.vendored", "bootstrap_main", "Setup", "Download core binaries."),
    "tool-downloads":       ("mangaeasy.tools.vendored", "downloads_main", "Setup", "Show portable tool URLs."),
    "env":                  ("mangaeasy.isolation", "main", "Setup", "Print isolated environment exports."),

    # ── Background Jobs ───────────────────────────────────────────────────────
    "job-start":            ("mangaeasy.jobs", "start_main", "Jobs", "Start long-running tool in background."),
    "job-status":           ("mangaeasy.jobs", "status_main", "Jobs", "Check background job status."),
    "jobs":                 ("mangaeasy.jobs", "list_main", "Jobs", "List active/past background jobs."),
    "job-run":              ("mangaeasy.jobs", "run_main", "Jobs", "(internal) Job supervisor process."),

    # ── Multi-agent Coordination ──────────────────────────────────────────────
    "work-status":          ("mangaeasy.workboard", "status_main", "Multi-agent", "Dashboard of stage & next tasks."),
    "work-claim":           ("mangaeasy.workboard", "claim_main", "Multi-agent", "Claim an item stage or resource."),
    "work-note":            ("mangaeasy.workboard", "note_main", "Multi-agent", "Shared project notebook."),
    "work-todo":            ("mangaeasy.workboard", "todo_main", "Multi-agent", "Shared session todo list."),
    "memory-init":          ("mangaeasy.workboard", "memory_init_main", "Multi-agent", "Initialize MEMORY.json."),
    "work-qa":              ("mangaeasy.qa_loop", "qa_main", "Multi-agent", "Run QA gate with fix commands."),
    "work-artifacts":       ("mangaeasy.qa_loop", "artifacts_main", "Multi-agent", "Inventory generated artifacts."),

    # ── Manga Acquire & Crop ──────────────────────────────────────────────────
    "download":             ("mangaeasy.download.mangadex", "main", "Manga: acquire", "Download chapters from MangaDex."),
    "style-detect":         ("mangaeasy.panels.style_detect", "main", "Manga: acquire", "Detect webtoon vs paged format."),
    "gutter-split":         ("mangaeasy.panels.gutter", "main", "Manga: acquire", "Low-level gutter panel splitter."),
    "webtoon-split":        ("mangaeasy.panels.webtoon", "main", "Manga: acquire", "Split webtoon strips into panels."),
    "webtoon-cutcheck":     ("mangaeasy.panels.cutcheck", "main", "Manga: acquire", "Review windows around forced cuts."),
    "webtoon-override":     ("mangaeasy.panels.overrides_tool", "main", "Manga: acquire", "Build overrides file for cuts."),
    "panels-remap":         ("mangaeasy.panels.remap", "main", "Manga: acquire", "Remap narration/audio across recrop."),
    "page-split":           ("mangaeasy.panels.page", "main", "Manga: acquire", "Split paged manga using MAGI v3."),
    "panel-transcript":     ("mangaeasy.ocr.panel_transcript", "main", "Manga: acquire", "Run DeepSeek-OCR 2 on panels."),

    # ── Sheets & Context Packaging ────────────────────────────────────────────
    "panel-reading-sheets": ("mangaeasy.video_pipeline.panel_reading_sheets", "main", "Manga: sheets", "Render multi-panel reading sheets."),
    "narration-review-sheets": ("mangaeasy.video_pipeline.narration_sheets", "main", "Manga: sheets", "Render review sheets with OCR."),
    "sheets-pack":          ("mangaeasy.images.sheets_zip", "main", "Manga: sheets", "Pack sheets into split ZIPs <= 1 GB stored in <project_root>/zips/."),
    "panels-context-pack":  ("mangaeasy.images.ai_zip_cli", "main", "Manga: sheets", "Pack panels into ZIP for AI context."),

    # ── Narration, Audio & Subtitles ──────────────────────────────────────────
    "narration-check":      ("mangaeasy.video_pipeline.narration_check", "main", "Audio & Narration", "Validate narration.json structure."),
    "narration-edit":       ("mangaeasy.video_pipeline.narration_edit", "main", "Audio & Narration", "Edit narration entries via CLI."),
    "video-audio":          ("mangaeasy.video_pipeline.generate_audio", "main", "Audio & Narration", "Generate audio with Kokoro or IndexTTS."),
    "video-audio-indextts": ("mangaeasy.video_pipeline.generate_audio_indextts", "main", "Audio & Narration", "Generate audio via IndexTTS."),
    "video-subtitles":      ("mangaeasy.audio.subtitles_whisper", "main", "Audio & Narration", "Generate .ass/.srt subtitles using Whisper large-v3-turbo from HuggingFace."),
    "video-audio-audit":    ("mangaeasy.video_pipeline.audio_audit", "main", "Audio & Narration", "Audit panel audio WAV files."),
    "video-fade-audio":     ("mangaeasy.video_pipeline.preprocess_audio_fades", "main", "Audio & Narration", "Apply edge fades to audio."),
    "audio-takes-list":     ("mangaeasy.video_pipeline.audio_takes", "list_main", "Audio & Narration", "List archived audio takes."),
    "audio-takes-restore":  ("mangaeasy.video_pipeline.audio_takes", "restore_main", "Audio & Narration", "Restore an archived audio take."),

    # ── Video Pipeline & Quality ──────────────────────────────────────────────
    "video":                ("mangaeasy.video_pipeline.run_pipeline", "main", "Video Pipeline", "Full video pipeline execution."),
    "video-render":         ("mangaeasy.video_pipeline.make_videos", "main", "Video Pipeline", "Render item videos from panels + audio."),
    "video-join":           ("mangaeasy.video_pipeline.make_long_video", "main", "Video Pipeline", "Join item videos into a full recap."),
    "video-add-bgm":        ("mangaeasy.video_pipeline.add_long_video_bgm", "main", "Video Pipeline", "Mix background music into video."),
    "video-normalize-audio":("mangaeasy.video_pipeline.normalize_long_audio", "main", "Video Pipeline", "Two-pass loudness normalization."),
    "video-validate":       ("mangaeasy.video_pipeline.validate_generation", "main", "Video Pipeline", "Validate generated outputs."),
    "video-chapters":       ("mangaeasy.video_pipeline.chapter_timestamps", "main", "Video Pipeline", "Generate YouTube chapter timestamps."),
    "video-quality":        ("mangaeasy.video_pipeline.quality_gate", "main", "Video Pipeline", "Measure deliverable loudness & quality."),
    "video-clean-audio":    ("mangaeasy.video_pipeline.cleanup_audio", "main", "Video Pipeline", "Clear generated audio for items."),
    "video-clean-video":    ("mangaeasy.video_pipeline.cleanup_videos", "main", "Video Pipeline", "Delete rendered item videos."),
    "video-clean-work":     ("mangaeasy.video_pipeline.cleanup_work", "main", "Video Pipeline", "Delete work scratch directory."),
    "video-clean-all":      ("mangaeasy.video_pipeline.cleanup_all", "main", "Video Pipeline", "Delete all generated output for project."),

    # ── Publishing & Review ───────────────────────────────────────────────────
    "manga-review":         ("mangaeasy.reviews", "main", "Publishing & Review", "Record/check hash-bound review approvals."),
    "panel-decisions":      ("mangaeasy.panel_decisions", "main", "Publishing & Review", "Legacy audit ledger for panel omissions."),
    "thumbnail-candidates": ("mangaeasy.images.thumbnail_candidates", "main", "Publishing & Review", "Shortlist panels for thumbnail."),
    "thumbnail-compose":    ("mangaeasy.images.thumbnail_compose", "main", "Publishing & Review", "Compose thumbnail from approved panels."),
    "title-check":          ("mangaeasy.images.title_check", "main", "Publishing & Review", "Check recap titles against house pattern."),
    "youtube-profiles":     ("mangaeasy.youtube.auth", "profiles_main", "Publishing & Review", "List YouTube account profiles."),
    "youtube-auth":         ("mangaeasy.youtube.auth", "auth_main", "Publishing & Review", "Connect YouTube account profile."),
    "youtube-status":       ("mangaeasy.youtube.auth", "status_main", "Publishing & Review", "Check YouTube profile status."),
    "youtube-logout":       ("mangaeasy.youtube.auth", "logout_main", "Publishing & Review", "Disconnect YouTube profile."),
    "youtube-upload":       ("mangaeasy.youtube.upload", "main", "Publishing & Review", "Upload video to YouTube."),
    "youtube-list":         ("mangaeasy.youtube.list_videos", "main", "Publishing & Review", "List profile's uploaded videos."),
    "youtube-delete":       ("mangaeasy.youtube.delete", "main", "Publishing & Review", "Delete video from YouTube."),
    "youtube-thumbnail":    ("mangaeasy.youtube.thumbnail", "main", "Publishing & Review", "Set video thumbnail."),

    # ── External AI Tools ─────────────────────────────────────────────────────
    "tools":                ("mangaeasy.tools.external", "main", "External Tools", "Show external tool env paths."),
    "index-tts":            ("mangaeasy.tools.index_tts", "main", "External Tools", "Run IndexTTS inside external env."),
}


def _print_help() -> None:
    print(f"{PRODUCT_NAME} {__version__} - manga and webtoon recap production\n")
    print("Usage: mangaeasy <command> [args...]\n")
    print("Available Commands:")
    for cmd, (_, _, group, desc) in sorted(COMMANDS.items()):
        print(f"  {cmd:<26} [{group}] {desc}")


def commands_main() -> int:
    import argparse
    import json
    from mangaeasy.modes import MODES

    parser = argparse.ArgumentParser(description=f"List {PRODUCT_NAME} commands.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--tools", nargs="+", dest="tools")
    parser.add_argument("--mode", choices=tuple(MODES))
    args = parser.parse_args()

    if args.full:
        from mangaeasy.command_spec import LONG_RUNNING, cli_args_schema

    visible = MODES[args.mode].commands if args.mode else frozenset(COMMANDS)
    if args.tools:
        requested = set(args.tools)
        visible = frozenset(name for name in args.tools if name in requested)

    catalog = []
    for name, (_, _, group, help_text) in COMMANDS.items():
        if name not in visible:
            continue
        entry: dict = {
            "name": name,
            "group": group,
            "help": help_text,
            "usage": f"{CLI_NAME} {name} --help",
        }
        if args.full:
            entry["long_running"] = name in LONG_RUNNING
            schema = cli_args_schema(name, args.mode)
            if schema is not None:
                entry["args"] = schema
        catalog.append(entry)

    if args.as_json:
        print(json.dumps({"product": PRODUCT_NAME, "version": __version__, "mode": args.mode, "commands": catalog}, ensure_ascii=False))
    else:
        _print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        _print_help()
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"{CLI_NAME} {__version__}")
        return 0

    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        print(f"{CLI_NAME}: unknown command '{command}'", file=sys.stderr)
        suggestions = difflib.get_close_matches(command, list(COMMANDS), n=3)
        if suggestions:
            print("Did you mean: " + ", ".join(suggestions) + "?", file=sys.stderr)
        return 2

    module_path, func_name, _, _ = COMMANDS[command]
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    sys.argv = [f"{CLI_NAME} {command}", *rest]
    return func() or 0


if __name__ == "__main__":
    raise SystemExit(main())