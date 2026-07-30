"""Pure-logic tests for the agent-flow layer: setup planning, full-series
download helpers, style detection verdicts, narration structural checks, and
the fixed-window series batcher."""

import json

import pytest
from PIL import Image

from mangaeasy.download.mangadex import _chapter_sort_key, _slugify_project_name
from mangaeasy.panels.style_detect import measure_item, style_guard, verdict_from_stats
from mangaeasy.series_plan import build_plan, load_publish_json, mark_main, save_publish_json
from mangaeasy.tools.setup import BASE_TOOLS, GPU_TOOLS, plan_tools
from mangaeasy.video_pipeline.narration_check import check_item


# ── setup planning ──────────────────────────────────────────────────────────

def test_plan_tools_auto_without_gpu_is_base_only():
    assert plan_tools("auto", gpu=False, skip=set()) == BASE_TOOLS


def test_plan_tools_auto_with_gpu_adds_gpu_tools():
    assert plan_tools("auto", gpu=True, skip=set()) == BASE_TOOLS + GPU_TOOLS


def test_plan_tools_minimal_and_skip():
    assert plan_tools("minimal", gpu=True, skip=set()) == []
    assert "deepseek-ocr2" not in plan_tools("auto", gpu=True, skip={"deepseek-ocr2"})


# ── download helpers ────────────────────────────────────────────────────────

def test_chapter_sort_key_orders_decimals_and_specials():
    chapters = ["10", "2", "1.5", "Extra", "1"]
    assert sorted(chapters, key=_chapter_sort_key) == ["1", "1.5", "2", "10", "Extra"]


def test_slugify_project_name_is_filesystem_safe():
    assert _slugify_project_name("Omniscient Reader's Viewpoint!") == \
        "Omniscient_Reader_s_Viewpoint"
    assert _slugify_project_name("???") == "manga"


# ── style detection ─────────────────────────────────────────────────────────

def _make_images(folder, sizes):
    folder.mkdir(parents=True)
    for i, (w, h) in enumerate(sizes):
        Image.new("RGB", (w, h)).save(folder / f"p{i:02d}.png")


def test_style_detect_webtoon_and_paged(tmp_path):
    _make_images(tmp_path / "wt", [(800, 8000)] * 4)
    _make_images(tmp_path / "pg", [(1080, 1600)] * 4)
    assert verdict_from_stats(measure_item(tmp_path / "wt")) == "webtoon"
    assert verdict_from_stats(measure_item(tmp_path / "pg")) == "paged"


def test_style_detect_empty_dir_returns_none(tmp_path):
    (tmp_path / "empty").mkdir()
    assert measure_item(tmp_path / "empty") is None


def test_sliced_webtoon_detected_despite_page_shaped_ratios(tmp_path):
    """Shared-width webtoon slices must not be mistaken for page scans."""
    heights = [1561, 1174, 1078, 1519, 1168, 1564, 1034, 1158, 1381, 993]
    source = tmp_path / "download"
    _make_images(source, [(800, height) for height in heights])
    stats = measure_item(source)
    assert stats["paged_fraction"] >= 0.6
    assert verdict_from_stats(stats) == "webtoon"
    ok, message = style_guard(source, "paged")
    assert not ok and "webtoon-split" in message


def test_uniform_page_scans_still_detect_as_paged(tmp_path):
    source = tmp_path / "download"
    _make_images(source, [(1000, 1500 + (index % 3)) for index in range(10)])
    assert verdict_from_stats(measure_item(source)) == "paged"


def test_style_guard_allows_matching_and_uncertain(tmp_path):
    source = tmp_path / "download"
    _make_images(source, [(1000, 1500)] * 4)
    ok, _ = style_guard(source, "paged")
    assert ok
    ok, message = style_guard(source, "webtoon")
    assert not ok and "page-split" in message
    empty = tmp_path / "empty"
    empty.mkdir()
    ok, message = style_guard(empty, "webtoon")
    assert ok and "no readable pages" in message


# ── narration structural checks ─────────────────────────────────────────────

@pytest.fixture
def item(tmp_path):
    item_dir = tmp_path / "01"
    panels = item_dir / "panels"
    panels.mkdir(parents=True)
    for name in ("a.jpg", "b.jpg"):
        (panels / name).write_bytes(b"x")
    return item_dir


def test_narration_check_clean(item):
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
        {"image": "b.jpg", "narration": "two"},
    ]))
    assert check_item(item)["ok"]


def test_narration_check_flags_empty_text(item):
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "  "},
        {"image": "b.jpg", "narration": "hi"},
    ]))
    report = check_item(item)
    assert not report["ok"]
    assert any("non-empty text" in problem for problem in report["problems"])


def test_narration_check_flags_dangling_image(item):
    (item / "narration.json").write_text(json.dumps([
        {"image": "ghost.jpg", "narration": "hi"},
    ]))
    report = check_item(item)
    assert not report["ok"]
    assert any("panel image not found" in problem for problem in report["problems"])


def test_narration_check_fails_on_a_panel_nobody_decided_about(item):
    """An un-narrated panel used to be an unfalsifiable warning.

    "confirm none is a story panel" recorded nothing, so a dropped story panel
    and a skipped credits page looked identical in every report.
    """
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
    ]))                                              # b.jpg unaccounted for
    report = check_item(item)
    assert not report["ok"]
    assert report["uncovered_panels"] == ["b.jpg"]
    assert any("deliberate omission" in problem for problem in report["problems"])


def test_narration_check_passes_once_the_omission_is_recorded(item):
    from mangaeasy.panel_decisions import record_decisions

    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
    ]))
    record_decisions(item, ["b.jpg"], reason="credit", reviewer="sam")
    report = check_item(item)
    assert report["ok"], report["problems"]
    assert report["uncovered_panels"] == []
    assert report["omitted_panels"][0]["reason"] == "credit"


def test_recorded_omission_is_invalidated_when_the_panel_changes(item):
    from mangaeasy.panel_decisions import record_decisions

    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
    ]))
    record_decisions(item, ["b.jpg"], reason="decorative", reviewer="sam")
    assert check_item(item)["ok"]

    # A re-crop replaces the pixels the decision was made about.
    (item / "panels" / "b.jpg").write_bytes(b"different art entirely")
    report = check_item(item)
    assert not report["ok"]
    assert any("changed after the omission decision" in p for p in report["problems"])


def test_narration_check_intro_json_is_covered_separately(item):
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
    ]))
    (item / "intro.json").write_text(json.dumps([
        {"image": "b.jpg", "narration": "hook"},
    ]))
    assert check_item(item)["ok"]  # intro entries count toward coverage


def test_narration_check_flags_intro_narration_overlap(item):
    # A cold-open panel that also appears in narration.json plays twice —
    # the intro is prepended, then the same panel shows again in-context.
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
        {"image": "b.jpg", "narration": "two"},
    ]))
    (item / "intro.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "cold open"},
    ]))
    report = check_item(item)
    assert not report["ok"]
    assert any("duplicate image" in p for p in report["problems"])


def test_narration_check_rejects_duplicate_image(item):
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
        {"image": "a.jpg", "narration": "duplicate"},
    ]))
    report = check_item(item)
    assert not report["ok"]
    assert any("duplicate image" in problem for problem in report["problems"])


def test_narration_check_rejects_shared_audio_stem(item):
    """Audio is `<stem>.wav`, so a.jpg and a.png would fight over one file."""
    (item / "panels" / "a.png").write_bytes(b"x")
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "one"},
        {"image": "a.png", "narration": "same audio stem"},
    ]))
    report = check_item(item)
    assert not report["ok"]
    assert any("<stem>.wav" in problem for problem in report["problems"])


def test_narration_check_intro_overlap_uses_audio_stem(item):
    (item / "panels" / "a.png").write_bytes(b"x")
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "main"},
    ]))
    (item / "intro.json").write_text(json.dumps([
        {"image": "a.png", "narration": "cold open"},
    ]))

    report = check_item(item)

    assert not report["ok"]
    assert any("<stem>.wav" in p for p in report["problems"])


def test_narration_check_reports_style_findings_as_warnings(item):
    """Repetition is editorial: reported, but never a blocking problem."""
    (item / "narration.json").write_text(json.dumps([
        {"image": "a.jpg", "narration": "The panel shows him drawing his blade."},
        {"image": "b.jpg", "narration": "He steps back into the rain, watching the gate."},
    ]))
    report = check_item(item)
    assert report["ok"], report["problems"]
    assert any("describes the artwork" in warning for warning in report["warnings"])


# ── series batching ─────────────────────────────────────────────────────────

def _make_project(tmp_path, items, narrated):
    root = tmp_path / "proj"
    for name in items:
        panels = root / name / "panels"
        panels.mkdir(parents=True)
        (panels / "p.jpg").write_bytes(b"x")
        if name in narrated:
            (root / name / "narration.json").write_text(
                json.dumps([{"image": "p.jpg", "narration": "hi"}]))
    return root


def test_series_plan_windows_are_stable_and_partial_flagged(tmp_path):
    items = [f"{i:02d}" for i in range(1, 27)]  # 26 items
    root = _make_project(tmp_path, items, narrated=set(items))
    plan = build_plan(root, batch_size=12)
    assert [b["batch"] for b in plan["batches"]] == ["01-12", "13-24", "25-26"]
    assert [b["full"] for b in plan["batches"]] == [True, True, False]
    assert plan["next_batch"]["batch"] == "01-12"


def test_series_plan_advances_past_published(tmp_path):
    items = [f"{i:02d}" for i in range(1, 25)]
    root = _make_project(tmp_path, items, narrated=set(items))
    publish = load_publish_json(root)
    publish["published"].append({"items": items[:12], "video_id": "vid1"})
    save_publish_json(root, publish)
    plan = build_plan(root, batch_size=12)
    assert plan["batches"][0]["published"] and plan["batches"][0]["video_id"] == "vid1"
    assert plan["next_batch"]["batch"] == "13-24"


def test_series_plan_readiness_requires_narration(tmp_path):
    items = [f"{i:02d}" for i in range(1, 13)]
    root = _make_project(tmp_path, items, narrated=set(items[:6]))
    plan = build_plan(root, batch_size=12)
    assert plan["batches"][0]["ready_to_render"] is False


def test_mark_published_records_account_and_replacement_provenance(tmp_path, monkeypatch):
    root = _make_project(tmp_path, ["01", "02"], narrated={"01", "02"})
    monkeypatch.setattr("sys.argv", [
        "mangaeasy", "--project-root", str(root), "--items", "01-02",
        "--video-id", "new-video", "--profile", "manga",
        "--channel-id", "channel-123", "--replaces-video-id", "old-video",
    ])

    assert mark_main() == 0
    record = load_publish_json(root)["published"][0]
    assert record["profile"] == "manga"
    assert record["channel_id"] == "channel-123"
    assert record["replaces_video_id"] == "old-video"
