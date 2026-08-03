"""mangaeasy.panels.page
Item-pipeline paged-manga splitter with verification output (`mangaeasy page-split`).

This is the paged-manga counterpart to `webtoon-split`. Where `webtoon-split`
finds gutters in one tall vertical strip, `page-split` runs **MAGI v3** panel
detection on each page, sorts the boxes into manga reading order, crops them,
and — like the webtoon splitter — writes verification artifacts so a
vision-capable reviewer can locate issues. Approval still requires opening
every overlay and every actual crop at readable/full resolution.

It exists to retire the copy-paste scratch scripts that used to live inside
docs/recap-video-playbook.md (Phases 2–3). MAGI is never fully trusted: in the
reference production it was wrong on ~4 of 61 pages (whole-page boxes, merged
panels, a missed column), so the verification overlays and the `--overrides`
escape hatch are load-bearing, not optional.

Pipeline per item:
  1. list pages in <item>/<source-subdir> (default: download/) in reading order
  2. run MAGI v3 once over the whole item in the external magi-v3 tool env
     (via assets/tools/batch_detect_magi.py) -> a detections.json
  3. per page: take MAGI's boxes (or a per-page override), clamp, sort into
     reading order, crop, save as <panels-subdir>/<item>_<page>_<panel>.jpg
  4. write verification images: a numbered box overlay per page + a contact
     sheet of every crop, plus the raw detections.json for crafting overrides
  5. print a per-item report (panels / suspect pages) + the standard
     MANGAEASY_PROGRESS / MANGAEASY_RESULT markers

Suspect pages (always eyeball these against the overlay before narration):
  * a page where MAGI found no panels -> no production crop until overridden
  * a page whose automatic single box covers most of the sheet -> no
    production crop until deliberate manual boxes are supplied

Every crop must fully contain its panel — never a partial edge, never the
whole page standing in for a panel that has its own border. A box far taller
than it is wide (>= TALL_PANEL_ASPECT_RATIO, reported as `tall_panel_boxes`)
usually swallowed gutter whitespace above/below the art instead of hugging
it; check it against the overlay and, if so, tighten it with --overrides —
the final video frame is 16:9 landscape, so a needlessly tall crop just
shrinks to a narrow sliver once fit to it. A squarish (1:1) crop is fine;
only trim when the excess is gutter, not when the panel is genuinely that
tall (e.g. a full-body action shot).

Fix a bad page with --overrides: a JSON file keyed by the page's filename whose
value is a list of [x1, y1, x2, y2] pixel boxes that fully replace MAGI's boxes
for that page, e.g. {"01_09.jpg": [[0, 0, 900, 700], [0, 700, 900, 1400]]}.
Overlapping override boxes are fine and often correct (diagonal borders).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess

from mangaeasy import runtime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from mangaeasy import fonts
from mangaeasy.brand import CLI_NAME
from mangaeasy.panels.ai import _clamp_box, _manga_reading_order
from mangaeasy.panels.gutter import collect_image_paths
from mangaeasy.panels.webtoon import _archive_existing_panels, _split_exit_code, write_contact_sheets
from mangaeasy.tools.external import python_command, resolve_tool_dir, tool_env
from mangaeasy.utils import emit_result

Image.MAX_IMAGE_PIXELS = None

Box = Dict[str, int]

# A single detected box covering at least this fraction of the page area is
# sometimes a real cover/splash, and sometimes MAGI returning the whole page
# instead of splitting it. Treat it as a review class, not a universal error.
FULL_PAGE_AREA_FRAC = 0.85
COVER_PAGE_RE = re.compile(r"(?:^|[_\-. ])(?:cover|front|title|splash)(?:$|[_\-. ])", re.IGNORECASE)

# height/width past this usually means the box swallowed gutter whitespace
# above/below the actual panel art rather than hugging it. The final video
# frame is 16:9 landscape; a needlessly tall crop just shrinks to a narrow
# sliver in the middle of it once fit to that frame — a square (1:1) crop
# still reads fine, this only flags crops well past that. Informational, not
# a suspect: many panels are legitimately tall (a full-body action shot), so
# this is a hint for a human or vision-capable crop reviewer to check whether
# the excess is trimmable gutter, not an automatic failure.
TALL_PANEL_ASPECT_RATIO = 2.2

# Where the shipped batch-detect adapter lives inside the package (fallback if
# it was not copied into the tool env, e.g. an env installed before it shipped).
_PACKAGED_BATCH_SCRIPT = (
    Path(__file__).resolve().parents[1] / "assets" / "tools" / "batch_detect_magi.py"
)


def _load_font(size: int) -> ImageFont.ImageFont:
    return fonts.load(size, fonts.BOLD)


def _resolve_batch_script(magi_dir: Path) -> Optional[Path]:
    installed = magi_dir / "batch_detect_magi.py"
    if installed.exists():
        return installed
    if _PACKAGED_BATCH_SCRIPT.exists():
        return _PACKAGED_BATCH_SCRIPT
    return None


def run_batch_detect(
    pages_dir: Path, out_path: Path, *, device: str = "auto", dtype: str = "auto"
) -> Optional[Dict[str, dict]]:
    """Run MAGI v3 over every page in `pages_dir`, streaming progress.

    Returns the parsed detections mapping {page_name: {size, panels}} or None
    if the tool env / model run was unavailable.
    """
    magi_dir = resolve_tool_dir("magi-v3", required=False)
    if magi_dir is None:
        print(
            "[page-split] MAGI v3 tool env not found. Install it with "
            f"`{CLI_NAME} install-tool magi-v3`.",
            flush=True,
        )
        return None
    script = _resolve_batch_script(magi_dir)
    if script is None:
        print("[page-split] batch_detect_magi.py missing (reinstall magi-v3).", flush=True)
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        *python_command(magi_dir),
        str(script),
        str(pages_dir),
        "--out", str(out_path),
        "--device", device,
        "--dtype", dtype,
    ]
    proc = runtime.popen(
        cmd, cwd=magi_dir, env=tool_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line.rstrip(), flush=True)
    code = proc.wait()
    if code != 0 or not out_path.exists():
        print(f"[page-split] MAGI batch detection failed (exit {code}).", flush=True)
        return None
    try:
        return json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[page-split] could not read detections: {exc}", flush=True)
        return None


def boxes_for_page(
    detection: dict | None, override: Sequence | None, width: int, height: int
) -> Tuple[List[Box], bool]:
    """Resolve, clamp and reading-order the boxes for one page.

    Returns (boxes, manual_crop_required). If nothing usable is found no
    production box is returned: a whole source page must never silently become
    a panel just because MAGI failed. The caller still renders the source-page
    overlay so a reviewer can supply deliberate boxes.
    """
    raw = list(override) if override is not None else list((detection or {}).get("panels", []))
    boxes = [b for entry in raw if (b := _clamp_box(entry, width, height))]
    if not boxes:
        return [], True
    return boxes, False


def is_likely_single_panel_page(page_path: Path, page_no: int) -> bool:
    """True for automatic full-page boxes that are plausible cover/splash art.

    A full-page crop in the middle of a chapter is risky: it can hide several
    bordered panels inside one video beat. The first page, or a filename that
    explicitly says cover/title/splash/front, is different enough to keep as a
    production crop while still requiring visual review.
    """
    return page_no == 1 or COVER_PAGE_RE.search(page_path.stem) is not None


def write_page_overlay(
    page_img: Image.Image,
    boxes: List[Box],
    dest: Path,
    *,
    max_side: int = 1800,
    review_message: str = "MANUAL VISUAL REVIEW REQUIRED",
) -> None:
    """Save a downscaled copy of the page with numbered red panel boxes."""
    overlay = page_img.convert("RGB").copy()
    draw = ImageDraw.Draw(overlay)
    font = _load_font(max(28, overlay.width // 22))
    for k, b in enumerate(boxes, 1):
        draw.rectangle([b["x1"], b["y1"], b["x2"], b["y2"]], outline=(255, 40, 40), width=max(4, overlay.width // 220))
        draw.text(
            (b["x1"] + 12, b["y1"] + 8), str(k), fill=(255, 40, 40), font=font,
            stroke_width=3, stroke_fill=(255, 255, 255),
        )
    # Every generated crop needs eyes on it. In particular, an empty overlay
    # must be unmistakably actionable rather than looking like an intentionally
    # accepted whole-page panel.
    border = max(6, overlay.width // 120)
    banner_h = max(64, overlay.height // 10)
    framed = Image.new(
        "RGB",
        (overlay.width + 2 * border, overlay.height + banner_h + 2 * border),
        (180, 0, 0),
    )
    framed.paste(overlay, (border, border + banner_h))
    framed_draw = ImageDraw.Draw(framed)
    framed_draw.text(
        (border + 12, border + 8),
        review_message,
        fill=(255, 255, 255),
        font=font,
        stroke_width=2,
        stroke_fill=(80, 0, 0),
    )
    overlay = framed
    overlay.thumbnail((max_side, max_side))
    dest.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(dest)


def process_item(item_dir: Path, args, overrides: Dict, verify_dir: Path) -> Dict:
    item = item_dir.name
    source_dir = item_dir / args.source_subdir
    panels_dir = item_dir / args.panels_subdir
    paths = collect_image_paths(source_dir, sort_mode=args.sort) if source_dir.is_dir() else []
    if not paths:
        print(f"[{item}] SKIP: no images in {source_dir}", flush=True)
        return {"item": item, "status": "skipped", "review_required": True}

    if not args.force_style:
        from mangaeasy.panels.style_detect import style_guard

        ok, guard_message = style_guard(source_dir, "paged")
        print(f"[{item}] {guard_message}", flush=True)
        if not ok:
            return {
                "item": item,
                "status": "error",
                "reason": "style_mismatch",
                "review_required": True,
            }

    item_verify = verify_dir / item
    item_verify.mkdir(parents=True, exist_ok=True)
    for stale in item_verify.glob(f"{item}_page_*.png"):
        stale.unlink(missing_ok=True)
    detections = run_batch_detect(
        source_dir, item_verify / f"{item}_detections.json",
        device=args.device, dtype=args.dtype,
    )
    if detections is None:
        return {
            "item": item,
            "status": "error",
            "reason": "detection_failed",
            "review_required": True,
        }

    rtl = None if args.reading_direction == "auto" else (args.reading_direction == "rtl")
    item_overrides = overrides.get(item, {})

    archived = _archive_existing_panels(panels_dir)
    panels_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix_template.format(item=item)

    crops: List[Tuple[int, Image.Image]] = []
    review_crops: List[str] = []
    suspects: List[str] = []
    full_page_boxes: List[str] = []
    full_page_candidates: List[str] = []
    tall_panel_boxes: List[str] = []
    total_panels = 0
    crop_index = 0
    for page_no, page_path in enumerate(paths, 1):
        img = Image.open(page_path).convert("RGB")
        W, H = img.size
        override = item_overrides.get(page_path.name)
        boxes, manual_crop_required = boxes_for_page(
            detections.get(page_path.name), override, W, H
        )
        boxes = _manga_reading_order(boxes, rtl=rtl)
        crop_boxes = boxes
        review_message = "MANUAL VISUAL REVIEW REQUIRED"

        if manual_crop_required:
            suspects.append(f"{page_path.name} no-panels")
            crop_boxes = []
            review_message = "NO USABLE BOXES - MANUAL CROP REQUIRED"
        elif len(boxes) == 1:
            b = boxes[0]
            if (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) >= FULL_PAGE_AREA_FRAC * W * H:
                full_page_boxes.append(f"{page_path.name} full-page-box")
                if override is None:
                    if is_likely_single_panel_page(page_path, page_no):
                        # Covers/title pages/splashes can genuinely be one
                        # page-sized panel. Keep them in production so the
                        # chapter does not lose its opening art, but keep them
                        # listed for review because MAGI is still only a
                        # proposal.
                        full_page_candidates.append(
                            f"{page_path.name} likely-cover-or-splash")
                        review_message = "FULL-PAGE CANDIDATE - VERIFY SINGLE PANEL"
                    else:
                        # A normal mid-chapter automatic full-page box is not
                        # trustworthy: it may hide multiple story panels.
                        # Keep it visible on the overlay, but never promote it
                        # to production without deliberate manual boxes.
                        suspects.append(f"{page_path.name} automatic-full-page-box")
                        crop_boxes = []
                        review_message = "AUTOMATIC FULL-PAGE BOX - MANUAL CROP REQUIRED"
                else:
                    # A reviewer may deliberately preserve true splash art via
                    # an override, but the result still remains review-listed.
                    review_message = "FULL-PAGE OVERRIDE - MANUAL REVIEW REQUIRED"

        for panel_no, b in enumerate(crop_boxes, 1):
            crop = img.crop((b["x1"], b["y1"], b["x2"], b["y2"]))
            name = f"{prefix}{page_no:03d}_{panel_no:02d}.jpg"
            crop_path = panels_dir / name
            crop.save(crop_path, "JPEG", quality=95, optimize=True)
            review_crops.append(str(crop_path.resolve()))
            crop_index += 1
            crops.append((crop_index, crop))
            total_panels += 1

            width, height = b["x2"] - b["x1"], b["y2"] - b["y1"]
            if width > 0 and height / width >= TALL_PANEL_ASPECT_RATIO:
                tall_panel_boxes.append(
                    f"{page_path.name}#{panel_no} tall-crop ({height / width:.1f}:1)")

        write_page_overlay(
            img,
            boxes,
            item_verify / f"{item}_page_{page_no:03d}.png",
            review_message=review_message,
        )

    write_contact_sheets(item, crops, item_verify)

    print(
        f"[{item}] pages={len(paths)} panels={total_panels} "
        f"suspects={suspects if suspects else 'none'}"
        + (f" full_page_boxes={len(full_page_boxes)}" if full_page_boxes else "")
        + (f" full_page_candidates={len(full_page_candidates)}" if full_page_candidates else "")
        + (f" tall_panel_boxes={len(tall_panel_boxes)}" if tall_panel_boxes else "")
        + (f" archived_previous={archived}" if archived else ""),
        flush=True,
    )
    return {
        "item": item,
        "status": "ok",
        "review_required": True,
        "pages": len(paths),
        "panels": total_panels,
        "suspects": suspects,
        # Single-box full pages always stay review-listed. Automatic boxes are
        # withheld from production; an explicit override can preserve a real
        # splash/title page but does not waive visual review.
        "full_page_boxes": full_page_boxes,
        # Automatic full-page crops that were kept because they look like a
        # cover/title/front/splash page. They are production crops, but still
        # review-listed before narration.
        "full_page_candidates": full_page_candidates,
        # Crops far taller than wide (>= TALL_PANEL_ASPECT_RATIO) — often a
        # box that swallowed gutter above/below the panel art instead of
        # hugging it. Check against the page overlay: if it's gutter, trim it
        # with --overrides so the crop reads well once fit to the 16:9 video
        # frame; if the panel genuinely is that tall (a full-body action
        # shot), leave it.
        "tall_panel_boxes": tall_panel_boxes,
        "source_images": [str(path.resolve()) for path in paths],
        # Sheets/overlays are indexes. The full-resolution crops below are the
        # actual production pixels a reviewer must open one by one.
        "review_crops": review_crops,
        "verify_images": sorted(str(p) for p in item_verify.glob(f"{item}_*.png")),
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    from mangaeasy.path_safety import portable_prefix_template_arg, relative_subpath_arg
    from mangaeasy.video_pipeline.common import DEFAULT_PROJECT_ROOT, DEFAULT_WORK_DIR

    parser = argparse.ArgumentParser(
        description="Split paged manga into panels with MAGI v3 detection and "
                    "verification sheets (item-pipeline layout)."
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT,
                        help="Project folder containing item subfolders (data/library/<name>).")
    parser.add_argument("--items", nargs="*", help="Item folders, e.g. 01 02 05-08.")
    parser.add_argument("--item-range", help="Inclusive item range, e.g. 01-19.")
    parser.add_argument("--source-subdir", type=relative_subpath_arg, default="download",
                        help="Subfolder inside each item with the raw pages (default: download).")
    parser.add_argument("--panels-subdir", type=relative_subpath_arg, default="panels",
                        help="Subfolder inside each item to write crops to (default: panels).")
    parser.add_argument("--verify-root", type=Path, default=None,
                        help="Where to write verification sheets "
                             "(default: <work-dir>/page_verify/<project-name>).")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--prefix-template", type=portable_prefix_template_arg, default="{item}_",
                        help="Crop filename prefix; '{item}' expands to the item name.")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--dtype", default="auto", choices=["auto", "fp16", "fp32"])
    parser.add_argument("--reading-direction", default="auto", choices=["auto", "rtl", "ltr"],
                        help="Panel reading order (default: auto = system config; "
                             "rtl for Japanese, ltr for Chinese/Korean).")
    parser.add_argument("--sort", default="numeric", choices=["numeric", "lex"])
    parser.add_argument("--overrides", type=Path, default=None,
                        help="JSON keyed by item -> {page filename: [[x1,y1,x2,y2], ...]} "
                             "that fully replace MAGI's boxes for that page.")
    parser.add_argument("--force-style", action="store_true",
                        help="Skip the webtoon-vs-paged pre-flight guard (only for deliberate "
                             "mixed-format items; wrong-splitter output is never usable).")
    parser.add_argument("--respect-claims", action="store_true",
                        help="Abort (exit 1) if another live agent's workboard claim covers any "
                             "selected item at this stage (see docs/multi-agent.md).")
    parser.add_argument("--agent", default=None,
                        help="This agent's identity for --respect-claims "
                             "(default: $MANGAEASY_AGENT or user@host).")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    from mangaeasy.video_pipeline.common import item_dirs, merge_item_selection

    args = parse_args(argv)
    if args.respect_claims:
        from mangaeasy.workboard import respect_claims_gate

        if not respect_claims_gate(args.project_root, args.items, args.item_range, ("crop",), args.agent):
            return 1
    project_root = args.project_root.resolve()
    if args.reading_direction == "auto":
        from mangaeasy.panels.direction import project_reading_direction

        args.reading_direction, reason = project_reading_direction(project_root)
        print(f"[page-split] reading direction: {args.reading_direction} ({reason})", flush=True)
    selection = merge_item_selection(args.items, args.item_range)
    selected = item_dirs(project_root, selection)
    if not selected:
        print(f"[FATAL] No item folders found under {project_root}")
        return 1

    overrides: Dict = {}
    if args.overrides and args.overrides.exists():
        overrides = json.loads(args.overrides.read_text(encoding="utf-8"))

    verify_dir = (
        args.verify_root
        if args.verify_root
        else args.work_dir / "page_verify" / project_root.name
    ).resolve()
    verify_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    for i, item_dir in enumerate(selected, 1):
        print(f"MANGAEASY_PROGRESS {i}/{len(selected)}", flush=True)
        reports.append(process_item(item_dir, args, overrides, verify_dir))

    emit_result(
        command="page-split",
        project=project_root.name,
        verify_dir=verify_dir,
        items=reports,
        review_required=True,
    )
    return _split_exit_code(reports)


if __name__ == "__main__":
    raise SystemExit(main())
