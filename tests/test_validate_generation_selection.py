from __future__ import annotations

import json
import sys

from mediaconductor.video_pipeline import validate_generation


def test_explicit_batch_allows_item_videos_from_other_batches(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "library" / "Story"
    selected_item = project_root / "02"
    selected_item.mkdir(parents=True)
    (selected_item / "narration.json").write_text("[]\n", encoding="utf-8")

    output_items = tmp_path / "output" / "Story" / "items"
    output_items.mkdir(parents=True)
    (output_items / "item_01.mp4").touch()
    (output_items / "item_02.mp4").touch()

    monkeypatch.setattr(
        validate_generation,
        "check_item",
        lambda _item, _args, _totals, _errors, _warnings: 1.0,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "video-validate",
            "--project-root",
            str(project_root),
            "--output-root",
            str(tmp_path / "output"),
            "--items",
            "02",
            "--no-require-long",
            "--json",
        ],
    )

    assert validate_generation.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["warnings"] == ["Item videos outside the selected batch: item_01.mp4"]
