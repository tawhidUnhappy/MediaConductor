"""Panel transcript seeding keeps OCR only while the source crop is identical."""

import json

from mangaeasy.ocr.panel_transcript import (
    load_bound_ocr,
    panel_sha256,
    seed_transcript,
)


def _entries(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_seed_transcript_records_panel_hash(tmp_path):
    item = tmp_path / "01"
    panels = item / "panels"
    panels.mkdir(parents=True)
    panel = panels / "01_001.jpg"
    panel.write_bytes(b"first crop")

    transcript, count, dropped, invalidated = seed_transcript(item)

    assert (count, dropped, invalidated) == (1, 0, 0)
    assert _entries(transcript) == [{
        "image": panel.name,
        "panel_sha256": panel_sha256(panel),
    }]


def test_seed_transcript_preserves_ocr_for_identical_panel(tmp_path):
    item = tmp_path / "01"
    panels = item / "panels"
    panels.mkdir(parents=True)
    panel = panels / "01_001.jpg"
    panel.write_bytes(b"unchanged crop")
    transcript, *_ = seed_transcript(item)
    entry = _entries(transcript)[0]
    entry["ocr"] = "UNVERIFIED TEXT"
    transcript.write_text(json.dumps([entry]), encoding="utf-8")

    transcript, _count, _dropped, invalidated = seed_transcript(item)

    assert invalidated == 0
    assert _entries(transcript)[0]["ocr"] == "UNVERIFIED TEXT"


def test_seed_transcript_invalidates_ocr_when_same_filename_pixels_change(tmp_path):
    item = tmp_path / "01"
    panels = item / "panels"
    panels.mkdir(parents=True)
    panel = panels / "01_001.jpg"
    panel.write_bytes(b"old crop")
    old_digest = panel_sha256(panel)
    transcript = item / "transcript.json"
    transcript.write_text(json.dumps([{
        "image": panel.name,
        "panel_sha256": old_digest,
        "ocr": "STALE TEXT",
    }]), encoding="utf-8")

    panel.write_bytes(b"new crop with different pixels")
    transcript, _count, _dropped, invalidated = seed_transcript(item)
    entry = _entries(transcript)[0]

    assert invalidated == 1
    assert "ocr" not in entry
    assert entry["panel_sha256"] != old_digest


def test_seed_transcript_invalidates_unbound_legacy_ocr(tmp_path):
    item = tmp_path / "01"
    panels = item / "panels"
    panels.mkdir(parents=True)
    panel = panels / "01_001.jpg"
    panel.write_bytes(b"current crop")
    transcript = item / "transcript.json"
    transcript.write_text(
        json.dumps([{"image": panel.name, "ocr": "UNBOUND LEGACY TEXT"}]),
        encoding="utf-8",
    )

    transcript, _count, _dropped, invalidated = seed_transcript(item)

    assert invalidated == 1
    assert "ocr" not in _entries(transcript)[0]


def test_bound_ocr_consumer_suppresses_changed_crop_without_seed_rerun(tmp_path):
    item = tmp_path / "01"
    panels = item / "panels"
    panels.mkdir(parents=True)
    panel = panels / "01_001.jpg"
    panel.write_bytes(b"original crop")
    (item / "transcript.json").write_text(json.dumps([{
        "image": panel.name,
        "panel_sha256": panel_sha256(panel),
        "ocr": "OLD TEXT",
    }]), encoding="utf-8")

    panel.write_bytes(b"recropped under the same filename")
    bound, total, stale = load_bound_ocr(item)

    assert bound == {}
    assert total == 1
    assert stale == 1


def test_bound_ocr_consumer_accepts_current_textless_result(tmp_path):
    item = tmp_path / "01"
    panels = item / "panels"
    panels.mkdir(parents=True)
    panel = panels / "01_001.jpg"
    panel.write_bytes(b"current crop")
    (item / "transcript.json").write_text(json.dumps([{
        "image": panel.name,
        "panel_sha256": panel_sha256(panel),
        "ocr": "",
    }]), encoding="utf-8")

    bound, total, stale = load_bound_ocr(item)

    assert bound == {panel.name: ""}
    assert total == 1
    assert stale == 0
