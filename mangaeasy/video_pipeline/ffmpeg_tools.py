from __future__ import annotations

import json
import os
import shlex
import subprocess
from functools import lru_cache
from pathlib import Path

from mangaeasy import runtime


def run(
    command: list[str],
    *,
    capture: bool = False,
    quiet_ffmpeg: bool = True,
    print_command: bool = True,
) -> subprocess.CompletedProcess[str]:
    if quiet_ffmpeg and command and Path(command[0]).name.lower() == "ffmpeg" and "-loglevel" not in command:
        insert_at = 2 if len(command) > 1 and command[1] == "-hide_banner" else 1
        command = command[:insert_at] + ["-loglevel", "error"] + command[insert_at:]
    if print_command:
        print(" ".join(shlex.quote(part) for part in command), flush=True)
    return runtime.run(
        command,
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ffconcat_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def write_concat_file(paths: list[Path], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as f:
        f.write("ffconcat version 1.0\n")
        for path in paths:
            f.write(f"file '{ffconcat_path(path)}'\n")
    return output


def probe_json(path: Path, entries: str) -> dict:
    result = run(
        ["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
        capture=True,
        quiet_ffmpeg=False,
        print_command=False,
    )
    return json.loads(result.stdout or "{}")


def probe_duration(path: Path) -> float:
    data = probe_json(path, "format=duration")
    value = data.get("format", {}).get("duration")
    if value is None:
        raise ValueError(f"Could not read duration: {path}")
    return max(0.08, float(value))


def first_stream(path: Path, codec_type: str, entries: str) -> dict[str, str]:
    data = probe_json(path, entries)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return {key: str(value) for key, value in stream.items()}
    raise ValueError(f"No {codec_type} stream found in {path}")


def video_stream(path: Path) -> dict[str, str]:
    return first_stream(
        path,
        "video",
        "stream=codec_type,pix_fmt,width,height,duration,nb_frames,avg_frame_rate",
    )


def validate_video_stream(path: Path, *, width: int | None = None, height: int | None = None) -> None:
    stream = video_stream(path)
    pix_fmt = stream.get("pix_fmt", "")
    if not pix_fmt or pix_fmt == "unknown":
        raise ValueError(f"Rendered video has invalid pixel format: {path}")
    if width is not None and stream.get("width") != str(width):
        print(f"WARNING: unexpected video width for {path}: {stream}", flush=True)
    if height is not None and stream.get("height") != str(height):
        print(f"WARNING: unexpected video height for {path}: {stream}", flush=True)


@lru_cache(maxsize=1)
def available_encoders() -> set[str]:
    try:
        result = runtime.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return set()
    encoders: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            encoders.add(parts[1])
    return encoders


@lru_cache(maxsize=8)
def encoder_works(encoder: str) -> bool:
    """Whether *encoder* can actually encode a frame on this machine right now.

    ``ffmpeg -encoders`` lists what the binary was **compiled with**, which is
    not the same as what it can **use**. A hardware encoder that is present in
    the build still fails to open when the driver is too old for its NVENC API
    version, when the GPU has no encode silicon, when a container does not map
    the encode libraries in, or when every encode session is already taken.

    That gap was reachable in practice: the vendored FFmpeg is a rolling
    ``master`` build, so it can require a newer NVENC API than the installed
    driver provides (seen as "Driver does not support the required nvenc API
    version. Required: 13.1 Found: 13.0"). Selection saw ``h264_nvenc`` in the
    list, chose it, and every render died on the first segment — on a machine
    whose libx264 path was fine.

    So probe it: one frame from a synthetic source straight to null. Costs a
    few tens of milliseconds, cached per process, and only ever runs for
    ``--encoder auto``.
    """
    try:
        runtime.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
                "-frames:v", "1", "-c:v", encoder,
                "-f", "null", os.devnull,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return False
    return True


@lru_cache(maxsize=1)
def supports_filter_complex_script() -> bool:
    """Whether this ffmpeg still accepts the legacy ``-filter_complex_script``.

    Long filter graphs must be passed as a *file*: at ~150 chars per panel a
    160-panel chapter pushes argv past Windows' 32,767-char limit and ffmpeg
    never starts (WinError 206). The option that does that was renamed —
    ``-filter_complex_script FILE`` became the generic ``-/filter_complex
    FILE`` and the old spelling was **removed** in FFmpeg 8, not merely
    deprecated. Passing it to a current build aborts with "Unrecognized option"
    before any work happens.

    Both spellings have to keep working: the vendored build is a rolling
    ``master`` (new spelling), while a distro or Homebrew ffmpeg a user already
    has may be 6.x or 7.x (old spelling only).
    """
    try:
        result = runtime.run(
            ["ffmpeg", "-hide_banner", "-h", "full"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return False
    return "-filter_complex_script" in (result.stdout or "")


def filter_script_args(script: Path) -> list[str]:
    """argv fragment that reads a filter_complex graph from *script*."""
    if supports_filter_complex_script():
        return ["-filter_complex_script", str(script)]
    return ["-/filter_complex", str(script)]


@lru_cache(maxsize=4)
def choose_h264_encoder(requested: str) -> str:
    """Resolve ``--encoder``. ``auto`` picks the fastest encoder that *works*.

    An explicit request is honoured as given: someone naming an encoder wants
    that encoder, and silently substituting another would hide a real
    misconfiguration behind a slow render.

    Cached because this is called once per rendered segment: without it a
    160-panel chapter re-ran ``ffmpeg -encoders`` plus a probe per candidate
    160 times, and printed the same three "unusable encoder" warnings 160
    times — burying the render log it was meant to explain.
    """
    if requested != "auto":
        return requested
    encoders = available_encoders()
    for candidate in ("h264_nvenc", "h264_amf", "h264_qsv", "h264_videotoolbox"):
        if candidate not in encoders:
            continue
        if encoder_works(candidate):
            print(f"Auto video encoder: {candidate}", flush=True)
            return candidate
        # Present but unusable — say why, because "it used the CPU and took
        # 40 minutes" is otherwise indistinguishable from "there is no GPU".
        print(f"[warn] {candidate} is built into ffmpeg but cannot open on this "
              f"machine (driver/GPU/session limit) — skipping it.", flush=True)
    print("Auto video encoder: libx264", flush=True)
    return "libx264"


def h264_encoder_args(encoder: str, preset: str, cq: int) -> list[str]:
    if encoder == "libx264":
        # The public video commands use NVENC's p1..p7 scale so one preset can
        # travel through encoder auto-selection. Translate that scale when the
        # CPU fallback is libx264; native x264 preset names still pass through
        # unchanged for callers that select one explicitly.
        x264_preset = {
            "p1": "ultrafast",
            "p2": "superfast",
            "p3": "veryfast",
            "p4": "fast",
            "p5": "medium",
            "p6": "slow",
            "p7": "veryslow",
        }.get(preset, preset)
        return ["-c:v", "libx264", "-preset", x264_preset, "-crf", str(cq)]
    if encoder == "h264_videotoolbox":
        return ["-c:v", encoder, "-q:v", str(max(1, min(100, cq)))]
    if encoder in {"h264_amf", "h264_qsv"}:
        return ["-c:v", encoder, "-global_quality", str(cq)]
    return ["-c:v", encoder, "-preset", preset, "-tune", "hq", "-rc", "vbr", "-cq", str(cq), "-b:v", "0"]
