"""Guards for the things that differ between Linux, Windows and macOS.

Each test here stands for a way the same command produced a different — and
on one OS, wrong — result:

* Pillow resolves a bare font name like ``arialbd.ttf`` only through the host
  font search, which in practice means Windows. On Linux and macOS every
  drawing call fell through to ``ImageFont.load_default()``, a bitmap face
  that ignores its size argument, so panel-index overlays and contact sheets
  rendered at ~10 px instead of the requested 28-104 px. Nothing crashed; the
  crop-review artifacts the production gates depend on were simply unreadable.
* ``shutil.rmtree`` cannot delete a read-only file on Windows, so
  ``workspace-reset`` and the ``video-clean-*`` commands could abort partway
  and leave a half-erased tree.
* A ``.bat`` checked out with LF endings mis-parses in cmd.exe.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest
from PIL import ImageFont

from mangaeasy import fonts
from mangaeasy.utils import remove_tree

ROOT = Path(__file__).resolve().parent.parent


# ── Fonts ─────────────────────────────────────────────────────────────────────

FONT_CALL_SITES = [
    ("mangaeasy.panels.page", "_load_font", (48,)),
    ("mangaeasy.panels.cutcheck", "_load_font", (28,)),
    ("mangaeasy.images.ai_zip", "_load_font", (40,)),
    ("mangaeasy.video_pipeline.narration_sheets", "_font", (30,)),
]


def _import(module: str, name: str):
    import importlib

    return getattr(importlib.import_module(module), name)


@pytest.mark.parametrize(("module", "name", "args"), FONT_CALL_SITES)
def test_font_call_sites_get_a_size_honouring_font(module, name, args):
    """Every text-drawing entry point must honour the size it asks for.

    Asserting on the rendered width rather than the type is deliberate: recent
    Pillow returns a FreeTypeFont from load_default() too, so only the metrics
    distinguish "a real face at 48 px" from "the fallback at 10 px".
    """
    font = _import(module, name)(*args)
    size = args[0]
    width = font.getbbox("Panel 12")[2]
    assert width > size, (
        f"{module}.{name}({size}) rendered 'Panel 12' only {width}px wide — "
        f"that is the unscaled bitmap fallback, not a {size}px font"
    )


def test_thumbnail_font_scales_at_playbook_size():
    from mangaeasy.images.thumbnail_compose import DEFAULT_FONT_SIZE, load_font

    font = load_font(DEFAULT_FONT_SIZE, None)
    assert font.getbbox("HOOK")[2] > DEFAULT_FONT_SIZE


def test_webtoon_contact_sheet_fonts_differ_by_size():
    from mangaeasy.panels.webtoon import _load_fonts

    small, large = _load_fonts()
    assert large.getbbox("Panel 12")[2] > small.getbbox("Panel 12")[2]


def test_bundled_font_ships_with_the_package():
    """The last real fallback must exist, or a bare container has no font."""
    bundled = fonts.bundled_font_path()
    assert bundled is not None and bundled.is_file()


def test_resolution_falls_back_to_bundled_font_with_no_system_fonts(monkeypatch):
    """A stripped container/CI image has no installed fonts at all."""
    monkeypatch.setattr(fonts, "_platform_font_dirs", lambda: ())
    fonts._installed_fonts.cache_clear()
    try:
        font = fonts.load(64, fonts.BOLD)
        # Pillow's own bare-name search may still succeed on Windows; either
        # way the result must scale.
        assert font.getbbox("Panel 12")[2] > 64
    finally:
        fonts._installed_fonts.cache_clear()


def test_explicit_font_wins_and_a_bad_one_still_renders():
    bundled = fonts.bundled_font_path()
    chosen = fonts.load(40, fonts.DISPLAY, explicit=bundled)
    assert chosen.getname() == ImageFont.truetype(str(bundled), 40).getname()
    # A bad --font must not abort a render.
    assert fonts.load(40, fonts.DISPLAY, explicit="/nonexistent/x.ttf").getbbox("A")[2] > 0


def test_platform_font_dirs_are_for_this_platform():
    dirs = [str(d) for d in fonts._platform_font_dirs()]
    assert dirs, "no font directories for this platform"
    if sys.platform == "darwin":
        assert any("/System/Library/Fonts" in d for d in dirs)
    elif sys.platform == "win32":
        assert any(d.lower().endswith("fonts") for d in dirs)
    else:
        assert any("/usr/share/fonts" in d for d in dirs)


def test_no_module_loads_fonts_by_bare_name_anymore():
    """Bare-name truetype() calls resolve on Windows only — route via fonts.py."""
    offenders = []
    for path in sorted((ROOT / "mangaeasy").rglob("*.py")):
        if path.name == "fonts.py" or path.parts[-2:-1] == ("assets",):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "ImageFont.truetype(" in line or "ImageFont.load_default(" in line:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}")
    assert not offenders, (
        "load fonts through mangaeasy.fonts.load() so every OS resolves "
        "the same face:\n" + "\n".join(offenders)
    )


# ── Tree removal ──────────────────────────────────────────────────────────────

def test_remove_tree_deletes_read_only_files(tmp_path):
    """The Windows failure mode: a read-only file inside a deleted tree."""
    target = tmp_path / "data" / "output"
    target.mkdir(parents=True)
    locked = target / "final.mp4"
    locked.write_bytes(b"video")
    locked.chmod(stat.S_IREAD)
    try:
        remove_tree(target.parent)
    finally:
        if locked.exists():
            locked.chmod(stat.S_IWRITE | stat.S_IREAD)
    assert not target.parent.exists()


def test_remove_tree_raises_on_a_missing_tree(tmp_path):
    with pytest.raises(FileNotFoundError):
        remove_tree(tmp_path / "never-existed")


def test_remove_tree_ignore_errors_is_quiet(tmp_path):
    remove_tree(tmp_path / "never-existed", ignore_errors=True)


def test_cleanup_commands_do_not_call_rmtree_directly():
    """Destructive commands must go through the Windows-safe helper."""
    offenders = []
    for name in (
        "workspace.py",
        "video_pipeline/cleanup_all.py",
        "video_pipeline/cleanup_work.py",
        "video_pipeline/cleanup_videos.py",
        "video_pipeline/cleanup_audio.py",
        "panels/gutter.py",
    ):
        text = (ROOT / "mangaeasy" / name).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if "shutil.rmtree(" in line and "ignore_errors=True" not in line:
                offenders.append(f"{name}:{number}: {line.strip()}")
    assert not offenders, (
        "use mangaeasy.utils.remove_tree() — plain rmtree cannot delete "
        "read-only files on Windows:\n" + "\n".join(offenders)
    )


# ── Launchers ─────────────────────────────────────────────────────────────────

def test_a_launcher_exists_for_every_platform():
    for name in ("run.sh", "run.bat", "run.command"):
        assert (ROOT / name).is_file(), f"missing launcher {name}"


def test_posix_launchers_are_lf_and_executable():
    for name in ("run.sh", "run.command"):
        path = ROOT / name
        assert b"\r\n" not in path.read_bytes(), f"{name} must use LF endings"
        if sys.platform != "win32":
            assert path.stat().st_mode & stat.S_IXUSR, f"{name} is not executable"


def test_gitattributes_pins_windows_and_posix_line_endings():
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rule in ("*.bat text eol=crlf", "*.command text eol=lf", "*.sh text eol=lf"):
        assert rule in text, f"missing .gitattributes rule: {rule}"


def test_launchers_agree_on_the_cli_name():
    from mangaeasy.brand import CLI_NAME

    for name in ("run.sh", "run.bat"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f"uv run {CLI_NAME} --help" in text, f"{name} does not invoke {CLI_NAME}"


# ── Tool installs must not resolve to platform-exclusive wheels ───────────────

def test_index_tts_excludes_the_windows_only_extras():
    """`uv sync --all-extras` must not pull a win_amd64-only package.

    IndexTTS declares `triton-windows` in two extras. `accel` was already
    excluded, but `torch_compile` was not, so --all-extras resolved to a
    package published solely as a win_amd64 wheel and `uv sync` refused to
    install on Linux/macOS — taking voice cloning down on every non-Windows
    machine while appearing to be a generic install failure.
    """
    from mangaeasy.tools.install import TOOLS

    excluded = set(TOOLS["index-tts"].exclude_extras or ())
    for extra in ("accel", "torch_compile"):
        assert extra in excluded, (
            f"index-tts must exclude the '{extra}' extra — it requires "
            f"triton-windows, which has no wheel outside Windows"
        )


def test_upstream_projects_never_take_all_extras_blindly():
    """--all-extras is only safe when the platform-specific extras are named.

    Scoped to `uv_project` tools, where *upstream* owns pyproject.toml and can
    add an OS-specific extra at any ref. `managed_env` tools use a pyproject
    mangaEasy writes itself (_write_managed_pyproject), so their extras cannot
    surprise us.
    """
    from mangaeasy.tools.install import TOOLS

    offenders = [
        key for key, spec in TOOLS.items()
        if spec.kind == "uv_project"
        and "--all-extras" in (spec.sync_args or ())
        and not spec.exclude_extras
    ]
    assert not offenders, (
        f"{offenders} sync an upstream project with --all-extras but exclude "
        f"nothing; an OS-specific extra there breaks the install on other "
        f"platforms (see index-tts / triton-windows)"
    )
