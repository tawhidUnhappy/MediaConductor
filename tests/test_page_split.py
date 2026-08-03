"""Unit tests for the deterministic parts of `page-split` (no MAGI/GPU needed)."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

import mangaeasy.panels.page as page_module
from mangaeasy.panels.ai import _manga_reading_order
from mangaeasy.panels.page import (
    FULL_PAGE_AREA_FRAC,
    TALL_PANEL_ASPECT_RATIO,
    _split_exit_code,
    boxes_for_page,
    is_likely_single_panel_page,
)


def test_boxes_for_page_uses_detection_panels():
    detection = {"size": [100, 200], "panels": [[0, 0, 50, 50], [50, 0, 100, 50]]}
    boxes, full_page = boxes_for_page(detection, None, 100, 200)
    assert full_page is False
    assert len(boxes) == 2
    assert all({"x1", "y1", "x2", "y2"} <= b.keys() for b in boxes)


def test_boxes_for_page_requires_manual_crop_when_detection_is_empty():
    boxes, full_page = boxes_for_page({"panels": []}, None, 120, 340)
    assert full_page is True
    assert boxes == []


def test_boxes_for_page_requires_manual_crop_when_detection_is_missing():
    boxes, full_page = boxes_for_page(None, None, 80, 90)
    assert full_page is True
    assert boxes == []


def test_boxes_for_page_requires_manual_crop_when_all_boxes_are_unusable():
    boxes, manual_crop = boxes_for_page(
        {"panels": [["bad"], [20, 20, 10, 10]]}, None, 80, 90
    )
    assert manual_crop is True
    assert boxes == []


def test_override_replaces_detection_and_clamps():
    detection = {"panels": [[0, 0, 10, 10]]}
    # Override boxes deliberately overshoot the page; they must be clamped.
    boxes, full_page = boxes_for_page(detection, [[-5, -5, 999, 999]], 100, 100)
    assert full_page is False
    assert boxes == [{"x1": 0, "y1": 0, "x2": 100, "y2": 100}]


def test_full_page_area_fraction_is_a_sane_threshold():
    assert 0.5 < FULL_PAGE_AREA_FRAC < 1.0


def test_tall_panel_aspect_ratio_permits_square_but_flags_far_taller():
    # A 1:1 crop must not trip the threshold; only meaningfully taller ones should.
    assert TALL_PANEL_ASPECT_RATIO > 1.0
    square_ok = 1.0 < TALL_PANEL_ASPECT_RATIO
    very_tall_flagged = 4.0 >= TALL_PANEL_ASPECT_RATIO
    assert square_ok and very_tall_flagged


def test_reading_order_direction_flips_row_order():
    # Two boxes on the same horizontal band, left box then right box.
    left = {"x1": 0, "y1": 0, "x2": 40, "y2": 100}
    right = {"x1": 60, "y1": 0, "x2": 100, "y2": 100}
    rtl = _manga_reading_order([left, right], rtl=True)
    ltr = _manga_reading_order([left, right], rtl=False)
    # Right-to-left reads the right box first; left-to-right reads the left first.
    assert rtl[0] is right and rtl[1] is left
    assert ltr[0] is left and ltr[1] is right


def _process_single_page(tmp_path, monkeypatch, detection, overrides=None, page_name="001.png"):
    item_dir = tmp_path / "project" / "01"
    source = item_dir / "download"
    source.mkdir(parents=True)
    Image.new("RGB", (100, 100), "white").save(source / page_name)
    verify_dir = tmp_path / "work" / "page_verify" / "project"
    stale_dir = verify_dir / "01"
    stale_dir.mkdir(parents=True)
    (stale_dir / "01_page_999.png").write_bytes(b"stale")
    args = SimpleNamespace(
        source_subdir="download",
        panels_subdir="panels",
        sort="numeric",
        force_style=True,
        device="cpu",
        dtype="fp32",
        reading_direction="ltr",
        prefix_template="{item}_",
    )
    monkeypatch.setattr(
        page_module,
        "run_batch_detect",
        lambda *_args, **_kwargs: {"001.png": detection},
    )
    report = page_module.process_item(item_dir, args, overrides or {}, verify_dir)
    return item_dir, verify_dir, report


def test_likely_single_panel_page_is_limited_to_covers_and_first_pages():
    assert is_likely_single_panel_page(Path("001.png"), 1)
    assert is_likely_single_panel_page(Path("chapter_cover.png"), 8)
    assert is_likely_single_panel_page(Path("05-title-page.jpg"), 8)
    assert not is_likely_single_panel_page(Path("023.png"), 23)


def test_no_detection_writes_obvious_overlay_but_no_production_crop(
    tmp_path, monkeypatch
):
    item_dir, verify_dir, report = _process_single_page(
        tmp_path, monkeypatch, {"panels": []}
    )

    assert report["review_required"] is True
    assert report["panels"] == 0
    assert report["suspects"] == ["001.png no-panels"]
    assert list((item_dir / "panels").glob("*.jpg")) == []
    overlay_path = verify_dir / "01" / "01_page_001.png"
    assert overlay_path.is_file()
    assert not (verify_dir / "01" / "01_page_999.png").exists()
    with Image.open(overlay_path) as overlay:
        r, g, b = overlay.getpixel((0, 0))
        assert r > 150 and g < 40 and b < 40


def test_automatic_first_page_full_page_box_is_kept_as_reviewed_candidate(
    tmp_path, monkeypatch
):
    item_dir, _verify_dir, report = _process_single_page(
        tmp_path, monkeypatch, {"panels": [[0, 0, 100, 100]]}
    )

    assert report["review_required"] is True
    assert report["panels"] == 1
    assert report["full_page_boxes"] == ["001.png full-page-box"]
    assert report["full_page_candidates"] == ["001.png likely-cover-or-splash"]
    assert report["suspects"] == []
    assert (item_dir / "panels" / "01_001_01.jpg").is_file()


def test_mid_chapter_automatic_full_page_box_is_review_only_not_a_production_crop(
    tmp_path, monkeypatch
):
    item_dir = tmp_path / "project" / "01"
    source = item_dir / "download"
    source.mkdir(parents=True)
    Image.new("RGB", (100, 100), "white").save(source / "001.png")
    Image.new("RGB", (100, 100), "white").save(source / "002.png")
    verify_dir = tmp_path / "work" / "page_verify" / "project"
    args = SimpleNamespace(
        source_subdir="download",
        panels_subdir="panels",
        sort="numeric",
        force_style=True,
        device="cpu",
        dtype="fp32",
        reading_direction="ltr",
        prefix_template="{item}_",
    )
    monkeypatch.setattr(
        page_module,
        "run_batch_detect",
        lambda *_args, **_kwargs: {
            "001.png": {"panels": [[0, 0, 50, 50]]},
            "002.png": {"panels": [[0, 0, 100, 100]]},
        },
    )

    report = page_module.process_item(item_dir, args, {}, verify_dir)

    assert report["review_required"] is True
    assert report["panels"] == 1
    assert report["full_page_boxes"] == ["002.png full-page-box"]
    assert "002.png automatic-full-page-box" in report["suspects"]
    assert report["full_page_candidates"] == []
    assert not (item_dir / "panels" / "01_002_01.jpg").exists()


def test_explicit_full_page_override_is_saved_but_still_review_listed(
    tmp_path, monkeypatch
):
    item_dir, _verify_dir, report = _process_single_page(
        tmp_path,
        monkeypatch,
        {"panels": [[10, 10, 80, 80]]},
        {"01": {"001.png": [[0, 0, 100, 100]]}},
    )

    assert report["review_required"] is True
    assert report["panels"] == 1
    assert report["full_page_boxes"] == ["001.png full-page-box"]
    assert (item_dir / "panels" / "01_001_01.jpg").is_file()
    assert report["review_crops"] == [
        str((item_dir / "panels" / "01_001_01.jpg").resolve())
    ]
    assert report["source_images"] == [
        str((item_dir / "download" / "001.png").resolve())
    ]


def test_page_split_exit_code_requires_review_unless_a_true_failure_occurs():
    assert _split_exit_code([{"status": "ok", "review_required": True}]) == 3
    assert _split_exit_code([{"status": "error", "review_required": True}]) == 1
    assert _split_exit_code([{"status": "skipped", "review_required": True}]) == 1
