"""Generate ready-to-paste YouTube chapters from rendered item videos."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mediaconductor import runtime
from mediaconductor.video_pipeline.common import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROJECT_ROOT,
    project_name,
)
from mediaconductor.video_pipeline.long_video_builder import (
    LongVideoConfig,
    discover_chapters,
    included_chapters,
    input_dir,
    selected_range,
)


DurationProbe = Callable[[Path], float]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print ready-to-paste YouTube chapter timestamps from rendered item videos."
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--items", nargs="*", help="Item names or ranges, for example: 01 02 05-08 9.5.")
    parser.add_argument("--item-range", help="Convenience integer range, for example: 01-12.")
    parser.add_argument(
        "--allow-gaps",
        action="store_true",
        help="Generate timestamps from the rendered items that exist when an integer item is genuinely absent.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit one JSON document instead of paste-ready chapter lines.",
    )
    return parser.parse_args(argv)


def format_timestamp(seconds: float) -> str:
    """Format a chapter start, flooring sub-seconds so it never starts late."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"Timestamp seconds must be a finite non-negative number, got {seconds!r}")

    whole_seconds = math.floor(seconds)
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def probe_video_duration(path: Path) -> float:
    """Read the video-stream duration that the long-video join concatenates.

    Item MP4 format duration can be longer than its video stream because AAC
    packets extend past the last frame. The joiner deliberately strips item
    audio and concatenates video-only copies, so format duration would make
    later YouTube timestamps drift late.
    """
    try:
        result = runtime.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Could not read rendered video duration with ffprobe: {path}{suffix}") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run ffprobe for rendered video: {path}: {exc}") from exc

    try:
        duration = float(result.stdout.strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"ffprobe returned an invalid duration for rendered video: {path}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"ffprobe returned a non-positive duration for rendered video: {path}")
    return duration


def build_chapter_report(
    *,
    project_root: Path,
    output_root: Path,
    project_name_override: str | None = None,
    items: list[str] | None = None,
    item_range: str | None = None,
    allow_gaps: bool = False,
    duration_probe: DurationProbe | None = None,
) -> dict[str, Any]:
    """Build ordered chapter entries and cumulative duration metadata."""
    source_root = project_root.resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Project root does not exist: {source_root}")

    name = project_name(source_root, project_name_override)
    # Use the joiner's own range rules so these timestamps describe the item
    # sequence that `video-join` actually concatenates. In particular, a
    # 01-03 range includes a rendered 2.1, and sparse endpoints 01/03 include
    # the rendered 02 between them.
    selection = LongVideoConfig(
        project_root=source_root,
        project_name_override=project_name_override,
        output_root=output_root.resolve(),
        work_dir=Path("."),
        items=items,
        item_range=item_range,
        allow_gaps=allow_gaps,
    )
    rendered = input_dir(selection)
    chapters = discover_chapters(rendered)
    if not chapters:
        raise FileNotFoundError(f"No rendered item videos found under {rendered}")
    start, end = selected_range(selection, chapters)
    names, gaps = included_chapters(chapters, start, end, allow_gaps)
    if gaps and not allow_gaps:
        raise FileNotFoundError(
            "Missing rendered item video(s): "
            + ", ".join(f"{number:02d}" for number in gaps)
            + "; pass --allow-gaps only when those source items genuinely do not exist"
        )
    if not names:
        raise FileNotFoundError(f"No rendered item videos selected under {rendered}")
    item_videos = [(item, chapters[item]) for item in names]

    probe = duration_probe or probe_video_duration
    entries: list[dict[str, Any]] = []
    elapsed = 0.0
    for item, video_path in item_videos:
        try:
            duration = float(probe(video_path))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Duration probe returned an invalid value for rendered video: {video_path}") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError(f"Duration probe returned a non-positive duration for rendered video: {video_path}")

        entries.append(
            {
                "item": item,
                "title": f"Chapter {item}",
                "timestamp": format_timestamp(elapsed),
                "start_seconds": round(elapsed, 6),
                "duration_seconds": round(duration, 6),
                "video": str(video_path),
            }
        )
        elapsed += duration

    return {
        "project": name,
        "entries": entries,
        "gaps": [f"{number:02d}" for number in gaps],
        "total_duration_seconds": round(elapsed, 6),
        "total_duration": format_timestamp(elapsed),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_chapter_report(
        project_root=args.project_root,
        output_root=args.output_root,
        project_name_override=args.project_name,
        items=args.items,
        item_range=args.item_range,
        allow_gaps=args.allow_gaps,
    )

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        if report["gaps"]:
            print("Skipped missing item(s): " + ", ".join(report["gaps"]), file=sys.stderr)
        for entry in report["entries"]:
            print(f"{entry['timestamp']} {entry['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
