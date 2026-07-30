"""Bind every generated WAV to the exact contract that produced it.

"Skip files that already exist" is the right default for a step that costs
GPU-hours — and the wrong one the moment anything upstream changes. A narration
line gets rewritten, the speaker reference is swapped, the engine moves from
Kokoro to IndexTTS, the speed changes: the WAV on disk is still *a* file with
the right name, so it is silently reused and the render ships last week's
sentence in last week's voice. That failure is invisible in structural reports;
only content-bound sidecar checks catch it automatically.

Each generated WAV therefore gets a sidecar ``<name>.wav.json`` recording the
normalized narration digest, the beat/panel identity, and the full engine
contract (engine, model, revision, voice, speaker-reference digest, language,
speed, settings). A WAV is reused only when *every* recorded field matches the
contract the current run would use; otherwise it is archived (never deleted —
raw TTS takes are expensive and sometimes better than the regeneration) and
regenerated.

A WAV with no sidecar is treated as current if nothing else can be checked:
projects generated before provenance existed must not be invalidated wholesale,
so the sidecar is written on the next regeneration and enforcement begins from
there. Pass ``require_sidecar=True`` to demand one.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1
SIDECAR_SUFFIX = ".json"


def sidecar_path(wav_path: Path) -> Path:
    """``audio/01/panel.wav`` -> ``audio/01/panel.wav.json``.

    Appending rather than replacing the suffix keeps the sidecar beside its
    WAV under every glob the pipeline already uses for ``*.wav``.
    """
    return Path(str(wav_path) + SIDECAR_SUFFIX)


def normalize_narration(text: str) -> str:
    """Canonical form of a narration line for hashing.

    Unicode-normalized and whitespace-collapsed, so re-indenting the JSON or
    pasting a line back with a non-breaking space does not look like a rewrite
    and trigger hours of pointless regeneration.
    """
    normalized = unicodedata.normalize("NFC", str(text or ""))
    return " ".join(normalized.split())


def narration_digest(text: str) -> str:
    return hashlib.sha256(normalize_narration(text).encode("utf-8")).hexdigest()


def file_digest(path: Path | None) -> str | None:
    """SHA-256 of a reference file (the speaker WAV), or None if absent."""
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TtsContract:
    """Everything about *how* a WAV was synthesized that can change its sound."""

    engine: str                      # "kokoro" | "indextts"
    model: str                       # repo id or checkpoint directory name
    revision: str | None = None      # pinned model revision, when known
    voice: str | None = None         # Kokoro voice name / IndexTTS speaker label
    speaker_wav_sha256: str | None = None
    language: str | None = None
    speed: float | None = None
    settings: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["settings"] = dict(self.settings)
        return data


# The fields that must match for a WAV to be reusable. Listed explicitly so
# adding an informational field to the sidecar later cannot accidentally start
# invalidating every existing take.
_CONTRACT_FIELDS = (
    "engine", "model", "revision", "voice",
    "speaker_wav_sha256", "language", "speed", "settings",
)
_IDENTITY_FIELDS = ("narration_sha256", "beat_id", "image")


def build_record(
    *,
    contract: TtsContract,
    narration: str,
    beat_id: str,
    image: str,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "narration_sha256": narration_digest(narration),
        "narration_preview": normalize_narration(narration)[:160],
        "beat_id": beat_id,
        "image": image,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **contract.as_dict(),
    }


def write_provenance(
    wav_path: Path,
    *,
    contract: TtsContract,
    narration: str,
    beat_id: str,
    image: str,
) -> Path:
    """Atomically write the sidecar for a WAV that was just generated."""
    record = build_record(contract=contract, narration=narration, beat_id=beat_id, image=image)
    path = sidecar_path(wav_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def read_provenance(wav_path: Path) -> dict | None:
    path = sidecar_path(wav_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return None
    return data


def stale_reason(
    wav_path: Path,
    *,
    contract: TtsContract,
    narration: str,
    beat_id: str,
    image: str,
    require_sidecar: bool = False,
) -> str | None:
    """Why this WAV cannot be reused, or ``None`` when it is current."""
    wav_path = Path(wav_path)
    if not wav_path.is_file():
        return "no audio file"
    record = read_provenance(wav_path)
    if record is None:
        if require_sidecar:
            return "no TTS provenance sidecar; regenerate to bind this take to its narration"
        return None
    expected = build_record(contract=contract, narration=narration, beat_id=beat_id, image=image)
    for name in _IDENTITY_FIELDS:
        if record.get(name) != expected[name]:
            label = {
                "narration_sha256": "narration text changed since this take",
                "beat_id": "beat identity changed since this take",
                "image": "panel changed since this take",
            }[name]
            return label
    for name in _CONTRACT_FIELDS:
        if record.get(name) != expected[name]:
            return (
                f"TTS {name.replace('_', ' ')} changed since this take "
                f"({record.get(name)!r} -> {expected[name]!r})"
            )
    return None


def is_current(
    wav_path: Path,
    *,
    contract: TtsContract,
    narration: str,
    beat_id: str,
    image: str,
    require_sidecar: bool = False,
) -> bool:
    return stale_reason(
        wav_path,
        contract=contract,
        narration=narration,
        beat_id=beat_id,
        image=image,
        require_sidecar=require_sidecar,
    ) is None


def archive_stale_take(wav_path: Path, archive_dir: Path, *, subdir: str | None = None) -> None:
    """Move a superseded WAV and its sidecar into the archive run directory.

    Raw TTS is never silently overwritten: a regeneration can come back worse
    (a mispronunciation the previous take got right), and recovering it must
    not mean re-running the whole item.
    """
    from mangaeasy.utils import archive_into_run

    wav_path = Path(wav_path)
    if wav_path.exists():
        archive_into_run(wav_path, archive_dir, subdir=subdir)
    sidecar = sidecar_path(wav_path)
    if sidecar.exists():
        archive_into_run(sidecar, archive_dir, subdir=subdir)
