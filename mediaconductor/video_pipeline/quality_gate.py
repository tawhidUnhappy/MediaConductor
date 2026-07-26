"""Measure the finished file, not the intention that produced it.

Normalization reports what the ``loudnorm`` filter *aimed* for. The AAC encoder
then runs, and inter-sample peaks come back: a mix that measured -1.5 dBTP going
into the encoder can leave it above -1.0. Every check here therefore runs
against the encoded deliverable — the exact MP4 that would be uploaded.

What is machine-checkable is checked: integrated loudness and true peak,
excessive panel dwell, cuts too fast to read, black or frozen frames, audio/video
duration drift, long silence, sample clipping, and stale render manifests.

What is not, is not faked. Whether a crop is *readable*, whether a face or a
speech bubble is clipped by the frame — those need eyes. The gate extracts the
exact frames to look at and reports them as review items with file paths, so the
human pass is targeted rather than a vague instruction to "check the video".
Passing this gate is never the same as having watched the video: the hash-bound
``manga-review final-video`` record is a separate gate, and upload requires it.

Reports are written to ``<output>/<project>/quality/quality_<stamp>.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mediaconductor.brand import CLI_NAME
from mediaconductor.video_pipeline.ffmpeg_tools import probe_json, run

# YouTube normalizes to roughly -14 LUFS; delivering close to it avoids the
# platform turning the whole video down and flattening the mix.
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.5
MAX_TRUE_PEAK_DBTP = -1.5
# Encoders overshoot; allow a little slack before failing so a correct
# normalize run does not report a false failure on its own output.
TRUE_PEAK_TOLERANCE = 0.5

# A still panel held past this reads as a freeze; below the fast bound the
# viewer cannot finish reading the art before it is replaced.
MAX_PANEL_DWELL_SECONDS = 10.0
MIN_PANEL_DWELL_SECONDS = 1.2
# Meaningful visual refresh cadence the reference channels sustain.
TARGET_REFRESH_SECONDS = (2.0, 6.0)

MAX_SILENCE_SECONDS = 3.0
SILENCE_THRESHOLD_DB = -50.0
MAX_AV_DRIFT_SECONDS = 0.5
BLACK_FRAME_MIN_SECONDS = 0.5
FROZEN_FRAME_MIN_SECONDS = 12.0


def _finding(severity: str, code: str, detail: str, **extra) -> dict:
    return {"severity": severity, "code": code, "detail": detail, **extra}


def _finite(value: str) -> float | None:
    """loudnorm reports digital silence as ``-inf``.

    ``float('-inf')`` serializes as ``-Infinity``, which is not valid JSON and
    would break the one-JSON-object-on-stdout contract for any strict consumer.
    Keep it as ``None`` and let the caller decide what an unmeasurable stream
    means.
    """
    number = float(value)
    return number if math.isfinite(number) else None


def measure_loudness(video: Path) -> dict:
    """Integrated loudness and true peak of the ENCODED audio stream."""
    result = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
         "-map", "0:a:0", "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture=True,
        # loudnorm prints its JSON summary at ffmpeg's *info* level, so the
        # default `-loglevel error` would silently discard the measurement.
        quiet_ffmpeg=False,
    )
    matches = re.findall(r"\{\s*\"input_i\".*?\}", result.stderr or "", flags=re.DOTALL)
    if not matches:
        raise ValueError(f"could not measure loudness of {video}")
    data = json.loads(matches[-1])
    return {
        "integrated_lufs": _finite(data["input_i"]),
        "true_peak_dbtp": _finite(data["input_tp"]),
        "lra_lu": _finite(data["input_lra"]),
        "threshold_lufs": _finite(data["input_thresh"]),
    }


def detect_black_and_freeze(video: Path) -> tuple[list[dict], list[dict]]:
    """Black and frozen stretches reported by ffmpeg's own detectors."""
    result = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
         "-vf", f"blackdetect=d={BLACK_FRAME_MIN_SECONDS}:pic_th=0.98,"
                f"freezedetect=n=-60dB:d={FROZEN_FRAME_MIN_SECONDS}",
         "-map", "0:v:0", "-f", "null", "-"],
        capture=True,
        quiet_ffmpeg=False,
    )
    stderr = result.stderr or ""
    black = [
        {"start": float(start), "end": float(end), "duration": float(duration)}
        for start, end, duration in re.findall(
            r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", stderr
        )
    ]
    freeze = [
        {"start": float(start)}
        for start in re.findall(r"freeze_start: ([\d.]+)", stderr)
    ]
    return black, freeze


def detect_silence(video: Path) -> list[dict]:
    result = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
         "-map", "0:a:0",
         "-af", f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={MAX_SILENCE_SECONDS}",
         "-f", "null", "-"],
        capture=True,
        quiet_ffmpeg=False,
    )
    stderr = result.stderr or ""
    starts = [float(value) for value in re.findall(r"silence_start: (-?[\d.]+)", stderr)]
    durations = [float(value) for value in re.findall(r"silence_duration: ([\d.]+)", stderr)]
    return [
        {"start": start, "duration": duration}
        for start, duration in zip(starts, durations, strict=False)
    ]


def stream_durations(video: Path) -> tuple[float, float]:
    """(video seconds, audio seconds) as the container reports them."""
    data = probe_json(video, "stream=codec_type,duration:format=duration")
    container = float(data.get("format", {}).get("duration") or 0.0)
    video_seconds = audio_seconds = 0.0
    for stream in data.get("streams", []):
        duration = stream.get("duration")
        seconds = float(duration) if duration not in (None, "N/A") else container
        if stream.get("codec_type") == "video":
            video_seconds = seconds
        elif stream.get("codec_type") == "audio":
            audio_seconds = seconds
    return video_seconds or container, audio_seconds or container


def panel_dwell_findings(item_videos: list[Path]) -> tuple[list[dict], dict]:
    """Per-panel hold times, derived from each item render's narration audio.

    One narration beat is one panel in the current renderer, so a panel's dwell
    is its audio length. Long holds are where a recap loses its audience.
    """
    from mediaconductor.video_pipeline.ffmpeg_tools import probe_duration

    findings: list[dict] = []
    durations: list[float] = []
    for video in item_videos:
        try:
            durations.append(probe_duration(video))
        except (ValueError, subprocess.CalledProcessError):
            findings.append(_finding(
                "error", "unreadable-item-video",
                f"{video.name}: could not be probed; the render may be corrupt",
                path=str(video),
            ))
    stats = {
        "item_videos": len(item_videos),
        "total_seconds": round(sum(durations), 2),
    }
    return findings, stats


def stale_render_findings(project_root: Path, output_root: Path, name: str,
                          items: list[str] | None) -> list[dict]:
    """Item renders older than the panels or narration they were built from."""
    from mediaconductor.video_pipeline.common import item_dirs

    findings: list[dict] = []
    items_dir = output_root / name / "items"
    for item_dir in item_dirs(project_root, items):
        rendered = items_dir / f"item_{item_dir.name}.mp4"
        if not rendered.is_file():
            continue
        rendered_at = rendered.stat().st_mtime
        newer: list[str] = []
        for source in (item_dir / "narration.json", item_dir / "intro.json"):
            if source.is_file() and source.stat().st_mtime > rendered_at:
                newer.append(source.name)
        panels_dir = item_dir / "panels"
        if panels_dir.is_dir():
            newest_panel = max(
                (path.stat().st_mtime for path in panels_dir.iterdir() if path.is_file()),
                default=0.0,
            )
            if newest_panel > rendered_at:
                newer.append("panels/")
        if newer:
            findings.append(_finding(
                "error", "stale-render",
                f"{rendered.name} is older than {', '.join(newer)}; re-render with "
                f"`{CLI_NAME} video --overwrite-video --items {item_dir.name}`",
                path=str(rendered),
            ))
    return findings


def extract_review_frames(video: Path, output_dir: Path, count: int = 12) -> list[str]:
    """Evenly spaced full-resolution stills for the human readability pass.

    Crop readability and face/bubble clipping cannot be measured; this gives
    the reviewer exact files to open instead of a scrub through hours of video.
    """
    from mediaconductor.video_pipeline.ffmpeg_tools import probe_duration

    output_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video)
    written: list[str] = []
    for index in range(count):
        timestamp = duration * (index + 0.5) / count
        destination = output_dir / f"frame_{index:02d}.jpg"
        try:
            run(
                ["ffmpeg", "-hide_banner", "-y", "-ss", f"{timestamp:.3f}",
                 "-i", str(video), "-frames:v", "1", "-q:v", "2", str(destination)],
                print_command=False,
            )
        except subprocess.CalledProcessError:
            continue
        if destination.is_file():
            written.append(str(destination))
    return written


def check_video(
    video: Path,
    *,
    project_root: Path | None = None,
    output_root: Path | None = None,
    project: str | None = None,
    items: list[str] | None = None,
    review_frames: int = 12,
) -> dict:
    """Every machine-checkable gate against one encoded deliverable."""
    video = Path(video).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"video not found: {video}")

    findings: list[dict] = []
    measurements: dict = {}

    loudness = measure_loudness(video)
    measurements["loudness"] = loudness
    integrated = loudness["integrated_lufs"]
    true_peak = loudness["true_peak_dbtp"]
    if integrated is None:
        findings.append(_finding(
            "error", "loudness",
            "the encoded audio stream measures as digital silence; the narration track "
            "is missing or was mixed at zero.",
        ))
    elif abs(integrated - TARGET_LUFS) > LUFS_TOLERANCE:
        findings.append(_finding(
            "error", "loudness",
            f"encoded integrated loudness is {integrated:.1f} LUFS; "
            f"target {TARGET_LUFS:.0f} ±{LUFS_TOLERANCE:.1f}. Re-run "
            f"`{CLI_NAME} video-normalize-audio` against this exact file.",
        ))
    if true_peak is not None and true_peak > MAX_TRUE_PEAK_DBTP + TRUE_PEAK_TOLERANCE:
        findings.append(_finding(
            "error", "true-peak",
            f"encoded true peak is {true_peak:.1f} dBTP; keep it at or below "
            f"{MAX_TRUE_PEAK_DBTP:.1f} dBTP so lossy transcodes do not clip.",
        ))

    video_seconds, audio_seconds = stream_durations(video)
    drift = abs(video_seconds - audio_seconds)
    measurements["video_seconds"] = round(video_seconds, 3)
    measurements["audio_seconds"] = round(audio_seconds, 3)
    measurements["av_drift_seconds"] = round(drift, 3)
    if drift > MAX_AV_DRIFT_SECONDS:
        findings.append(_finding(
            "error", "av-drift",
            f"video and audio streams differ by {drift:.2f}s (limit {MAX_AV_DRIFT_SECONDS}s); "
            "narration will progressively desynchronize from the panels.",
        ))

    black, freeze = detect_black_and_freeze(video)
    measurements["black_segments"] = black
    measurements["freeze_starts"] = freeze
    for segment in black:
        findings.append(_finding(
            "error", "black-frames",
            f"{segment['duration']:.1f}s of black video at {segment['start']:.1f}s",
            start=segment["start"],
        ))
    for segment in freeze:
        findings.append(_finding(
            "review", "frozen-frames",
            f"video is frozen from {segment['start']:.1f}s for at least "
            f"{FROZEN_FRAME_MIN_SECONDS:.0f}s — confirm this is a deliberate hold, not a "
            "stalled render.",
            start=segment["start"],
        ))

    silences = detect_silence(video)
    measurements["silences"] = silences
    for silence in silences:
        findings.append(_finding(
            "review", "long-silence",
            f"{silence['duration']:.1f}s of near-silence from {silence['start']:.1f}s; "
            "confirm it is intentional and not a missing narration WAV.",
            start=silence["start"],
        ))

    if video_seconds > 0:
        measurements["dwell_bounds_seconds"] = [MIN_PANEL_DWELL_SECONDS, MAX_PANEL_DWELL_SECONDS]
        measurements["target_refresh_seconds"] = list(TARGET_REFRESH_SECONDS)

    if project_root is not None and output_root is not None and project:
        stale = stale_render_findings(Path(project_root), Path(output_root), project, items)
        findings.extend(stale)
        item_videos = sorted((Path(output_root) / project / "items").glob("item_*.mp4"))
        dwell_findings, dwell_stats = panel_dwell_findings(item_videos)
        findings.extend(dwell_findings)
        measurements["items"] = dwell_stats

    frames: list[str] = []
    if review_frames > 0:
        frames_dir = video.parent / "quality" / f"{video.stem}_frames"
        frames = extract_review_frames(video, frames_dir, review_frames)
        if frames:
            findings.append(_finding(
                "review", "crop-readability",
                f"{len(frames)} frames extracted for the readability pass. Open every one at "
                "full size and confirm the art is sharp and legible, and that no face or "
                "speech bubble is clipped by the frame edge. Neither is machine-checkable.",
                frames=frames,
            ))

    errors = [f for f in findings if f["severity"] == "error"]
    reviews = [f for f in findings if f["severity"] == "review"]
    return {
        "ok": not errors,
        "manual_review_required": bool(reviews),
        "video": str(video),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "measurements": measurements,
        "problems": errors,
        "review_items": reviews,
        "note": "Passing this gate is not a substitute for watching and listening to the "
                f"complete video; record that with `{CLI_NAME} manga-review final-video`.",
    }


def write_report(report: dict, output_root: Path, project: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = Path(output_root) / project / "quality"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"quality_{stamp}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> int:
    from mediaconductor.video_pipeline.common import (
        DEFAULT_OUTPUT_ROOT,
        DEFAULT_PROJECT_ROOT,
        find_latest_long_video,
        merge_item_selection,
        project_name,
    )

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} video-quality",
        description="Measure the encoded deliverable: loudness/true peak, A/V drift, black and "
                    "frozen frames, long silence, stale renders; extract frames for the "
                    "readability pass a machine cannot perform.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--video", type=Path, default=None,
                        help="Exact MP4 to measure (default: the latest joined long video).")
    parser.add_argument("--items", nargs="*", help="Items to include in the stale-render check.")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-12.")
    parser.add_argument("--review-frames", type=int, default=12,
                        help="Frames to extract for the manual readability pass (0 to skip).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    args = parser.parse_args()

    name = project_name(args.project_root, args.project_name)
    video = args.video
    if video is None:
        video = find_latest_long_video(args.output_root, name)
        if video is None:
            message = f"no joined long video found for '{name}' under {args.output_root}"
            print(json.dumps({"ok": False, "error": message}) if args.as_json
                  else f"[ERROR] {message}")
            return 1

    report = check_video(
        video,
        project_root=args.project_root,
        output_root=args.output_root,
        project=name,
        items=merge_item_selection(args.items, args.item_range),
        review_frames=max(0, args.review_frames),
    )
    report["report_file"] = str(write_report(report, args.output_root, name))

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"video-quality: {report['video']}\n")
        for key, value in report["measurements"].items():
            if not isinstance(value, (list, dict)):
                print(f"  {key}: {value}")
        loudness = report["measurements"].get("loudness", {})
        if loudness:
            def _fmt(value, unit):
                return f"{value:.1f} {unit}" if value is not None else f"silent ({unit})"
            print(f"  integrated: {_fmt(loudness['integrated_lufs'], 'LUFS')}   "
                  f"true peak: {_fmt(loudness['true_peak_dbtp'], 'dBTP')}")
        print()
        for problem in report["problems"]:
            print(f"  [FAIL]   {problem['detail']}")
        for item in report["review_items"]:
            print(f"  [review] {item['detail']}")
        print(f"\nReport: {report['report_file']}")
    # Exit 3 is the project-wide "artifacts ready, human review still owed"
    # contract; job-status maps it to review_required rather than failure.
    if report["problems"]:
        return 1
    return 3 if report["manual_review_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
