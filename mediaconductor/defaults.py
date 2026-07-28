"""Default media paths used by the video and TTS workflows.

The two the user sets are the IndexTTS voice-clone reference
(``tts.speaker_wav``) and the background music (``bgm.file``) in
``config.system.json``. **Each is one exact file, named by the user.** They
accept a Windows absolute path, a Linux absolute path, or a path relative to
the config file — see
:func:`mediaconductor.path_safety.resolve_portable_path` for why the host's
own ``Path.is_absolute()`` is not good enough.

Nothing is guessed. There is no folder scanning and no conventional-location
fallback: an earlier version picked "the first audio file in ``bgm/``" and
fell back to ``media/background-music.wav``, which meant the bed under a
finished video depended on directory ordering, and a report naming that
fallback pointed at a path the user had never written. Unset means unset —
the render simply has no music, and says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from mediaconductor.config import SYSTEM_CONFIG_FILE
from mediaconductor.path_safety import UnsafePathComponentError, resolve_portable_path

# -30 keeps the bed comfortably in the background for long-form recap
# watching (previously -26, then -28, both still read as too present over a
# full video per viewer feedback). -26 to -22 suits punchier or sparser edits
# that want the bed to read more.
DEFAULT_MUSIC_VOLUME_DB = -30.0
DEFAULT_NARRATION_VOLUME = 1.2
DEFAULT_TTS_ENGINE = "auto"
DEFAULT_MANGA_VIDEO_AUDIO_SOURCE = "faded"
DEFAULT_MANGA_VIDEO_AUDIO_FADE_MS = 8.0


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


class ConfiguredMediaError(ValueError):
    """A config media key is set to something unusable (e.g. a removed key)."""


def default_speaker_wav() -> Path | None:
    """The configured voice-clone reference, or None when unset.

    None means "no voice configured", not "look somewhere sensible" — an
    implicit ``media/speaker-reference.wav`` fallback only ever produced a
    confusing "not found" for a path the user never chose.
    """
    value = _system_config().get("tts", {}).get("speaker_wav")
    return project_path(value) if str(value or "").strip() else None


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


def configured_background_music() -> Path | None:
    """The configured music track, or None when unset.

    One exact file the user named. ``bgm.directory`` is deliberately gone:
    picking "the first audio file in a folder" made the bed under a finished
    video depend on directory ordering, and nothing in the render reported
    which track had won.
    """
    cfg = _system_config().get("bgm", {})
    if cfg.get("directory") or cfg.get("dir"):
        raise ConfiguredMediaError(
            "config.system.json -> bgm.directory is no longer supported: a folder "
            "scan makes the music bed depend on directory ordering. Set bgm.file "
            "to the exact track instead (any absolute path on this machine, or a "
            "path relative to config.system.json)."
        )
    value = cfg.get("file") or cfg.get("path")
    return project_path(value) if str(value or "").strip() else None


def default_background_music() -> Path | None:
    """The configured track, but only when it actually exists on disk."""
    path = configured_background_music()
    return path if path is not None and path.is_file() else None


def background_music_source() -> dict:
    """What is configured and whether it is usable, for reporting.

    Kept separate from :func:`configured_background_music` so ``doctor`` can
    say *why* there is no bed without raising on a stale key.
    """
    try:
        path = configured_background_music()
    except ConfiguredMediaError as exc:
        return {"source": None, "track": None, "problem": str(exc)}
    if path is None:
        return {"source": None, "track": None,
                "problem": "not set — add bgm.file, or pass --background-music per run"}
    if not path.is_file():
        return {"source": str(path), "track": None, "problem": "file not found"}
    from mediaconductor.audio.formats import describe_unsupported, is_supported_audio

    if not is_supported_audio(path):
        return {"source": str(path), "track": None,
                "problem": describe_unsupported(path, label="music bed")}
    return {"source": str(path), "track": str(path), "problem": None}
