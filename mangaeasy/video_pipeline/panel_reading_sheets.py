"""Render bounded multi-panel sheets for LLM panel reading before narration."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mangaeasy import fonts
from mangaeasy.brand import CLI_NAME
from mangaeasy.utils import emit_result
from mangaeasy.video_pipeline.item_assets import panel_filenames

MIN_PANELS_PER_SHEET = 3
MAX_PANELS_PER_SHEET = 8
DEFAULT_PANELS_PER_SHEET = 6
CELL_W = 620
CELL_H = 760
PAD = 18
HEADER_H = 52
SHEET_BG = (18, 18, 18)
CELL_BG = (32, 32, 32)


def _font(size: int, candidates: str = fonts.BOLD) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return fonts.load(size, candidates)


def clamp_per_sheet(value: int) -> int:
    return max(MIN_PANELS_PER_SHEET, min(MAX_PANELS_PER_SHEET, int(value)))


def sheet_grid(per_sheet: int) -> tuple[int, int]:
    per_sheet = clamp_per_sheet(per_sheet)
    cols = 2 if per_sheet <= 6 else 4
    rows = math.ceil(per_sheet / cols)
    return cols, rows


def _fit_panel(path: Path) -> Image.Image:
    with Image.open(path) as image:
        panel = image.convert("RGB")
    panel.thumbnail((CELL_W - 2 * PAD, CELL_H - HEADER_H - 2 * PAD), Image.LANCZOS)
    return panel


def render_sheet(item_dir: Path, names: list[str], sheet_index: int, per_sheet: int) -> Image.Image:
    cols, rows = sheet_grid(per_sheet)
    width = cols * CELL_W + (cols + 1) * PAD
    height = rows * CELL_H + (rows + 1) * PAD
    sheet = Image.new("RGB", (width, height), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    title_font = _font(28)
    label_font = _font(22)
    panels_dir = item_dir / "panels"

    for offset, name in enumerate(names):
        row, col = divmod(offset, cols)
        x = PAD + col * (CELL_W + PAD)
        y = PAD + row * (CELL_H + PAD)
        draw.rectangle((x, y, x + CELL_W, y + CELL_H), fill=CELL_BG, outline=(90, 90, 90), width=2)
        absolute_index = (sheet_index - 1) * per_sheet + offset + 1
        draw.text(
            (x + PAD, y + 12),
            f"{absolute_index:03d}  {name}",
            fill=(255, 232, 120),
            font=title_font,
        )
        panel = _fit_panel(panels_dir / name)
        px = x + (CELL_W - panel.width) // 2
        py = y + HEADER_H + (CELL_H - HEADER_H - panel.height) // 2
        sheet.paste(panel, (px, py))
        draw.text(
            (x + PAD, y + CELL_H - 32),
            "Read in order. Narration must cover this panel.",
            fill=(190, 190, 190),
            font=label_font,
        )
    return sheet


def _prune_old_sheets(out_dir: Path) -> None:
    for stale in out_dir.glob("reading_*.jpg"):
        stale.unlink(missing_ok=True)


def render_item_sheets(
    item_dir: Path,
    out_dir: Path,
    *,
    per_sheet: int = DEFAULT_PANELS_PER_SHEET,
) -> dict:
    per_sheet = clamp_per_sheet(per_sheet)
    names = panel_filenames(item_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _prune_old_sheets(out_dir)
    sheets: list[str] = []
    for start in range(0, len(names), per_sheet):
        chunk = names[start:start + per_sheet]
        sheet_index = start // per_sheet + 1
        sheet = render_sheet(item_dir, chunk, sheet_index, per_sheet)
        path = out_dir / f"reading_{sheet_index:03d}.jpg"
        sheet.save(path, quality=94, subsampling=0)
        sheets.append(str(path))
    return {
        "item": item_dir.name,
        "panels": len(names),
        "per_sheet": per_sheet,
        "sheets": sheets,
    }


def parse_args() -> argparse.Namespace:
    from mangaeasy.video_pipeline.common import DEFAULT_PROJECT_ROOT, DEFAULT_WORK_DIR

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} panel-reading-sheets",
        description="Render bounded multi-panel sheets for LLM pre-narration reading. "
                    "Panels per sheet are clamped to 3..8 so text stays readable.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--items", nargs="*")
    parser.add_argument("--item-range")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--output-root", type=Path, default=None,
                        help="Default: <work-dir>/panel_reading/<project-name>.")
    parser.add_argument("--per-sheet", type=int, default=DEFAULT_PANELS_PER_SHEET,
                        help="Panels per sheet, clamped to 3..8 (default 6).")
    return parser.parse_args()


def main() -> int:
    from mangaeasy.video_pipeline.common import item_dirs, merge_item_selection

    args = parse_args()
    project_root = args.project_root.resolve()
    selected = item_dirs(project_root, merge_item_selection(args.items, args.item_range))
    if not selected:
        print(f"[FATAL] No item folders found under {project_root}")
        return 1
    out_root = (args.output_root or args.work_dir / "panel_reading" / project_root.name).resolve()
    reports = []
    all_sheets: list[str] = []
    for index, item_dir in enumerate(selected, start=1):
        print(f"MANGAEASY_PROGRESS {index}/{len(selected)}", flush=True)
        report = render_item_sheets(item_dir, out_root / item_dir.name, per_sheet=args.per_sheet)
        reports.append(report)
        all_sheets.extend(report["sheets"])
        print(
            f"[{item_dir.name}] {report['panels']} panel(s) -> "
            f"{len(report['sheets'])} reading sheet(s)",
            flush=True,
        )
    emit_result(
        command="panel-reading-sheets",
        output_dir=out_root,
        sheets=all_sheets,
        items={report["item"]: report for report in reports},
    )
    return 0 if all_sheets else 1


if __name__ == "__main__":
    raise SystemExit(main())
