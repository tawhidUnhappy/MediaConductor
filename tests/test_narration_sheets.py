from mediaconductor.video_pipeline.narration_sheets import (
    _prune_review_sheets,
    _review_exit_code,
)


def test_narration_sheets_require_review_when_artifacts_are_valid():
    report = {"01": {"entries": 4, "missing_images": []}}
    assert _review_exit_code(report) == 3


def test_narration_sheets_fail_when_content_cannot_be_reviewed():
    assert _review_exit_code({"01": {"entries": 0, "missing_images": []}}) == 1
    assert _review_exit_code({
        "01": {"entries": 1, "missing_images": ["missing.jpg"]},
    }) == 1


def test_narration_sheet_regeneration_prunes_surplus_old_sheets(tmp_path):
    (tmp_path / "review_001.jpg").write_bytes(b"current")
    (tmp_path / "review_009.jpg").write_bytes(b"stale")
    (tmp_path / "keep.txt").write_text("unrelated", encoding="utf-8")

    _prune_review_sheets(tmp_path)

    assert not list(tmp_path.glob("review_*.jpg"))
    assert (tmp_path / "keep.txt").is_file()
