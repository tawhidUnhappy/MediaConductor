"""Per-project reading-direction resolution: manga.json original_language
drives RTL/LTR so Japanese manga, Chinese manhua, and Korean manhwa each crop
in their own panel order on the same machine — no install-wide guess."""

import json

from mediaconductor.download.mangadex import merge_manga_record
from mediaconductor.panels.direction import direction_for_language, project_reading_direction


def test_language_to_direction_mapping():
    assert direction_for_language("ja") == "rtl"       # Japanese manga
    assert direction_for_language("zh-hk") == "rtl"    # traditional HK manhua
    assert direction_for_language("ko") == "ltr"       # manhwa
    assert direction_for_language("zh") == "ltr"       # mainland digital manhua
    assert direction_for_language("en") == "ltr"
    assert direction_for_language("JA ") == "rtl"      # normalized
    assert direction_for_language(None) is None
    assert direction_for_language("") is None


def test_project_resolution_prefers_manga_json(tmp_path):
    (tmp_path / "manga.json").write_text(
        json.dumps({"original_language": "ko"}), encoding="utf-8")
    direction, reason = project_reading_direction(tmp_path)
    assert direction == "ltr" and "original_language=ko" in reason

    (tmp_path / "manga.json").write_text(
        json.dumps({"original_language": "ja"}), encoding="utf-8")
    assert project_reading_direction(tmp_path)[0] == "rtl"


def test_project_resolution_falls_back_without_language(tmp_path):
    # No manga.json at all: config or the rtl default — never an exception.
    direction, reason = project_reading_direction(tmp_path)
    assert direction in ("rtl", "ltr")
    assert reason


def test_download_records_original_language():
    record = merge_manga_record(
        {}, name="P", manga_id="x", lang="en", chapter_str="01",
        chapter_id="c", pages=10, title="T", original_language="ja",
    )
    assert record["original_language"] == "ja"
    # merging another chapter without the field keeps the recorded one
    record = merge_manga_record(
        record, name="P", manga_id="x", lang="en", chapter_str="02",
        chapter_id="d", pages=8,
    )
    assert record["original_language"] == "ja"
