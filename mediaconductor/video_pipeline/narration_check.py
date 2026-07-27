"""mediaconductor.video_pipeline.narration_check — structural narration validation.

``mediaconductor narration-check`` verifies each item's narration before audio
generation. Three passes, one report:

1. **Contract** — :mod:`mediaconductor.video_pipeline.narration_contract`
   validates every entry in ``intro.json`` and ``narration.json``: safe
   basename images that resolve inside ``panels/``, non-empty narration,
   case-insensitive filename *and* stem uniqueness across the combined
   playback list (the intro is prepended at render time, so a panel in both
   files would play twice and both beats would fight over one WAV), no unknown
   properties, and in-range motion/pause values.
2. **Quality** — unspeakable text (phonetic screams, copied stammers, empty
   lines) is a problem; editorial style findings (repetition, meta phrasing,
   beats too short or too long) are warnings.
3. **Coverage** — every cropped panel must be narrated or carry a recorded
   omission decision (``mediaconductor panel-decisions``). An un-narrated,
   un-decided panel is a problem, not an unfalsifiable warning.

This is the machine half of narration verification. The semantic half — is
the narration faithful to the panels, is dialogue attributed to the right
speaker — cannot be checked structurally; an agent does that by reading the
panels against the text (see docs/operate/crop-verify-narrate.md).

Exit code 0 = every checked item is clean; 1 = at least one problem.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mediaconductor.audio.narration_safety import narration_quality_findings
from mediaconductor.brand import CLI_NAME
from mediaconductor.panel_decisions import audit_item as audit_panel_decisions
from mediaconductor.video_pipeline.narration_contract import (
    NarrationContractError,
    narration_problems,
    validate_item_narration,
)


def check_item(item_dir: Path) -> dict:
    """Structural + editorial report for one item; 'problems' empty means clean."""
    panels_dir = item_dir / "panels"
    problems: list[str] = list(narration_problems(item_dir))
    warnings: list[str] = []

    if not panels_dir.is_dir():
        problems.append("panels/ folder missing")

    entries: list[dict] = []
    if not problems:
        try:
            entries = validate_item_narration(item_dir)
        except NarrationContractError as exc:  # pragma: no cover — narration_problems caught it
            problems.append(str(exc))

    # Style findings never fail the check on their own: whether a repeated
    # opening is a tic or a deliberate refrain is an editorial call. Errors
    # from the same pass (unspeakable text) are already blocking at TTS time,
    # so surface them here as problems rather than letting a render discover
    # them an hour later.
    for finding in narration_quality_findings(entries):
        message = f"{finding.beat}: {finding.message}"
        (problems if finding.is_error else warnings).append(message)

    decisions = audit_panel_decisions(item_dir, [entry["image"] for entry in entries])
    uncovered = decisions["unaccounted"]
    if uncovered:
        problems.append(
            f"{len(uncovered)} panel image(s) are neither narrated nor recorded as a "
            "deliberate omission: "
            + ", ".join(uncovered[:5]) + ("…" if len(uncovered) > 5 else "")
            + f". Narrate them, or run `{CLI_NAME} panel-decisions --item {item_dir.name} "
            "--panels <image> --reason <reason> --reviewer <name>`."
        )
    for stale in decisions["stale_decisions"]:
        problems.append(f"{stale['panel']}: {stale['detail']}")
    if decisions["decided"]:
        warnings.append(
            f"{len(decisions['decided'])} panel(s) deliberately omitted: "
            + ", ".join(
                f"{entry['panel']} ({entry['reason']})" for entry in decisions["decided"][:5]
            )
            + ("…" if len(decisions["decided"]) > 5 else "")
        )

    return {
        "item": item_dir.name,
        "entries": len(entries),
        "uncovered_panels": uncovered,
        "omitted_panels": decisions["decided"],
        "problems": problems,
        "warnings": warnings,
        "ok": not problems,
    }


def main() -> int:
    from mediaconductor.video_pipeline.common import DEFAULT_PROJECT_ROOT, item_dirs, merge_item_selection

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} narration-check",
        description="Validate narration.json/intro.json per item against the strict "
                    "narration contract, lint the script for unspeakable text and "
                    "editorial repetition, and require every cropped panel to be "
                    "narrated or recorded as a deliberate omission. Semantic review "
                    "(accuracy, speaker attribution) remains an agent's reading job.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT,
                        help="Project folder containing item subfolders (data/library/<name>).")
    parser.add_argument("--items", nargs="*", help="Item folders, e.g. 01 02 05-08 (default: all).")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-19.")
    parser.add_argument("--json", action="store_true", help="Emit one JSON object on stdout.")
    args = parser.parse_args()

    selection = merge_item_selection(args.items, args.item_range)
    selected = item_dirs(Path(args.project_root), selection)
    if not selected:
        message = f"no items found under {args.project_root}"
        if args.json:
            print(json.dumps({"ok": False, "error": message, "items": []}))
        else:
            print(f"[ERROR] {message}")
        return 1

    reports = [check_item(item_dir) for item_dir in selected]
    ok = all(r["ok"] for r in reports)

    if args.json:
        print(json.dumps({"ok": ok, "items": reports}, ensure_ascii=False))
        return 0 if ok else 1

    print(f"narration-check: {args.project_root} ({len(reports)} item(s))\n")
    for r in reports:
        status = "ok " if r["ok"] else "FAIL"
        print(f"  [{status}] {r['item']}: {r['entries']} entries")
        for problem in r["problems"]:
            print(f"         - {problem}")
        for warning in r.get("warnings", []):
            print(f"         ~ warning: {warning}")
    print("\nAll clean." if ok else "\nFix the problems above, then re-run.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
