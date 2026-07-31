"""The manga rights manifest: who owns the source, and on what basis it is used.

A recap channel republishes someone else's artwork. That can be lawful — a
license, an explicit permission, a public-domain edition, or genuine
commentary — and it can equally be a straightforward copyright violation. The
difference is a set of facts about the source, and those facts are knowable
*before* an upload, not after a strike.

This module makes them explicit and **fails closed**: with no
``rights.json``, or with an unknown permission basis, publication is refused.
Two beliefs are specifically not accepted as permission, because both are
common and both are wrong:

* that a page being reachable on a webtoon site implies a licence to reuse it;
* that crediting the author, or adding a "no copyright intended" disclaimer,
  substitutes for permission.

Records live at ``<project>/rights.json``.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from mangaeasy.brand import CLI_NAME

SCHEMA_VERSION = 1
RIGHTS_FILENAME = "rights.json"

# What actually authorizes the use. "accessible_online" is deliberately absent.
PERMISSION_BASES: tuple[str, ...] = (
    "license",              # a licence covering this use, identified in detail
    "explicit_permission",  # rights holder said yes, in writing, recorded below
    "public_domain",        # the edition itself is public domain
    "commentary",           # criticism/commentary/analysis under a fair-use style exception
)
# Bases that only hold up when the video adds genuine commentary and uses no
# more of the work than that commentary needs.
COMMENTARY_BASES = frozenset({"commentary"})

VOICE_CONSENT_BASES: tuple[str, ...] = (
    "synthetic_licensed",   # TTS voice used within its licence terms
    "own_voice",            # the operator's own recorded voice
    "speaker_consent",      # a named human consented, recorded below
)

SAFETY_SCANS: tuple[str, ...] = (
    "nudity",
    "sexualized_minors",
    "graphic_gore",
    "misleading_thumbnail",
)


class RightsError(ValueError):
    """The rights manifest is missing, incomplete, or does not authorize this use."""


def rights_path(project_root: Path) -> Path:
    return Path(project_root).expanduser().resolve() / RIGHTS_FILENAME


def _template() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "url": "",
            "title": "",
            "edition": "",
            "language": "",
            "creator": "",
            "publisher": "",
        },
        "permission": {
            "basis": "",
            "detail": "",
            "granted_by": "",
            "evidence": "",
            "allowed_chapters": [],
        },
        "attribution": "",
        "translation": {
            "provenance": "",
            "scanlator": "",
        },
        "voice_consent": {
            "basis": "",
            "detail": "",
            "speaker": "",
        },
        "music": [],
        "thumbnail_sources": [],
        "commentary": {
            "adds": "",
            "source_to_script_originality": "",
            "edit_decision_list": "",
        },
        "safety_scans": {name: {"scanned_by": "", "scanned_at": "", "clear": None}
                         for name in SAFETY_SCANS},
    }


# ── Operator-level seeding ────────────────────────────────────────────────
#
# Some facts in this manifest are about the *operator*, not about the manga:
# whose voice narrates, what the channel adds editorially, who runs the safety
# scans. Those are identical for every project, so re-eliciting them per series
# is pure repetition — an interrogation that carries no new information and
# trains everyone to answer without reading.
#
# These fields may therefore be seeded from ``config.system.json`` →
# ``rights_defaults``. Everything absent from this list stays blank on purpose,
# because it genuinely differs per work and a wrong inherited value would be
# worse than an empty one.
OPERATOR_SEEDABLE: tuple[tuple[str, ...], ...] = (
    ("attribution",),
    ("permission", "basis"),
    ("permission", "detail"),
    ("permission", "granted_by"),
    ("permission", "evidence"),
    ("voice_consent", "basis"),
    ("voice_consent", "detail"),
    ("voice_consent", "speaker"),
    ("commentary", "adds"),
    ("commentary", "source_to_script_originality"),
)

# Never seeded, and why. Kept as data so `init` can tell an agent exactly what
# is still outstanding instead of the agent asking the operator to recite it.
PER_WORK_FIELDS: tuple[tuple[str, str], ...] = (
    ("source.url", "which series this is"),
    ("source.title", "which series this is"),
    ("source.creator", "who made this one"),
    ("source.publisher", "who published this one"),
    ("source.language", "which edition/translation"),
    ("permission.allowed_chapters", "which chapters this basis actually covers"),
    ("translation.provenance", "whose translation these pages are"),
    ("commentary.edit_decision_list", "what this particular recap cut"),
    ("safety_scans.*.clear", "the scan result for these pages"),
)


def _operator_defaults() -> dict:
    """``rights_defaults`` from config.system.json, or {} when unset."""
    from mangaeasy.config import load_system_config

    block = load_system_config().get("rights_defaults")
    return block if isinstance(block, dict) else {}


def _dig(data: dict, path: Sequence[str]):
    node = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def seed_template(template: dict, defaults: dict) -> list[str]:
    """Fill operator-level fields from ``defaults``. Returns what was seeded.

    Only paths in :data:`OPERATOR_SEEDABLE` are copied, and only when the
    default is a non-empty string — so a half-written config can never quietly
    blank a field that the validator would otherwise have caught.
    """
    seeded: list[str] = []
    for path in OPERATOR_SEEDABLE:
        value = _dig(defaults, path)
        if not isinstance(value, str) or not value.strip():
            continue
        node = template
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value.strip()
        seeded.append(".".join(path))

    scanned_by = _dig(defaults, ("safety_scans", "scanned_by"))
    if isinstance(scanned_by, str) and scanned_by.strip():
        for name in SAFETY_SCANS:
            # Only the scanner's identity carries over. `clear` stays None: the
            # result is a fact about *these* pages and must be established here.
            template["safety_scans"][name]["scanned_by"] = scanned_by.strip()
        seeded.append("safety_scans.*.scanned_by")
    return seeded


def load_rights(project_root: Path) -> dict:
    path = rights_path(project_root)
    if not path.is_file():
        raise RightsError(
            f"no rights manifest at {path}. Source ownership and permission are unknown, so "
            f"publication is refused. Create one with `{CLI_NAME} manga-rights init "
            f"--project-root {project_root}` and fill in every field."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RightsError(f"could not read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise RightsError(
            f"unsupported rights manifest schema at {path}; expected schema_version {SCHEMA_VERSION}"
        )
    return data


def write_rights(project_root: Path, data: dict) -> Path:
    path = rights_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _text(container: object, key: str) -> str:
    if not isinstance(container, dict):
        return ""
    value = container.get(key)
    return value.strip() if isinstance(value, str) else ""


def check_rights(project_root: Path) -> dict:
    """Report whether the manifest authorizes publication. Fails closed."""
    problems: list[str] = []
    warnings: list[str] = []
    try:
        data = load_rights(project_root)
    except RightsError as exc:
        return {
            "ok": False,
            "project_root": str(Path(project_root).expanduser().resolve()),
            "rights_file": str(rights_path(project_root)),
            "problems": [str(exc)],
            "warnings": [],
        }

    source = data.get("source")
    for field in ("url", "title", "language", "creator"):
        if not _text(source, field):
            problems.append(f"source.{field} is unknown; record where the pages came from")
    for field in ("edition", "publisher"):
        if not _text(source, field):
            warnings.append(f"source.{field} is empty; record it when it is known")

    permission = data.get("permission")
    basis = _text(permission, "basis")
    if not basis:
        problems.append(
            "permission.basis is unknown. A page being reachable online is not permission, "
            "and neither is attribution or a disclaimer. Choose one of: "
            + ", ".join(PERMISSION_BASES)
        )
    elif basis not in PERMISSION_BASES:
        problems.append(
            f"permission.basis {basis!r} is not a recognized basis; choose one of: "
            + ", ".join(PERMISSION_BASES)
        )
    else:
        if not _text(permission, "detail"):
            problems.append("permission.detail must identify the licence, grant, or exception relied on")
        if basis == "explicit_permission" and not _text(permission, "granted_by"):
            problems.append("permission.granted_by must name who granted permission")
        if basis in {"license", "explicit_permission"} and not _text(permission, "evidence"):
            problems.append("permission.evidence must point at the licence text or the written grant")
        allowed = permission.get("allowed_chapters") if isinstance(permission, dict) else None
        if not isinstance(allowed, list) or not allowed:
            problems.append(
                "permission.allowed_chapters must list the chapters this basis actually covers"
            )

    if not _text(data, "attribution"):
        problems.append("attribution is empty; credit the creator even when a licence applies")
    elif basis and basis not in PERMISSION_BASES:
        warnings.append("attribution is recorded, but attribution alone is never permission")

    translation = data.get("translation")
    if not _text(translation, "provenance"):
        problems.append(
            "translation.provenance is unknown; a scanlation carries its own rights and must be "
            "identified (or the source declared as an official translation)"
        )

    voice = data.get("voice_consent")
    voice_basis = _text(voice, "basis")
    if not voice_basis:
        problems.append(
            "voice_consent.basis is unknown; choose one of: " + ", ".join(VOICE_CONSENT_BASES)
        )
    elif voice_basis not in VOICE_CONSENT_BASES:
        problems.append(
            f"voice_consent.basis {voice_basis!r} is not recognized; choose one of: "
            + ", ".join(VOICE_CONSENT_BASES)
        )
    elif voice_basis == "speaker_consent" and not _text(voice, "speaker"):
        problems.append("voice_consent.speaker must name the consenting speaker")

    music = data.get("music")
    if not isinstance(music, list):
        problems.append("music must be an array of {path, license, source} objects")
    else:
        for index, track in enumerate(music):
            if not _text(track, "path") or not _text(track, "license"):
                problems.append(f"music[{index}] must record both a path and a license")

    thumbnails = data.get("thumbnail_sources")
    if not isinstance(thumbnails, list) or not thumbnails:
        problems.append("thumbnail_sources must list the source panels the thumbnail is built from")

    commentary = data.get("commentary")
    if not _text(commentary, "adds"):
        problems.append(
            "commentary.adds must state the criticism, explanation, analysis, or interpretation "
            "this video contributes beyond replaying the pages"
        )
    if not _text(commentary, "source_to_script_originality"):
        problems.append(
            "commentary.source_to_script_originality must record how the script differs from the "
            "source dialogue (narration must not be copied bubble text)"
        )
    if basis in COMMENTARY_BASES and not _text(commentary, "edit_decision_list"):
        problems.append(
            "commentary.edit_decision_list must identify the edit record showing only the panels "
            "the commentary needs were used, not a complete readable substitute for the chapter"
        )

    scans = data.get("safety_scans")
    if not isinstance(scans, dict):
        problems.append("safety_scans must be an object")
    else:
        for name in SAFETY_SCANS:
            record = scans.get(name)
            if not isinstance(record, dict) or record.get("clear") is not True:
                problems.append(
                    f"safety_scans.{name} is not recorded clear; scan the panels and thumbnail "
                    "and record the result before publishing"
                )
            elif not _text(record, "scanned_by"):
                problems.append(f"safety_scans.{name}.scanned_by must name who performed the scan")

    return {
        "ok": not problems,
        "project_root": str(Path(project_root).expanduser().resolve()),
        "rights_file": str(rights_path(project_root)),
        "source": source if isinstance(source, dict) else {},
        "permission_basis": basis,
        "problems": problems,
        "warnings": warnings,
    }


def require_publishable_rights(project_root: Path) -> dict:
    """Raise unless the manifest authorizes publishing this project."""
    report = check_rights(project_root)
    if not report["ok"]:
        detail = "\n".join(f"  - {problem}" for problem in report["problems"])
        raise RightsError(
            "manga rights gate failed; publication refused because source ownership or "
            f"permission is unresolved:\n{detail}\n"
            f"Fix {report['rights_file']} and re-run `{CLI_NAME} manga-rights check`."
        )
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    from mangaeasy.video_pipeline.common import DEFAULT_PROJECT_ROOT

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} manga-rights",
        description="Create and verify the manga rights manifest that authorizes publication. "
                    "Fails closed: unknown ownership or permission blocks upload.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    init = subparsers.add_parser("init", help="Write a blank rights.json template.")
    init.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    init.add_argument("--force", action="store_true", help="Overwrite an existing manifest.")

    check = subparsers.add_parser("check", help="Verify the manifest authorizes publication.")
    check.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)

    show = subparsers.add_parser("show", help="Print the current manifest.")
    show.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()
    try:
        if args.action == "init":
            if rights_path(root).is_file() and not args.force:
                print(json.dumps({
                    "ok": False,
                    "error": f"{rights_path(root)} already exists; pass --force to overwrite",
                }))
                return 1
            template = _template()
            template["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            seeded = seed_template(template, _operator_defaults())
            path = write_rights(root, template)
            print(json.dumps({
                "ok": True,
                "rights_file": str(path),
                "seeded_from_system_config": seeded,
                "still_required": [field for field, _ in PER_WORK_FIELDS],
                "next": f"Fill in the per-work fields listed in 'still_required', then run "
                        f"`{CLI_NAME} manga-rights check --project-root {root}`."
                        + ("" if seeded else
                           "  Tip: set `rights_defaults` in config.system.json to carry your "
                           "standing voice consent, permission basis, and commentary policy "
                           "into every new project instead of re-entering them."),
            }, ensure_ascii=False))
            return 0
        if args.action == "show":
            print(json.dumps(load_rights(root), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        report = check_rights(root)
    except RightsError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
