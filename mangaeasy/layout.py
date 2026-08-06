"""The one map of where mangaEasy puts things on disk.

Two roots:
1. data/ - Everything downloaded or generated.
   When operating on a specific manga, outputs are isolated inside:
       data/library/<MangaName>/
       ├── manga.json
       ├── MEMORY.json
       ├── .mangaeasy/manga-reviews.json
       ├── 01/                     (Source chapter images & narration.json)
       ├── audio/                  (Raw TTS .wav files & .json sidecars)
       ├── audio_faded/            (8ms edge-faded render derivatives)
       ├── output/                 (Item MP4s, full merged video, quality reports)
       ├── review/                 (Reading & review contact sheets)
       ├── zips/                   (Packed sheet & context ZIP files <= 1 GB)
       ├── subtitles/              (Generated .ass/.srt subtitle files)
       └── work/                   (Job logs, scratch renders, manifests)

2. runtime/ - Re-downloadable machinery (tool envs, caches, state, secrets).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIRNAME = "data"
RUNTIME_DIRNAME = "runtime"

# Subfolders of data/
DATA_SUBDIRS: tuple[tuple[str, str], ...] = (
    ("library", "downloaded chapters, cropped panels, narration, and review records"),
    ("audio", "raw TTS takes with their provenance sidecars"),
    ("audio_faded", "render-safe narration derivatives (8ms edge fades)"),
    ("output", "item videos, the joined full video, and quality reports"),
    ("review", "review sheets and evidence rendered for approval"),
    ("zips", "packed sheet and panel context ZIP files (<= 1 GB each)"),
    ("subtitles", "generated ASS and SRT subtitle files"),
    ("work", "scratch space and background job logs — safe to delete any time"),
)

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
    ("secrets", "gitignored OAuth tokens — never printed, only paths/booleans"),
)

CACHE_SUBDIRS: dict[str, str] = {
    "hf": "Hugging Face hub downloads (models, tokenizers)",
    "torch": "torch.hub checkpoints",
    "torch_extensions": "compiled torch C++/CUDA extensions",
    "torchinductor": "TorchInductor compilation cache",
    "triton": "Triton kernel cache",
    "uv": "uv wheel/source cache",
    "uv_python": "uv-managed Python interpreters",
    "xdg": "XDG_CACHE_HOME for tools that ignore the rest",
}


def _resolved(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def workspace_root() -> Path:
    """The workspace this process is operating on (holds config.json, data/)."""
    from mangaeasy.config import PROJECT_ROOT
    return PROJECT_ROOT


def data_root() -> Path:
    """<workspace>/data — home for production state."""
    configured = os.environ.get("MANGAEASY_DATA_ROOT")
    if configured:
        return _resolved(configured)
    return (workspace_root() / DATA_DIRNAME).resolve()


def runtime_root() -> Path:
    """<install>/runtime — tool envs, caches, state, secrets."""
    configured = os.environ.get("MANGAEASY_HOME")
    if configured:
        return _resolved(configured)
    from mangaeasy.tools.external import app_root
    return (app_root() / RUNTIME_DIRNAME).resolve()


def _paths_config() -> dict:
    from mangaeasy.config import SYSTEM_CONFIG_FILE
    try:
        loaded = json.loads(SYSTEM_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    value = loaded.get("paths") if isinstance(loaded, dict) else None
    return value if isinstance(value, dict) else {}


def library_root() -> Path:
    """Every downloaded title, one subfolder each: data/library/<project>."""
    from mangaeasy.path_safety import validate_relative_subpath

    configured = _paths_config().get("library_subdir")
    if configured:
        subdir = validate_relative_subpath(configured, label="configured library subdirectory")
        return data_root() / subdir
    return data_root() / "library"


def project_dir(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return _resolved(project_root)
    from mangaeasy.config import PROJECT_ROOT
    return _resolved(PROJECT_ROOT)


def audio_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "audio"
    return data_root() / "audio"


def faded_audio_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "audio_faded"
    return data_root() / "audio_faded"


def output_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "output"
    return data_root() / "output"


def review_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "review"
    return data_root() / "review"


def work_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "work"
    return data_root() / "work"


def zips_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "zips"
    return data_root() / "zips"


def subtitles_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_dir(project_root) / "subtitles"
    return data_root() / "subtitles"


def project_memory_path(project_root: Path) -> Path:
    return project_dir(project_root) / "MEMORY.json"


def tools_root() -> Path:
    configured = os.environ.get("MANGAEASY_TOOLS_DIR")
    if configured:
        return _resolved(configured)
    return runtime_root() / "tools"


def cache_root() -> Path:
    return runtime_root() / "cache"


def cache_dir(name: str) -> Path:
    if name not in CACHE_SUBDIRS:
        raise KeyError(f"unknown cache {name!r}; known: {', '.join(sorted(CACHE_SUBDIRS))}")
    return cache_root() / name


def state_root() -> Path:
    return runtime_root() / "state"


def secrets_root() -> Path:
    return runtime_root() / "secrets"


DATA_README = """# mangaEasy data

Everything mangaEasy downloaded or generated lives here, and nothing else does.
Delete this whole folder to start completely fresh.

## Subfolders
{subdirs}
"""


def data_readme_text() -> str:
    lines = [f"- `{name}/` — {description}" for name, description in DATA_SUBDIRS]
    return DATA_README.format(subdirs="\n".join(lines))


def ensure_data_root(write_readme: bool = True, project_root: Path | None = None) -> Path:
    if project_root is not None:
        p_dir = project_dir(project_root)
        p_dir.mkdir(parents=True, exist_ok=True)
        for name, _ in MANGA_SUBDIRS:
            (p_dir / name).mkdir(parents=True, exist_ok=True)
        return p_dir

    root = data_root()
    for name, _ in DATA_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    if write_readme:
        readme = root / "README.md"
        text = data_readme_text()
        try:
            if not readme.exists() or readme.read_text(encoding="utf-8") != text:
                readme.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return root


def ensure_runtime_root() -> Path:
    root = runtime_root()
    for name, _ in RUNTIME_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root