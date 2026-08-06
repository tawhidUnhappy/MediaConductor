from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from mangaeasy.layout import (
    audio_root,
    faded_audio_root,
    library_root,
    output_root,
    review_root,
    subtitles_root,
    work_root,
    zips_root,
)
from mangaeasy.path_safety import validate_portable_segment


def _env_path(namespaced: str, default_fn: Callable[[Path | None], Path], project_root: Path | None = None) -> Path:
    value = os.environ.get(namespaced)
    if value:
        return Path(value).expanduser().resolve()
    return default_fn(project_root)


def default_project_root() -> Path:
    return library_root()


def default_audio_root(project_root: Path | None = None) -> Path:
    return _env_path("MANGAEASY_AUDIO_ROOT", audio_root, project_root)


def default_output_root(project_root: Path | None = None) -> Path:
    return _env_path("MANGAEASY_OUTPUT_ROOT", output_root, project_root)


def default_work_dir(project_root: Path | None = None) -> Path:
    return _env_path("MANGAEASY_WORK_DIR", work_root, project_root)


def default_review_root(project_root: Path | None = None) -> Path:
    return _env_path("MANGAEASY_REVIEW_ROOT", review_root, project_root)


def default_zips_root(project_root: Path | None = None) -> Path:
    return _env_path("MANGAEASY_ZIPS_ROOT", zips_root, project_root)


def default_subtitles_root(project_root: Path | None = None) -> Path:
    return _env_path("MANGAEASY_SUBTITLES_ROOT", subtitles_root, project_root)


DEFAULT_PROJECT_ROOT = library_root()
DEFAULT_AUDIO_ROOT = audio_root()
DEFAULT_OUTPUT_ROOT = output_root()
DEFAULT_WORK_DIR = work_root()
DEFAULT_REVIEW_ROOT = review_root()
DEFAULT_KOKORO_ROOT = Path(os.environ.get("KOKORO_ROOT", "kokoro-82m"))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac"}

GPU_WORKERS_SAFE_MAX = 4


def clamp_gpu_workers(requested: int) -> int:
    import sys
    if requested <= GPU_WORKERS_SAFE_MAX:
        return max(1, requested)
    if os.environ.get("MANGAEASY_UNSAFE_GPU_WORKERS") == "1":
        print(f"[warn] --gpu-workers {requested} exceeds safe max {GPU_WORKERS_SAFE_MAX}; proceeding.", file=sys.stderr)
        return requested
    print(f"[warn] --gpu-workers {requested} clamped to {GPU_WORKERS_SAFE_MAX}.", file=sys.stderr)
    return GPU_WORKERS_SAFE_MAX


def project_name(project_root: Path, override: str | None = None) -> str:
    value = override if override is not None else project_root.resolve().name
    return validate_portable_segment(value, label="project name")


class ProjectScoped(Protocol):
    project_root: Path
    work_dir: Path
    project_name_override: str | None


def project_work_dir(config: ProjectScoped) -> Path:
    return config.project_root.resolve() / "work"


def count_files(path: Path) -> int:
    if path.is_file():
        return 1
    return sum(1 for child in path.rglob("*") if child.is_file())


def item_number(value: str) -> int:
    match = re.search(r"\d+", value)
    if not match:
        raise ValueError(f"Could not find a number in: {value}")
    return int(match.group(0))


def item_value(value: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        raise ValueError(f"Could not find a number in: {value}")
    return float(match.group(0))


ITEM_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|\.\.|:)\s*(\d+(?:\.\d+)?)")


def is_item_range_token(token: str) -> bool:
    return ITEM_RANGE_RE.fullmatch(token.strip()) is not None


def expand_item_tokens(
    tokens: list[str] | None,
    width: int = 2,
    *,
    expand_ranges: bool = True,
) -> list[str] | None:
    if not tokens:
        return None

    expanded: list[str] = []
    for raw_token in tokens:
        for token in (part.strip() for part in raw_token.split(",")):
            if not token:
                continue

            range_match = ITEM_RANGE_RE.fullmatch(token)
            if range_match:
                if expand_ranges:
                    start = int(float(range_match.group(1)))
                    end = int(float(range_match.group(2)))
                    step = 1 if end >= start else -1
                    expanded.extend(f"{number:0{width}d}" for number in range(start, end + step, step))
                else:
                    expanded.append(token)
                continue

            if token.isdigit():
                expanded.append(f"{int(token):0{width}d}")
            else:
                expanded.append(token)

    seen: set[str] = set()
    deduped: list[str] = []
    for item in expanded:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _parse_selection_specs(selected: list[str] | None) -> tuple[list[tuple[float, float]], set[str], set[float]]:
    intervals: list[tuple[float, float]] = []
    wanted_names: set[str] = set()
    wanted_values: set[float] = set()

    if not selected:
        return intervals, wanted_names, wanted_values

    tokens: list[str] = []
    for item in selected:
        for part in item.split(","):
            part = part.strip()
            if part:
                tokens.append(part)

    for token in tokens:
        range_match = ITEM_RANGE_RE.fullmatch(token)
        if range_match:
            v1 = float(range_match.group(1))
            v2 = float(range_match.group(2))
            lo, hi = min(v1, v2), max(v1, v2)
            if lo <= 1.0:
                lo = 0.0
            intervals.append((lo, hi))
        else:
            wanted_names.add(token)
            if any(ch.isdigit() for ch in token):
                wanted_values.add(item_value(token))

    int_vals = sorted({int(item_value(t)) for t in tokens if t.isdigit() or re.fullmatch(r"\d+", t)})
    if len(int_vals) >= 2:
        run_start = int_vals[0]
        run_end = int_vals[0]
        for val in int_vals[1:]:
            if val == run_end + 1:
                run_end = val
            else:
                if run_end - run_start >= 1:
                    lo = 0.0 if run_start <= 1 else float(run_start)
                    intervals.append((lo, float(run_end)))
                run_start = val
                run_end = val
        if run_end - run_start >= 1:
            lo = 0.0 if run_start <= 1 else float(run_start)
            intervals.append((lo, float(run_end)))

    return intervals, wanted_names, wanted_values


def merge_item_selection(items: list[str] | None, item_range: str | None) -> list[str] | None:
    tokens: list[str] = []
    if items:
        tokens.extend(items)
    if item_range:
        tokens.append(item_range)
    return expand_item_tokens(tokens, expand_ranges=False)


def _sort_key(path: Path) -> tuple[int, float, str]:
    has_number = any(ch.isdigit() for ch in path.name)
    number = item_value(path.name) if has_number else float(10**9)
    return (0 if has_number else 1, number, path.name.lower())


def chunk_list(items: list, shards: int) -> list[list]:
    if shards <= 1 or len(items) <= 1:
        return [items]
    size = -(-len(items) // shards)
    return [items[i:i + size] for i in range(0, len(items), size)]


def item_dirs(root: Path, selected: list[str] | None = None) -> list[Path]:
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
        and path.name not in {"audio", "audio_faded", "output", "review", "zips", "subtitles", "work"}
        and ((path / "narration.json").exists() or (path / "panels").is_dir() or any(ch.isdigit() for ch in path.name))
    ]
    if selected:
        intervals, wanted_names, wanted_values = _parse_selection_specs(selected)
        filtered: list[Path] = []
        for path in candidates:
            if path.name in wanted_names:
                filtered.append(path)
                continue
            if any(ch.isdigit() for ch in path.name):
                val = item_value(path.name)
                if val in wanted_values:
                    filtered.append(path)
                    continue
                if any(lo <= val <= hi for lo, hi in intervals):
                    filtered.append(path)
                    continue
        candidates = filtered
    return sorted(candidates, key=_sort_key)