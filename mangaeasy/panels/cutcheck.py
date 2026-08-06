"""mangaeasy.panels.cutcheck — full-resolution crop-review windows ("virtual windows").

``mangaeasy webtoon-cutcheck`` renders, for every forced auto-split cut and
every short panel recorded in an item's ranges manifest (written by
``webtoon-split``), a full-resolution window of the stitched source strip
around that location, with the cut / panel boundaries drawn on top. Windows
are montaged into fixed-column review sheets that an agent Reads one by one.

This is the QA pass that catches half panels, fused stuck-together panels and
sliced speech bubbles *before* narration/audio are built on top of bad crops —
judge every flagged location on the actual art, never on downscaled contact
sheets. Production verdict guide:

- FIX (add a ``merge`` override; see the manifest's ``merge_note``): the cut
  passes through a figure or a speech bubble, or a short panel is a bubble /
  SFX fragment whose art continues into a neighbour.
- ACCEPT: cuts through background or effect art, bordered thin scenery
  panels, scanlator promo banners (skip those in narration instead).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mangaeasy import fonts
from mangaeasy.brand import CLI_NAME
from mangaeasy.panels.gutter import collect_image_paths, stitch_images
from mangaeasy.utils import emit_result

RED = (255, 0, 0)
GREEN = (0, 200, 0)
ORANGE = (255, 140, 0)

def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return fonts.load(size, fonts.BOLD)


def stitch_pages(source_dir: Path, sort_mode: str = "numeric") -> Image.Image:
    """Stitch an item's raw pages into one strip, same geometry as webtoon-split."""
    pages = collect_image_paths(source_dir, sort_mode=sort_mode)
    if not pages:
        raise FileNotFoundError(f"no source pages under {source_dir}")
    return stitch_images(pages)


def prune_item_artifacts(out_dir: Path, item: str) -> None:
    """Remove only review files owned by this item before regenerating them."""
    for pattern in (
        f"{item}_cut_*.jpg",
        f"{item}_short_*.jpg",
        f"{item}_withheld_*.jpg",
    ):
        for stale in out_dir.glob(pattern):
            stale.unlink(missing_ok=True)


def parse_forced_cuts(manifest: dict) -> list[int]:
    cuts = []
    for token in manifest.get("forced_cuts", []):
        m = re.match(r"y=(\d+)", str(token))
        if m:
            cuts.append(int(m.group(1)))

    # ``forced_cuts`` records the splitter's original auto-cut candidates so
    # agents can resolve overrides against stable stitched-strip coordinates.
    # Once overrides merge one of those boundaries away, however, it is no
    # longer a cut in the generated panels and must not be presented to crop
    # QA again.  Otherwise the documented split -> QA -> override loop can
    # never reach a clean exit: the model keeps reviewing a red line that no
    # longer exists in ``final``.
    if manifest.get("overrides_applied") and isinstance(manifest.get("final"), list):
        final_tops = {
            int(panel["top"])
            for panel in manifest["final"]
            if isinstance(panel, dict) and "top" in panel
        }
        final_bottoms = {
            int(panel["bottom"])
            for panel in manifest["final"]
            if isinstance(panel, dict) and "bottom" in panel
        }
        live_boundaries = final_tops & final_bottoms
        cuts = [y for y in cuts if y in live_boundaries]
    return cuts


def window_bounds(y_top: int, y_bottom: int, strip_height: int, margin: int) -> tuple[int, int]:
    return max(0, y_top - margin), min(strip_height, y_bottom + margin)


def render_window(strip: Image.Image, top: int, bottom: int, thumb_width: int,
                  marks: list[tuple[int, tuple, str]]) -> Image.Image:
    win = strip.crop((0, top, strip.width, bottom)).copy()
    draw = ImageDraw.Draw(win)
    font = _load_font(max(18, strip.width // 40))
    for y, color, label in marks:
        ly = y - top
        draw.line([(0, ly), (win.width, ly)], fill=color, width=5)
        draw.text((10, min(max(0, ly + 6), win.height - 30)), label, fill=color, font=font)
    if thumb_width > 0 and win.width > thumb_width:
        win = win.resize((thumb_width, round(win.height * thumb_width / win.width)))
    return win


def montage(windows: list[tuple[str, Image.Image]], columns: int, pad: int = 14,
            header_h: int = 40) -> Image.Image:
    cols = windows[:columns]
    cell_w = max(im.width for _, im in cols)
    cell_h = max(im.height for _, im in cols) + header_h
    sheet = Image.new("RGB", (columns * (cell_w + pad) + pad, cell_h + 2 * pad), "black")
    draw = ImageDraw.Draw(sheet)
    font = _load_font(28)
    for i, (name, im) in enumerate(cols):
        x = pad + i * (cell_w + pad)
        draw.text((x + 4, pad), name, fill=(255, 230, 0), font=font)
        sheet.paste(im, (x, pad + header_h))
    return sheet


def _cutcheck_exit_code(per_item: dict[str, dict]) -> int:
    """Return review-required unless artifact generation actually failed."""
    return 1 if any("error" in report for report in per_item.values()) else 3


def parse_args() -> argparse.Namespace:
    from mangaeasy.path_safety import relative_subpath_arg
    from mangaeasy.video_pipeline.common import DEFAULT_PROJECT_ROOT, DEFAULT_WORK_DIR

    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} webtoon-cutcheck",
        description="Render full-resolution review windows around every forced cut and "
                    "short panel from a webtoon-split ranges manifest.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--items", nargs="*", help="Item folders, e.g. 01 02 05-08.")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-07.")
    parser.add_argument("--source-subdir", type=relative_subpath_arg, default="download")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--verify-root", type=Path, default=None,
                        help="Where webtoon-split wrote <item>_ranges.json "
                             "(default: <work-dir>/webtoon_verify/<project-name>).")
    parser.add_argument("--output-root", type=Path, default=None,
                        help="Where to write windows and sheets "
                             "(default: <work-dir>/cutcheck/<project-name>).")
    parser.add_argument("--window", type=int, default=650,
                        help="Rows of context above/below each flagged location (default 650).")
    parser.add_argument("--short-height", type=int, default=460,
                        help="Panels shorter than this get a review window (default 460).")
    parser.add_argument("--thumb-width", type=int, default=960,
                        help="Width of each sheet preview (default 960); individual "
                             "review windows remain at source resolution.")
    parser.add_argument("--columns", type=int, default=3, help="Windows per sheet (default 3).")
    return parser.parse_args()


def main() -> int:
    from mangaeasy.video_pipeline.common import item_dirs, merge_item_selection, DEFAULT_WORK_DIR

    args = parse_args()
    project_root = args.project_root.resolve()
    selected = item_dirs(project_root, merge_item_selection(args.items, args.item_range))
    if not selected:
        print(f"[FATAL] No item folders found under {project_root}")
        return 1

    effective_work = (project_root / "work") if args.work_dir.resolve() == DEFAULT_WORK_DIR.resolve() else args.work_dir
    verify_dir = (args.verify_root or effective_work / "webtoon_verify").resolve()
    out_dir = (args.output_root or effective_work / "cutcheck").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("sheet_*.jpg"):
        stale.unlink(missing_ok=True)

    windows: list[tuple[str, Image.Image]] = []
    review_windows: list[str] = []
    per_item: dict[str, dict] = {}
    for i, item_dir in enumerate(selected, 1):
        print(f"MANGAEASY_PROGRESS {i}/{len(selected)}", flush=True)
        item = item_dir.name
        prune_item_artifacts(out_dir, item)
        manifest_path = verify_dir / f"{item}_ranges.json"
        if not manifest_path.is_file():
            print(f"[{item}] no ranges manifest at {manifest_path} — run webtoon-split first")
            per_item[item] = {"error": "missing manifest"}
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sort_mode = str(manifest.get("sort") or "numeric")
        if sort_mode not in {"numeric", "lex"}:
            sort_mode = "numeric"
        source_dir = item_dir / args.source_subdir
        source_images = collect_image_paths(source_dir, sort_mode=sort_mode)
        strip = stitch_pages(source_dir, sort_mode=sort_mode)
        cuts = parse_forced_cuts(manifest)
        shorts = [p for p in manifest.get("final", [])
                  if p.get("height", 0) < args.short_height]
        for y in cuts:
            top, bottom = window_bounds(y, y, strip.height, args.window)
            name = f"{item}_cut_y{y}"
            win = render_window(strip, top, bottom, 0,
                                [(y, RED, f"CUT y={y}")])
            window_path = out_dir / f"{name}.jpg"
            win.save(window_path, quality=95, subsampling=0)
            review_windows.append(str(window_path))
            windows.append((name, render_window(
                strip, top, bottom, args.thumb_width, [(y, RED, f"CUT y={y}")],
            )))
        for panel in shorts:
            top, bottom = window_bounds(panel["top"], panel["bottom"], strip.height, args.window)
            name = f"{item}_short_p{panel['index']:03d}"
            marks = [
                (panel["top"], GREEN, f"#{panel['index']} top y={panel['top']}"),
                (panel["bottom"], ORANGE, f"#{panel['index']} bottom y={panel['bottom']}"),
            ]
            win = render_window(strip, top, bottom, 0, marks)
            window_path = out_dir / f"{name}.jpg"
            win.save(window_path, quality=95, subsampling=0)
            review_windows.append(str(window_path))
            windows.append((name, render_window(
                strip, top, bottom, args.thumb_width, marks,
            )))
        withheld_tiles: list[str] = []
        if manifest.get("withheld_reason"):
            for tile_index, top in enumerate(range(0, strip.height, 4000), 1):
                bottom = min(strip.height, top + 4000)
                name = f"{item}_withheld_t{tile_index:03d}"
                tile = render_window(strip, top, bottom, 0, [])
                tile_path = out_dir / f"{name}.jpg"
                tile.save(tile_path, quality=95, subsampling=0)
                withheld_tiles.append(str(tile_path))
                review_windows.append(str(tile_path))
                windows.append((
                    name,
                    render_window(strip, top, bottom, args.thumb_width, []),
                ))
        per_item[item] = {
            "forced_cuts": len(cuts),
            "short_panels": len(shorts),
            "withheld_reason": manifest.get("withheld_reason"),
            "withheld_source_tiles": withheld_tiles,
            "source_images": [str(path.resolve()) for path in source_images],
        }
        print(
            f"[{item}] windows: {len(cuts)} cut(s), {len(shorts)} short panel(s), "
            f"{len(withheld_tiles)} withheld-source tile(s)",
            flush=True,
        )

    sheets = []
    for n in range(0, len(windows), args.columns):
        sheet = montage(windows[n:n + args.columns], args.columns)
        sheet_path = out_dir / f"sheet_{n // args.columns + 1:02d}.jpg"
        sheet.save(sheet_path, quality=95, subsampling=0)
        sheets.append(str(sheet_path))
    print(f"{len(windows)} window(s) -> {len(sheets)} sheet(s) under {out_dir}")
    print("Use the sheets as an index, then open EVERY individual window at full "
          "source resolution; judge each flagged location on the art "
          "(FIX = figure/bubble cut; ACCEPT = background/banner/bordered thin panel).")
    emit_result(command="webtoon-cutcheck", output_dir=out_dir, windows=len(windows),
                review_windows=review_windows, sheets=sheets, items=per_item,
                review_required=True)
    return _cutcheck_exit_code(per_item)


if __name__ == "__main__":
    raise SystemExit(main())