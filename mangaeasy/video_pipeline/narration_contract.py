"""The one narration schema every consumer validates against.

``narration.json`` and ``intro.json`` describe what the narrator says over
which panel.  Historically each consumer re-derived its own idea of a valid
entry: the renderer only needed ``image``/``narration``, the audio step keyed
WAV filenames off the image *stem*, and ``narration-check`` did its own
structural pass.  Anything the writer put in the file that no consumer
happened to read was silently accepted, and an ``image`` value was joined onto
``panels/`` without ever asking whether the result was still inside
``panels/``.

This module is the single validator.  It is deliberately strict:

* ``image`` is a **basename**, never a path.  Absolute paths, drive-qualified
  paths (``C:\\...``), UNC paths (``\\\\server\\share``), any ``/`` or ``\\``
  separator, and ``..`` are all rejected — and the joined path is additionally
  resolved and required to be a *direct child* of ``panels/``, so a symlink or
  a platform quirk cannot smuggle a file in from outside the item.
* Filenames must be unique case-insensitively, and so must their **stems**,
  because generated audio is ``<stem>.wav``: two panels whose names differ only
  in case or extension would silently share one WAV.
* Unknown properties are rejected.  A typo (``naration``) or a field invented
  by one tool and read by none is a bug, not data.

The optional editorial fields (``beat_id``, ``evidence``,
``pause_after_ms``) are what the video renderer and the reveal ledger
consume; see :mod:`mangaeasy.video_pipeline.edit_timeline`.

``beat_id`` is stable and unique by construction.  Supplying one explicitly is
encouraged (it survives re-cropping and lets a reveal ledger cite a beat), but
omitting it is not an error: the contract derives ``<item>-<stem>`` instead,
which is equally stable and unique for a valid file.  Explicit ids are checked
for format and uniqueness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mangaeasy.video_pipeline.common import IMAGE_EXTENSIONS

# Narration entries name panel images; the renderer only knows these formats.
SUPPORTED_IMAGE_EXTENSIONS = frozenset(IMAGE_EXTENSIONS)

ALLOWED_ENTRY_FIELDS = frozenset({
    "beat_id", "image", "narration", "evidence", "pause_after_ms",
})
REQUIRED_ENTRY_FIELDS = ("image", "narration")

# Bounds keep a typo from producing an unwatchable render.
FOCUS_MIN = 0.0
FOCUS_MAX = 1.0
PAUSE_AFTER_MS_MIN = 0
PAUSE_AFTER_MS_MAX = 5000

_BEAT_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")

# Windows reserves these device names regardless of extension.
_RESERVED_STEMS = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
})

# Renamed rather than removed: an old file saying "text" is a real narration
# script, and the fix is one rename, so say so instead of "unknown property".
_RENAMED_FIELDS = {"text": "narration"}


class NarrationContractError(ValueError):
    """A narration entry violates the schema every consumer relies on."""


def _fail(where: str, detail: str) -> None:
    raise NarrationContractError(f"{where}: {detail}")


def validate_image_name(value: Any, where: str) -> str:
    """Return *value* as a safe panel basename, or raise.

    String-level rejection first (it produces the actionable message), then the
    caller resolves the joined path — string checks alone cannot see a symlink.
    """
    if not isinstance(value, str) or not value.strip():
        _fail(where, "'image' must be a non-empty string")
    if value != value.strip():
        _fail(where, f"'image' has leading/trailing whitespace: {value!r}")
    if "\x00" in value:
        _fail(where, "'image' contains a NUL byte")
    if value.startswith("\\\\") or value.startswith("//"):
        _fail(where, f"'image' must be a panel filename, not a UNC path: {value!r}")
    if re.match(r"\A[A-Za-z]:", value):
        _fail(where, f"'image' must be a panel filename, not a drive path: {value!r}")
    if value.startswith("/") or value.startswith("\\"):
        _fail(where, f"'image' must be a panel filename, not an absolute path: {value!r}")
    if "/" in value or "\\" in value:
        _fail(
            where,
            f"'image' must be a bare filename directly inside panels/, not a path: {value!r}",
        )
    if value in {".", ".."} or ".." in value.split("."):
        _fail(where, f"'image' must not contain traversal segments: {value!r}")
    if Path(value).name != value:
        _fail(where, f"'image' must be a bare filename: {value!r}")
    suffix = Path(value).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        _fail(where, f"'image' has unsupported extension {suffix or '(none)'}; use one of: {supported}")
    stem = Path(value).stem
    if not stem:
        _fail(where, f"'image' has no filename stem: {value!r}")
    if stem.casefold() in _RESERVED_STEMS:
        _fail(where, f"'image' uses a reserved device name: {value!r}")
    if value.endswith((".", " ")):
        _fail(where, f"'image' must not end with a dot or space: {value!r}")
    return value


def resolve_panel_path(image: str, panels_dir: Path, where: str) -> Path:
    """Resolve *image* under *panels_dir*, requiring a direct child.

    ``resolve()`` follows symlinks and normalizes the platform's own quirks,
    so this catches what the string checks structurally cannot.
    """
    root = Path(panels_dir).resolve(strict=False)
    candidate = (root / image).resolve(strict=False)
    if candidate.parent != root:
        _fail(where, f"'image' {image!r} does not resolve to a direct child of {root}")
    return candidate


def _validate_pause(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(where, "'pause_after_ms' must be an integer number of milliseconds")
    if not PAUSE_AFTER_MS_MIN <= value <= PAUSE_AFTER_MS_MAX:
        _fail(
            where,
            f"'pause_after_ms' must be between {PAUSE_AFTER_MS_MIN} and {PAUSE_AFTER_MS_MAX}",
        )
    return value


def _validate_evidence(value: Any, where: str) -> list[str]:
    if not isinstance(value, list):
        _fail(where, "'evidence' must be an array of panel filenames")
    if not value:
        _fail(where, "'evidence' must not be empty when present")
    evidence: list[str] = []
    for index, name in enumerate(value):
        evidence.append(validate_image_name(name, f"{where}.evidence[{index}]"))
    return evidence


def validate_entries(
    entries: Any,
    *,
    label: str,
    panels_dir: Path,
    item_name: str = "",
    require_files: bool = True,
    seen_images: dict[str, str] | None = None,
    seen_stems: dict[str, str] | None = None,
    seen_beats: dict[str, str] | None = None,
) -> list[dict]:
    """Validate one narration file's entries and return normalized copies."""
    if not isinstance(entries, list):
        raise NarrationContractError(f"{label}: must be a JSON array")
    seen_images = {} if seen_images is None else seen_images
    seen_stems = {} if seen_stems is None else seen_stems
    seen_beats = {} if seen_beats is None else seen_beats

    validated: list[dict] = []
    for index, entry in enumerate(entries):
        where = f"{label}[{index}]"
        if not isinstance(entry, dict):
            _fail(where, "entry must be a JSON object")

        renamed = sorted(set(entry) & set(_RENAMED_FIELDS))
        if renamed:
            pairs = ", ".join(f"'{old}' -> '{_RENAMED_FIELDS[old]}'" for old in renamed)
            _fail(where, f"rename legacy field(s): {pairs}")
        unknown = sorted(set(entry) - ALLOWED_ENTRY_FIELDS)
        if unknown:
            allowed = ", ".join(sorted(ALLOWED_ENTRY_FIELDS))
            _fail(where, f"unknown propert(ies): {', '.join(unknown)}; allowed: {allowed}")
        missing = [name for name in REQUIRED_ENTRY_FIELDS if name not in entry]
        if missing:
            _fail(where, f"missing required propert(ies): {', '.join(missing)}")

        image = validate_image_name(entry["image"], where)
        panel_path = resolve_panel_path(image, panels_dir, where)
        if require_files and not panel_path.is_file():
            _fail(where, f"panel image not found: {panel_path}")

        narration = entry["narration"]
        if not isinstance(narration, str) or not narration.strip():
            _fail(where, f"'narration' must be non-empty text (image {image!r})")

        image_key = image.casefold()
        if image_key in seen_images:
            _fail(where, f"duplicate image {image!r} (already used by {seen_images[image_key]})")
        stem_key = Path(image).stem.casefold()
        if stem_key in seen_stems:
            _fail(
                where,
                f"image stem {Path(image).stem!r} collides with {seen_stems[stem_key]!r}; "
                "narration audio is written as <stem>.wav, so both beats would share one file",
            )

        normalized: dict = {"image": image, "narration": narration}

        beat_id = entry.get("beat_id")
        if beat_id is None:
            prefix = f"{item_name}-" if item_name else ""
            beat_id = f"{prefix}{Path(image).stem}"
        else:
            if not isinstance(beat_id, str) or not _BEAT_ID_RE.fullmatch(beat_id):
                _fail(
                    where,
                    "'beat_id' must be 1-80 chars of letters/digits/._- starting alphanumeric",
                )
        if beat_id in seen_beats:
            _fail(where, f"duplicate beat_id {beat_id!r} (already used by {seen_beats[beat_id]})")
        normalized["beat_id"] = beat_id

        if entry.get("evidence") is not None:
            evidence = _validate_evidence(entry["evidence"], where)
            if require_files:
                for name in evidence:
                    path = resolve_panel_path(name, panels_dir, f"{where}.evidence")
                    if not path.is_file():
                        _fail(where, f"evidence panel not found: {path}")
            normalized["evidence"] = evidence
        if entry.get("pause_after_ms") is not None:
            normalized["pause_after_ms"] = _validate_pause(entry["pause_after_ms"], where)

        seen_images[image_key] = f"{label}[{index}]"
        seen_stems[stem_key] = image
        seen_beats[beat_id] = f"{label}[{index}]"
        validated.append(normalized)
    return validated


def _read_json_array(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise NarrationContractError(f"{path}: could not be read ({exc})") from exc
    except ValueError as exc:
        raise NarrationContractError(f"{path}: invalid JSON ({exc})") from exc


def validate_item_narration(
    item_dir: Path,
    *,
    require_files: bool = True,
    panels_subdir: str = "panels",
) -> list[dict]:
    """Validate ``intro.json`` + ``narration.json`` for one item, in playback order.

    Returns the combined, normalized entry list — the exact sequence the
    renderer and the TTS step will consume.
    """
    item_dir = Path(item_dir)
    panels_dir = item_dir / panels_subdir
    narration_path = item_dir / "narration.json"
    if not narration_path.is_file():
        raise NarrationContractError(f"{narration_path}: narration.json is missing")

    seen_images: dict[str, str] = {}
    seen_stems: dict[str, str] = {}
    seen_beats: dict[str, str] = {}

    combined: list[dict] = []
    intro_path = item_dir / "intro.json"
    if intro_path.is_file():
        combined.extend(validate_entries(
            _read_json_array(intro_path),
            label="intro.json",
            panels_dir=panels_dir,
            item_name=item_dir.name,
            require_files=require_files,
            seen_images=seen_images,
            seen_stems=seen_stems,
            seen_beats=seen_beats,
        ))
    combined.extend(validate_entries(
        _read_json_array(narration_path),
        label="narration.json",
        panels_dir=panels_dir,
        item_name=item_dir.name,
        require_files=require_files,
        seen_images=seen_images,
        seen_stems=seen_stems,
        seen_beats=seen_beats,
    ))
    return combined


def narration_problems(item_dir: Path, *, require_files: bool = True) -> list[str]:
    """Contract violations for one item as a list, for report-style callers.

    ``narration-check`` and ``work-qa`` want every problem they can show at
    once; raising on the first one would make an agent fix a 40-entry file one
    error per run. Validation still stops at the first failure *per file*, so
    this reports at most one violation from each of intro/narration.
    """
    problems: list[str] = []
    item_dir = Path(item_dir)
    panels_dir = item_dir / "panels"
    seen_images: dict[str, str] = {}
    seen_stems: dict[str, str] = {}
    seen_beats: dict[str, str] = {}
    for name in ("intro.json", "narration.json"):
        path = item_dir / name
        if not path.is_file():
            if name == "narration.json":
                problems.append("narration.json missing")
            continue
        try:
            validate_entries(
                _read_json_array(path),
                label=name,
                panels_dir=panels_dir,
                item_name=item_dir.name,
                require_files=require_files,
                seen_images=seen_images,
                seen_stems=seen_stems,
                seen_beats=seen_beats,
            )
        except NarrationContractError as exc:
            problems.append(str(exc))
    return problems
