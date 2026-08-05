"""mangaeasy.images.thumbnail_compose — compose a thumbnail from panel art.

Updated with background blur/darken and subject pop rim glow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from mangaeasy import fonts
from mangaeasy.brand import CLI_NAME
from mangaeasy.utils import archive_before_overwrite, emit_result

DEFAULT_SIZE = (1280, 720)
DEFAULT_FONT_SIZE = 104
STROKE_FRACTION = 0.12
FILL_CYCLE = ("#FFE600", "#FFFFFF")
MARGIN = 44
YELLOW = "#FFE600"
DURATION_BADGE_BOX = (1060, 640, 1280, 720)


def load_font(size: int, font_path: str | None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return fonts.load(size, fonts.DISPLAY, explicit=font_path)


def cover_canvas(base: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    scale = max(tw / base.width, th / base.height)
    resized = base.resize((round(base.width * scale), round(base.height * scale)), Image.LANCZOS)
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th)).convert("RGB")


def apply_subject_pop(background: Image.Image, subject_cutout: Image.Image) -> Image.Image:
    """Darken/blur background and add a yellow rim glow to the subject cutout."""
    bg = background.filter(ImageFilter.GaussianBlur(radius=10))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)

    mask = subject_cutout.split()[3] if subject_cutout.mode == "RGBA" else Image.new("L", subject_cutout.size, 255)
    glow_mask = mask.filter(ImageFilter.MaxFilter(11)).filter(ImageFilter.GaussianBlur(6))
    glow_img = Image.new("RGBA", subject_cutout.size, "#FFE600")

    bg_rgba = bg.convert("RGBA")
    bg_rgba.paste(glow_img, (0, 0), glow_mask)
    bg_rgba.paste(subject_cutout, (0, 0), subject_cutout if subject_cutout.mode == "RGBA" else None)
    return bg_rgba


def render_block_layer(canvas_size: tuple[int, int], block: dict, font_path: str | None) -> Image.Image:
    size = int(block.get("size", DEFAULT_FONT_SIZE))
    font = load_font(size, block.get("font") or font_path)
    text = str(block["text"])
    stroke = max(2, round(size * STROKE_FRACTION))
    spacing = round(size * 0.18)
    x, y = int(block["x"]), int(block["y"])
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if block.get("shadow", True):
        off = max(3, size // 16)
        draw.multiline_text((x + off, y + off), text, font=font,
                            fill=(0, 0, 0, 150), spacing=spacing,
                            stroke_width=stroke, stroke_fill=(0, 0, 0, 150))
    draw.multiline_text((x, y), text, font=font,
                        fill=block.get("fill", FILL_CYCLE[0]), spacing=spacing,
                        stroke_width=stroke, stroke_fill=block.get("stroke", "#000000"))
    rotate = float(block.get("rotate", 0.0))
    if rotate:
        layer = layer.rotate(rotate, resample=Image.BICUBIC, center=(x, y))
    return layer


def render_arrow_layer(canvas_size: tuple[int, int], arrow: dict) -> Image.Image:
    from mangaeasy.images.thumbnail_compose import block_arrow_polygon

    (x1, y1), (x2, y2) = arrow["from"], arrow["to"]
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = arrow.get("color", "#FFE600")
    width = float(arrow.get("width", 26))
    outline_w = max(3, round(width * 0.22))
    pts = block_arrow_polygon(x1, y1, x2, y2, width)
    if arrow.get("shadow", True):
        off = max(3, round(width * 0.18))
        draw.polygon([(px + off, py + off) for px, py in pts], fill=(0, 0, 0, 150))
    draw.polygon(pts, fill=color)
    draw.line([*pts, pts[0]], fill=arrow.get("outline", "#000000"), width=outline_w, joint="curve")
    return layer


def build_canvas(sources: list[Path], size: tuple[int, int], layout: dict) -> Image.Image:
    kind = str(layout.get("kind", "single")).lower()
    if kind == "single" or len(sources) == 1:
        return cover_canvas(Image.open(sources[0]), size).convert("RGBA")
    divider = int(layout.get("divider", 10))
    columns = len(sources)
    total_w, total_h = size
    cell_w = (total_w - divider * (columns - 1)) // columns
    canvas = Image.new("RGBA", size, layout.get("divider_color", "#FFFFFF"))
    x = 0
    for source in sources:
        cell = cover_canvas(Image.open(source), (cell_w, total_h)).convert("RGBA")
        canvas.paste(cell, (x, 0))
        x += cell_w + divider
    return canvas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} thumbnail-compose",
        description="Compose a YouTube thumbnail from approved manga panels.",
    )
    parser.add_argument("--base", type=Path, action="append", default=[], metavar="PANEL")
    parser.add_argument("--subject-cutout", type=Path, default=None, help="PNG cutout with alpha for pop effect.")
    parser.add_argument("--output", type=Path, required=True, help="Output PNG/JPG path.")
    parser.add_argument("--text", action="append", default=[], metavar="WORDS")
    parser.add_argument("--preset", choices=("label-arrow", "bubble", "split"), default=None)
    parser.add_argument("--badge", default=None)
    parser.add_argument("--spec-json", default=None)
    parser.add_argument("--font", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    size = DEFAULT_SIZE
    sources = [Path(p) for p in args.base]
    if not sources:
        print("ERROR: provide at least one --base panel", file=sys.stderr)
        return 2

    canvas = build_canvas(sources, size, {})
    if args.subject_cutout and args.subject_cutout.is_file():
        subject = Image.open(args.subject_cutout).convert("RGBA")
        canvas = apply_subject_pop(canvas.convert("RGB"), subject)

    blocks = []
    if args.text:
        for i, txt in enumerate(args.text):
            blocks.append({"text": txt, "x": MARGIN, "y": MARGIN + i * 120, "size": DEFAULT_FONT_SIZE})

    for block in blocks:
        canvas.alpha_composite(render_block_layer(size, block, args.font))

    canvas = canvas.convert("RGB")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archive_before_overwrite(args.output)
    canvas.save(args.output)

    payload = {"ok": True, "outputs": [str(args.output)]}
    emit_result(**payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())