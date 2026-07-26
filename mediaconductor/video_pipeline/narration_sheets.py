"""mediaconductor.video_pipeline.narration_sheets — panel+text pairs for semantic QA.

``mediaconductor narration-review-sheets`` renders review sheets that pair every
narration entry's panel image with (a) the narration text that will be spoken
over it and (b) an unverified OCR candidate when ``panel-transcript`` has been
run. OCR is a fallible second reading, never ground truth: the original panel
pixels, bubble tails, and established sequence remain authoritative. This is
the *semantic* half of narration verification that ``narration-check``
deliberately does not do — an agent Reads each sheet and checks, per panel:

1. the narration describes THIS panel (not a summary smeared across several);
2. quoted/paraphrased dialogue is attributed to the right character by
   inspecting the visible bubble and its tail;
3. paraphrases stay faithful to the original pixels; OCR disagreements trigger
   another look at the source, not automatic acceptance of the OCR;
4. the line reads naturally when spoken aloud.

The embedded panel is a convenience preview. Reviewers still open every
original crop at readable/full resolution before approving a line.

Fix problems by editing narration.json, delete the affected WAVs
(``video-audio-audit --fix`` after emptying them, or remove by stem), and
re-run audio generation — it only regenerates missing files.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mediaconductor.brand import CLI_NAME
from mediaconductor.ocr.panel_transcript import load_bound_ocr
from mediaconductor.utils import emit_result

PANEL_W = 960
PANEL_MAX_H = 1600
TEXT_W = 820
PAD = 16

_FONT_CANDIDATES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
_BODY_CANDIDATES = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]


def _font(size: int, candidates: list[str]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def load_transcript(item_dir: Path) -> dict[str, str]:
    """Load only OCR whose stored digest matches the current panel file."""
    transcript, _total, _stale = load_bound_ocr(item_dir)
    return transcript


def wrap(text: str, width: int = 46) -> list[str]:
    lines: list[str] = []
    for para in (text or "").splitlines() or [""]:
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return lines


def _review_exit_code(per_item: dict[str, dict]) -> int:
    """Return review-required unless there is no valid material to review."""
    failed = any(
        not report.get("entries") or report.get("missing_images")
        for report in per_item.values()
    )
    return 1 if failed else 3


def _prune_review_sheets(out_dir: Path) -> None:
    """Remove surplus sheets from an older generation for this item."""
    for stale in out_dir.glob("review_*.jpg"):
        stale.unlink(missing_ok=True)


def render_entry(item_dir: Path, entry: dict, ocr: str) -> Image.Image:
    head_font = _font(30, _FONT_CANDIDATES)
    body_font = _font(28, _BODY_CANDIDATES)
    image_path = item_dir / "panels" / entry["image"]
    if image_path.is_file():
        panel = Image.open(image_path).convert("RGB")
        panel.thumbnail((PANEL_W, PANEL_MAX_H))
        cropped_note = ""
    else:
        panel = Image.new("RGB", (PANEL_W, 200), (60, 0, 0))
        cropped_note = "IMAGE MISSING"

    narration_lines = wrap(entry.get("narration", ""))
    ocr_lines = wrap(ocr, width=52) if ocr else [
        "(no OCR candidate — optional; inspect the original panel)",
    ]
    line_h = 36
    text_h = (len(narration_lines) + len(ocr_lines) + 4) * line_h + 2 * PAD
    cell_h = max(panel.height + 2 * PAD, text_h, 240)
    cell = Image.new("RGB", (PANEL_W + TEXT_W + 3 * PAD, cell_h + 40), (18, 18, 18))
    draw = ImageDraw.Draw(cell)
    draw.text(
        (PAD, 8),
        f"PREVIEW ONLY — OPEN ORIGINAL: {entry['image']}  {cropped_note}",
        fill=(255, 230, 0),
        font=head_font,
    )
    cell.paste(panel, (PAD, 40 + PAD))
    x = PANEL_W + 2 * PAD
    y = 40 + PAD
    draw.text((x, y), "NARRATION:", fill=(120, 220, 120), font=head_font)
    y += line_h
    for line in narration_lines:
        draw.text((x, y), line, fill=(235, 235, 235), font=body_font)
        y += line_h
    y += line_h // 2
    draw.text(
        (x, y),
        "OCR CANDIDATE (UNVERIFIED):",
        fill=(120, 170, 255),
        font=head_font,
    )
    y += line_h
    for line in ocr_lines:
        draw.text((x, y), line, fill=(170, 170, 170), font=body_font)
        y += line_h
    return cell


def parse_args() -> argparse.Namespace:
    from mediaconductor.video_pipeline.common import DEFAULT_PROJECT_ROOT, DEFAULT_WORK_DIR

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} narration-review-sheets",
        description="Render panel + narration + unverified-OCR review sheets for "
                    "source-first semantic and speaker verification of narration.json.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--items", nargs="*")
    parser.add_argument("--item-range")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--output-root", type=Path, default=None,
                        help="Default: <work-dir>/narration_review/<project-name>.")
    parser.add_argument("--per-sheet", type=int, default=4,
                        help="Entries per sheet (default 4).")
    parser.add_argument("--only-images", nargs="*", default=None,
                        help="Limit to these image names/stems (e.g. the panels-remap "
                             "review list, or panels flagged in an earlier pass).")
    return parser.parse_args()


def main() -> int:
    from mediaconductor.video_pipeline.common import item_dirs, merge_item_selection
    from mediaconductor.video_pipeline.item_assets import load_narration

    args = parse_args()
    project_root = args.project_root.resolve()
    selected = item_dirs(project_root, merge_item_selection(args.items, args.item_range))
    if not selected:
        print(f"[FATAL] No item folders found under {project_root}")
        return 1
    out_root = (args.output_root or args.work_dir / "narration_review" / project_root.name).resolve()

    only = None
    if args.only_images:
        only = {Path(name).stem for name in args.only_images}

    all_sheets: list[str] = []
    per_item: dict[str, dict] = {}
    for i, item_dir in enumerate(selected, 1):
        print(f"MEDIACONDUCTOR_PROGRESS {i}/{len(selected)}", flush=True)
        entries = load_narration(item_dir)
        if only is not None:
            entries = [e for e in entries if Path(e["image"]).stem in only]
        transcript, _transcript_rows, stale_ocr = load_bound_ocr(item_dir)
        missing_images = [e["image"] for e in entries
                          if not (item_dir / "panels" / e["image"]).is_file()]
        out_dir = out_root / item_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)
        _prune_review_sheets(out_dir)
        sheets = []
        for n in range(0, len(entries), args.per_sheet):
            cells = [render_entry(item_dir, e, transcript.get(e["image"], ""))
                     for e in entries[n:n + args.per_sheet]]
            width = max(c.width for c in cells)
            sheet = Image.new("RGB", (width, sum(c.height + PAD for c in cells)), (0, 0, 0))
            y = 0
            for c in cells:
                sheet.paste(c, (0, y))
                y += c.height + PAD
            path = out_dir / f"review_{n // args.per_sheet + 1:03d}.jpg"
            sheet.save(path, quality=95, subsampling=0)
            sheets.append(str(path))
        all_sheets.extend(sheets)
        per_item[item_dir.name] = {
            "entries": len(entries), "sheets": len(sheets),
            "with_ocr": sum(1 for e in entries if transcript.get(e["image"])),
            "stale_ocr_ignored": stale_ocr,
            "missing_images": missing_images,
        }
        print(f"[{item_dir.name}] {len(entries)} entries -> {len(sheets)} sheet(s)"
              + (f", {stale_ocr} stale OCR row(s) ignored" if stale_ocr else "")
              + (f", MISSING IMAGES: {missing_images}" if missing_images else ""), flush=True)

    print(f"{len(all_sheets)} sheet(s) under {out_root}")
    print(
        "Read every sheet AND open every original crop at readable/full resolution. "
        "Verify narration against panel pixels, bubble tails, and sequence; OCR is an "
        "unverified candidate and never authoritative."
    )
    emit_result(command="narration-review-sheets", output_dir=out_root,
                sheets=len(all_sheets), items=per_item, review_required=True)
    return _review_exit_code(per_item)


if __name__ == "__main__":
    raise SystemExit(main())
