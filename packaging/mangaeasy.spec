# PyInstaller spec for the standalone mangaEasy build (one-folder + macOS .app).
#
#   uv run pyinstaller packaging/mangaeasy.spec
#
# Produces dist/mangaEasy/ on Windows/Linux and
# dist/mangaEasy.app/ on macOS.

import sys as _sys
import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # repo root (spec lives in packaging/)
PKG  = ROOT / "mangaeasy"
VERSION = os.environ.get("MANGAEASY_VERSION") or os.environ.get("MEDIACONDUCTOR_VERSION")
if not VERSION:
    with open(ROOT / "pyproject.toml", "rb") as _f:
        VERSION = tomllib.load(_f)["project"]["version"]

# Platform-appropriate icon file. PyInstaller converts ordinary image formats
# to ICNS through Pillow, so macOS uses the tracked source image instead of
# silently falling back when an ungenerated icon.icns is absent.
if _sys.platform == "darwin":
    ICON  = str(ROOT / "packaging" / "icon.png")
elif _sys.platform == "win32":
    ICON  = str(ROOT / "packaging" / "icon.ico")
else:
    ICON  = str(ROOT / "packaging" / "icon.png")

hiddenimports = collect_submodules("mangaeasy")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(PKG), "mangaeasy"),
        (str(ROOT / "skills"), "mangaeasy/agent_skills"),
        (str(ROOT / "packaging" / "icon.png"), "."),
        (str(ROOT / "packaging" / "icon.ico"), "."),  # loaded at runtime to set the Win32 window icon
    ],
    hiddenimports=hiddenimports,
    excludes=["torch", "torchvision", "transformers"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mangaeasy",
    console=True,  # CLI/MCP stdio must remain available in frozen builds
    icon=ICON,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="mangaEasy",
)

# macOS: wrap in a proper .app bundle so Finder shows the icon and the app
# behaves like a native macOS application
if _sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="mangaEasy.app",
        icon=ICON,
        bundle_identifier="app.mangaeasy.cli",
        info_plist={
            "CFBundleName": "mangaEasy",
            "CFBundleDisplayName": "mangaEasy",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # supports dark mode
        },
    )
