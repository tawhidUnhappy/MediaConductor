"""Tests for decimal and interval chapter range resolution in MangaDex downloads."""

import pytest
import argparse
from mangaeasy.download.mangadex import (
    _complete_download,
    _parse_chapter_tokens,
    _chapter_token_arg,
)


def test_parse_chapter_tokens_with_chapter_map():
    chapter_map = {
        "0.1": {}, "1": {}, "2": {}, "8": {}, "9": {},
        "9.1": {}, "9.2": {}, "10": {}, "11": {}, "12": {}, "13": {},
    }
    assert _parse_chapter_tokens(["1-12"], chapter_map) == [
        "0.1", "1", "2", "8", "9", "9.1", "9.2", "10", "11", "12"
    ]
    assert _parse_chapter_tokens(["01-13"], chapter_map) == [
        "0.1", "1", "2", "8", "9", "9.1", "9.2", "10", "11", "12", "13"
    ]
    assert _parse_chapter_tokens(["8-10"], chapter_map) == [
        "8", "9", "9.1", "9.2", "10"
    ]
    assert _parse_chapter_tokens(["9.1"], chapter_map) == ["9.1"]


def test_parse_chapter_tokens_fallback_without_chapter_map():
    assert _parse_chapter_tokens(["1-5"]) == ["1", "2", "3", "4", "5"]


def test_chapter_token_arg_validates_decimals_and_ranges():
    assert _chapter_token_arg("1-12") == "1-12"
    assert _chapter_token_arg("9.1") == "9.1"
    assert _chapter_token_arg("9.1-9.5") == "9.1-9.5"

    with pytest.raises(argparse.ArgumentTypeError):
        _chapter_token_arg("invalid_token")


def test_complete_download_detects_numbered_holes(tmp_path):
    out = tmp_path / "download"
    out.mkdir()
    (out / "01_01.jpg").write_bytes(b"page")
    (out / "01_03.jpg").write_bytes(b"page")
    (out / "01_99.jpg").write_bytes(b"extra")

    complete, missing = _complete_download(out, "01", 3)

    assert complete is False
    assert missing == [2]


def test_complete_download_accepts_all_expected_pages(tmp_path):
    out = tmp_path / "download"
    out.mkdir()
    for idx in range(1, 4):
        (out / f"01_{idx:02d}.webp").write_bytes(b"page")

    assert _complete_download(out, "01", 3) == (True, [])
