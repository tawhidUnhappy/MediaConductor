"""Default media paths used by the video and TTS workflows.

The two the user actually sets are the IndexTTS voice-clone reference
(``tts.speaker_wav``) and the background music (``bgm.file`` /
``bgm.directory``) in ``config.system.json``. Both accept a Windows absolute
path, a Linux absolute path, or a path relative to the config file — see
:func:`mediaconductor.path_safety.resolve_portable_path` for why the host's
own ``Path.is_absolute()`` is not good enough.
"""

from __future__ import annotations

import json
from pathlib import Path

from mediaconductor.config import SYSTEM_CONFIG_FILE
from mediaconductor.path_safety import UnsafePathComponentError, resolve_portable_path

DEFAULT_BACKGROUND_MUSIC = Path("media/background-music.wav")
DEFAULT_BACKGROUND_MUSIC_DIR = Path("bgm")
DEFAULT_SPEAKER_WAV = Path("media/speaker-reference.wav")
# -30 keeps the bed comfortably in the background for long-form recap
# watching (previously -26, then -28, both still read as too present over a
# full video per viewer feedback). -26 to -22 suits punchier or sparser edits
# that want the bed to read more.
DEFAULT_MUSIC_VOLUME_DB = -30.0
DEFAULT_NARRATION_VOLUME = 1.2
DEFAULT_TTS_ENGINE = "auto"
DEFAULT_MANGA_VIDEO_AUDIO_SOURCE = "faded"
DEFAULT_MANGA_VIDEO_AUDIO_FADE_MS = 8.0
_MUSIC_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def _system_config() -> dict:
    if not SYSTEM_CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(SYSTEM_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def config_dir() -> Path:
    """The directory configured relative paths resolve against.

    The config file's own folder, deliberately — not the cwd. Agents run
    commands from wherever they happen to be, and ``"vocal/narrator.wav"``
    has to mean the same file every time.
    """
    return SYSTEM_CONFIG_FILE.parent


def project_path(value: str | Path) -> Path:
    """Resolve a configured media path (Windows-absolute, POSIX-absolute, or
    relative to the config file)."""
    try:
        return resolve_portable_path(str(value), config_dir())
    except UnsafePathComponentError:
        # A malformed value must not take the whole command down; the caller
        # reports "configured file not found" against a path that cannot exist.
        return config_dir() / "__invalid_configured_path__"


def _pick_music_file(path: Path) -> Path | None:
    if path.is_file():
        return path
    if path.is_dir():
        for candidate in sorted(path.iterdir()):
            if candidate.is_file() and candidate.suffix.lower() in _MUSIC_EXTS:
                return candidate
    return None


def default_speaker_wav() -> Path:
    cfg = _system_config().get("tts", {})
    return project_path(cfg.get("speaker_wav") or DEFAULT_SPEAKER_WAV)


def default_tts_engine() -> str:
    cfg = _system_config().get("tts", {})
    value = str(cfg.get("engine", DEFAULT_TTS_ENGINE)).strip().lower()
    return value if value in {"auto", "indextts", "kokoro"} else DEFAULT_TTS_ENGINE


def default_music_volume_db() -> float:
    cfg = _system_config().get("bgm", {})
    try:
        return float(cfg.get("volume_db", DEFAULT_MUSIC_VOLUME_DB))
    except (TypeError, ValueError):
        return DEFAULT_MUSIC_VOLUME_DB


def default_manga_video_audio_source() -> str:
    """Return the safe manga-video audio derivative from system config."""
    cfg = _system_config().get("manga_video", {})
    value = str(cfg.get("audio_source", DEFAULT_MANGA_VIDEO_AUDIO_SOURCE)).strip().lower()
    return value if value in {"raw", "faded"} else DEFAULT_MANGA_VIDEO_AUDIO_SOURCE


def default_manga_video_audio_fade_ms() -> float:
    cfg = _system_config().get("manga_video", {})
    try:
        value = float(cfg.get("audio_fade_ms", DEFAULT_MANGA_VIDEO_AUDIO_FADE_MS))
    except (TypeError, ValueError):
        return DEFAULT_MANGA_VIDEO_AUDIO_FADE_MS
    return value if value > 0 else DEFAULT_MANGA_VIDEO_AUDIO_FADE_MS


def configured_background_music() -> Path:
    cfg = _system_config().get("bgm", {})
    explicit = cfg.get("file") or cfg.get("path")
    directory = cfg.get("directory") or cfg.get("dir")

    if explicit:
        chosen = _pick_music_file(project_path(explicit))
        if chosen is not None:
            return chosen

    if directory:
        chosen = _pick_music_file(project_path(directory))
        if chosen is not None:
            return chosen

    # Fall back to the conventional folders — resolved against the config
    # file too, so a command run from another directory finds the same bed.
    for fallback in (DEFAULT_BACKGROUND_MUSIC, DEFAULT_BACKGROUND_MUSIC_DIR):
        chosen = _pick_music_file(project_path(fallback))
        if chosen is not None:
            return chosen

    return project_path(cfg.get("file") or DEFAULT_BACKGROUND_MUSIC)


def default_background_music() -> Path | None:
    path = configured_background_music()
    return path if path.is_file() else None


def background_music_source() -> dict:
    """What the user configured, and what it resolved to — reported separately.

    ``configured_background_music()`` falls through to the conventional
    folders when the configured one yields nothing, which makes it a bad
    thing to show a user: they set ``bgm.directory: "bgm"``, the folder is
    empty, and the report names ``media/background-music.wav`` — a path they
    never wrote, so the real problem (an empty folder) stays hidden.
    """
    cfg = _system_config().get("bgm", {})
    explicit = cfg.get("file") or cfg.get("path")
    directory = cfg.get("directory") or cfg.get("dir")

    if explicit:
        source, kind = project_path(explicit), "file"
    elif directory:
        source, kind = project_path(directory), "directory"
    else:
        source, kind = project_path(DEFAULT_BACKGROUND_MUSIC_DIR), "default directory"

    track = _pick_music_file(source)
    if track is None and (explicit or directory):
        # Configured but unusable: say so about the configured path itself.
        return {"kind": kind, "source": str(source), "track": None,
                "problem": ("file not found" if kind == "file"
                            else f"no audio file in {source.name}/"
                                 if source.is_dir() else "folder not found")}
    if track is None:
        track = default_background_music()
    return {"kind": kind, "source": str(source),
            "track": str(track) if track else None,
            "problem": None if track else "no music configured"}
