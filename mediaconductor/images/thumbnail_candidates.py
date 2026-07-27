"""mediaconductor.images.thumbnail_candidates — shortlist panels worth compositing.

``mediaconductor thumbnail-candidates`` answers one question: *of the few
thousand panels this batch produced, which twenty are worth opening?* It
scores every cropped panel on properties that are cheap to measure and
genuinely predict a usable thumbnail base — size, how close the shape is to
16:9, how much detail survives at phone scale, ink coverage — and renders
numbered contact sheets plus a JSON shortlist.

**The score never picks the thumbnail.** No pixel statistic knows which panel
shows the reversal the title promises, whose face is in it, or whether the
composition reads as a sexualized minor. The command exists so a
vision-capable agent opens twenty full-resolution candidates instead of two
thousand, and then *looks* at them. Treat the ranking exactly like MAGI's
panel boxes: a proposal, never an approval.

The measurements, and why each one is here:

``detail``
    Standard deviation of luminance. A panel that is 95 % empty sky or flat
    screentone scores near zero and is a smudge at 320×180 — the size most
    viewers actually see.
``ink``
    Fraction of dark pixels. Both extremes are bad: an almost-white panel has
    no subject, an almost-black one has no readable subject either. Peaks
    around a quarter to a third inked, which is what a figure with linework
    against a light background looks like.
``shape``
    Penalises panels far from 16:9, because the composer cover-crops to
    1280×720 and a tall webtoon strip loses most of its content to that crop.
``size``
    Rewards resolution up to 1280×720; below that the base is upscaled and
    the linework goes soft.

Every candidate is reported with its component scores so an agent can say
*why* it opened one — and so a bad ranking is debuggable rather than magic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mediaconductor.brand import CLI_NAME
from mediaconductor.utils import emit_result

TARGET_W, TARGET_H = 1280, 720
TARGET_RATIO = TARGET_W / TARGET_H
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Contact-sheet geometry: 4 columns reads well in a chat client's image
# viewer without shrinking each panel below recognisability.
SHEET_COLUMNS = 4
SHEET_CELL = (420, 260)
SHEET_LABEL_H = 34
SHEET_PAD = 12
SHEET_ROWS_PER_SHEET = 5

# Ink coverage that tends to mean "a drawn subject against a light ground".
IDEAL_INK = 0.28


def _panel_dirs(project_root: Path, items: list[str] | None) -> list[tuple[str, Path]]:
    """(item, panels dir) for each selected item that has cropped panels."""
    found: list[tuple[str, Path]] = []
    for item_dir in sorted(p for p in project_root.iterdir() if p.is_dir()):
        if items is not None and item_dir.name not in items:
            continue
        panels = item_dir / "panels"
        if panels.is_dir():
            found.append((item_dir.name, panels))
    return found


def score_image(path: Path) -> dict | None:
    """Measure one panel. Returns None when it cannot be read as an image."""
    import numpy as np
    from PIL import Image

    try:
        with Image.open(path) as handle:
            handle.draft("L", (512, 512))  # cheap decode: we only need statistics
            grey = handle.convert("L")
            width, height = handle.size
            sample = np.asarray(grey.resize((160, 90)), dtype="float32") / 255.0
    except Exception:
        return None
    if width < 2 or height < 2:
        return None

    detail = float(sample.std())
    ink = float((sample < 0.5).mean())
    ratio = width / height

    # Each component in 0..1, then a weighted blend. Weights favour detail:
    # an empty panel is the failure that survives every other check.
    detail_score = min(1.0, detail / 0.30)
    ink_score = max(0.0, 1.0 - abs(ink - IDEAL_INK) / 0.45)
    shape_score = max(0.0, 1.0 - abs(ratio - TARGET_RATIO) / TARGET_RATIO)
    size_score = min(1.0, (width * height) / (TARGET_W * TARGET_H))

    score = (0.40 * detail_score + 0.25 * ink_score
             + 0.20 * shape_score + 0.15 * size_score)
    return {
        "path": str(path),
        "name": path.name,
        "width": width,
        "height": height,
        "ratio": round(ratio, 3),
        "score": round(score, 4),
        "detail": round(detail_score, 3),
        "ink": round(ink_score, 3),
        "shape": round(shape_score, 3),
        "size": round(size_score, 3),
        "notes": _notes(width, height, ratio, detail, ink),
    }


def _notes(width: int, height: int, ratio: float, detail: float, ink: float) -> list[str]:
    """Plain-language caveats an agent should carry into the visual check."""
    notes: list[str] = []
    if width < TARGET_W or height < TARGET_H:
        notes.append(f"below 1280x720 ({width}x{height}) — will be upscaled, check linework")
    if ratio < 1.0:
        notes.append("portrait — cover-crop keeps the middle; confirm the subject survives")
    elif ratio > 2.6:
        notes.append("very wide — cover-crop trims the sides")
    if detail < 0.12:
        notes.append("low detail — may read as empty at phone size")
    if ink < 0.08:
        notes.append("very light panel — subject may disappear against a white background")
    elif ink > 0.72:
        notes.append("very dark panel — text needs a light fill to stay readable")
    return notes


def build_sheets(candidates: list[dict], out_dir: Path, project: str) -> list[Path]:
    """Numbered contact sheets so an agent can eyeball the shortlist at once."""
    from PIL import Image, ImageDraw

    from mediaconductor.images.thumbnail_compose import load_font

    out_dir.mkdir(parents=True, exist_ok=True)
    font = load_font(22, None)
    cell_w, cell_h = SHEET_CELL
    per_sheet = SHEET_COLUMNS * SHEET_ROWS_PER_SHEET
    written: list[Path] = []

    for sheet_index, start in enumerate(range(0, len(candidates), per_sheet), start=1):
        chunk = candidates[start:start + per_sheet]
        rows = (len(chunk) + SHEET_COLUMNS - 1) // SHEET_COLUMNS
        sheet = Image.new(
            "RGB",
            (SHEET_COLUMNS * (cell_w + SHEET_PAD) + SHEET_PAD,
             rows * (cell_h + SHEET_LABEL_H + SHEET_PAD) + SHEET_PAD),
            (24, 24, 24),
        )
        draw = ImageDraw.Draw(sheet)
        for offset, candidate in enumerate(chunk):
            col, row = offset % SHEET_COLUMNS, offset // SHEET_COLUMNS
            x = SHEET_PAD + col * (cell_w + SHEET_PAD)
            y = SHEET_PAD + row * (cell_h + SHEET_LABEL_H + SHEET_PAD)
            try:
                with Image.open(candidate["path"]) as handle:
                    thumb = handle.convert("RGB")
                    thumb.thumbnail((cell_w, cell_h), Image.LANCZOS)
            except Exception:
                continue
            sheet.paste(thumb, (x + (cell_w - thumb.width) // 2,
                                y + (cell_h - thumb.height) // 2))
            label = (f"#{candidate['rank']}  {candidate['item']}/{candidate['name']}  "
                     f"score {candidate['score']:.2f}")
            draw.text((x, y + cell_h + 6), label, font=font, fill="#FFE600")
        path = out_dir / f"{project}_thumbnail_candidates_{sheet_index:02d}.jpg"
        sheet.save(path, quality=90)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} thumbnail-candidates",
        description="Shortlist cropped panels worth compositing into a thumbnail, "
                    "with numbered contact sheets. Ranking is a proposal — open the "
                    "full-resolution candidates and choose by looking at them.",
    )
    from mediaconductor.video_pipeline.common import (
        DEFAULT_PROJECT_ROOT,
        DEFAULT_REVIEW_ROOT,
        expand_item_tokens,
        project_name,
    )

    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT,
                        help="Project folder containing item subfolders (data/library/<name>).")
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--items", nargs="*", help="Item folders, e.g. 01 02 03.")
    parser.add_argument("--item-range", help="Inclusive range, e.g. 01-12.")
    parser.add_argument("--top", type=int, default=20,
                        help="How many candidates to shortlist (default: 20).")
    parser.add_argument("--review-root", type=Path, default=DEFAULT_REVIEW_ROOT,
                        help="Where contact sheets are written (default: data/review).")
    parser.add_argument("--no-sheets", action="store_true",
                        help="Score only; skip contact-sheet rendering.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    args = parser.parse_args(argv)

    root = args.project_root
    if not root.is_dir():
        print(f"ERROR: project root not found: {root}", file=sys.stderr)
        return 1

    selection = list(args.items or [])
    if args.item_range:
        selection.append(args.item_range)
    items = expand_item_tokens(selection) if selection else None

    scored: list[dict] = []
    for item, panels in _panel_dirs(root, items):
        for panel in sorted(panels.iterdir()):
            if panel.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            measured = score_image(panel)
            if measured is not None:
                measured["item"] = item
                scored.append(measured)

    if not scored:
        print(f"ERROR: no cropped panels found under {root}"
              f"{' for the selected items' if items else ''}. Run the splitter first.",
              file=sys.stderr)
        return 1

    scored.sort(key=lambda entry: entry["score"], reverse=True)
    shortlist = scored[:max(1, args.top)]
    for rank, candidate in enumerate(shortlist, start=1):
        candidate["rank"] = rank

    project = project_name(root, args.project_name)
    sheets: list[Path] = []
    if not args.no_sheets:
        sheets = build_sheets(shortlist, args.review_root / project / "thumbnail-candidates",
                              project)

    payload = {
        "ok": True,
        "project": project,
        "panels_scored": len(scored),
        "candidates": shortlist,
        "sheets": [str(p) for p in sheets],
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"[thumbnail-candidates] scored {len(scored)} panel(s); top {len(shortlist)}:\n")
        for candidate in shortlist:
            print(f"  #{candidate['rank']:<3} {candidate['score']:.2f}  "
                  f"{candidate['item']}/{candidate['name']}  "
                  f"({candidate['width']}x{candidate['height']})")
            for note in candidate["notes"]:
                print(f"        note: {note}")
        for sheet in sheets:
            print(f"\n[sheet] {sheet}")
        print("\nRanking is a proposal, not a choice. Open the candidates at full "
              "resolution and pick the one whose beat the title actually promises.")
    emit_result(**payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
