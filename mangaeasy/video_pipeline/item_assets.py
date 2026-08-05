from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from mangaeasy.audio.narration_safety import narration_quality_findings
from mangaeasy.video_pipeline.common import IMAGE_EXTENSIONS  # noqa: F401  (single home: common.py)
from mangaeasy.video_pipeline.common import project_name
from mangaeasy.video_pipeline.ffmpeg_tools import probe_duration
from mangaeasy.video_pipeline.narration_contract import validate_item_narration


def frame_aligned_duration(audio_duration: float, fps: int) -> tuple[float, int]:
    frames = max(1, math.ceil(audio_duration * fps))
    return frames / fps, frames


@dataclass(frozen=True)
class PanelAsset:
    image_path: Path
    audio_path: Path
    audio_duration: float
    visual_duration: float
    frame_count: int
    pause_after_ms: int = 0


def load_narration(item_dir: Path, *, require_files: bool = True) -> list[dict]:
    """Load an item's narration entries, in playback order, contract-validated.

    If `intro.json` exists alongside `narration.json`, its entries are
    prepended -- a project-agnostic way to give one item (usually the first
    chapter) a cold-open trailer/hook reel without splicing it into the
    item's own narration.json. Same `{"image": ..., "narration": ...}` shape,
    same panels/ folder; every caller (audio generation, rendering,
    validation) sees one combined list.

    Every entry is validated by
    :mod:`mangaeasy.video_pipeline.narration_contract` first, so no
    consumer downstream has to re-derive what a safe ``image`` value is. Pass
    ``require_files=False`` to validate shape without touching the disk.
    """
    return validate_item_narration(Path(item_dir), require_files=require_files)


def validate_calm_narration(entries: list[dict], source: Path) -> None:
    """Reject narration that cannot be spoken acceptably.

    This preflight stays separate from ``load_narration`` so QA can still load
    unsafe entries and report precise edit commands. Audio and video entry
    points call it before doing expensive or destructive work.

    Only ``error`` findings raise. Style warnings (repetition, meta phrasing,
    beat length) are reported by ``narration-check`` and ``work-qa``, where a
    human can weigh them, and never block a render on their own.
    """
    problems = [
        f"{finding.beat}: {finding.message}"
        for finding in narration_quality_findings(entries)
        if finding.is_error
    ]
    if problems:
        details = "\n".join(f"  - {problem}" for problem in problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise ValueError(
            f"Narration under {source} violates the calm-narration policy; "
            "fix narration.json or intro.json before TTS or rendering:\n"
            f"{details}{more}"
        )


def item_audio_dir(audio_root: Path, project_root: Path, project_name_override: str | None, item_dir: Path) -> Path:
    return audio_root.resolve() / project_name(project_root, project_name_override) / item_dir.name


def item_narration_dir(audio_root: Path, project_root: Path, project_name_override: str | None) -> Path:
    return audio_root.resolve() / project_name(project_root, project_name_override) / "_items"


def item_narration_path(audio_root: Path, project_root: Path, project_name_override: str | None, item_dir: Path) -> Path:
    return item_narration_dir(audio_root, project_root, project_name_override) / f"item_{item_dir.name}_narration.wav"


def panel_filenames(item_dir: Path, panels_subdir: str = "panels") -> list[str]:
    panels_dir = Path(item_dir) / panels_subdir
    if not panels_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in panels_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def assert_all_panels_narrated(item_dir: Path, entries: list[dict]) -> None:
    panels = panel_filenames(item_dir)
    narrated = [entry["image"] for entry in entries if isinstance(entry, dict) and entry.get("image")]
    missing = [name for name in panels if name not in narrated]
    if missing:
        shown = ", ".join(missing[:20])
        more = f"\n  ... and {len(missing) - 20} more" if len(missing) > 20 else ""
        raise ValueError(
            f"{item_dir.name}: {len(missing)} cropped panel(s) have no narration and "
            f"would be skipped by the video: {shown}{more}. Strict mode requires every "
            "panel in panels/ to appear in narration.json or intro.json."
        )


def collect_panel_assets(
    item_dir: Path,
    *,
    project_root: Path,
    audio_root: Path,
    project_name_override: str | None,
    fps: int,
) -> list[PanelAsset]:
    assets: list[PanelAsset] = []
    audio_dir = item_audio_dir(audio_root, project_root, project_name_override, item_dir)
    entries = load_narration(item_dir)
    assert_all_panels_narrated(item_dir, entries)
    for item in entries:
        image_name = item.get("image")
        if not image_name:
            raise ValueError(f"Missing image key in {item_dir / 'narration.json'}")
        image_path = item_dir / "panels" / image_name
        audio_path = audio_dir / f"{Path(image_name).stem}.wav"
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS or not image_path.exists():
            raise FileNotFoundError(f"Missing panel image: {image_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Missing audio for {image_name}: {audio_path}. Run generate_audio.py first.")
        audio_duration = probe_duration(audio_path)
        pause_after_ms = int(item.get("pause_after_ms") or 0)
        visual_duration, frame_count = frame_aligned_duration(
            audio_duration + pause_after_ms / 1000.0,
            fps,
        )
        assets.append(
            PanelAsset(
                image_path,
                audio_path,
                audio_duration,
                visual_duration,
                frame_count,
                pause_after_ms,
            )
        )
    return assets
