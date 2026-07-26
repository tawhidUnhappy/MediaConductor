"""mediaconductor.ocr.panel_transcript — OCR every panel BEFORE narration exists.

``mediaconductor panel-transcript`` writes ``<item>/transcript.json`` — one entry
per panel image, each carrying an ``ocr`` field with the bubble/caption text
DeepSeek-OCR 2 proposed for that panel. It is optional, untrusted
cross-evidence for narration writing:

- the narration author reads the original panel and can compare uncertain
  small text with an independent OCR attempt;
- speaker attribution still comes from the artwork, bubble tails, and panel
  sequence rather than from OCR or memory;
- ``narration-review-sheets`` shows the transcript next to each narration
  line for the verification pass, clearly labeled as unverified.

Under the hood it seeds the transcript files and binds every OCR value to the
SHA-256 of the exact panel file bytes it was generated from. Re-cropping a panel under
the same filename invalidates stale OCR instead of silently preserving it. It
then runs the existing ``deepseek-ocr2`` command over pending entries in one
subprocess, so the model loads once for all items. Requires the
``deepseek-ocr2`` tool env (``mediaconductor install-tool deepseek-ocr2``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mediaconductor import runtime
from mediaconductor.brand import CLI_NAME
from mediaconductor.runtime import cli_command
from mediaconductor.utils import emit_result

PANEL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def panel_sha256(path: Path) -> str:
    """Return the content digest that binds an OCR value to one panel."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_bound_ocr(item_dir: Path) -> tuple[dict[str, str], int, int]:
    """Return current OCR by image plus (total rows, stale rows ignored).

    Consumers call this directly instead of trusting transcript filenames.
    A row is usable only when its stored digest still matches the current panel
    file; legacy, missing, or changed crops are suppressed even if the caller
    forgot to run ``panel-transcript --seed-only`` after re-cropping.
    """
    path = item_dir / "transcript.json"
    if not path.is_file():
        return {}, 0, 0
    try:
        entries = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}, 0, 0
    if not isinstance(entries, list):
        return {}, 0, 0

    bound: dict[str, str] = {}
    stale = 0
    for entry in entries:
        if not isinstance(entry, dict) or "ocr" not in entry:
            continue
        image = entry.get("image")
        if not isinstance(image, str) or not image or Path(image).name != image:
            stale += 1
            continue
        panel = item_dir / "panels" / image
        try:
            current_digest = panel_sha256(panel)
        except OSError:
            stale += 1
            continue
        if entry.get("panel_sha256") != current_digest:
            stale += 1
            continue
        value = entry.get("ocr")
        bound[image] = value if isinstance(value, str) else str(value or "")
    return bound, len(entries), stale


def seed_transcript(item_dir: Path) -> tuple[Path, int, int, int]:
    """Refresh transcript.json and keep OCR only for byte-identical panels."""
    panels = sorted(
        (p for p in (item_dir / "panels").iterdir()
         if p.suffix.lower() in PANEL_EXTENSIONS),
        key=lambda panel: panel.name,
    )
    path = item_dir / "transcript.json"
    existing: dict[str, dict] = {}
    if path.is_file():
        try:
            for entry in json.loads(path.read_text(encoding="utf-8-sig")):
                if isinstance(entry, dict) and entry.get("image"):
                    existing[entry["image"]] = entry
        except Exception:
            print(f"[{item_dir.name}] unreadable transcript.json — rebuilding")
    entries: list[dict] = []
    invalidated = 0
    for panel in panels:
        digest = panel_sha256(panel)
        previous = existing.get(panel.name)
        if previous is not None and previous.get("panel_sha256") == digest:
            entry = dict(previous)
            entry["image"] = panel.name
            entry["panel_sha256"] = digest
        else:
            if previous is not None and "ocr" in previous:
                invalidated += 1
            entry = {"image": panel.name, "panel_sha256": digest}
        entries.append(entry)
    panel_names = {panel.name for panel in panels}
    dropped = len(set(existing) - panel_names)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path, len(entries), dropped, invalidated


def coverage(path: Path) -> tuple[int, int]:
    entries = json.loads(path.read_text(encoding="utf-8-sig"))
    # DeepSeek intentionally writes ``ocr: ""`` for textless panels.  The
    # presence of the key means the panel was processed; a seeded skeleton has
    # no key yet.
    done = sum(1 for e in entries if isinstance(e, dict) and "ocr" in e)
    return done, len(entries)


def parse_args() -> argparse.Namespace:
    from mediaconductor.video_pipeline.common import DEFAULT_PROJECT_ROOT

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} panel-transcript",
        description="Propose optional, unverified DeepSeek-OCR 2 text for every panel in "
                    "<item>/transcript.json; original pixels and bubble tails remain authoritative.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--items", nargs="*")
    parser.add_argument("--item-range")
    parser.add_argument("--force", action="store_true",
                        help="Re-OCR panels that already have an ocr value.")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--seed-only", action="store_true",
                        help="Only (re)write the transcript skeletons; skip the OCR run.")
    parser.add_argument("--respect-claims", action="store_true",
                        help="Abort (exit 1) if another live agent's workboard claim covers any "
                             "selected item at this stage (see docs/multi-agent.md).")
    parser.add_argument("--agent", default=None,
                        help="This agent's identity for --respect-claims "
                             "(default: $MEDIACONDUCTOR_AGENT or user@host).")
    return parser.parse_args()


def main() -> int:
    from mediaconductor.video_pipeline.common import item_dirs, merge_item_selection

    args = parse_args()
    if args.respect_claims:
        from mediaconductor.workboard import respect_claims_gate

        if not respect_claims_gate(args.project_root, args.items, args.item_range, ("transcribe",), args.agent):
            return 1
    project_root = args.project_root.resolve()
    selected = item_dirs(project_root, merge_item_selection(args.items, args.item_range))
    if not selected:
        print(f"[FATAL] No item folders found under {project_root}")
        return 1

    transcripts: list[Path] = []
    for item_dir in selected:
        if not (item_dir / "panels").is_dir():
            print(f"[{item_dir.name}] no panels dir — skipped")
            continue
        path, count, dropped, invalidated = seed_transcript(item_dir)
        transcripts.append(path)
        print(f"[{item_dir.name}] transcript seeded: {count} panel(s)"
              + (f", {dropped} stale entr(ies) dropped" if dropped else "")
              + (f", {invalidated} changed-panel OCR value(s) invalidated"
                 if invalidated else ""), flush=True)
    if not transcripts:
        print("[FATAL] nothing to transcribe")
        return 1

    if not args.seed_only:
        cmd = cli_command(
            "deepseek-ocr2",
            "--project-root", str(project_root),
            "--device", args.device,
        )
        for t in transcripts:
            cmd += ["--narration", str(t)]
        if args.force:
            cmd.append("--force")
        result = runtime.run(cmd)
        if result.returncode != 0:
            print("[FATAL] deepseek-ocr2 run failed — transcripts are seeded, re-run to resume")
            return 1

    items = {}
    for t in transcripts:
        done, total = coverage(t)
        items[t.parent.name] = {"transcript": str(t), "ocr_done": done, "panels": total}
        print(f"[{t.parent.name}] ocr coverage: {done}/{total}", flush=True)
    emit_result(command="panel-transcript", items=items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
