from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from mangaeasy.utils import archive_before_overwrite
from mangaeasy.video_pipeline.common import DEFAULT_OUTPUT_ROOT, DEFAULT_PROJECT_ROOT, project_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mix background music into an already-joined long video, without rebuilding it from item clips."
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--input", type=Path, default=None,
                        help="Long video to add music to (default: the project's joined long video).")
    parser.add_argument("--background-music", type=Path, required=True)
    parser.add_argument("--music-volume-db", type=float, default=-25.0,
                        help="Background music loudness in dB (negative = quieter), applied via ffmpeg's volume filter.")
    parser.add_argument("--narration-volume", type=float, default=1.0)
    parser.add_argument("--audio-bitrate", default="192k")
    return parser.parse_args()


def add_background_music(
    video_in: Path, music_file: Path, music_volume_db: float, narration_volume: float, audio_bitrate: str
) -> Path:
    if not video_in.is_file():
        raise FileNotFoundError(f"Long video not found: {video_in}. Run the join step first.")
    if not music_file.is_file():
        raise FileNotFoundError(f"Background music not found: {music_file}")

    archived = archive_before_overwrite(video_in)
    assert archived is not None  # video_in.is_file() was just checked above
    print(f"Archived previous long video to: {archived}", flush=True)

    filter_complex = (
        f"[0:a]volume={narration_volume},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[narr];"
        f"[1:a]volume={music_volume_db}dB,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[music];"
        "[narr][music]amix=inputs=2:duration=first:dropout_transition=3,"
        "alimiter=limit=0.95,aresample=async=1:first_pts=0[a]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(archived),
        "-guess_layout_max", "0", "-stream_loop", "-1", "-i", str(music_file),
        "-filter_complex", filter_complex,
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-movflags", "+faststart",
        str(video_in),
    ]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    return video_in


def main() -> int:
    args = parse_args()
    name = project_name(args.project_root, args.project_name)
    video_in = (args.input or (args.output_root / name / f"{name}_full.mp4")).resolve()
    add_background_music(video_in, args.background_music, args.music_volume_db, args.narration_volume, args.audio_bitrate)
    print(f"\nAdded background music to: {video_in}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
