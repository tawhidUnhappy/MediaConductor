from __future__ import annotations

import json
import subprocess
import sys

import pytest

from mangaeasy.cli import COMMANDS
from mangaeasy.command_spec import JSON_COMMANDS, LONG_RUNNING, TOOLS
from mangaeasy.mcp_server import _allowed_tools, _run_tool, _tools_list
from mangaeasy.modes import DEFAULT_MODE, MODES, resolve_skill_path
from mangaeasy.tools.install import TOOLS as EXTERNAL_TOOLS
from mangaeasy.tools.setup import MODE_TOOLS


def test_mode_registries_reference_real_surfaces():
    for key, mode in MODES.items():
        assert mode.commands <= set(COMMANDS)
        assert mode.tools <= set(TOOLS)
        assert set(mode.required_external_tools + mode.optional_external_tools) <= set(EXTERNAL_TOOLS)
        assert (resolve_skill_path(key) / "SKILL.md").is_file()


def test_manga_is_the_only_mode_and_the_default():
    assert set(MODES) == {"manga-video"}
    assert DEFAULT_MODE == "manga-video"
    assert set(MODE_TOOLS) == {"manga-video"}


# ── Registry integrity ───────────────────────────────────────────────────────
# These exist because CLI, modes, MCP, setup, installer, and jobs each used to
# keep their own idea of what a command was, and a removal that missed one of
# them left the feature reachable through whichever registry was forgotten.

def test_every_mcp_tool_maps_to_a_real_cli_command():
    for tool, (cli_name, *_rest) in TOOLS.items():
        assert cli_name in COMMANDS, f"MCP tool {tool!r} maps to unknown command {cli_name!r}"


def test_every_mode_tool_and_command_agree_with_each_other():
    """A mode's tool list and command list must describe the same surface."""
    for mode in MODES.values():
        for tool in mode.tools:
            cli_name = TOOLS[tool][0]
            assert cli_name in mode.commands, (
                f"tool {tool!r} is visible in {mode.key} but its command "
                f"{cli_name!r} is not"
            )


def test_json_and_long_running_tables_reference_real_commands():
    assert JSON_COMMANDS <= set(COMMANDS)
    assert LONG_RUNNING <= set(COMMANDS)


def test_removed_features_are_absent_from_every_registry():
    """Nothing that was deleted may survive in a registry under any spelling."""
    removed = (
        "story", "song", "lyric", "ace-step", "ace_step", "demucs", "whisperx",
        "zimage", "z-image", "deepseek-ocr2", "to-pdf", "convert-images",
        "watermark", "ai-zip",
    )
    surfaces = set(COMMANDS) | set(TOOLS) | JSON_COMMANDS | LONG_RUNNING
    for mode in MODES.values():
        surfaces |= mode.commands | mode.tools
    for name in sorted(surfaces):
        lowered = name.casefold()
        for token in removed:
            assert token not in lowered, f"removed feature {token!r} still registered as {name!r}"


def test_mcp_catalog_is_the_manga_catalog():
    manga = {tool["name"] for tool in _tools_list()}
    assert manga == MODES[DEFAULT_MODE].tools & set(TOOLS)
    assert {
        "webtoon_cutcheck", "webtoon_override", "panels_remap",
        "narration_review_sheets", "narration_edit", "audio_audit",
        "manga_review", "panel_decisions", "manga_rights", "video_quality",
    } <= manga
    assert not {"story_init", "song_init", "generate_image", "generate_song"} & manga


def test_no_review_confirmation_boolean_is_accepted_anywhere():
    """Review must be a recorded artifact, never an argument a model can set."""
    for tool, (_cli, _desc, props, _required, _flags) in TOOLS.items():
        for prop in props:
            assert "review_confirmed" not in prop, (
                f"{tool}.{prop} would let a caller assert its own review"
            )


def test_job_start_only_offers_long_running_mode_tools():
    schema = next(tool for tool in _tools_list() if tool["name"] == "job_start")
    targets = schema["inputSchema"]["properties"]["tool"]["enum"]
    allowed = _allowed_tools(DEFAULT_MODE)
    for target in targets:
        assert target in allowed
        assert TOOLS[target][0] in LONG_RUNNING
    assert "job_start" not in targets


def test_mode_rejects_hidden_tools_and_job_escape():
    with pytest.raises(ValueError, match="not available"):
        _run_tool("youtube_auth", {}, DEFAULT_MODE)
    with pytest.raises(ValueError, match="outside MCP mode"):
        _run_tool("job_start", {"tool": "youtube_auth", "arguments": {}}, DEFAULT_MODE)
    with pytest.raises(ValueError, match="outside MCP mode"):
        _run_tool("install_tool", {"name": "ace-step"}, DEFAULT_MODE)


def test_job_start_rejects_recursion():
    with pytest.raises(ValueError, match="outside MCP mode|recursive"):
        _run_tool("job_start", {"tool": "job_start", "arguments": {}}, DEFAULT_MODE)


def test_mcp_help_does_not_start_server():
    proc = subprocess.run(
        [sys.executable, "-m", "mangaeasy.cli", "mcp", "--help"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0
    assert "--mode" in proc.stdout
    assert "--allow-root" in proc.stdout
    # The escape hatch that exposed every tool regardless of mode is gone.
    assert "--all-tools" not in proc.stdout


def test_mode_setup_dry_run_is_exact():
    proc = subprocess.run(
        [sys.executable, "-m", "mangaeasy.cli", "setup", "--mode", "manga-video", "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0
    marker = next(line for line in proc.stdout.splitlines() if line.startswith("MANGAEASY_RESULT "))
    payload = json.loads(marker.partition(" ")[2])
    assert payload["tools"] == ["kokoro-82m", "index-tts", "magi-v3", "deepseek-ocr2"]
