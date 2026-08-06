"""mangaeasy.images.thumbnail_compose — compose a thumbnail from panel art."""

from __future__ import annotations

import argparse
import json
import math
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


def load_font(
    size: int, font_path: str | None
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return fonts.load(size, fonts.DISPLAY, explicit=font_path)


def cover_canvas(base: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    scale = max(tw / base.width, th / base.height)
    resized = base.resize(
        (round(base.width * scale), round(base.height * scale)), Image.LANCZOS
    )
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th)).convert("RGB")


def apply_subject_pop(
    background: Image.Image, subject_cutout: Image.Image
) -> Image.Image:
    """Darken/blur background and add a yellow rim glow to the subject cutout."""
    bg = background.filter(ImageFilter.GaussianBlur(radius=10))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)

    mask = (
        subject_cutout.split()[3]
        if subject_cutout.mode == "RGBA"
        else Image.new("L", subject_cutout.size, 255)
    )
    glow_mask = mask.filter(ImageFilter.MaxFilter(11)).filter(
        ImageFilter.GaussianBlur(6)
    )
    glow_img = Image.new("RGBA", subject_cutout.size, "#FFE600")

    bg_rgba = bg.convert("RGBA")
    bg_rgba.paste(glow_img, (0, 0), glow_mask)
    bg_rgba.paste(
        subject_cutout,
        (0, 0),
        subject_cutout if subject_cutout.mode == "RGBA" else None,
    )
    return bg_rgba


def block_arrow_polygon(
    x1: float, y1: float, x2: float, y2: float, width: float
) -> list[tuple[float, float]]:
    """Return 7-point polygon coordinates for a block arrow from (x1, y1) to (x2, y2)."""
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-3:
        return [(x1, y1)] * 7

    angle = math.atan2(dy, dx)
    head_len = max(width * 1.5, min(30.0, length * 0.4))
    head_w = width * 2.0
    shaft_len = length - head_len

    # Arrow shape in local horizontal coordinates (pointing right)
    local_pts = [
        (0.0, -width / 2.0),
        (shaft_len, -width / 2.0),
        (shaft_len, -head_w / 2.0),
        (length, 0.0),
        (shaft_len, head_w / 2.0),
        (shaft_len, width / 2.0),
        (0.0, width / 2.0),
    ]

    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    pts = []
    for lx, ly in local_pts:
        rx = x1 + lx * cos_a - ly * sin_a
        ry = y1 + lx * sin_a + ly * cos_a
        pts.append((rx, ry))
    return pts


def preset_spec(
    preset: str,
    texts: list[str],
    canvas_size: tuple[int, int] = DEFAULT_SIZE,
    has_badge: bool = False,
) -> dict:
    """Generate preset dictionary spec for label-arrow, bubble, or split."""
    tw, th = canvas_size
    first_text = texts[0] if texts else "HOOK"

    if preset == "label-arrow":
        x = 140 if has_badge else MARGIN
        blocks = []
        for i, txt in enumerate(texts or ["HOOK"]):
            blocks.append({
                "text": txt,
                "x": x,
                "y": MARGIN + i * 110,
                "size": 104,
                "rotate": -3,
                "fill": YELLOW,
            })
        arrows = [{
            "from": [x + 130, 150],
            "to": [x + 260, 250],
            "width": 30,
            "color": YELLOW,
            "style": "block",
        }]
        return {"blocks": blocks, "arrows": arrows}

    elif preset == "bubble":
        return {
            "bubbles": [{
                "text": first_text,
                "center": [270, 260],
                "rx": 168,
                "ry": 196,
                "style": "dark",
                "tail": [410, 450],
                "size": 56,
            }]
        }

    elif preset == "split":
        txt1 = texts[0] if len(texts) > 0 else "WEAK"
        txt2 = texts[1] if len(texts) > 1 else "STRONG"
        return {
            "layout": {"kind": "split"},
            "blocks": [
                {"text": txt1, "x": MARGIN, "y": 580, "size": 90},
                {"text": txt2, "x": 680, "y": 580, "size": 90},
            ],
        }

    return {}


def check_composition(
    layout: dict,
    blocks: list[dict],
    arrows: list[dict],
    canvas_size: tuple[int, int] = DEFAULT_SIZE,
    badge: dict | None = None,
) -> list[str]:
    """Validate text bounds, font sizes (>= 44px), canvas containment, and badge collisions."""
    problems: list[str] = []
    cw, ch = canvas_size

    # Duration badge box on YouTube: (1060, 640, 1280, 720)
    db_x1, db_y1, db_x2, db_y2 = DURATION_BADGE_BOX

    boxes: list[tuple[int, int, int, int, str]] = []

    for idx, block in enumerate(blocks):
        size = int(block.get("size", DEFAULT_FONT_SIZE))
        if size < 44:
            problems.append(
                f"block[{idx}] font size {size}px is under 44px and unreadable at mobile scale"
            )
        text = str(block.get("text", ""))
        font = load_font(size, block.get("font"))
        _d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        bbox = _d.multiline_textbbox((0, 0), text, font=font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]

        bx1, by1 = int(block.get("x", 0)), int(block.get("y", 0))
        bx2, by2 = bx1 + bw, by1 + bh

        if bx2 > cw or by2 > ch:
            problems.append(
                f"block[{idx}] '{text}' spills off the canvas ({bx2}x{by2} > {cw}x{ch})"
            )

        # Check collision with YouTube duration badge in bottom-right
        if not (bx2 < db_x1 or bx1 > db_x2 or by2 < db_y1 or by1 > db_y2):
            problems.append(
                f"block[{idx}] '{text}' collides with YouTube duration badge at bottom-right"
            )

        boxes.append((bx1, by1, bx2, by2, f"block[{idx}] '{text}'"))

    if badge:
        corner = badge.get("corner", "top-left")
        bw, bh = 180, 80
        if corner == "top-left":
            bx1, by1 = MARGIN, MARGIN
        elif corner == "top-right":
            bx1, by1 = cw - MARGIN - bw, MARGIN
        elif corner == "top-center":
            bx1, by1 = (cw - bw) // 2, MARGIN
        else:
            bx1, by1 = MARGIN, MARGIN
        bx2, by2 = bx1 + bw, by1 + bh

        if not (bx2 < db_x1 or bx1 > db_x2 or by2 < db_y1 or by1 > db_y2):
            problems.append("chapter badge collides with YouTube duration badge")

        boxes.append((bx1, by1, bx2, by2, f"badge '{badge.get('text')}'"))

    # Overlap collision detection between boxes
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ax1, ay1, ax2, ay2, label_a = boxes[i]
            bx1, by1, bx2, by2, label_b = boxes[j]
            if not (ax2 <= bx1 or ax1 >= bx2 or ay2 <= by1 or ay1 >= by2):
                problems.append(f"{label_a} overlaps with {label_b}")

    return problems


def render_block_layer(
    canvas_size: tuple[int, int], block: dict, font_path: str | None
) -> Image.Image:
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
        draw.multiline_text(
            (x + off, y + off),
            text,
            font=font,
            fill=(0, 0, 0, 150),
            spacing=spacing,
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, 150),
        )
    draw.multiline_text(
        (x, y),
        text,
        font=font,
        fill=block.get("fill", FILL_CYCLE[0]),
        spacing=spacing,
        stroke_width=stroke,
        stroke_fill=block.get("stroke", "#000000"),
    )
    rotate = float(block.get("rotate", 0.0))
    if rotate:
        layer = layer.rotate(rotate, resample=Image.BICUBIC, center=(x, y))
    return layer


def render_arrow_layer(canvas_size: tuple[int, int], arrow: dict) -> Image.Image:
    (x1, y1), (x2, y2) = arrow["from"], arrow["to"]
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    color = arrow.get("color", "#FFE600")
    width = float(arrow.get("width", 26))
    outline_w = max(3, round(width * 0.22))
    pts = block_arrow_polygon(x1, y1, x2, y2, width)
    if arrow.get("shadow", True):
        off = max(3, round(width * 0.18))
        draw.polygon(
            [(px + off, py + off) for px, py in pts], fill=(0, 0, 0, 150)
        )
    draw.polygon(pts, fill=color)
    draw.line(
        [*pts, pts[0]],
        fill=arrow.get("outline", "#000000"),
        width=outline_w,
        joint="curve",
    )
    return layer


def render_bubble_layer(
    canvas_size: tuple[int, int], bubble: dict, font_path: str | None
) -> Image.Image:
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = bubble.get("center", [270, 260])
    rx, ry = bubble.get("rx", 168), bubble.get("ry", 196)
    style = bubble.get("style", "dark")
    bg_color = (18, 18, 18, 240) if style == "dark" else (255, 255, 255, 240)
    text_color = "#FFFFFF" if style == "dark" else "#000000"

    # Draw tail first if provided
    tail = bubble.get("tail")
    if tail:
        tx, ty = tail
        draw.polygon([(cx, cy), (tx - 15, ty), (tx + 15, ty)], fill=bg_color)

    # Draw main ellipse
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=bg_color, outline="#000000", width=4)

    # Render text inside bubble
    text = str(bubble.get("text", ""))
    size = int(bubble.get("size", 56))
    font = load_font(size, font_path)
    bbox = draw.multiline_textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.multiline_text(
        (cx - tw // 2, cy - th // 2), text, font=font, fill=text_color, align="center"
    )
    return layer


def render_badge_layer(
    canvas_size: tuple[int, int], badge: dict, font_path: str | None
) -> Image.Image:
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    text = str(badge.get("text", ""))
    size = int(badge.get("size", 64))
    font = load_font(size, font_path)
    corner = badge.get("corner", "top-left")

    cw, ch = canvas_size
    pad = 16
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    bw, bh = tw + 2 * pad, th + 2 * pad

    if corner == "top-left":
        bx1, by1 = MARGIN, MARGIN
    elif corner == "top-right":
        bx1, by1 = cw - MARGIN - bw, MARGIN
    elif corner == "top-center":
        bx1, by1 = (cw - bw) // 2, MARGIN
    else:
        bx1, by1 = MARGIN, MARGIN

    draw.rectangle([bx1, by1, bx1 + bw, by1 + bh], fill=(0, 0, 0, 220), outline="#000000", width=3)
    draw.text(
        (bx1 + pad, by1 + pad - bbox[1]),
        text,
        font=font,
        fill=badge.get("fill", YELLOW),
    )
    return layer


def render_border_layer(
    canvas_size: tuple[int, int], color: str = "#FFFFFF", width: int = 8
) -> Image.Image:
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cw, ch = canvas_size
    draw.rectangle([0, 0, cw - 1, ch - 1], outline=color, width=width)
    return layer


def build_canvas(
    sources: list[Path], size: tuple[int, int], layout: dict
) -> Image.Image:
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
    parser.add_argument(
        "--base", type=Path, action="append", default=[], metavar="PANEL"
    )
    parser.add_argument(
        "--subject-cutout",
        type=Path,
        default=None,
        help="PNG cutout with alpha for pop effect.",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output PNG/JPG path."
    )
    parser.add_argument("--text", action="append", default=[], metavar="WORDS")
    parser.add_argument(
        "--preset", choices=("label-arrow", "bubble", "split"), default=None
    )
    parser.add_argument("--badge", default=None)
    parser.add_argument("--badge-corner", default="top-left")
    parser.add_argument("--spec-json", default=None)
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--font", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    size = DEFAULT_SIZE
    sources = [Path(p) for p in args.base]
    if not sources:
        print("ERROR: provide at least one --base panel", file=sys.stderr)
        return 2

    spec: dict = {}
    if args.spec is not None and args.spec.is_file():
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    elif args.spec_json:
        spec = json.loads(args.spec_json)

    if args.preset:
        preset_data = preset_spec(
            args.preset, args.text, size, has_badge=bool(args.badge or spec.get("badge"))
        )
        for k, v in preset_data.items():
            spec.setdefault(k, v)

    if args.text and "blocks" not in spec and not args.preset:
        blocks = []
        for i, txt in enumerate(args.text):
            blocks.append({
                "text": txt,
                "x": MARGIN,
                "y": MARGIN + i * 120,
                "size": DEFAULT_FONT_SIZE,
            })
        spec["blocks"] = blocks

    if args.badge:
        spec["badge"] = {"text": args.badge, "corner": args.badge_corner}

    layout = spec.get("layout", {})
    blocks = spec.get("blocks", [])
    arrows = spec.get("arrows", [])
    bubbles = spec.get("bubbles", [])
    badge = spec.get("badge")
    border = spec.get("border")

    problems: list[str] = []
    if args.check:
        problems = check_composition(layout, blocks, arrows, size, badge)
        if problems:
            for prob in problems:
                print(f"[check] {prob}", file=sys.stderr)

    canvas = build_canvas(sources, size, layout)
    if args.subject_cutout and args.subject_cutout.is_file():
        subject = Image.open(args.subject_cutout).convert("RGBA")
        canvas = apply_subject_pop(canvas.convert("RGB"), subject)

    for block in blocks:
        canvas.alpha_composite(render_block_layer(size, block, args.font))

    for arrow in arrows:
        canvas.alpha_composite(render_arrow_layer(size, arrow))

    for bubble in bubbles:
        canvas.alpha_composite(render_bubble_layer(size, bubble, args.font))

    if badge:
        canvas.alpha_composite(render_badge_layer(size, badge, args.font))

    if border:
        border_color = border if isinstance(border, str) else "#FFFFFF"
        canvas.alpha_composite(render_border_layer(size, border_color))

    canvas = canvas.convert("RGB")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archive_before_overwrite(args.output)
    canvas.save(args.output)

    payload = {"ok": not problems, "outputs": [str(args.output)]}
    if problems:
        payload["problems"] = problems
    emit_result(**payload)

    if args.check and problems:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())