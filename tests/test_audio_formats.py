"""A user's narrator sample and music live in whatever format their recorder
or library produced. Both settings take any mainstream audio file.

The music path always could — it is piped through ffmpeg into a conditioned
FLAC. The voice path could not be trusted to: IndexTTS loads the prompt via
librosa/torchaudio, whose codec support depends on how those wheels were
built, so an MP3 that decodes on one machine can raise on another.
``as_pcm_wav`` removes that variable.
"""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import pytest

from mangaeasy.audio.formats import (
    SUPPORTED_AUDIO_EXTENSIONS,
    as_pcm_wav,
    describe_unsupported,
    is_supported_audio,
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.mark.parametrize("name", [
    "narrator.wav", "narrator.mp3", "narrator.m4a", "narrator.aac",
    "narrator.flac", "narrator.ogg", "narrator.opus", "narrator.wma",
    "narrator.aiff", "narrator.aif", "theme.mp4", "theme.webm", "theme.caf",
])
def test_mainstream_formats_are_accepted(name: str):
    assert is_supported_audio(name)


@pytest.mark.parametrize("name", ["NARRATOR.MP3", "Theme.FLAC", "bed.Opus"])
def test_extension_matching_is_case_insensitive(name: str):
    """Windows hands back whatever case the filesystem stored."""
    assert is_supported_audio(name)


@pytest.mark.parametrize("name", ["notes.txt", "cover.png", "voice", "clip.mkv2"])
def test_non_audio_is_rejected(name: str):
    assert not is_supported_audio(name)


def test_the_rejection_message_names_the_format_and_the_alternatives():
    message = describe_unsupported("D:/voices/notes.txt", label="Speaker reference")
    assert "Speaker reference" in message
    assert "'.txt'" in message
    assert "mp3" in message and "flac" in message


def test_a_file_with_no_extension_is_reported_readably():
    assert "(no extension)" in describe_unsupported("D:/voices/narrator", label="Voice")


def test_wav_is_the_canonical_form_and_never_copied(tmp_path: Path):
    """Converting a WAV would burn a transcode per run for nothing."""
    source = tmp_path / "narrator.wav"
    source.write_bytes(b"RIFF")
    assert as_pcm_wav(source, tmp_path / "cache") == source
    assert not (tmp_path / "cache").exists()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is required to transcode")
def test_a_non_wav_reference_is_transcoded_to_mono_pcm(tmp_path: Path):
    from mangaeasy import runtime

    source = tmp_path / "narrator.mp3"
    runtime.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "sine=frequency=440:duration=1", str(source)], check=True)

    converted = as_pcm_wav(source, tmp_path / "cache")
    assert converted != source and converted.suffix == ".wav"
    with wave.open(str(converted)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 22050
        assert handle.getnframes() > 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is required to transcode")
def test_the_conversion_is_cached_across_runs(tmp_path: Path):
    """Re-decoding the same MP3 for every audio shard would be pure waste."""
    from mangaeasy import runtime

    source = tmp_path / "narrator.mp3"
    runtime.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "sine=frequency=440:duration=1", str(source)], check=True)

    cache = tmp_path / "cache"
    first = as_pcm_wav(source, cache)
    stamp = first.stat().st_mtime_ns
    second = as_pcm_wav(source, cache)
    assert second == first
    assert second.stat().st_mtime_ns == stamp, "the cached conversion was rewritten"


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg is required to transcode")
def test_replacing_the_reference_invalidates_the_cached_conversion(tmp_path: Path):
    """Swapping the narrator's sample must not keep serving the old voice."""
    from mangaeasy import runtime

    source = tmp_path / "narrator.mp3"
    cache = tmp_path / "cache"
    runtime.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "sine=frequency=440:duration=1", str(source)], check=True)
    first = as_pcm_wav(source, cache)

    runtime.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                 "-i", "sine=frequency=880:duration=3", str(source)], check=True)
    second = as_pcm_wav(source, cache)
    assert second != first, "a different reference reused the previous conversion"


def test_wav_variants_are_all_treated_as_pcm(tmp_path: Path):
    for name in ("a.wav", "b.WAV", "c.wave"):
        source = tmp_path / name
        source.write_bytes(b"RIFF")
        assert as_pcm_wav(source, tmp_path / "cache") == source


def test_the_supported_set_stays_lowercase_and_dotted():
    """Matching is done on `Path.suffix.lower()`, so an entry missing its dot
    or carrying a capital would silently never match."""
    for extension in SUPPORTED_AUDIO_EXTENSIONS:
        assert extension.startswith(".") and extension == extension.lower()
