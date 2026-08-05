"""Item video builder updated with Ken Burns motion & hook speedup filters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mangaeasy.utils import archive_before_overwrite
from mangaeasy.video_pipeline.common import item_dirs, merge_item_selection, project_name, project_work_dir
from mangaeasy.video_pipeline.ffmpeg_tools import choose_h264_encoder, h264_encoder_args, run, validate_video_stream
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
    panel_scale: float = 1.0
    camera_motion: bool = False
    hook_speedup: bool = False
    workers: int = 1


def item_output_dir(config: VideoBuildConfig) -> Path:
    if config.output_dir is not None:
        return config.output_dir.resolve()
    return (config.output_root.resolve() / project_name(config.project_root, config.project_name_override) / "items").resolve()


def ken_burns_filter(width: int, height: int, duration_frames: int, motion_type: str = "zoom_in") -> str:
    """Jitter-free Ken Burns filter using 8000px pre-scaling."""
    zoom_expr = "min(zoom+0.0015,1.25)" if motion_type == "zoom_in" else "max(1.25-0.0015*on,1.0)"
    return (
        f"scale=8000:-1,"
        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={duration_frames}:s={width}x{height}:fps=30,"
        f"format=yuv420p"
    )


def hook_speedup_filtergraph() -> str:
    """Synchronized 1.15x speedup for cold open / hook segments."""
    return "[0:v]setpts=PTS/1.15[v];[0:a]atempo=1.15[a]"


def render_panel_segment(asset: PanelAsset, segment_path: Path, config: VideoBuildConfig) -> None:
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    if segment_path.exists() and not config.overwrite:
        return

    encoder = choose_h264_encoder(config.encoder)
    if config.camera_motion:
        vf = ken_burns_filter(config.width, config.height, asset.frame_count, "zoom_in")
    else:
        vf = f"scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p"

    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-loop", "1", "-framerate", str(config.fps),
        "-i", str(asset.image_path),
        "-vf", vf,
        *h264_encoder_args(encoder, config.preset, config.cq),
        "-frames:v", str(asset.frame_count),
        "-an", "-movflags", "+faststart", str(segment_path),
    ]
    run(cmd)


def build_one_chapter(chapter_dir: Path, config: VideoBuildConfig) -> None:
    output_dir = item_output_dir(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"item_{chapter_dir.name}.mp4"

    if output_path.exists() and not config.overwrite:
        return
    if output_path.exists():
        archive_before_overwrite(output_path)

    assets = collect_panel_assets(
        chapter_dir, project_root=config.project_root, audio_root=config.audio_root,
        project_name_override=config.project_name_override, fps=config.fps,
    )
    segment_dir = config.work_dir / "segments" / chapter_dir.name
    for idx, asset in enumerate(assets, start=1):
        segment_path = segment_dir / f"{idx:04d}_{asset.image_path.stem}.mp4"
        render_panel_segment(asset, segment_path, config)

    validate_video_stream(output_path, width=config.width, height=config.height)


def build_item_videos(config: VideoBuildConfig) -> Path:
    items = item_dirs(config.project_root.resolve(), merge_item_selection(config.items, config.item_range))
    for item_dir in items:
        build_one_chapter(item_dir, config)
    return item_output_dir(config)