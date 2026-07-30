"""Thumbnails come from panels, and titles follow the house pattern.

The thumbnail path has no image generation and must not grow one: the base
pixels are always approved manga panels. These tests pin the composition
elements the reference thumbnails actually use, the mechanical checks that
catch a spec an agent cannot see is wrong, and the title rules calibrated
against the titles this channel already ships.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from mangaeasy.images.thumbnail_candidates import score_image
from mangaeasy.images.thumbnail_compose import (
    check_composition,
    main as compose_main,
    preset_spec,
)
from mangaeasy.images.title_check import check_title

# The titles this channel has actually published — the calibration set. A
# check that flags these as errors is miscalibrated, not strict.
SHIPPED_TITLES = [
    "He Refused To Become A Hero, So The Gods Cursed Him And He Became A Villain (1-6) - Manhwa Recap",
    "REINCARNATED As VILLAIN But The Heroines Are YANDERE for Him - Manga Recap",
    "Reincarnated As Villain He Ditches Main Story To Live In Peace! - Manga Recap",
    "REINCARNATED As The SECRET VILLAIN He Ditches Main Story To Live In Peace! - Manga Recap",
    "ISEKAI'D In a 1:5 Ratio World, He Turns Every Girl YANDERE - Manga Recap",
    "Isekai'd as Evil Villain but the Heroines Fall in Love with Him - Manga Recap",
    "Farmer Accidentally Defeated The Demon Queen And She Fell In Love For His Strength | Manhwa Recap",
]


@pytest.fixture()
def panel(tmp_path: Path) -> Path:
    """A stand-in cropped panel: light ground with dark linework."""
    image = Image.new("RGB", (1600, 900), "white")
    for x in range(200, 1400, 40):
        for y in range(150, 750):
            image.putpixel((x, y), (20, 20, 20))
    path = tmp_path / "panel.jpg"
    image.save(path)
    return path


# ── Titles ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", SHIPPED_TITLES)
def test_shipped_titles_pass_without_errors(title: str):
    report = check_title(title)
    assert report["ok"], f"{title!r} -> {report['errors']}"


@pytest.mark.parametrize("title", SHIPPED_TITLES)
def test_shipped_titles_are_also_warning_free(title: str):
    """Warnings must stay rare enough to mean something.

    Every one of these shipped as-is; if the check nags about them, an agent
    learns to ignore its output, which is worse than having no check.
    """
    assert check_title(title)["warnings"] == []


def test_over_youtube_limit_is_an_error():
    report = check_title("X" * 101 + " - Manga Recap")
    assert not report["ok"]
    assert any("100" in error for error in report["errors"])


def test_all_caps_title_is_an_error():
    report = check_title("REINCARNATED AS THE VILLAIN BUT EVERYONE LOVES HIM - MANGA RECAP")
    assert not report["ok"]
    assert any("capitals" in error for error in report["errors"])


def test_emoji_is_an_error():
    report = check_title("Reincarnated As Villain 🔥 He Wants Peace - Manga Recap")
    assert not report["ok"]
    assert any("emoji" in error for error in report["errors"])


def test_missing_recap_suffix_warns_but_does_not_block():
    report = check_title("When a Genius Reborn Into Valhalla Became The Valkyries Favorite!")
    assert report["ok"]
    assert any("recap suffix" in warning for warning in report["warnings"])


def test_chapter_range_is_extracted_and_validated():
    assert check_title(
        "He Refused To Be A Hero So The Gods Cursed Him (1-6) - Manhwa Recap"
    )["chapter_range"] == "1-6"
    backwards = check_title("Something Happens Here Then (12-3) - Manga Recap")
    assert not backwards["ok"]


def test_stacked_punctuation_warns():
    report = check_title("He Became The Villain?! And Nobody Noticed It - Manga Recap")
    assert any("clickbait" in warning for warning in report["warnings"])


# ── Thumbnail composition ────────────────────────────────────────────────────

def test_every_preset_renders_from_a_panel(panel: Path, tmp_path: Path):
    for preset in ("label-arrow", "bubble", "split"):
        out = tmp_path / f"{preset}.png"
        code = compose_main(["--base", str(panel), "--output", str(out),
                             "--preset", preset, "--text", "VILLAIN", "--text", "HERO"])
        assert code == 0
        with Image.open(out) as rendered:
            assert rendered.size == (1280, 720)


def test_split_layout_accepts_two_panels(panel: Path, tmp_path: Path):
    out = tmp_path / "split.png"
    assert compose_main(["--base", str(panel), "--base", str(panel),
                         "--output", str(out), "--preset", "split",
                         "--text", "WEAK", "--text", "STRONG"]) == 0
    with Image.open(out) as rendered:
        assert rendered.size == (1280, 720)


def test_bubble_and_badge_render(panel: Path, tmp_path: Path):
    out = tmp_path / "bubble.png"
    spec = ('{"bubbles": [{"text": "YOU\'RE MINE", "center": [270, 260], '
            '"rx": 160, "ry": 190, "style": "dark", "tail": [410, 450]}], '
            '"badge": {"text": "1-12", "corner": "top-right"}}')
    assert compose_main(["--base", str(panel), "--output", str(out),
                         "--spec-json", spec, "--check"]) == 0


def test_check_catches_text_running_off_canvas():
    problems = check_composition(
        {}, [{"text": "A VERY LONG HOOK LINE INDEED", "x": 900, "y": 40, "size": 104}],
        [], (1280, 720), None)
    assert any("spills off the canvas" in problem for problem in problems)


def test_check_catches_unreadable_type():
    problems = check_composition({}, [{"text": "TINY", "x": 40, "y": 40, "size": 20}],
                                 [], (1280, 720), None)
    assert any("unreadable" in problem for problem in problems)


def test_check_catches_the_duration_badge_corner():
    problems = check_composition({}, [{"text": "HOOK", "x": 1090, "y": 660, "size": 60}],
                                 [], (1280, 720), None)
    assert any("duration badge" in problem for problem in problems)


def test_check_catches_two_elements_stacked_on_each_other():
    """A badge and a label pinned to the same corner render both unreadable,
    and nothing about that looks wrong in the JSON."""
    problems = check_composition(
        {"badge": {"text": "1-12", "corner": "top-left"}},
        [{"text": "VILLAIN", "x": 44, "y": 30, "size": 100}],
        [], (1280, 720), None)
    assert any("overlaps" in problem for problem in problems)


def test_preset_moves_the_label_clear_of_the_badge():
    with_badge = preset_spec("label-arrow", ["VILLAIN"], (1280, 720), has_badge=True)
    without = preset_spec("label-arrow", ["VILLAIN"], (1280, 720), has_badge=False)
    assert with_badge["blocks"][0]["x"] > without["blocks"][0]["x"]
    problems = check_composition(
        {"badge": {"text": "1-12", "corner": "top-left"}},
        with_badge["blocks"], [], (1280, 720), None)
    assert not any("overlaps" in problem for problem in problems)


def test_check_flag_returns_exit_3_not_zero(panel: Path, tmp_path: Path):
    """Exit 3 is the house contract for 'artifact exists, review required'."""
    out = tmp_path / "bad.png"
    spec = '{"blocks": [{"text": "WAY OFF THE EDGE", "x": 1200, "y": 40, "size": 104}]}'
    assert compose_main(["--base", str(panel), "--output", str(out),
                         "--spec-json", spec, "--check"]) == 3
    assert out.exists(), "the artifact is still written; only the exit code differs"


def test_missing_base_panel_fails_cleanly(tmp_path: Path):
    assert compose_main(["--base", str(tmp_path / "nope.jpg"),
                         "--output", str(tmp_path / "o.png"), "--text", "X"]) == 1


# ── Candidate ranking ────────────────────────────────────────────────────────

def test_an_empty_panel_scores_below_a_drawn_one(tmp_path: Path, panel: Path):
    blank = tmp_path / "blank.jpg"
    Image.new("RGB", (1600, 900), "white").save(blank)
    assert score_image(blank)["score"] < score_image(panel)["score"]


def test_score_reports_its_components_so_a_ranking_is_debuggable(panel: Path):
    measured = score_image(panel)
    assert {"detail", "ink", "shape", "size", "score", "notes"} <= set(measured)


def test_a_small_panel_is_flagged_for_upscaling(tmp_path: Path):
    small = tmp_path / "small.jpg"
    Image.new("RGB", (320, 180), "grey").save(small)
    assert any("below 1280x720" in note for note in score_image(small)["notes"])


def test_unreadable_files_are_skipped_not_fatal(tmp_path: Path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    assert score_image(broken) is None
