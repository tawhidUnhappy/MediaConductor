from __future__ import annotations

import json
import sys
from pathlib import Path

from mediaconductor.video_pipeline import audio_audit


def _ready_item(project_root: Path, audio_root: Path, name: str) -> None:
    item_dir = project_root / name
    panels_dir = item_dir / "panels"
    panels_dir.mkdir(parents=True)
    (panels_dir / "panel.png").write_bytes(b"panel")
    (item_dir / "narration.json").write_text(
        json.dumps([{"image": "panel.png", "narration": "Example."}]),
        encoding="utf-8",
    )
    item_audio = audio_root / project_root.name / name
    item_audio.mkdir(parents=True)
    (item_audio / "panel.wav").write_bytes(b"audio")


def test_human_audit_emits_one_progress_tick_per_item(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "Story"
    audio_root = tmp_path / "audio"
    _ready_item(project_root, audio_root, "01")
    _ready_item(project_root, audio_root, "02")
    monkeypatch.setattr(audio_audit, "ffprobe_duration", lambda _path: 1.0)
    monkeypatch.setattr(sys, "argv", [
        "video-audio-audit",
        "--project-root", str(project_root),
        "--audio-root", str(audio_root),
    ])

    assert audio_audit.main() == 0
    progress = [
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("MEDIACONDUCTOR_PROGRESS")
    ]
    assert progress == [
        "MEDIACONDUCTOR_PROGRESS 1/2 Audited 01",
        "MEDIACONDUCTOR_PROGRESS 2/2 Audited 02",
    ]


def test_json_audit_stdout_remains_one_json_object(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "Story"
    audio_root = tmp_path / "audio"
    _ready_item(project_root, audio_root, "01")
    (project_root / "02").mkdir()
    monkeypatch.setattr(audio_audit, "ffprobe_duration", lambda _path: 1.0)
    monkeypatch.setattr(sys, "argv", [
        "video-audio-audit",
        "--project-root", str(project_root),
        "--audio-root", str(audio_root),
        "--json",
    ])

    assert audio_audit.main() == 0
    captured = capsys.readouterr()
    stdout = captured.out.strip()
    assert len(stdout.splitlines()) == 1
    payload = json.loads(stdout)
    assert payload["checked_items"] == 1
    assert payload["not_ready"] == ["02"]
    assert payload["ok"] is True
    assert captured.err.splitlines() == [
        "MEDIACONDUCTOR_PROGRESS 1/2 Audited 01",
        "MEDIACONDUCTOR_PROGRESS 2/2 Audited 02",
    ]
