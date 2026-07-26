from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from mediaconductor import defaults
from mediaconductor.reviews import (
    REVIEW_RECORD_RELATIVE_PATH,
    ReviewRecordError,
    check_review_records,
    load_review_store,
    record_crop_review,
    record_final_video_review,
    record_narration_review,
)
from mediaconductor.video_pipeline import run_pipeline

REVIEWED_AT = "2026-07-26T12:00:00+00:00"


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "library" / "Story"
    item = root / "01"
    (item / "download").mkdir(parents=True)
    (item / "panels").mkdir()
    (item / "download" / "001.jpg").write_bytes(b"source-page-v1")
    (item / "panels" / "ch01_001.jpg").write_bytes(b"panel-crop-v1")
    (item / "narration.json").write_text(
        json.dumps([
            {
                "image": "ch01_001.jpg",
                "narration": "The traveler reaches the silent gate.",
            }
        ]),
        encoding="utf-8",
    )
    return root, item


def _approve_inputs(root: Path) -> None:
    record_crop_review(
        root,
        ["01"],
        reviewer="vision-reviewer",
        reviewed_at=REVIEWED_AT,
    )
    record_narration_review(
        root,
        ["01"],
        reviewer="narration-reviewer",
        reviewed_at=REVIEWED_AT,
    )


def test_crop_and_narration_records_are_current_and_canonical(tmp_path):
    root, _item = _project(tmp_path)
    _approve_inputs(root)

    report = check_review_records(root, ["01"])
    assert report["ok"] is True
    assert report["stages"]["crop"]["items"]["01"]["status"] == "current"
    assert report["stages"]["narration"]["items"]["01"]["status"] == "current"

    record_path = root / REVIEW_RECORD_RELATIVE_PATH
    stored = json.loads(record_path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == 1
    assert stored["crop"]["01"]["reviewer"] == "vision-reviewer"
    assert stored["crop"]["01"]["reviewed_at"] == REVIEWED_AT
    assert stored["crop"]["01"]["sources"]["files"][0]["path"] == "download/001.jpg"
    assert stored["crop"]["01"]["panels"]["files"][0]["path"] == "panels/ch01_001.jpg"
    assert stored["narration"]["01"]["scripts"]["files"][0]["path"] == "narration.json"
    # Canonical serializer is stable for an unchanged in-memory store.
    before = record_path.read_bytes()
    record_narration_review(
        root,
        ["01"],
        reviewer="narration-reviewer",
        reviewed_at=REVIEWED_AT,
    )
    assert record_path.read_bytes() == before


def test_exact_input_changes_invalidate_only_affected_stages(tmp_path):
    root, item = _project(tmp_path)
    _approve_inputs(root)

    (item / "download" / "001.jpg").write_bytes(b"source-page-v2")
    report = check_review_records(root, ["01"])
    assert report["ok"] is False
    assert report["stages"]["crop"]["items"]["01"]["status"] == "stale"
    assert report["stages"]["narration"]["items"]["01"]["status"] == "current"

    record_crop_review(
        root,
        ["01"],
        reviewer="vision-reviewer",
        reviewed_at=REVIEWED_AT,
    )
    (item / "panels" / "ch01_001.jpg").write_bytes(b"panel-crop-v2")
    report = check_review_records(root, ["01"])
    assert report["stages"]["crop"]["items"]["01"]["status"] == "stale"
    assert report["stages"]["narration"]["items"]["01"]["status"] == "stale"


def test_new_intro_or_changed_narration_invalidates_narration_review(tmp_path):
    root, item = _project(tmp_path)
    _approve_inputs(root)

    (item / "intro.json").write_text(
        json.dumps([
            {
                "image": "ch01_001.jpg",
                "narration": "A warning from later in the story opens the recap.",
            }
        ]),
        encoding="utf-8",
    )
    report = check_review_records(root, ["01"], stages=("narration",))
    assert report["ok"] is False
    assert report["stages"]["narration"]["items"]["01"]["status"] == "stale"


def test_final_video_review_binds_mp4_inputs_and_acknowledgements(tmp_path):
    root, item = _project(tmp_path)
    _approve_inputs(root)
    video = tmp_path / "output" / "Story_full.mp4"
    video.parent.mkdir()
    video.write_bytes(b"final-video-v1")

    with pytest.raises(ReviewRecordError, match="source_permission_confirmed"):
        record_final_video_review(
            root,
            video,
            ["01"],
            reviewer="final-reviewer",
            reviewed_at=REVIEWED_AT,
            rights_confirmed=True,
            voice_consent_confirmed=True,
            source_permission_confirmed=False,
        )

    record_final_video_review(
        root,
        video,
        ["01"],
        reviewer="final-reviewer",
        reviewed_at=REVIEWED_AT,
        rights_confirmed=True,
        voice_consent_confirmed=True,
        source_permission_confirmed=True,
    )
    current = check_review_records(
        root,
        ["01"],
        stages=("final_video",),
        video=video,
    )
    assert current["ok"] is True

    video.write_bytes(b"final-video-v2")
    changed_video = check_review_records(
        root,
        ["01"],
        stages=("final_video",),
        video=video,
    )
    assert changed_video["ok"] is False
    assert changed_video["stages"]["final_video"]["status"] == "stale"

    video.write_bytes(b"final-video-v1")
    narration = json.loads((item / "narration.json").read_text(encoding="utf-8"))
    narration[0]["narration"] = "The traveler cautiously approaches the silent gate."
    (item / "narration.json").write_text(json.dumps(narration), encoding="utf-8")
    changed_inputs = check_review_records(
        root,
        ["01"],
        stages=("final_video",),
        video=video,
    )
    assert changed_inputs["ok"] is False
    assert "crop or narration inputs changed" in changed_inputs["problems"][0]


def test_full_pipeline_requires_current_reviews_before_any_stage(tmp_path, monkeypatch):
    root, _item = _project(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(run_pipeline, "run", lambda command, _cwd: commands.append(command))
    monkeypatch.setattr(sys, "argv", [
        "video",
        "--project-root", str(root),
        "--audio-root", str(tmp_path / "audio"),
        "--output-root", str(tmp_path / "output"),
        "--work-dir", str(tmp_path / "work"),
        "--items", "01",
        "--skip-audio",
        "--audio-source", "raw",
        "--no-background-music",
        "--no-validate",
    ])

    with pytest.raises(ReviewRecordError, match="review gate failed before the full pipeline"):
        run_pipeline.main()
    assert commands == []


def test_full_pipeline_accepts_current_reviews(tmp_path, monkeypatch):
    root, _item = _project(tmp_path)
    _approve_inputs(root)
    commands: list[list[str]] = []
    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(run_pipeline, "resolve_tts_engine", lambda *_args: "kokoro")
    monkeypatch.setattr(run_pipeline, "run", lambda command, _cwd: commands.append(list(command)))
    monkeypatch.setattr(run_pipeline, "emit_result", lambda **_kwargs: None)
    monkeypatch.setattr(sys, "argv", [
        "video",
        "--project-root", str(root),
        "--audio-root", str(tmp_path / "audio"),
        "--output-root", str(tmp_path / "output"),
        "--work-dir", str(tmp_path / "work"),
        "--items", "01",
        "--skip-audio",
        "--audio-source", "raw",
        "--no-background-music",
        "--no-validate",
    ])

    assert run_pipeline.main() == 0
    assert len(commands) == 1
    assert "video-render" in commands[0]
    store = load_review_store(root)
    assert store["crop"]["01"]["input_digest"]
    assert store["narration"]["01"]["input_digest"]
