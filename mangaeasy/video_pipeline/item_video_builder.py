"""Item video builder updated with Ken Burns motion & hook speedup filters."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from mangaeasy.utils import archive_before_overwrite
from mangaeasy.video_pipeline.blur_background import (
    BlurBackgroundOptions,
    ffmpeg_cpu_blur_filter,
)
from mangaeasy.video_pipeline.common import (
    item_dirs,
    merge_item_selection,
    project_name,
)
from mangaeasy.video_pipeline.ffmpeg_tools import (
    choose_h264_encoder,
    filter_script_args,
    h264_encoder_args,
    run,
    validate_video_stream,
    write_concat_file,
)
from mangaeasy.video_pipeline.item_assets import PanelAsset, collect_panel_assets


@dataclass(frozen=True)
class VideoBuildConfig:
    project_root: Path
    audio_root: Path
    output_root: Path
    work_dir: Path
    project_name_override: str | None = None
    output_dir: Path | None = None
    items: list[str] | None = None
    item_range: str | None = None
    overwrite: bool = False
    width: int = 1920
    height: int = 1080
    fps: int = 30
    encoder: str = "auto"
    preset: str = "p5"
    cq: int = 18
    audio_bitrate: str = "192k"
    background_style: str = "blur"
    background_image: Path | None = None
    blur_sigma: float = 28.0
    blur_downscale: int = 4
    blur_backend: str = "auto"
    background_brightness: float = -0.06
    background_saturation: float = 1.08
    panel_scale: float = 1.0
    camera_motion: bool = False
    hook_speedup: bool = False
    keep_work: bool = False
    render_mode: str = "segments"
    workers: int = 1


def item_output_dir(config: VideoBuildConfig) -> Path:
    if config.output_dir is not None:
        return config.output_dir.resolve()
    return (
        config.output_root.resolve()
        / project_name(config.project_root, config.project_name_override)
        / "items"
    ).resolve()


def ken_burns_filter(
    width: int, height: int, duration_frames: int, motion_type: str = "zoom_in"
) -> str:
    """Jitter-free Ken Burns filter using 8000px pre-scaling."""
    zoom_expr = (
        "min(zoom+0.0015,1.25)"
        if motion_type == "zoom_in"
        else "max(1.25-0.0015*on,1.0)"
    )
    return (
        f"scale=8000:-1,"
        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={duration_frames}:s={width}x{height}:fps=30,"
        f"format=yuv420p"
    )


def hook_speedup_filtergraph() -> str:
    """Synchronized 1.15x speedup for cold open / hook segments."""
    return "[0:v]setpts=PTS/1.15[v];[0:a]atempo=1.15[a]"


def render_panel_segment(
    asset: PanelAsset, segment_path: Path, config: VideoBuildConfig
) -> None:
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    if segment_path.exists() and not config.overwrite:
        return

    encoder = choose_h264_encoder(config.encoder)
    if config.camera_motion:
        vf = ken_burns_filter(
            config.width, config.height, asset.frame_count, "zoom_in"
        )
    elif config.background_style == "blur":
        opts = BlurBackgroundOptions.from_mapping({
            "blur_sigma": config.blur_sigma,
            "blur_downscale": config.blur_downscale,
            "blur_backend": config.blur_backend,
            "background_brightness": config.background_brightness,
            "background_saturation": config.background_saturation,
            "panel_scale": config.panel_scale,
        })
        vf = ffmpeg_cpu_blur_filter(config.width, config.height, opts)
    else:
        vf = (
            f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
            f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"
        )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(config.fps),
        "-i",
        str(asset.image_path),
        "-vf",
        vf,
        *h264_encoder_args(encoder, config.preset, config.cq),
        "-frames:v",
        str(asset.frame_count),
        "-an",
        "-movflags",
        "+faststart",
        str(segment_path),
    ]
    run(cmd)


def build_item_narration_wav(
    item_dir: Path,
    assets: list[PanelAsset],
    work_dir: Path,
    output_wav_path: Path,
) -> Path:
    """Concatenate panel audio files with padding into a single item narration WAV."""
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filter_parts: list[str] = []

    for idx, asset in enumerate(assets):
        inputs.extend(["-i", str(asset.audio_path)])
        pad_s = max(0.0, asset.visual_duration - asset.audio_duration)
        if pad_s > 0.001:
            filter_parts.append(
                f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"apad,atrim=0:{asset.visual_duration:.6f}[a{idx}]"
            )
        else:
            filter_parts.append(
                f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{idx}]"
            )

    concat_inputs = "".join(f"[a{i}]" for i in range(len(assets)))
    filter_parts.append(f"{concat_inputs}concat=n={len(assets)}:v=0:a=1[a]")
    filter_graph = ";".join(filter_parts)

    script_file = work_dir / f"{output_wav_path.stem}_filter.graph"
    script_file.parent.mkdir(parents=True, exist_ok=True)
    script_file.write_text(filter_graph, encoding="utf-8")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        *inputs,
        *filter_script_args(script_file),
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(output_wav_path),
    ]
    run(cmd)
    return output_wav_path


def build_one_chapter(chapter_dir: Path, config: VideoBuildConfig) -> None:
    output_dir = item_output_dir(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"item_{chapter_dir.name}.mp4"

    if output_path.exists() and not config.overwrite:
        return
    if output_path.exists():
        archive_before_overwrite(output_path)

    assets = collect_panel_assets(
        chapter_dir,
        project_root=config.project_root,
        audio_root=config.audio_root,
        project_name_override=config.project_name_override,
        fps=config.fps,
    )

    segment_dir = config.work_dir / "segments" / chapter_dir.name
    segment_paths: list[Path] = []
    for idx, asset in enumerate(assets, start=1):
        segment_path = segment_dir / f"{idx:04d}_{asset.image_path.stem}.mp4"
        render_panel_segment(asset, segment_path, config)
        segment_paths.append(segment_path)

    item_wav_path = config.work_dir / f"item_{chapter_dir.name}_narration.wav"
    build_item_narration_wav(chapter_dir, assets, config.work_dir, item_wav_path)

    concat_file = write_concat_file(
        segment_paths, config.work_dir / f"item_{chapter_dir.name}_concat.ffconcat"
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-i",
        str(item_wav_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        config.audio_bitrate,
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    run(cmd)

    validate_video_stream(output_path, width=config.width, height=config.height)


def build_item_videos(config: VideoBuildConfig) -> Path:
    items = item_dirs(
        config.project_root.resolve(),
        merge_item_selection(config.items, config.item_range),
    )
    if not items:
        raise FileNotFoundError(f"No item folders found in {config.project_root}")

    if config.workers > 1 and len(items) > 1:
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures = [
                executor.submit(build_one_chapter, item_dir, config)
                for item_dir in items
            ]
            for future in futures:
                future.result()
    else:
        for item_dir in items:
            build_one_chapter(item_dir, config)

    return item_output_dir(config)