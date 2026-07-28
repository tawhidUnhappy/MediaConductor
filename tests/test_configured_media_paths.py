"""The two paths a user actually configures: the IndexTTS voice-clone
reference and the background music bed.

Both must accept a Windows absolute path, a Linux absolute path, and a path
relative to the config file, on either host. ``Path.is_absolute()`` answers
only for the host it runs on — on Windows it calls ``/home/me/v.wav``
relative, on Linux it calls ``D:\\vocal\\v.wav`` relative — and either wrong
answer silently rebases a good path under the workspace, then reports the
wrong file as missing.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from mediaconductor.path_safety import (
    UnsafePathComponentError,
    is_portable_absolute,
    resolve_portable_path,
)

WINDOWS_ABSOLUTE = [
    "D:\\vocal\\narrator.wav",
    "D:/vocal/narrator.wav",
    "c:\\Users\\me\\Music\\bed.mp3",
    "\\\\nas\\share\\bed.wav",      # UNC
    "//nas/share/bed.wav",          # UNC, forward slashes
]

POSIX_ABSOLUTE = [
    "/home/me/vocal/narrator.wav",
    "/mnt/media/bgm/bed.flac",
    "/vocal.wav",
]

RELATIVE = [
    "vocal/narrator.wav",
    "vocal\\narrator.wav",
    "./vocal/narrator.wav",
    "media/bgm/bed.wav",
]


@pytest.mark.parametrize("value", WINDOWS_ABSOLUTE + POSIX_ABSOLUTE)
def test_absolute_paths_from_either_os_are_recognised(value: str):
    assert is_portable_absolute(value), f"{value!r} should read as absolute"


@pytest.mark.parametrize("value", RELATIVE)
def test_relative_paths_are_recognised(value: str):
    assert not is_portable_absolute(value), f"{value!r} should read as relative"


@pytest.mark.parametrize("value", RELATIVE)
def test_relative_paths_resolve_against_the_config_file_not_the_cwd(
    value: str, tmp_path: Path, monkeypatch
):
    """An agent runs commands from wherever it happens to be; a configured
    media path must not follow it around."""
    config_dir = tmp_path / "workspace"
    config_dir.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    resolved = resolve_portable_path(value, config_dir)
    assert resolved.is_absolute()
    assert config_dir in resolved.parents


@pytest.mark.parametrize("value", WINDOWS_ABSOLUTE + POSIX_ABSOLUTE)
def test_absolute_paths_are_never_rebased_under_the_config_dir(value: str, tmp_path: Path):
    resolved = resolve_portable_path(value, tmp_path)
    assert tmp_path not in resolved.parents, (
        f"{value!r} was rebased to {resolved} — an absolute path from the other "
        f"OS must stay absolute and simply not exist here"
    )


def test_backslash_and_slash_spellings_agree(tmp_path: Path):
    """One config file has to work on Windows and Linux unchanged."""
    assert (resolve_portable_path("vocal\\narrator.wav", tmp_path)
            == resolve_portable_path("vocal/narrator.wav", tmp_path))
    assert (resolve_portable_path("D:\\vocal\\n.wav", tmp_path)
            == resolve_portable_path("D:/vocal/n.wav", tmp_path))


def test_unc_shares_keep_both_leading_slashes(tmp_path: Path):
    """A NAS-hosted music library is a real case, and one lost slash breaks it."""
    resolved = resolve_portable_path("\\\\nas\\share\\bed.wav", tmp_path)
    text = str(resolved).replace("\\", "/")
    assert text.startswith("//nas/share"), text


def test_home_relative_paths_expand(tmp_path: Path):
    resolved = resolve_portable_path("~/vocal/n.wav", tmp_path)
    assert resolved.is_absolute()
    assert tmp_path not in resolved.parents


@pytest.mark.parametrize("value", ["", "   ", "\x00bad"])
def test_malformed_values_are_rejected(value: str, tmp_path: Path):
    with pytest.raises(UnsafePathComponentError):
        resolve_portable_path(value, tmp_path)


def test_the_host_pathlib_alone_would_get_these_wrong():
    """Pins *why* this module exists, so nobody 'simplifies' it back.

    Each of these is the answer the host's own pathlib gives for a path that
    is genuinely absolute on the other OS.
    """
    assert not PureWindowsPath("/home/me/v.wav").drive      # rootless on Windows
    assert not PurePosixPath("D:\\vocal\\v.wav").is_absolute()
    # ...but the portable check gets both right.
    assert is_portable_absolute("/home/me/v.wav")
    assert is_portable_absolute("D:\\vocal\\v.wav")


# ── End to end through the config loaders ────────────────────────────────────

def _write_system_config(tmp_path: Path, monkeypatch, payload: str) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.system.json").write_text(payload, encoding="utf-8")
    import mediaconductor.defaults as defaults

    monkeypatch.setattr(defaults, "SYSTEM_CONFIG_FILE", workspace / "config.system.json")
    return workspace


def test_configured_speaker_wav_resolves_relative_to_the_config(tmp_path, monkeypatch):
    import mediaconductor.defaults as defaults

    workspace = _write_system_config(
        tmp_path, monkeypatch, '{"tts": {"speaker_wav": "vocal/narrator.wav"}}')
    assert defaults.default_speaker_wav() == workspace / "vocal" / "narrator.wav"


def test_configured_speaker_wav_keeps_an_absolute_path(tmp_path, monkeypatch):
    import mediaconductor.defaults as defaults

    _write_system_config(
        tmp_path, monkeypatch, '{"tts": {"speaker_wav": "D:/voices/narrator.wav"}}')
    resolved = str(defaults.default_speaker_wav()).replace("\\", "/")
    assert resolved.lower() == "d:/voices/narrator.wav"


def test_configured_background_music_resolves_relative_to_the_config(
    tmp_path, monkeypatch
):
    import mediaconductor.defaults as defaults

    workspace = _write_system_config(
        tmp_path, monkeypatch, '{"bgm": {"file": "music/bed.wav"}}')
    (workspace / "music").mkdir()
    (workspace / "music" / "bed.wav").write_bytes(b"RIFF")
    assert defaults.configured_background_music() == workspace / "music" / "bed.wav"


def test_configured_background_music_keeps_an_absolute_path(tmp_path, monkeypatch):
    import mediaconductor.defaults as defaults

    _write_system_config(
        tmp_path, monkeypatch, '{"bgm": {"file": "D:/music/theme.wav"}}')
    resolved = str(defaults.configured_background_music()).replace("\\", "/")
    assert resolved.lower() == "d:/music/theme.wav"


def test_a_missing_configured_track_reports_none_rather_than_a_wrong_file(
    tmp_path, monkeypatch
):
    import mediaconductor.defaults as defaults

    _write_system_config(
        tmp_path, monkeypatch, '{"bgm": {"file": "/mnt/nas/does-not-exist.wav"}}')
    assert defaults.default_background_music() is None


# ── Nothing is guessed ───────────────────────────────────────────────────────
# Folder scanning was removed: picking "the first audio file in bgm/" made the
# bed under a finished video depend on directory ordering, and no fallback
# location may be invented on the user's behalf.

def test_unset_music_is_unset_not_a_guessed_location(tmp_path, monkeypatch):
    import mediaconductor.defaults as defaults

    workspace = _write_system_config(tmp_path, monkeypatch, '{"bgm": {"volume_db": -30}}')
    # A folder that the old fallback would have happily scanned.
    (workspace / "bgm").mkdir()
    (workspace / "bgm" / "whatever.wav").write_bytes(b"RIFF")

    assert defaults.configured_background_music() is None
    assert defaults.default_background_music() is None
    assert defaults.background_music_source()["source"] is None


def test_unset_speaker_wav_is_unset_not_a_guessed_location(tmp_path, monkeypatch):
    import mediaconductor.defaults as defaults

    workspace = _write_system_config(tmp_path, monkeypatch, '{"tts": {"engine": "auto"}}')
    (workspace / "media").mkdir()
    (workspace / "media" / "speaker-reference.wav").write_bytes(b"RIFF")

    assert defaults.default_speaker_wav() is None


def test_the_removed_directory_key_fails_loudly(tmp_path, monkeypatch):
    """Silently ignoring a stale key would leave a video with no bed and no
    explanation — the exact failure the key was removed to prevent."""
    import mediaconductor.defaults as defaults

    _write_system_config(tmp_path, monkeypatch, '{"bgm": {"directory": "bgm"}}')
    with pytest.raises(defaults.ConfiguredMediaError, match="no longer supported"):
        defaults.configured_background_music()
    # doctor still reports rather than crashing.
    assert "no longer supported" in defaults.background_music_source()["problem"]


def test_a_missing_configured_file_names_that_file(tmp_path, monkeypatch):
    import mediaconductor.defaults as defaults

    _write_system_config(
        tmp_path, monkeypatch, '{"bgm": {"file": "D:/music/gone.wav"}}')
    source = defaults.background_music_source()
    assert source["source"].replace("\\", "/").lower() == "d:/music/gone.wav"
    assert source["problem"] == "file not found"
