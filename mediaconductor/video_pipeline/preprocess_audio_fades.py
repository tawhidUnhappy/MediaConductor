from __future__ import annotations

import argparse
import shlex
import subprocess
import wave

import numpy as np

from mediaconductor import runtime
from pathlib import Path

from mediaconductor.video_pipeline.common import (
    DEFAULT_AUDIO_ROOT,
    DEFAULT_PROJECT_ROOT,
    item_dirs,
    merge_item_selection,
    project_name,
)
from mediaconductor.video_pipeline.item_assets import load_narration


DEFAULT_OUTPUT_AUDIO_ROOT = Path("audio_preprocessed")
AUDIO_EXTENSIONS = {".wav"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy generated panel audio to a new folder while adding tiny fades to remove edge clicks."
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--source-audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--output-audio-root", type=Path, default=DEFAULT_OUTPUT_AUDIO_ROOT)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--items", nargs="*", help="Item names or ranges, for example: 01 02 05-08.")
    parser.add_argument("--item-range", help="Convenience range, for example: 01-12.")
    parser.add_argument("--fade-ms", type=float, default=8.0, help="Fade-in and fade-out length in milliseconds.")
    parser.add_argument(
        "--no-declick",
        action="store_true",
        help="Disable adaptive fade-out extension for trailing TTS click artifacts "
             "(use the fixed --fade-ms fade-out for every file).",
    )
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(command: list[str], *, capture: bool = False, print_command: bool = True) -> subprocess.CompletedProcess[str]:
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


def audio_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture=True,
        print_command=False,
    )
    return float(result.stdout.strip())


# IndexTTS occasionally leaves a spurious click/pop transient a few milliseconds
# before the true end of a clip -- the real speech decays to near-silence, then a
# short burst appears with no further decay before the file just stops. A fixed
# 8 ms fade-out lands mid-artifact and only partially attenuates it (still audible
# as a click). Detect that quiet-then-blip tail shape and extend the fade-out to
# start before the blip instead of at a fixed offset; ordinary clips (blip-free,
# or ending naturally within the floor window) are unaffected.
_DECLICK_HOP_MS = 2.0
_DECLICK_QUIET_FRAC = 0.06
_DECLICK_MIN_QUIET_MS = 20.0
_DECLICK_MAX_EXTEND_MS = 150.0


def read_wav_mono_float(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        sr = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if width != 2:
        # Only 16-bit PCM (the pipeline's own format) is supported; anything else
        # skips adaptive detection and falls back to the floor fade.
        return np.array([], dtype=np.float32), sr
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sr


def compute_adaptive_fade_out_ms(samples: np.ndarray, sr: int, floor_ms: float) -> float:
    """Return the fade-out duration (>= floor_ms) needed to cover a trailing click."""
    if samples.size == 0 or sr <= 0:
        return floor_ms
    peak = float(np.max(np.abs(samples)))
    if peak <= 0:
        return floor_ms
    hop = max(1, int(sr * _DECLICK_HOP_MS / 1000))
    n_hops = samples.size // hop
    if n_hops < 3:
        return floor_ms
    envelope = np.array(
        [np.max(np.abs(samples[i * hop:(i + 1) * hop])) / peak for i in range(n_hops)]
    )
    loud = envelope > _DECLICK_QUIET_FRAC

    if not loud[n_hops - 1]:
        return floor_ms  # clip already ends quiet -- nothing to fix

    # Walk back over the trailing loud run (the tail artifact may itself span
    # several hops, e.g. a short burst) to find where it starts.
    idx = n_hops - 1
    while idx >= 0 and loud[idx]:
        idx -= 1
    run_start = idx + 1

    # Now measure the quiet gap immediately before that trailing run.
    quiet_run = 0
    while idx >= 0 and not loud[idx]:
        quiet_run += 1
        idx -= 1
    if quiet_run * _DECLICK_HOP_MS < _DECLICK_MIN_QUIET_MS:
        return floor_ms  # trailing loud run isn't preceded by a real gap --
        # it's just natural speech running to the end, not an isolated artifact.

    extend_ms = (n_hops - run_start) * _DECLICK_HOP_MS
    return float(min(max(extend_ms, floor_ms), _DECLICK_MAX_EXTEND_MS))


def source_audio_dir(args: argparse.Namespace, chapter_dir: Path) -> Path:
    return args.source_audio_root.resolve() / project_name(args.project_root, args.project_name) / chapter_dir.name


def output_audio_dir(args: argparse.Namespace, chapter_dir: Path) -> Path:
    return args.output_audio_root.resolve() / project_name(args.project_root, args.project_name) / chapter_dir.name


def validate_roots(args: argparse.Namespace) -> None:
    source_root = args.source_audio_root.resolve()
    output_root = args.output_audio_root.resolve()
    if source_root == output_root:
        raise ValueError("Output audio root must be different from source audio root.")
    if output_root in source_root.parents:
        raise ValueError(f"Refusing to write output audio above the source root: {output_root}")
    if source_root in output_root.parents:
        # This is usually okay for separate folders under make_video, but not if the
        # selected manga folder would overlap. The per-file target check catches that.
        return


def panel_audio_files(chapter_dir: Path, args: argparse.Namespace) -> list[tuple[Path, Path]]:
    source_dir = source_audio_dir(args, chapter_dir)
    target_dir = output_audio_dir(args, chapter_dir)
    result: list[tuple[Path, Path]] = []
    for item in load_narration(chapter_dir):
        image_name = item.get("image")
        if not image_name:
            raise ValueError(f"Missing image key in {chapter_dir / 'narration.json'}")
        source = source_dir / f"{Path(image_name).stem}.wav"
        target = target_dir / source.name
        if not source.exists():
            raise FileNotFoundError(f"Missing source audio: {source}")
        if source.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio type: {source}")
        if source.resolve() == target.resolve():
            raise ValueError(f"Refusing to overwrite source audio: {source}")
        result.append((source, target))
    return result


def fade_filter(duration: float, fade_in_seconds: float, fade_out_seconds: float) -> str:
    fade_in = max(0.001, min(fade_in_seconds, duration / 4))
    fade_out = max(0.001, min(fade_out_seconds, duration / 4))
    out_start = max(0.0, duration - fade_out)
    return (
        f"afade=t=in:st=0:d={fade_in:.6f},"
        f"afade=t=out:st={out_start:.6f}:d={fade_out:.6f},"
        "asetpts=N/SR/TB"
    )


def process_audio(source: Path, target: Path, args: argparse.Namespace) -> bool:
    if target.exists() and not args.overwrite:
        print(f"  skip exists: {target.name}", flush=True)
        return False
    duration = audio_duration(source)
    floor_ms = args.fade_ms
    fade_out_ms = floor_ms
    if not args.no_declick:
        samples, sr = read_wav_mono_float(source)
        fade_out_ms = compute_adaptive_fade_out_ms(samples, sr, floor_ms)
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-y" if args.overwrite else "-n",
        "-i", str(source),
        "-af", fade_filter(duration, floor_ms / 1000, fade_out_ms / 1000),
        "-ar", str(args.sample_rate),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(target),
    ]
    if args.dry_run:
        print(" ".join(shlex.quote(part) for part in command), flush=True)
        return False
    note = f" (declicked, fade-out {fade_out_ms:.1f}ms)" if fade_out_ms > floor_ms else ""
    print(f"  write: {target.name}{note}", flush=True)
    run(command)
    return True


def main() -> int:
    args = parse_args()
    if args.fade_ms <= 0:
        raise ValueError("--fade-ms must be positive.")
    if args.sample_rate <= 0:
        raise ValueError("--sample-rate must be positive.")
    validate_roots(args)

    chapters = item_dirs(
        args.project_root.resolve(),
        merge_item_selection(args.items, args.item_range),
    )
    if not chapters:
        raise FileNotFoundError(f"No item folders selected under {args.project_root.resolve()}")

    total = 0
    written = 0
    skipped = 0
    print(f"Source audio root: {args.source_audio_root.resolve()}", flush=True)
    print(f"Output audio root: {args.output_audio_root.resolve()}", flush=True)
    print(f"Fade: {args.fade_ms:.3f} ms at both audio edges", flush=True)
    print()

    for chapter_dir in chapters:
        pairs = panel_audio_files(chapter_dir, args)
        print(f"[{chapter_dir.name}] {len(pairs)} audio file(s)", flush=True)
        for source, target in pairs:
            total += 1
            changed = process_audio(source, target, args)
            if changed:
                written += 1
            else:
                skipped += 1

    print()
    print(f"Processed item folders: {len(chapters)}", flush=True)
    print(f"Audio files seen:   {total}", flush=True)
    print(f"Written:            {written}", flush=True)
    print(f"Skipped:            {skipped}", flush=True)
    print(f"Output folder:      {args.output_audio_root.resolve() / project_name(args.project_root, args.project_name)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
