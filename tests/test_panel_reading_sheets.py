from __future__ import annotations

from PIL import Image

from mangaeasy.video_pipeline.panel_reading_sheets import (
    MAX_PANELS_PER_SHEET,
    MIN_PANELS_PER_SHEET,
    clamp_per_sheet,
    render_item_sheets,
    sheet_grid,
)


def _make_item(tmp_path, count: int):
    panels = tmp_path / "panels"
    panels.mkdir(parents=True)
    for index in range(1, count + 1):
        image = Image.new("RGB", (160 + index, 220 + index), (index * 20 % 255, 60, 90))
        image.save(panels / f"{index:03d}.jpg", quality=95)
    return tmp_path


def test_per_sheet_is_bounded_for_readability():
    assert clamp_per_sheet(1) == MIN_PANELS_PER_SHEET
    assert clamp_per_sheet(6) == 6
    assert clamp_per_sheet(99) == MAX_PANELS_PER_SHEET
    assert sheet_grid(6) == (2, 3)
    assert sheet_grid(8) == (4, 2)


def test_render_item_sheets_covers_every_panel_and_prunes_old_outputs(tmp_path):
    item = _make_item(tmp_path / "01", 7)
    out_dir = tmp_path / "sheets"
    out_dir.mkdir()
    stale = out_dir / "reading_999.jpg"
    stale.write_bytes(b"old")

    report = render_item_sheets(item, out_dir, per_sheet=3)

    assert report["item"] == "01"
    assert report["panels"] == 7
    assert report["per_sheet"] == 3
    assert len(report["sheets"]) == 3
    assert not stale.exists()
    for path in report["sheets"]:
        with Image.open(path) as sheet:
            assert sheet.width > 0
            assert sheet.height > 0
