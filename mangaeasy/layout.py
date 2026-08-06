"""The one map of where mangaEasy puts things on disk.

Everything related to a specific manga is now completely isolated inside
its project directory:
    data/library/<MangaName>/
    ├── manga.json
    ├── MEMORY.json
    ├── .mangaeasy/manga-reviews.json
    ├── 01/                     (Source chapter images & narration.json)
    ├── audio/                  (Raw TTS .wav files & .json sidecars)
    ├── audio_faded/            (8ms edge-faded render derivatives)
    ├── output/                 (Item MP4s, full merged video, and quality reports)
    ├── review/                 (Reading & review contact sheets)
    ├── zips/                   (Packed sheet & context ZIP files <= 1 GB)
    ├── subtitles/              (Generated .ass/.srt subtitle files)
    └── work/                   (Job logs, scratch renders, manifests)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIRNAME = "data"
RUNTIME_DIRNAME = "runtime"

# Subfolders of data/library/<project>/
MANGA_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("audio", "raw TTS takes with their provenance sidecars"),
    ("audio_faded", "render-safe narration derivatives (8ms edge fades)"),
    ("output", "item videos, the joined full video, and quality reports"),
    ("review", "review sheets and evidence rendered for approval"),
    ("zips", "packed sheet and panel context ZIP files (<= 1 GB each)"),
    ("subtitles", "generated ASS and SRT subtitle files"),
    ("work", "scratch space and background job logs"),
)

RUNTIME_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("tools", "isolated AI tool environments (install-tool)"),
    ("cache", "Hugging Face, Torch, uv, Triton and Inductor caches"),
    ("state", "install-level state: which workspace this install points at"),
    ("secrets", "gitignored OAuth tokens"),
)


def _resolved(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def workspace_root() -> Path:
    """The workspace this process is operating on."""
    from mangaeasy.config import PROJECT_ROOT
    return PROJECT_ROOT


def data_root() -> Path:
    """data/ root folder."""
    configured = os.environ.get("MANGAEASY_DATA_ROOT")
    if configured:
        return _resolved(configured)
    return (workspace_root() / DATA_DIRNAME).resolve()


def runtime_root() -> Path:
    """runtime/ root folder for machinery and tools."""
    configured = os.environ.get("MANGAEASY_HOME")
    if configured:
        return _resolved(configured)
    from mangaeasy.tools.external import app_root
    return (app_root() / RUNTIME_DIRNAME).resolve()


def library_root() -> Path:
    """Every downloaded title, one subfolder each: data/library/<project>."""
    return data_root() / "library"


# ── Per-Manga Isolated Paths ─────────────────────────────────────────────────

def project_dir(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return _resolved(project_root)
    from mangaeasy.config import PROJECT_ROOT
    return _resolved(PROJECT_ROOT)


def audio_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "audio"


def faded_audio_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "audio_faded"


def output_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "output"


def review_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "review"


def work_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "work"


def zips_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "zips"


def subtitles_root(project_root: Path | None = None) -> Path:
    return project_dir(project_root) / "subtitles"


def project_memory_path(project_root: Path) -> Path:
    return project_dir(project_root) / "MEMORY.json"


# ── Runtime Sub-roots ────────────────────────────────────────────────────────

def tools_root() -> Path:
    configured = os.environ.get("MANGAEASY_TOOLS_DIR")
    if configured:
        return _resolved(configured)
    return runtime_root() / "tools"


def cache_root() -> Path:
    return runtime_root() / "cache"


def cache_dir(name: str) -> Path:
    return cache_root() / name


def state_root() -> Path:
    return runtime_root() / "state"


def secrets_root() -> Path:
    return runtime_root() / "secrets"


def ensure_data_root(project_root: Path | None = None) -> Path:
    p_dir = project_dir(project_root)
    p_dir.mkdir(parents=True, exist_ok=True)
    for name, _ in MANGA_SUBDIRS:
        (p_dir / name).mkdir(parents=True, exist_ok=True)
    return p_dir


def ensure_runtime_root() -> Path:
    root = runtime_root()
    for name, _ in RUNTIME_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root