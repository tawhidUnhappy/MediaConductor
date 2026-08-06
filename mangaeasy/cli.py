"""mangaeasy.cli — the single entry point."""

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

    # ── Manga Acquire & Crop ──────────────────────────────────────────────────
    "download":             ("mangaeasy.download.mangadex", "main", "Manga: acquire", "Download chapters from MangaDex."),
    "style-detect":         ("mangaeasy.panels.style_detect", "main", "Manga: acquire", "Detect webtoon vs paged format."),
    "gutter-split":         ("mangaeasy.panels.gutter", "main", "Manga: acquire", "Low-level gutter panel splitter."),
    "webtoon-split":        ("mangaeasy.panels.webtoon", "main", "Manga: acquire", "Split webtoon strips into panels."),
    "page-split":           ("mangaeasy.panels.page", "main", "Manga: acquire", "Split paged manga using MAGI v3."),
    "panel-transcript":     ("mangaeasy.ocr.panel_transcript", "main", "Manga: acquire", "Run DeepSeek-OCR 2 on panels."),

    # ── Context & Sheets Packaging ────────────────────────────────────────────
    "panel-reading-sheets": ("mangaeasy.video_pipeline.panel_reading_sheets", "main", "Manga: sheets", "Render multi-panel reading sheets."),
    "narration-review-sheets": ("mangaeasy.video_pipeline.narration_sheets", "main", "Manga: sheets", "Render review sheets with OCR."),
    "sheets-pack":          ("mangaeasy.images.sheets_zip", "main", "Manga: sheets", "Pack generated sheets into split ZIPs <= 1 GB stored in <project_root>/zips/."),

    # ── Narration, Audio & Subtitles ──────────────────────────────────────────
    "narration-check":      ("mangaeasy.video_pipeline.narration_check", "main", "Audio & Narration", "Validate narration.json structure."),
    "narration-edit":       ("mangaeasy.video_pipeline.narration_edit", "main", "Audio & Narration", "Edit narration entries via CLI."),
    "video-audio":          ("mangaeasy.video_pipeline.generate_audio", "main", "Audio & Narration", "Generate audio with Kokoro or IndexTTS."),
    "video-subtitles":      ("mangaeasy.audio.subtitles_whisper", "main", "Audio & Narration", "Generate .ass/.srt subtitles using Whisper large-v3-turbo from HuggingFace."),

    # ── Video Build & Quality ─────────────────────────────────────────────────
    "video":                ("mangaeasy.video_pipeline.run_pipeline", "main", "Video Pipeline", "Full video pipeline execution."),
    "video-render":         ("mangaeasy.video_pipeline.make_videos", "main", "Video Pipeline", "Render item videos from panels + audio."),
    "video-join":           ("mangaeasy.video_pipeline.make_long_video", "main", "Video Pipeline", "Join item videos into a full recap."),
    "video-add-bgm":        ("mangaeasy.video_pipeline.add_long_video_bgm", "main", "Video Pipeline", "Mix background music into video."),
    "video-quality":        ("mangaeasy.video_pipeline.quality_gate", "main", "Video Pipeline", "Measure deliverable loudness & quality."),
}


def _print_help():
    print(f"{PRODUCT_NAME} {__version__} - manga and webtoon recap production\n")
    print("Usage: mangaeasy <command> [args...]\n")
    print("Available Commands:")
    for cmd, (_, _, group, desc) in sorted(COMMANDS.items()):
        print(f"  {cmd:<24} [{group}] {desc}")


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