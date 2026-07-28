"""Which audio files a user may point MediaConductor at, and how to feed them
to a model that only wants PCM.

Two settings take a user-supplied audio file: the IndexTTS voice-clone
reference (``tts.speaker_wav``) and the background music bed (``bgm.file``).
Neither has any reason to insist on ``.wav`` — people keep their narrator
samples and their music in whatever their recorder or library produced, and
ffmpeg is already a hard prerequisite, so every mainstream format is readable.

The music path never needed a conversion: it is piped straight through ffmpeg
into a conditioned FLAC. The voice path does, because IndexTTS loads the
prompt through librosa/torchaudio, whose codec support depends on how the
wheels were built on a given machine — an MP3 that loads on one box can raise
on another. :func:`as_pcm_wav` removes that variable by transcoding anything
non-WAV through ffmpeg first, which costs a fraction of a second on a
10-30 s sample.
"""

from __future__ import annotations

from pathlib import Path

# Mainstream container/codec extensions ffmpeg reads. Deliberately generous:
# the cost of accepting one exotic format is a clear ffmpeg error, while the
# cost of rejecting a common one is a user editing their config to satisfy a
# list that had no reason to be short.
SUPPORTED_AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".wav", ".wave",           # PCM
    ".mp3",                    # MPEG-1 Layer III
    ".m4a", ".mp4", ".aac",    # AAC / ALAC in MP4
    ".flac",                   # FLAC
    ".ogg", ".oga", ".opus",   # Vorbis / Opus
    ".wma",                    # Windows Media Audio
    ".aiff", ".aif", ".aifc",  # Apple/SGI PCM
    ".caf",                    # Core Audio
    ".mka", ".webm",           # Matroska / WebM audio
    ".amr", ".ape", ".wv",     # AMR, Monkey's Audio, WavPack
})

# What to print when someone points at a .txt by mistake.
FRIENDLY_FORMAT_LIST = "wav, mp3, m4a, aac, flac, ogg, opus, wma, aiff (and other ffmpeg formats)"


def is_supported_audio(path: Path | str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def describe_unsupported(path: Path | str, *, label: str) -> str:
    """The error message for a file MediaConductor will not try to decode."""
    suffix = Path(path).suffix or "(no extension)"
    return (f"{label} has an unsupported audio format '{suffix}': {path}. "
            f"Supported: {FRIENDLY_FORMAT_LIST}.")


def as_pcm_wav(source: Path, work_dir: Path, *, sample_rate: int = 22050) -> Path:
    """Return *source* itself when it is already a WAV, else a transcoded copy.

    Cached on the source's name, size and mtime, so a repeated run reuses the
    conversion instead of re-decoding the same MP3 for every shard.

    The caller must keep hashing the **original** file for TTS provenance: a
    temporary copy's digest would differ between runs and invalidate every
    take, regenerating hours of audio for no reason.
    """
    from mediaconductor import runtime

    if source.suffix.lower() in {".wav", ".wave"}:
        return source

    stat = source.stat()
    key = f"{source.stem}_{stat.st_size}_{int(stat.st_mtime)}"
    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / f"voice_{key}.wav"
    if target.is_file() and target.stat().st_size > 0:
        return target

    print(f"[voice] converting {source.suffix} reference to WAV for IndexTTS: {source.name}",
          flush=True)
    runtime.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source),
         "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(target)],
        check=True,
    )
    return target
