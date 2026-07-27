"""The machine-readable CLI contract agents rely on: `commands --json`,
`where --json`, exit codes, and the MEDIACONDUCTOR_RESULT marker helper."""

import json
import subprocess
import sys

from mediaconductor import __version__
from mediaconductor.cli import COMMANDS, main
from mediaconductor.utils import emit_result


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mediaconductor.cli", *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_commands_json_catalog(capsys):
    assert main(["commands", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == __version__
    names = {entry["name"] for entry in data["commands"]}
    assert names == set(COMMANDS)
    sample = data["commands"][0]
    assert set(sample) == {"name", "group", "help", "usage"}


def test_full_catalog_describes_typed_job_wrapper_and_source_layout(capsys):
    assert main(["commands", "--mode", "manga-video", "--json", "--full"]) == 0
    data = json.loads(capsys.readouterr().out)
    commands = {entry["name"]: entry for entry in data["commands"]}
    assert not {"llm", "crop-qa", "characters", "narrate-auto", "manga-auto"} & set(commands)

    job_args = commands["job-start"]["args"]
    assert job_args["tool"]["flag"] == "--tool"
    assert job_args["arguments"]["flag"] == "--arguments-json"
    assert job_args["arguments"]["kind"] == "json"

    assert commands["style-detect"]["args"]["source_subdir"]["flag"] == "--source-subdir"
    assert commands["panel-transcript"]["args"]["seed_only"]["flag"] == "--seed-only"
    chapters = commands["video-chapters"]["args"]
    assert chapters["output_root"]["flag"] == "--output-root"
    assert chapters["item_range"]["flag"] == "--item-range"
    assert chapters["allow_gaps"]["flag"] == "--allow-gaps"
    assert commands["video"]["args"]["validate"]["flag"] == "--no-validate"
    assert "emo_alpha" not in commands["video"]["args"]
    assert "no_emotion" not in commands["video"]["args"]
    sheets = commands["narration-review-sheets"]["args"]
    assert sheets["output_root"]["flag"] == "--output-root"

    # The review gates are part of the published contract, not side doors.
    assert commands["manga-review"]["args"]["action"]["kind"] == "positional"
    assert commands["youtube-upload"]["args"]["project_root"]["required"] is True
    assert commands["manga-rights"]["args"]["action"]["kind"] == "positional"
    assert "review_policy" not in commands["video"]["args"]


def test_where_json_keys(capsys):
    assert main(["where", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    for key in ("version", "platform", "frozen", "app_root", "data_root",
                "runtime_home", "tools_home", "vendored_bin_dirs", "env_overrides"):
        assert key in data
    assert data["version"] == __version__


def test_tools_json(capsys):
    assert main(["tools", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "tools_home" in data
    # Only the manga toolchain remains: TTS (two engines), panel detection,
    # and the optional OCR cross-check.
    assert set(data["tools"]) == {
        "kokoro-82m", "index-tts", "magi-v3", "deepseek-ocr2",
    }


def test_emit_result_line_is_parseable(capsys):
    emit_result(outputs=["a/b.mp4"], extra=1)
    line = capsys.readouterr().out.strip()
    assert line.startswith("MEDIACONDUCTOR_RESULT ")
    payload = json.loads(line[len("MEDIACONDUCTOR_RESULT "):])
    assert payload == {"outputs": ["a/b.mp4"], "extra": 1}


def test_exit_code_2_on_usage_error():
    proc = run_cli("video-check", "--no-such-flag")
    assert proc.returncode == 2


def test_exit_code_1_on_runtime_failure(tmp_path):
    proc = run_cli("video-check", "--project-root", str(tmp_path / "does-not-exist"))
    assert proc.returncode == 1


def test_piped_stdout_is_utf8():
    """Help output contains non-cp1252 characters (e.g. U+2212); piping it
    must not crash on Windows (the historical failure mode)."""
    proc = run_cli("--help")
    assert proc.returncode == 0
    assert "video" in proc.stdout
