"""mediaconductor.paths
Per-chapter folder conventions, built on top of :mod:`mediaconductor.layout`.

layout.py answers "where does the library live"; this module answers "where
inside one chapter do panels/audio/tmp go". Subdirectory names (panels,
audio, processed) are read from config.system.json → paths section so they
can be changed without touching any Python files.
"""

from pathlib import Path

from mediaconductor.config import load_download_config, load_system_config
from mediaconductor.layout import library_root
from mediaconductor.path_safety import validate_portable_segment, validate_relative_subpath


def _dl() -> dict:
    return load_download_config()


def _path_cfg() -> dict:
    value = load_system_config().get("paths", {})
    return value if isinstance(value, dict) else {}


def _configured_subdir(value: object, label: str) -> Path:
    return Path(validate_relative_subpath(value, label=label))


# ── Library / chapter dirs ────────────────────────────────────────────────────

def library_dir() -> Path:
    """The folder that holds every manga — one subfolder per title.

    ``data/library/`` (see :func:`mediaconductor.layout.library_root`), named
    so it can't be confused with a single manga's own folder:
    ``data/library/{name}/`` holds that manga's chapters.
    """
    return library_root()


def manga_dir(name: str | None = None) -> Path:
    """One manga's own folder (holds its chapter subfolders)."""
    if name is None:
        name = str(_dl()["name"])
    return library_dir() / validate_portable_segment(name, label="manga project name")


def chapter_dir(name: str | None = None, chapter: int | None = None) -> Path:
    if name is None or chapter is None:
        dl = _dl()
        name    = name    or str(dl["name"])
        chapter = chapter if chapter is not None else int(dl["chapter"])
    return manga_dir(name) / f"{chapter:02d}"


def download_dir(name=None, chapter=None) -> Path:
    return chapter_dir(name, chapter) / "download"


def panels_dir(name=None, chapter=None) -> Path:
    subdir = _path_cfg().get("panels_subdir", "panels")
    return chapter_dir(name, chapter) / _configured_subdir(
        subdir, "configured panels subdirectory"
    )


def processed_panels_dir(name=None, chapter=None) -> Path:
    """Post-processed (upscaled / mirrored / cleaned) panels directory."""
    subdir = _path_cfg().get("processed_subdir", "panels_processed")
    return chapter_dir(name, chapter) / _configured_subdir(
        subdir, "configured processed-panel subdirectory"
    )


def audio_dir(name=None, chapter=None) -> Path:
    subdir = _path_cfg().get("audio_subdir", "audio")
    return chapter_dir(name, chapter) / _configured_subdir(
        subdir, "configured audio subdirectory"
    )


def narration_json(name=None, chapter=None) -> Path:
    if name is None or chapter is None:
        dl = _dl()
        name    = name    or str(dl["name"])
        chapter = chapter if chapter is not None else int(dl["chapter"])
    return chapter_dir(name, chapter) / f"narration_{chapter:02d}.json"


def output_video(name=None, chapter=None) -> Path:
    dl = _dl()
    n = name    or str(dl["name"])
    c = chapter if chapter is not None else int(dl["chapter"])
    return chapter_dir(n, c) / f"{c:02d}_{n}.mp4"


# ── Temp dirs ─────────────────────────────────────────────────────────────────

def tmp_dir(name=None, chapter=None) -> Path:
    """Temporary build artefacts live inside the chapter folder (library/{name}/{ch}/tmp/).

    Everything for a chapter stays together; the folder is removed after
    render unless config.system.json → render.keep_tmp is true.
    """
    return chapter_dir(name, chapter) / "tmp"


def faded_audio_dir(name=None, chapter=None) -> Path:
    return chapter_dir(name, chapter) / "audio_faded"
