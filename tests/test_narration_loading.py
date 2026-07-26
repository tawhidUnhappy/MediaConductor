"""`load_narration` is the single source of truth for reading an item's
narration — including the `intro.json` prepend behaviour that has bitten
modules re-implementing their own loader in the past.

Since the strict contract landed it is also the single *validator*: every
consumer gets entries that have already been checked, so none of them has to
re-derive what a safe `image` value is. The traversal/uniqueness/unknown-field
rules themselves live in test_narration_contract.py.
"""

import json
import sys

import pytest

from mediaconductor.video_pipeline import generate_audio_indextts
from mediaconductor.video_pipeline.item_assets import (
    frame_aligned_duration,
    load_narration,
    validate_calm_narration,
)
from mediaconductor.video_pipeline.narration_contract import NarrationContractError


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def make_item(root, *, narration, intro=None, panels=("a.png",)):
    """A minimally valid item: panels/ plus narration.json (and maybe intro)."""
    root.mkdir(parents=True, exist_ok=True)
    panels_dir = root / "panels"
    panels_dir.mkdir(exist_ok=True)
    for name in panels:
        (panels_dir / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    write_json(root / "narration.json", narration)
    if intro is not None:
        write_json(root / "intro.json", intro)
    return root


def test_reads_narration_json(tmp_path):
    make_item(tmp_path, narration=[{"image": "a.png", "narration": "Hello"}])
    entries = load_narration(tmp_path)
    assert [(e["image"], e["narration"]) for e in entries] == [("a.png", "Hello")]


def test_intro_json_is_prepended(tmp_path):
    make_item(
        tmp_path,
        narration=[{"image": "a.png", "narration": "main"}],
        intro=[{"image": "hook.png", "narration": "cold open"}],
        panels=("a.png", "hook.png"),
    )
    entries = load_narration(tmp_path)
    assert [e["image"] for e in entries] == ["hook.png", "a.png"]


def test_every_entry_gets_a_stable_unique_beat_id(tmp_path):
    make_item(
        tmp_path,
        narration=[
            {"image": "a.png", "narration": "one"},
            {"image": "b.png", "narration": "two"},
        ],
        panels=("a.png", "b.png"),
    )
    beats = [entry["beat_id"] for entry in load_narration(tmp_path)]
    assert len(set(beats)) == len(beats)
    # Derived from item + panel stem, so it survives a re-read unchanged.
    assert beats == [f"{tmp_path.name}-a", f"{tmp_path.name}-b"]
    assert beats == [entry["beat_id"] for entry in load_narration(tmp_path)]


def test_utf8_bom_tolerated(tmp_path):
    make_item(tmp_path, narration=[])
    (tmp_path / "narration.json").write_bytes(
        b"\xef\xbb\xbf" + json.dumps([{"image": "a.png", "narration": "hi"}]).encode()
    )
    assert [e["image"] for e in load_narration(tmp_path)] == ["a.png"]


def test_intro_panel_reused_in_narration_is_rejected(tmp_path):
    """The intro is prepended, so a shared panel would render twice."""
    make_item(
        tmp_path,
        narration=[{"image": "a.png", "narration": "main"}],
        intro=[{"image": "a.png", "narration": "cold open"}],
    )
    with pytest.raises(NarrationContractError, match="duplicate image"):
        load_narration(tmp_path)


def test_non_array_narration_rejected(tmp_path):
    make_item(tmp_path, narration=[])
    write_json(tmp_path / "narration.json", {"image": "a.png"})
    with pytest.raises(NarrationContractError):
        load_narration(tmp_path)


def test_non_array_intro_rejected(tmp_path):
    make_item(tmp_path, narration=[], intro=[])
    write_json(tmp_path / "intro.json", {"image": "a.png"})
    with pytest.raises(NarrationContractError):
        load_narration(tmp_path)


def test_missing_narration_file_is_reported_by_path(tmp_path):
    (tmp_path / "panels").mkdir(parents=True)
    with pytest.raises(NarrationContractError, match="narration.json is missing"):
        load_narration(tmp_path)


def test_calm_preflight_blocks_unsafe_delivery_before_tts(tmp_path):
    entries = [
        {"image": "a.png", "narration": "GHAHA!"},
    ]
    with pytest.raises(ValueError, match="calm-narration policy") as exc:
        validate_calm_narration(entries, tmp_path / "narration.json")
    assert "a.png" in str(exc.value)


def test_calm_preflight_accepts_restrained_narration(tmp_path):
    entries = [
        {"image": "a.png", "narration": "The phoenix appears above the ruined gate."},
        {"image": "b.png", "narration": "NASA records the event from orbit that night."},
    ]
    validate_calm_narration(entries, tmp_path / "narration.json")


def test_calm_preflight_does_not_block_on_style_warnings(tmp_path):
    """Repetition is an editorial call; it must not stop a render by itself."""
    entries = [
        {"image": f"{index}.png", "narration": "Then he walks into the empty hall."}
        for index in range(8)
    ]
    validate_calm_narration(entries, tmp_path / "narration.json")


def test_indextts_outer_preflight_blocks_all_workers_before_start(tmp_path, monkeypatch):
    project_root = tmp_path / "Story"
    for name, narration in (
        ("01", "The first chapter begins calmly in the rain."),
        ("02", "GHAHA! The second chapter begins."),
    ):
        make_item(
            project_root / name,
            narration=[{"image": f"{name}_001.png", "narration": narration}],
            panels=(f"{name}_001.png",),
        )
    # The review gate runs before narration validation, so record it first;
    # this test is about the narration preflight, not the review gate.
    from mediaconductor.reviews import record_crop_review, record_narration_review
    record_crop_review(project_root, None, reviewer="test", source_subdir="panels")
    record_narration_review(project_root, None, reviewer="test")

    speaker = tmp_path / "speaker.wav"
    speaker.write_bytes(b"placeholder")
    subprocesses: list[list[str]] = []
    monkeypatch.setattr(generate_audio_indextts.runtime, "run",
                        lambda command, **_kwargs: subprocesses.append(command))
    monkeypatch.setattr(sys, "argv", [
        "video-audio-indextts",
        "--project-root", str(project_root),
        "--speaker-wav", str(speaker),
        "--gpu-workers", "2",
        "--item-range", "01-02",
    ])
    with pytest.raises(ValueError, match="calm-narration policy"):
        generate_audio_indextts.main()
    assert subprocesses == []


def test_frame_aligned_duration_rounds_up_to_whole_frames():
    # 1.01 s at 30 fps -> 31 frames, never truncating audio
    duration, frames = frame_aligned_duration(1.01, 30)
    assert frames == 31
    assert duration == pytest.approx(31 / 30)


def test_frame_aligned_duration_minimum_one_frame():
    duration, frames = frame_aligned_duration(0.0, 30)
    assert frames == 1
    assert duration == pytest.approx(1 / 30)
