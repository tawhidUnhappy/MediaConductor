"""All-in-one pipeline runner updated with hard tool gates and quality flags."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mangaeasy import runtime
from mangaeasy.brand import CLI_NAME
from mangaeasy.defaults import (
    configured_background_music,
    default_manga_video_audio_fade_ms,
    default_manga_video_audio_source,
    default_music_volume_db,
    default_speaker_wav,
    default_tts_engine,
)
from mangaeasy.reviews import enforce_production_reviews
from mangaeasy.runtime import cli_command
from mangaeasy.tools.hardware import has_nvidia_gpu
from mangaeasy.tools.install import doctor
from mangaeasy.utils import emit_result
from mangaeasy.video_pipeline.common import (
    DEFAULT_AUDIO_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROJECT_ROOT,
    DEFAULT_WORK_DIR,
    find_latest_long_video,
    item_dirs,
    merge_item_selection,
    project_name,
)


def enforce_tool_readiness(mode: str = "manga-video") -> None:
    """Refuse to run if required mode tools are missing or unready."""
    report = doctor(mode=mode)
    missing = [
        k
        for k, v in report["tools"].items()
        if v.get("needs_gpu") and not v.get("ready") and not v.get("installed")
    ]
    if missing:
        raise RuntimeError(
            f"Missing required tools for {mode}: {', '.join(missing)}. "
            f"Run '{CLI_NAME} setup --mode {mode}' or '{CLI_NAME} install-tool <name>' first."
        )


def resolve_tts_engine(
    requested: str, speaker_wav: Path | None, project_root: Path
) -> str:
    """Resolve the TTS engine to use based on requested preference, GPU, and reference WAV."""
    if requested != "auto":
        return requested
    speaker = speaker_wav or default_speaker_wav()
    if has_nvidia_gpu() and speaker is not None and speaker.is_file():
        report = doctor()
        if report.get("tools", {}).get("index-tts", {}).get("installed"):
            return "indextts"
    return "kokoro"


def run(command: list[str], cwd: Path | None = None) -> None:
    """Execute a CLI subcommand and raise an error if it fails."""
    runtime.run(command, cwd=cwd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} video",
        description="Full manga recap video pipeline orchestration.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--audio-root", type=Path, default=DEFAULT_AUDIO_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--project-name", default=None)
    parser.add_argument(
        "--items",
        nargs="*",
        help="Item folder names or ranges, e.g. 01 02 05-08.",
    )
    parser.add_argument("--item-range", help="Convenience range, e.g. 01-12.")
    parser.add_argument(
        "--tts",
        choices=("auto", "kokoro", "indextts"),
        default=default_tts_engine(),
    )
    parser.add_argument("--speaker-wav", type=Path, default=None)
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument(
        "--audio-source",
        choices=("raw", "faded"),
        default=default_manga_video_audio_source(),
    )
    parser.add_argument(
        "--audio-fade-ms", type=float, default=default_manga_video_audio_fade_ms()
    )
    parser.add_argument("--background-music", type=Path, default=None)
    parser.add_argument("--no-background-music", action="store_true")
    parser.add_argument(
        "--music-volume-db", type=float, default=default_music_volume_db()
    )
    parser.add_argument(
        "--camera-motion",
        action="store_true",
        help="Apply jitter-free Ken Burns camera motion.",
    )
    parser.add_argument(
        "--burn-subtitles",
        action="store_true",
        help="Burn styled ASS captions onto video.",
    )
    parser.add_argument(
        "--hook-speedup",
        action="store_true",
        help="Apply 1.15x speedup to cold open/hook clips.",
    )
    parser.add_argument("--video-preset", "--preset", default="p5")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--build-long-video", action="store_true")
    parser.add_argument("--normalize-audio", action="store_true")
    parser.add_argument(
        "--validate", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--overwrite-audio", action="store_true")
    parser.add_argument("--overwrite-video", action="store_true")
    parser.add_argument("--gpu-workers", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    enforce_tool_readiness("manga-video")

    project_root = args.project_root.resolve()
    audio_root = args.audio_root.resolve()
    output_root = args.output_root.resolve()
    work_dir = args.work_dir.resolve()
    name = project_name(project_root, args.project_name)

    selection = merge_item_selection(args.items, args.item_range)
    selected_dirs = item_dirs(project_root, selection)
    if not selected_dirs:
        raise FileNotFoundError(f"No item folders found in {project_root}")

    item_names = [d.name for d in selected_dirs]
    enforce_production_reviews(project_root, item_names, stage="full pipeline")

    has_bgm = False
    bgm_file = None
    if args.build_long_video and not args.no_background_music:
        bgm_file = args.background_music or configured_background_music()
        if bgm_file is not None and bgm_file.is_file():
            has_bgm = True

    stages: list[str] = []
    if not args.skip_audio:
        stages.append("Generate narration audio")
    if args.audio_source == "faded":
        stages.append("Apply narration fades")
    stages.append("Render item videos")
    if args.build_long_video:
        stages.append("Join long video")
        if has_bgm:
            stages.append("Mix background music")
        if args.normalize_audio:
            stages.append("Normalize final audio")
    if args.validate:
        stages.append("Validate generated video")

    total_stages = len(stages)
    current_stage = 0

    def progress_step(label: str, is_start: bool) -> None:
        nonlocal current_stage
        if is_start:
            print(
                f"MANGAEASY_PROGRESS {current_stage}/{total_stages} Starting {label}",
                flush=True,
            )
        else:
            current_stage += 1
            print(
                f"MANGAEASY_PROGRESS {current_stage}/{total_stages} Completed {label}",
                flush=True,
            )

    # 1. Generate audio
    if not args.skip_audio:
        progress_step("Generate narration audio", is_start=True)
        engine = resolve_tts_engine(args.tts, args.speaker_wav, project_root)
        audio_cmd = "video-audio-indextts" if engine == "indextts" else "video-audio"
        cmd = [
            *cli_command(audio_cmd),
            "--project-root",
            str(project_root),
            "--audio-root",
            str(audio_root),
            "--gpu-workers",
            str(args.gpu_workers),
        ]
        if args.project_name:
            cmd += ["--project-name", args.project_name]
        if args.items:
            cmd += ["--items", *args.items]
        if args.item_range:
            cmd += ["--item-range", args.item_range]
        if args.speaker_wav:
            cmd += ["--speaker-wav", str(args.speaker_wav)]
        if args.overwrite_audio:
            cmd.append("--overwrite")
        run(cmd)
        progress_step("Generate narration audio", is_start=False)

    # 2. Fade audio
    effective_audio_root = audio_root
    if args.audio_source == "faded":
        progress_step("Apply narration fades", is_start=True)
        faded_root = audio_root.with_name("audio_faded")
        cmd = [
            *cli_command("video-fade-audio"),
            "--project-root",
            str(project_root),
            "--source-audio-root",
            str(audio_root),
            "--output-audio-root",
            str(faded_root),
            "--fade-ms",
            str(args.audio_fade_ms),
        ]
        if args.project_name:
            cmd += ["--project-name", args.project_name]
        if args.items:
            cmd += ["--items", *args.items]
        if args.item_range:
            cmd += ["--item-range", args.item_range]
        run(cmd)
        effective_audio_root = faded_root
        progress_step("Apply narration fades", is_start=False)

    # 3. Render item videos
    progress_step("Render item videos", is_start=True)
    cmd = [
        *cli_command("video-render"),
        "--project-root",
        str(project_root),
        "--audio-root",
        str(effective_audio_root),
        "--output-root",
        str(output_root),
        "--work-dir",
        str(work_dir),
        "--fps",
        str(args.fps),
        "--preset",
        args.video_preset,
    ]
    if args.project_name:
        cmd += ["--project-name", args.project_name]
    if args.items:
        cmd += ["--items", *args.items]
    if args.item_range:
        cmd += ["--item-range", args.item_range]
    if args.camera_motion:
        cmd.append("--camera-motion")
    if args.hook_speedup:
        cmd.append("--hook-speedup")
    if args.overwrite_video:
        cmd.append("--overwrite")
    run(cmd)
    progress_step("Render item videos", is_start=False)

    # 4. Join long video
    joined_video = None
    if args.build_long_video:
        progress_step("Join long video", is_start=True)
        narration_vol = "1.0" if has_bgm else "1.2"
        cmd = [
            *cli_command("video-join"),
            "--project-root",
            str(project_root),
            "--audio-root",
            str(effective_audio_root),
            "--output-root",
            str(output_root),
            "--work-dir",
            str(work_dir),
            "--narration-volume",
            narration_vol,
        ]
        if args.project_name:
            cmd += ["--project-name", args.project_name]
        if args.items:
            cmd += ["--items", *args.items]
        if args.item_range:
            cmd += ["--item-range", args.item_range]
        if args.overwrite_video:
            cmd.append("--overwrite")
        run(cmd)
        progress_step("Join long video", is_start=False)
        joined_video = find_latest_long_video(output_root, name)

    # 5. Mix BGM
    if args.build_long_video and has_bgm and joined_video is not None:
        progress_step("Mix background music", is_start=True)
        cmd = [
            *cli_command("video-add-bgm"),
            "--project-root",
            str(project_root),
            "--output-root",
            str(output_root),
            "--work-dir",
            str(work_dir),
            "--input",
            str(joined_video),
            "--background-music",
            str(bgm_file),
            "--music-volume-db",
            str(args.music_volume_db),
            "--narration-volume",
            "1.2",
            "--replace",
        ]
        if args.project_name:
            cmd += ["--project-name", args.project_name]
        run(cmd)
        progress_step("Mix background music", is_start=False)
        joined_video = find_latest_long_video(output_root, name)

    # 6. Normalize audio
    if args.build_long_video and args.normalize_audio and joined_video is not None:
        progress_step("Normalize final audio", is_start=True)
        cmd = [
            *cli_command("video-normalize-audio"),
            "--project-root",
            str(project_root),
            "--output-root",
            str(output_root),
            "--input",
            str(joined_video),
            "--replace",
        ]
        if args.project_name:
            cmd += ["--project-name", args.project_name]
        run(cmd)
        progress_step("Normalize final audio", is_start=False)
        joined_video = find_latest_long_video(output_root, name)

    # 7. Validate video
    if args.validate:
        progress_step("Validate generated video", is_start=True)
        cmd = [
            *cli_command("video-validate"),
            "--project-root",
            str(project_root),
            "--audio-root",
            str(effective_audio_root),
            "--output-root",
            str(output_root),
            "--fps",
            str(args.fps),
        ]
        if args.project_name:
            cmd += ["--project-name", args.project_name]
        if args.items:
            cmd += ["--items", *args.items]
        if args.item_range:
            cmd += ["--item-range", args.item_range]
        if not args.build_long_video:
            cmd.append("--no-require-long")
        run(cmd)
        progress_step("Validate generated video", is_start=False)

    outputs: list[str] = []
    if joined_video is not None:
        outputs.append(str(joined_video))
    else:
        items_out = output_root / name / "items"
        if items_out.is_dir():
            outputs.extend(str(p) for p in sorted(items_out.glob("item_*.mp4")))

    emit_result(status="success", outputs=outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())