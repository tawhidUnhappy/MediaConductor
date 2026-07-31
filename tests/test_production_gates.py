"""The gates that make an unreviewed publish impossible.

Each test here corresponds to a way the previous design could be satisfied
without doing the work: a reused WAV that no longer matched its narration, an
omission nobody decided, a persistent root quietly landing outside the
workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mangaeasy.audio.provenance import (
    TtsContract,
    is_current,
    narration_digest,
    normalize_narration,
    read_provenance,
    sidecar_path,
    stale_reason,
    write_provenance,
)
from mangaeasy.panel_decisions import (
    PanelDecisionError,
    audit_item,
    record_decisions,
)


# ── TTS provenance ───────────────────────────────────────────────────────────

CONTRACT = TtsContract(
    engine="indextts",
    model="IndexTTS2",
    revision="checkpoints",
    voice="narrator.wav",
    speaker_wav_sha256="a" * 64,
    language="en",
    speed=1.0,
    settings={"use_deepspeed": False},
)
BEAT = {"narration": "He realizes the gate was opened from inside.",
        "beat_id": "ch01-b0042", "image": "01_005_03.jpg"}


@pytest.fixture()
def take(tmp_path):
    wav = tmp_path / "01_005_03.wav"
    wav.write_bytes(b"RIFF....WAVE")
    write_provenance(wav, contract=CONTRACT, **BEAT)
    return wav


def test_a_matching_take_is_reused(take):
    assert is_current(take, contract=CONTRACT, **BEAT)
    assert stale_reason(take, contract=CONTRACT, **BEAT) is None


def test_narration_whitespace_changes_do_not_force_regeneration(take):
    """Re-indenting the JSON must not cost an hour of GPU time."""
    reflowed = {**BEAT, "narration": "  He realizes the gate\twas opened   from inside.  "}
    assert is_current(take, contract=CONTRACT, **reflowed)


def test_rewriting_the_line_invalidates_the_take(take):
    changed = {**BEAT, "narration": "He realizes the gate was opened from outside."}
    assert stale_reason(take, contract=CONTRACT, **changed) == "narration text changed since this take"


@pytest.mark.parametrize("field,value", [
    ("engine", "kokoro"),
    ("model", "IndexTTS3"),
    ("revision", "checkpoints-v2"),
    ("voice", "other.wav"),
    ("speaker_wav_sha256", "b" * 64),
    ("language", "ja"),
    ("speed", 1.15),
])
def test_any_voice_or_model_change_invalidates_the_take(take, field, value):
    """Swapping the reference WAV's *contents* changes the voice with no rename."""
    changed = TtsContract(**{**CONTRACT.as_dict(), field: value})
    reason = stale_reason(take, contract=changed, **BEAT)
    assert reason is not None
    assert field.replace("_", " ") in reason


def test_generation_settings_are_part_of_the_contract(take):
    changed = TtsContract(**{**CONTRACT.as_dict(), "settings": {"use_deepspeed": True}})
    assert stale_reason(take, contract=changed, **BEAT) is not None


def test_changing_the_panel_or_beat_identity_invalidates_the_take(take):
    assert stale_reason(take, contract=CONTRACT, **{**BEAT, "image": "01_006_01.jpg"}) \
        == "panel changed since this take"
    assert stale_reason(take, contract=CONTRACT, **{**BEAT, "beat_id": "ch01-b0043"}) \
        == "beat identity changed since this take"


def test_a_missing_file_is_never_current(tmp_path):
    assert stale_reason(tmp_path / "nope.wav", contract=CONTRACT, **BEAT) == "no audio file"


def test_pre_provenance_takes_are_not_invalidated_wholesale(tmp_path):
    """Projects generated before sidecars existed must keep working."""
    legacy = tmp_path / "legacy.wav"
    legacy.write_bytes(b"RIFF")
    assert is_current(legacy, contract=CONTRACT, **BEAT)
    assert stale_reason(legacy, contract=CONTRACT, require_sidecar=True, **BEAT) is not None


def test_sidecar_records_the_full_contract(take):
    record = read_provenance(take)
    assert sidecar_path(take).name.endswith(".wav.json")
    assert record["narration_sha256"] == narration_digest(BEAT["narration"])
    assert record["narration_preview"] == normalize_narration(BEAT["narration"])
    for field in ("engine", "model", "revision", "voice", "speaker_wav_sha256",
                  "language", "speed", "settings", "beat_id", "image", "generated_at"):
        assert field in record


def test_archiving_a_stale_take_moves_its_sidecar_too(take, tmp_path):
    from mangaeasy.audio.provenance import archive_stale_take

    archive = tmp_path / "old" / "run_0001"
    archive_stale_take(take, archive, subdir="01")
    assert not take.exists()
    assert not sidecar_path(take).exists()
    archived = sorted(p.name for p in (archive / "01").iterdir())
    assert archived == ["01_005_03.wav", "01_005_03.wav.json"]


# ── Panel decisions ──────────────────────────────────────────────────────────

@pytest.fixture()
def item(tmp_path):
    panels = tmp_path / "panels"
    panels.mkdir(parents=True)
    for name in ("a.png", "b.png", "credits.png"):
        (panels / name).write_bytes(b"\x89PNG\r\n\x1a\n" + name.encode())
    (tmp_path / "narration.json").write_text(
        json.dumps([{"image": "a.png", "narration": "The gate opens from inside."},
                    {"image": "b.png", "narration": "He steps back into the rain."}]),
        encoding="utf-8",
    )
    return tmp_path


def test_an_undecided_panel_is_unaccounted_for(item):
    report = audit_item(item)
    assert not report["ok"]
    assert report["unaccounted"] == ["credits.png"]


def test_a_recorded_omission_accounts_for_the_panel(item):
    record_decisions(item, ["credits.png"], reason="credit", reviewer="sam")
    report = audit_item(item)
    assert report["ok"]
    assert report["decided"][0]["reason"] == "credit"
    assert report["decided"][0]["decided_by"] == "sam"


def test_other_requires_a_note(item):
    with pytest.raises(PanelDecisionError, match="requires --note"):
        record_decisions(item, ["credits.png"], reason="other", reviewer="sam")
    record_decisions(item, ["credits.png"], reason="other", reviewer="sam",
                     note="duplicate of the previous chapter's closing splash")
    assert audit_item(item)["ok"]


def test_reason_vocabulary_is_closed(item):
    with pytest.raises(PanelDecisionError, match="reason must be one of"):
        record_decisions(item, ["credits.png"], reason="looked boring", reviewer="sam")


def test_a_recrop_invalidates_the_decision(item):
    record_decisions(item, ["credits.png"], reason="credit", reviewer="sam")
    (item / "panels" / "credits.png").write_bytes(b"different art entirely")
    report = audit_item(item)
    assert not report["ok"]
    assert "changed after the omission decision" in report["stale_decisions"][0]["detail"]


def test_decisions_cannot_name_a_panel_outside_the_folder(item):
    with pytest.raises(PanelDecisionError, match="filename inside panels/"):
        record_decisions(item, ["../narration.json"], reason="credit", reviewer="sam")


def test_reviewer_is_required(item):
    with pytest.raises(PanelDecisionError, match="reviewer must be"):
        record_decisions(item, ["credits.png"], reason="credit", reviewer="  ")


# ── Workspace layout ─────────────────────────────────────────────────────────

def test_workspace_layout_reports_every_persistent_root(monkeypatch, tmp_path):
    import mangaeasy.workspace as workspace

    report = workspace.layout_report()
    names = {entry["name"] for entry in report["roots"]}
    assert {
        "workspace_root", "data_root", "items_root", "audio_root", "faded_audio_root",
        "output_root", "review_root", "work_dir", "jobs_dir", "runtime_home",
        "tools_home", "cache_home", "state_home", "secrets_home",
    } <= names
    for entry in report["roots"]:
        assert entry["path"]


def test_every_production_root_lands_inside_the_deletable_data_folder(monkeypatch, tmp_path):
    """The whole promise: deleting data/ is a complete fresh start.

    If any root that holds downloaded or generated files resolves outside
    data/, that promise silently becomes false — the case this asserts
    against, on the real resolution path rather than a stubbed one.
    """
    import mangaeasy.workspace as workspace

    report = workspace.layout_report()
    data_root = Path(report["data_root"])
    production = ("items_root", "audio_root", "faded_audio_root", "output_root",
                  "review_root", "work_dir", "jobs_dir")
    for entry in report["roots"]:
        if entry["name"] in production:
            path = Path(entry["path"])
            assert path == data_root or path.is_relative_to(data_root), \
                f"{entry['name']} -> {path} is outside {data_root}"
    # ...and the machinery must NOT be in there, or a reset costs a re-download.
    runtime = Path(report["runtime_home"])
    assert not (runtime == data_root or runtime.is_relative_to(data_root))


def test_a_root_escaping_its_tree_is_reported(monkeypatch, tmp_path):
    """A stray env var used to scatter gigabytes with no symptom for weeks."""
    import mangaeasy.workspace as workspace

    workspace_root = tmp_path / "workspace"
    data_root = workspace_root / "data"
    outside = tmp_path / "elsewhere"          # a sibling, genuinely outside
    monkeypatch.setattr(workspace, "resolved_roots", lambda: {
        "workspace_root": workspace_root,
        "data_root": data_root,
        "runtime_home": workspace_root / "runtime",
        "audio_root": outside,
        "items_root": data_root / "library",
    })
    report = workspace.layout_report()
    assert not report["ok"]
    assert report["escaped_roots"] == ["audio_root"]
    problems = workspace.workspace_problems()
    assert any(str(data_root) in problem for problem in problems)


def test_data_and_runtime_overlap_is_reported(monkeypatch, tmp_path):
    """runtime/ inside data/ would make workspace-reset delete the tool envs."""
    import mangaeasy.workspace as workspace

    workspace_root = tmp_path / "workspace"
    data_root = workspace_root / "data"
    monkeypatch.setattr(workspace, "resolved_roots", lambda: {
        "workspace_root": workspace_root,
        "data_root": data_root,
        "runtime_home": data_root / "runtime",
    })
    report = workspace.layout_report()
    assert report["data_runtime_overlap"] is True
    assert not report["ok"]
    assert any("overlap" in problem for problem in workspace.workspace_problems())
