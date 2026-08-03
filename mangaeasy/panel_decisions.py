"""Legacy/audit ledger for deliberate panel omission decisions.

Production coverage now requires every cropped panel to be narrated and
rendered. Older projects may still carry omission decisions, and this module
keeps those records hash-bound and auditable so stale metadata cannot silently
survive a re-crop.

This is a legacy content/quality ledger only. It does not satisfy the current
production video gate, and it is not a source-clearance or permission gate.

Records live in ``<item>/panel_decisions.json``.
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
from mangaeasy.reviews import ReviewRecordError, sha256_file
from mangaeasy.video_pipeline.common import IMAGE_EXTENSIONS

SCHEMA_VERSION = 1
DECISIONS_FILENAME = "panel_decisions.json"

# A closed vocabulary, because free-text reasons stop being auditable the
# moment two agents phrase the same decision differently.
SKIP_REASONS: tuple[str, ...] = (
    "credit",             # scanlation/publisher credit page
    "scanlator_notice",   # translator note, join-us banner, release info
    "decorative",         # borders, dividers, chapter ornaments
    "duplicate",          # the same art already narrated in another panel
    "sfx_only",           # pure sound effect with no story content
    "platform_safety",    # withheld for YouTube policy reasons
    "other",              # anything else — requires a note
)
REASON_REQUIRING_NOTE = "other"


class PanelDecisionError(ValueError):
    """A panel decision cannot be recorded, or does not match current panels."""


def decisions_path(item_dir: Path) -> Path:
    return Path(item_dir) / DECISIONS_FILENAME


def panel_images(item_dir: Path, panels_subdir: str = "panels") -> list[Path]:
    """Every panel image in the item, in reading (name-sorted) order."""
    panels_dir = Path(item_dir) / panels_subdir
    if not panels_dir.is_dir():
        return []
    return sorted(
        (path for path in panels_dir.iterdir()
         if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: path.name.casefold(),
    )


def load_decisions(item_dir: Path) -> dict:
    path = decisions_path(item_dir)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "panels_subdir": "panels", "decisions": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PanelDecisionError(f"could not read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise PanelDecisionError(
            f"unsupported panel decision schema at {path}; expected schema_version {SCHEMA_VERSION}"
        )
    if not isinstance(data.get("decisions"), dict):
        raise PanelDecisionError(f"{path}: 'decisions' must be an object")
    return data


def _write_decisions(item_dir: Path, store: dict) -> Path:
    path = decisions_path(item_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    payload = json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def record_decisions(
    item_dir: Path,
    images: Sequence[str],
    *,
    reason: str,
    reviewer: str,
    note: str | None = None,
    panels_subdir: str = "panels",
) -> dict:
    """Record a deliberate omission for each named panel, bound to its bytes."""
    if reason not in SKIP_REASONS:
        raise PanelDecisionError(
            f"reason must be one of: {', '.join(SKIP_REASONS)}"
        )
    note = (note or "").strip()
    if reason == REASON_REQUIRING_NOTE and not note:
        raise PanelDecisionError(
            f"reason '{REASON_REQUIRING_NOTE}' requires --note explaining the omission"
        )
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise PanelDecisionError("reviewer must be a non-empty name or agent identity")
    if not images:
        raise PanelDecisionError("no panels named; pass --panels <image> [...]")

    item_dir = Path(item_dir).resolve()
    panels_dir = item_dir / panels_subdir
    store = load_decisions(item_dir)
    store["panels_subdir"] = panels_subdir
    decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    recorded: list[str] = []
    for name in images:
        candidate = (panels_dir / name).resolve(strict=False)
        if candidate.parent != panels_dir.resolve(strict=False):
            raise PanelDecisionError(f"panel must be a filename inside panels/: {name!r}")
        if not candidate.is_file():
            raise PanelDecisionError(f"panel does not exist: {candidate}")
        digest, size = sha256_file(candidate)
        store["decisions"][candidate.name] = {
            "reason": reason,
            "note": note,
            "decided_by": reviewer,
            "decided_at": decided_at,
            "sha256": digest,
            "size": size,
        }
        recorded.append(candidate.name)
    path = _write_decisions(item_dir, store)
    return {
        "ok": True,
        "item": item_dir.name,
        "record_file": str(path),
        "reason": reason,
        "reviewer": reviewer,
        "panels": sorted(recorded),
    }


def audit_item(
    item_dir: Path,
    narrated_images: Sequence[str] | None = None,
    *,
    panels_subdir: str = "panels",
) -> dict:
    """Report every panel that is neither narrated nor in the legacy omission ledger.

    ``narrated_images`` defaults to the item's own contract-valid narration.
    A panel whose bytes changed since its decision was recorded counts as
    unaccounted for: the decision approved different pixels.
    """
    item_dir = Path(item_dir).resolve()
    if narrated_images is None:
        from mangaeasy.video_pipeline.narration_contract import (
            NarrationContractError,
            validate_item_narration,
        )
        try:
            entries = validate_item_narration(item_dir, require_files=False)
            narrated_images = [entry["image"] for entry in entries]
        except NarrationContractError:
            narrated_images = []

    narrated = {name.casefold() for name in narrated_images}
    try:
        store = load_decisions(item_dir)
    except PanelDecisionError as exc:
        return {
            "item": item_dir.name,
            "ok": False,
            "error": str(exc),
            "unaccounted": [],
            "stale_decisions": [],
            "decided": [],
        }
    decisions = store["decisions"]

    unaccounted: list[str] = []
    stale: list[dict] = []
    decided: list[dict] = []
    for path in panel_images(item_dir, store.get("panels_subdir", panels_subdir)):
        if path.name.casefold() in narrated:
            continue
        record = decisions.get(path.name)
        if not isinstance(record, dict):
            unaccounted.append(path.name)
            continue
        try:
            digest, _size = sha256_file(path)
        except OSError as exc:
            stale.append({"panel": path.name, "detail": f"panel unreadable: {exc}"})
            continue
        if record.get("sha256") != digest:
            stale.append({
                "panel": path.name,
                "detail": "panel changed after the omission decision was recorded",
            })
            continue
        decided.append({
            "panel": path.name,
            "reason": record.get("reason"),
            "note": record.get("note") or "",
            "decided_by": record.get("decided_by"),
            "decided_at": record.get("decided_at"),
        })

    orphaned = sorted(
        name for name in decisions
        if not (item_dir / store.get("panels_subdir", panels_subdir) / name).is_file()
    )
    return {
        "item": item_dir.name,
        "ok": not unaccounted and not stale,
        "narrated": len(narrated),
        "unaccounted": unaccounted,
        "stale_decisions": stale,
        "decided": decided,
        "orphaned_decisions": orphaned,
    }


def audit_problems(item_dir: Path, narrated_images: Sequence[str] | None = None) -> list[str]:
    """Human-readable problems from :func:`audit_item`, for report callers."""
    report = audit_item(item_dir, narrated_images)
    problems: list[str] = []
    if report.get("error"):
        problems.append(report["error"])
    if report["unaccounted"]:
        shown = ", ".join(report["unaccounted"][:5])
        more = "…" if len(report["unaccounted"]) > 5 else ""
        problems.append(
            f"{len(report['unaccounted'])} panel(s) are neither narrated nor in the "
            f"legacy omission ledger: {shown}{more}. Production video still requires "
            "narrating every panel."
        )
    for entry in report["stale_decisions"]:
        problems.append(f"{entry['panel']}: {entry['detail']}")
    return problems


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    from mangaeasy.video_pipeline.common import DEFAULT_PROJECT_ROOT

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} panel-decisions",
        description="Record and audit legacy deliberate panel omissions. Production "
                    "video still requires every cropped panel to be narrated.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--items", nargs="*", help="Item folders/ranges (default: all).")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-12.")
    parser.add_argument("--item", help="Single item folder to record decisions for.")
    parser.add_argument("--panels", nargs="*", default=[],
                        help="Panel filenames to mark as deliberately omitted.")
    parser.add_argument("--reason", choices=SKIP_REASONS,
                        help="Why those panels carry no narration.")
    parser.add_argument("--note", default=None,
                        help=f"Explanation; required when --reason {REASON_REQUIRING_NOTE}.")
    parser.add_argument("--reviewer", default=None,
                        help="Who made the decision (name or agent identity).")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    from mangaeasy.video_pipeline.common import item_dirs, merge_item_selection

    args = parse_args(argv)
    root = Path(args.project_root).expanduser().resolve()

    if args.panels:
        if not args.item:
            print(json.dumps({"ok": False, "error": "--panels requires --item"}))
            return 2
        if not args.reason or not args.reviewer:
            print(json.dumps({
                "ok": False,
                "error": "--panels requires --reason and --reviewer",
            }))
            return 2
        try:
            report = record_decisions(
                root / args.item,
                args.panels,
                reason=args.reason,
                reviewer=args.reviewer,
                note=args.note,
            )
        except (PanelDecisionError, ReviewRecordError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0

    selection = merge_item_selection(args.items, args.item_range)
    if args.item:
        selection = [args.item]
    selected = item_dirs(root, selection)
    if not selected:
        print(json.dumps({"ok": False, "error": f"no items found under {root}", "items": []}))
        return 1
    reports = [audit_item(item_dir) for item_dir in selected]
    ok = all(report["ok"] for report in reports)
    payload = {"ok": ok, "project_root": str(root), "items": reports}
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if ok else 1
    print(f"panel-decisions: {root} ({len(reports)} item(s))\n")
    for report in reports:
        status = "ok " if report["ok"] else "FAIL"
        print(f"  [{status}] {report['item']}: {report['narrated']} narrated, "
              f"{len(report['decided'])} deliberately omitted")
        for name in report["unaccounted"]:
            print(f"         - unaccounted panel: {name}")
        for entry in report["stale_decisions"]:
            print(f"         - {entry['panel']}: {entry['detail']}")
    if not ok:
        print(f"\nRecord each omission with `{CLI_NAME} panel-decisions --item <item> "
              f"--panels <image> --reason <reason> --reviewer <name>`.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
