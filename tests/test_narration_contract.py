"""The strict narration contract.

Each case here is a way an `image` value, or an entry field, used to reach a
consumer that assumed someone else had validated it.
"""

from __future__ import annotations

import json

import pytest

from mangaeasy.video_pipeline.narration_contract import (
    NarrationContractError,
    narration_problems,
    validate_entries,
    validate_item_narration,
)


@pytest.fixture()
def item(tmp_path):
    """An item with three real panels and no narration file yet."""
    panels = tmp_path / "panels"
    panels.mkdir(parents=True)
    for name in ("a.png", "b.png", "c.jpg"):
        (panels / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


def write(item, entries, name="narration.json"):
    (item / name).write_text(json.dumps(entries), encoding="utf-8")


def check(item, entries):
    write(item, entries)
    return validate_item_narration(item)


def expect_error(item, entries, match):
    write(item, entries)
    with pytest.raises(NarrationContractError, match=match):
        validate_item_narration(item)


# ── image must be a plain basename inside panels/ ────────────────────────────

@pytest.mark.parametrize("image", [
    "/etc/passwd",
    "\\windows\\system32\\config",
    "C:/Windows/win.ini",
    "c:a.png",
    "//server/share/a.png",
    "\\\\server\\share\\a.png",
])
def test_absolute_drive_and_unc_paths_are_rejected(item, image):
    expect_error(item, [{"image": image, "narration": "x"}],
                 "absolute path|drive path|UNC path|not a path")


@pytest.mark.parametrize("image", [
    "../a.png",
    "..\\a.png",
    "sub/../a.png",
    "../../panels/a.png",
])
def test_traversal_paths_are_rejected(item, image):
    expect_error(item, [{"image": image, "narration": "x"}], "path|traversal")


@pytest.mark.parametrize("image", ["sub/a.png", "sub\\a.png", "nested/dir/a.png"])
def test_nested_panel_paths_are_rejected(item, image):
    expect_error(item, [{"image": image, "narration": "x"}], "bare filename")


def test_panel_must_resolve_to_a_direct_child(item):
    """Resolved containment, not only a string check on the raw value."""
    from mangaeasy.video_pipeline.narration_contract import resolve_panel_path

    panels = item / "panels"
    assert resolve_panel_path("a.png", panels, "x") == (panels / "a.png").resolve()
    # ".." resolves to the item folder, whose parent is not panels/.
    with pytest.raises(NarrationContractError, match="direct child"):
        resolve_panel_path("..", panels, "x")


def test_unsupported_extension_is_rejected(item):
    (item / "panels" / "notes.txt").write_text("x", encoding="utf-8")
    expect_error(item, [{"image": "notes.txt", "narration": "x"}], "unsupported extension")


def test_missing_panel_file_is_reported(item):
    expect_error(item, [{"image": "gone.png", "narration": "x"}], "panel image not found")


# ── uniqueness ───────────────────────────────────────────────────────────────

def test_case_insensitive_filename_collision_is_rejected(item):
    (item / "panels" / "A.PNG").write_bytes(b"x")
    expect_error(
        item,
        [{"image": "a.png", "narration": "one"}, {"image": "A.PNG", "narration": "two"}],
        "duplicate image",
    )


def test_case_insensitive_stem_collision_is_rejected(item):
    """Audio is `<stem>.wav`, so a.png and a.jpg would share one WAV."""
    (item / "panels" / "A.jpg").write_bytes(b"x")
    expect_error(
        item,
        [{"image": "a.png", "narration": "one"}, {"image": "A.jpg", "narration": "two"}],
        "collides",
    )


def test_duplicate_explicit_beat_ids_are_rejected(item):
    expect_error(
        item,
        [
            {"image": "a.png", "narration": "one", "beat_id": "ch01-b1"},
            {"image": "b.png", "narration": "two", "beat_id": "ch01-b1"},
        ],
        "duplicate beat_id",
    )


# ── field discipline ─────────────────────────────────────────────────────────

def test_unknown_properties_are_rejected(item):
    expect_error(item, [{"image": "a.png", "narration": "x", "speaker": "Ren"}],
                 "unknown propert")


def test_typo_in_a_known_field_is_caught_rather_than_ignored(item):
    expect_error(item, [{"image": "a.png", "naration": "x"}], "unknown propert")


def test_legacy_text_field_names_its_replacement(item):
    expect_error(item, [{"image": "a.png", "text": "x"}], "rename legacy field")


def test_empty_narration_is_rejected(item):
    expect_error(item, [{"image": "a.png", "narration": "   "}], "non-empty text")


def test_missing_required_fields_are_reported(item):
    expect_error(item, [{"image": "a.png"}], "missing required")


# ── editorial fields and their bounds ────────────────────────────────────────

def test_valid_strict_entry_round_trips(item):
    entries = check(item, [{
        "beat_id": "ch01-b0042",
        "image": "a.png",
        "narration": "He realizes the gate was opened from inside.",
        "evidence": ["a.png", "b.png"],
        "pause_after_ms": 240,
    }])
    assert entries[0]["beat_id"] == "ch01-b0042"
    assert entries[0]["pause_after_ms"] == 240
    assert entries[0]["evidence"] == ["a.png", "b.png"]


@pytest.mark.parametrize("pause", [-1, 60_000, 1.5, True, "240"])
def test_invalid_pause_values_are_rejected(item, pause):
    expect_error(item, [{"image": "a.png", "narration": "x", "pause_after_ms": pause}],
                 "pause_after_ms")


def test_evidence_must_name_existing_panels(item):
    expect_error(item, [{"image": "a.png", "narration": "x", "evidence": ["missing.png"]}],
                 "evidence panel not found")


def test_evidence_entries_obey_the_same_path_rules(item):
    expect_error(item, [{"image": "a.png", "narration": "x", "evidence": ["../a.png"]}],
                 "path|traversal")


# ── report-style access ──────────────────────────────────────────────────────

def test_narration_problems_reports_instead_of_raising(item):
    write(item, [{"image": "../a.png", "narration": "x"}])
    problems = narration_problems(item)
    assert problems and "narration.json" in problems[0]


def test_narration_problems_is_empty_for_a_clean_item(item):
    write(item, [{"image": "a.png", "narration": "A clean, complete beat."}])
    assert narration_problems(item) == []


def test_validate_entries_can_skip_disk_access(item):
    entries = validate_entries(
        [{"image": "not-on-disk.png", "narration": "x"}],
        label="narration.json",
        panels_dir=item / "panels",
        require_files=False,
    )
    assert entries[0]["image"] == "not-on-disk.png"
