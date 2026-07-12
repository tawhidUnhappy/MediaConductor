"""included_chapters decides which item videos the long-video join stitches.

Strict by default (a gap is a failed render and must stop the build); with
--allow-gaps a genuinely-absent chapter (e.g. a scanlation gap on the source)
is skipped so the chapters that exist still join in order.
"""

from pathlib import Path

from mangaeasy.video_pipeline.long_video_builder import included_chapters


def _chapters(*numbers: int) -> dict[int, Path]:
    return {n: Path(f"item_{n:02d}.mp4") for n in numbers}


def test_contiguous_range_has_no_gaps_either_mode():
    chapters = _chapters(1, 2, 3)
    for allow in (False, True):
        numbers, gaps = included_chapters(chapters, 1, 3, allow_gaps=allow)
        assert numbers == [1, 2, 3]
        assert gaps == []


def test_strict_reports_gap_but_keeps_full_range():
    # ch 2 missing: strict mode returns the whole range so the caller raises.
    numbers, gaps = included_chapters(_chapters(1, 3, 4), 1, 4, allow_gaps=False)
    assert numbers == [1, 2, 3, 4]
    assert gaps == [2]


def test_allow_gaps_joins_only_existing_chapters_sorted():
    numbers, gaps = included_chapters(_chapters(1, 3, 4), 1, 4, allow_gaps=True)
    assert numbers == [1, 3, 4]
    assert gaps == [2]


def test_allow_gaps_multiple_holes():
    numbers, gaps = included_chapters(_chapters(1, 3, 5), 1, 5, allow_gaps=True)
    assert numbers == [1, 3, 5]
    assert gaps == [2, 4]


def test_allow_gaps_ignores_chapters_outside_range():
    # A rendered ch 13 lying around must not sneak into a 1-12 join.
    numbers, gaps = included_chapters(_chapters(1, 3, 12, 13), 1, 12, allow_gaps=True)
    assert numbers == [1, 3, 12]
    assert 13 not in numbers
