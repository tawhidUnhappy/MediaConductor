"""mangaeasy.fonts — the one place that answers "which TrueType file?".

Every image this project draws text onto — panel-index overlays, cutcheck
strips, contact sheets, narration sheets, thumbnails, the labelled AI ZIP —
needs a real scalable font. Pillow only resolves a *bare* font name like
``arialbd.ttf`` through the host's own font search, which in practice means
Windows: on Linux and macOS the bare name raises and the caller falls back to
``ImageFont.load_default()``. That default is a small bitmap face whose size
argument is ignored, so a 48 px panel number renders about 41x8 px — legible
enough that nothing crashes, illegible enough that the crop-review artifacts
the production gates depend on cannot be read. Every call site had its own
partial candidate list, so the same page looked different on each OS.

This module resolves fonts the same way on Windows, macOS and Linux:

1. an explicit path the user passed (``--font``), used as-is;
2. named families, looked up in that platform's real font directories,
   including the distro-specific ones (Debian's ``truetype/dejavu``,
   Fedora's ``dejavu``, Arch's ``TTF``, …) rather than one hardcoded path;
3. the TTF bundled in ``assets/fonts/``, which ships with the package and is
   therefore always present;
4. only then Pillow's bitmap default — reached now only if the bundled font
   is missing too, which means a broken install.

Resolution is cached: a contact sheet asks for the same face hundreds of
times, and scanning font directories per panel showed up in render profiles.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FontLike = "ImageFont.FreeTypeFont | ImageFont.ImageFont"

# Roles, not font names: call sites ask for the *job* the text does, so the
# per-platform substitutions live here instead of at every draw site.
BOLD = "bold"
REGULAR = "regular"
DISPLAY = "display"

# Ordered per role, best first. Bare filenames are matched case-insensitively
# against the files found in the platform font directories below, so one entry
# covers ``Arial Bold.ttf`` on macOS and ``arialbd.ttf`` on Windows.
_FAMILIES: dict[str, tuple[str, ...]] = {
    BOLD: (
        "arialbd.ttf", "Arial Bold.ttf", "Arial-Bold.ttf", "ArialBd.ttf",
        "HelveticaNeue-Bold.ttf", "Helvetica-Bold.ttf",
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
        "NotoSans-Bold.ttf", "Ubuntu-B.ttf", "FreeSansBold.ttf",
        "SFNSDisplay-Bold.otf", "seguisb.ttf", "segoeuib.ttf", "calibrib.ttf",
        "Helvetica.ttc", "HelveticaNeue.ttc",
    ),
    REGULAR: (
        "arial.ttf", "Arial.ttf",
        "Helvetica.ttc", "HelveticaNeue.ttc", "Helvetica.ttf",
        "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
        "NotoSans-Regular.ttf", "Ubuntu-R.ttf", "FreeSans.ttf",
        "segoeui.ttf", "calibri.ttf", "tahoma.ttf", "consola.ttf", "cour.ttf",
    ),
    # Thumbnails want a heavy condensed display face (the channel look);
    # a bold sans is an acceptable stand-in, never a bitmap.
    DISPLAY: (
        "impact.ttf", "Impact.ttf", "Impact.ttc",
        "arialbd.ttf", "Arial Bold.ttf", "Arial-Bold.ttf",
        "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
        "NotoSans-Bold.ttf", "FreeSansBold.ttf",
    ),
}

# The font shipped inside the package — the guaranteed last real font.
BUNDLED_FONT = "edosz.ttf"

_FONT_SUFFIXES = (".ttf", ".ttc", ".otf")


def bundled_font_path(name: str = BUNDLED_FONT) -> Path | None:
    """Absolute path to a font shipped in ``assets/fonts/``, or None."""
    candidate = Path(__file__).resolve().parent / "assets" / "fonts" / name
    return candidate if candidate.is_file() else None


def _platform_font_dirs() -> tuple[Path, ...]:
    """Every directory this OS keeps installed fonts in, best first.

    Deliberately broad on Linux: ``/usr/share/fonts`` is laid out differently
    per distribution (``truetype/dejavu`` on Debian, ``dejavu`` on Fedora,
    ``TTF`` on Arch), so the tree is walked instead of guessed at.
    """
    home = Path.home()
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        local = os.environ.get("LOCALAPPDATA")
        dirs = [windir / "Fonts"]
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
        return tuple(dirs)
    if sys.platform == "darwin":
        return (
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            home / "Library" / "Fonts",
        )
    dirs = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".local" / "share" / "fonts",
        home / ".fonts",
    ]
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        dirs.insert(0, Path(xdg) / "fonts")
    return tuple(dirs)


@lru_cache(maxsize=1)
def _installed_fonts() -> dict[str, Path]:
    """Map lowercase font filename -> path, for every installed font file.

    Cached for the life of the process: a contact sheet resolves the same face
    once per panel, and walking the font tree each time is measurable.
    """
    found: dict[str, Path] = {}
    for directory in _platform_font_dirs():
        try:
            if not directory.is_dir():
                continue
            # Font trees are shallow and small; a full walk is cheap and is the
            # only way to be distro-agnostic. Sorted for deterministic wins.
            for path in sorted(directory.rglob("*")):
                if path.suffix.lower() in _FONT_SUFFIXES and path.is_file():
                    found.setdefault(path.name.lower(), path)
        except OSError:
            continue  # unreadable font dir is not a reason to fail a render
    return found


def find_font_file(names: tuple[str, ...]) -> Path | None:
    """First installed font file matching *names* (case-insensitive), or None."""
    installed = _installed_fonts()
    for name in names:
        hit = installed.get(name.lower())
        if hit is not None:
            return hit
    return None


@lru_cache(maxsize=256)
def _cached_truetype(path: str, size: int):
    return ImageFont.truetype(path, size)


def load(size: int, role: str = BOLD, explicit: str | Path | None = None):
    """A real scalable font of *size*, resolved identically on every platform.

    *role* is one of :data:`BOLD`, :data:`REGULAR`, :data:`DISPLAY`. *explicit*
    (a ``--font`` value) wins when it loads. Falls through to the bundled font
    and only then to Pillow's bitmap default, so text is never silently
    rendered at the wrong size.
    """
    size = max(1, int(size))
    if explicit:
        try:
            return _cached_truetype(str(explicit), size)
        except (OSError, ValueError):
            pass  # a bad --font must not abort a render; fall back below

    candidates = _FAMILIES.get(role, _FAMILIES[BOLD])
    resolved = find_font_file(candidates)
    if resolved is not None:
        try:
            return _cached_truetype(str(resolved), size)
        except (OSError, ValueError):
            pass

    # Bare names still work where Pillow's own search finds them (Windows).
    for name in candidates:
        try:
            return _cached_truetype(name, size)
        except (OSError, ValueError):
            continue

    bundled = bundled_font_path()
    if bundled is not None:
        try:
            return _cached_truetype(str(bundled), size)
        except (OSError, ValueError):
            pass

    return load_default_sized(size)


def load_default_sized(size: int):
    """Pillow's built-in face at *size* — the scalable spelling of the default.

    ``load_default()`` with no argument returns the face at ~10 px and ignores
    every later size, which is what made the old fallbacks unreadable. Pillow
    has accepted a size since 10.1 (this project requires 12.1+); the guard is
    only for an unexpectedly old Pillow, where an unscaled face still beats a
    traceback mid-render.
    """
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()
