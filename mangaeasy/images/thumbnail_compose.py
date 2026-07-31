"""mangaeasy.images.thumbnail_compose — compose a thumbnail from panel art.

``mangaeasy thumbnail-compose`` turns **manga panels the crop review
already approved** into a finished 1280×720 YouTube thumbnail. There is no
image generation anywhere in this path and there is not meant to be: the
channel's value is the actual comic, and art the video does not contain is
both a thumbnail-policy problem and a straight disappointment for whoever
clicked. Every base pixel comes from a panel the crop review approved.

Four layout elements, which between them reproduce the reference thumbnails
this channel imitates:

``blocks``
    Short ALL-CAPS hook words in a heavy face with a thick black stroke
    (≈ 12 % of the font size) — ``VILLAIN``, ``YANDERE``, ``CHEATED``.
    Yellow ``#FFE600`` by default. A −2…−5° ``rotate`` reads hand-placed;
    perfectly horizontal reads templated.
``arrows``
    Fat outlined block-arrows pointing from a label to the character it
    names. This is the single most repeated element in the references, and
    the reason it works is that it answers "which one?" before the viewer
    has to parse the picture.
``bubbles``
    A speech bubble carrying one line of real dialogue — dark bubble with
    white brush text, or light bubble with black text. Use it when the hook
    is something a character *said*; use ``blocks`` when the hook is a label
    the narrator applies.
``badge``
    The chapter range (``1-12``) in a corner, so a returning viewer can see
    at a glance which part this is.

Drive it three ways:

- quick: repeated ``--text "3-5 WORDS"`` — stacked top-left, alternating
  yellow/white;
- ``--spec spec.json`` / ``--spec-json '{...}'`` — the full document below;
- ``--preset label-arrow|bubble|split`` — a worked starting spec you then
  adjust, which is usually faster than writing coordinates from scratch.

```json
{
  "layout": {"kind": "split", "sources": ["a.jpg", "b.jpg"], "divider": 10},
  "blocks":  [{"text", "x", "y", "size", "fill", "stroke", "rotate", "shadow", "font"}],
  "arrows":  [{"from": [x, y], "to": [x, y], "width", "color", "style", "shadow"}],
  "bubbles": [{"text", "center": [x, y], "rx", "ry", "style": "dark|light",
               "tail": [x, y], "size", "font", "rotate"}],
  "badge":   {"text": "1-12", "corner": "top-left", "fill", "stroke", "size"},
  "border": true
}
```

Deterministic on purpose: an agent writes a spec, renders, **opens the output
and looks at it**, adjusts, re-renders. Nothing here judges whether the
result is good — that is the agent's job, and `--check` only reports the
mechanical failures (text spilling off-canvas, a bubble overlapping the
duration badge, contrast too low to read at phone size).

The previous output file is archived (old/run_NNNN/), never clobbered.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mangaeasy import fonts
from mangaeasy.brand import CLI_NAME
from mangaeasy.utils import archive_before_overwrite, emit_result

DEFAULT_SIZE = (1280, 720)
DEFAULT_FONT_SIZE = 104          # inside the playbook's 90-120 pt band
STROKE_FRACTION = 0.12           # black stroke ≈ 12 % of font size
FILL_CYCLE = ("#FFE600", "#FFFFFF")
MARGIN = 44
YELLOW = "#FFE600"

# YouTube stamps the duration over the bottom-right corner. Anything the
# viewer needs to read has to stay out of it — learned the expensive way,
# with a hook word half-covered by "12:04".
DURATION_BADGE_BOX = (1060, 640, 1280, 720)

# Impact first (the channel look), then bold fallbacks; mangaeasy.fonts
# resolves the actual file per platform, so no path is hardcoded here.
_FONT_CANDIDATES = fonts.DISPLAY


def bundled_font(name: str = fonts.BUNDLED_FONT) -> str | None:
    """Path to a font shipped with the package, or None when missing."""
    candidate = fonts.bundled_font_path(name)
    return str(candidate) if candidate is not None else None


def load_font(size: int, font_path: str | None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A display face at *size*; ``--font`` wins, otherwise resolved per platform.

    A thumbnail draws at ~104 pt, so falling back to Pillow's unscaled default
    would produce unreadable text rather than a slightly different look — see
    :mod:`mangaeasy.fonts`.
    """
    return fonts.load(size, fonts.DISPLAY, explicit=font_path)


# Kept for callers that imported the private spelling.
_load_font = load_font


def cover_canvas(base: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale *base* to cover *size*, center-crop the overflow."""
    tw, th = size
    scale = max(tw / base.width, th / base.height)
    resized = base.resize((round(base.width * scale), round(base.height * scale)), Image.LANCZOS)
    left = (resized.width - tw) // 2
    top = (resized.height - th) // 2
    return resized.crop((left, top, left + tw, top + th)).convert("RGB")


def render_block_layer(canvas_size: tuple[int, int], block: dict,
                       font_path: str | None) -> Image.Image:
    """One text block on its own RGBA layer: shadow + stroke + optional tilt."""
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
        # Rotate around the block's own anchor so x/y keep their meaning.
        layer = layer.rotate(rotate, resample=Image.BICUBIC, center=(x, y))
    return layer


def block_arrow_polygon(x1: float, y1: float, x2: float, y2: float,
                        width: float) -> list[tuple[float, float]]:
    """Fat block-arrow polygon (shaft + triangular head) from tail to tip."""
    import math

    angle = math.atan2(y2 - y1, x2 - x1)
    length = max(1.0, math.hypot(x2 - x1, y2 - y1))
    head_len = min(length * 0.45, width * 1.9)
    head_w = width * 2.15
    pts = [
        (0, -width / 2), (length - head_len, -width / 2), (length - head_len, -head_w / 2),
        (length, 0),
        (length - head_len, head_w / 2), (length - head_len, width / 2), (0, width / 2),
    ]
    cos, sin = math.cos(angle), math.sin(angle)
    return [(x1 + px * cos - py * sin, y1 + px * sin + py * cos) for px, py in pts]


def render_arrow_layer(canvas_size: tuple[int, int], arrow: dict) -> Image.Image:
    (x1, y1), (x2, y2) = arrow["from"], arrow["to"]
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if arrow.get("style", "block") == "line":
        import math

        color = arrow.get("color", "#FF3333")
        width = int(arrow.get("width", 14))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
        angle = math.atan2(y2 - y1, x2 - x1)
        head = width * 3.2
        for offset in (math.radians(150), math.radians(-150)):
            draw.line(
                [(x2, y2),
                 (x2 + head * math.cos(angle + offset), y2 + head * math.sin(angle + offset))],
                fill=color, width=width,
            )
        return layer
    color = arrow.get("color", "#FFE600")
    width = float(arrow.get("width", 26))
    outline_w = max(3, round(width * 0.22))
    pts = block_arrow_polygon(x1, y1, x2, y2, width)
    if arrow.get("shadow", True):
        off = max(3, round(width * 0.18))
        draw.polygon([(px + off, py + off) for px, py in pts], fill=(0, 0, 0, 150))
    draw.polygon(pts, fill=color)
    # Outline via a closed line loop (portable across Pillow versions).
    draw.line([*pts, pts[0]], fill=arrow.get("outline", "#000000"),
              width=outline_w, joint="curve")
    return layer


def _wrap_to_width(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Greedy word wrap. Explicit \\n in the text is always honoured."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            probe = f"{current} {word}"
            if draw.textlength(probe, font=font) <= max_width:
                current = probe
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def render_bubble_layer(canvas_size: tuple[int, int], bubble: dict,
                        font_path: str | None) -> Image.Image:
    """A speech bubble carrying one spoken line: ellipse + tail + wrapped text.

    Two treatments, both taken from the reference thumbnails: ``dark`` (black
    bubble, white text) for a menacing or possessive line, ``light`` (white
    bubble, black text) for a plain statement. The default face is the
    bundled brush font, which is what makes the dark variant read as manga
    lettering rather than as a caption pasted on top.
    """
    style = str(bubble.get("style", "dark")).lower()
    dark = style != "light"
    fill = bubble.get("fill", "#0A0A0A" if dark else "#FFFFFF")
    text_fill = bubble.get("text_fill", "#FFFFFF" if dark else "#111111")
    outline = bubble.get("outline", "#000000" if not dark else "#FFFFFF")
    outline_w = int(bubble.get("outline_width", 0 if dark else 5))

    cx, cy = bubble.get("center", (240, 240))
    rx = int(bubble.get("rx", 170))
    ry = int(bubble.get("ry", 190))
    size = int(bubble.get("size", 54))
    font = load_font(size, bubble.get("font") or bundled_font() or font_path)

    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # Tail first, so the ellipse covers where it joins the body.
    tail = bubble.get("tail")
    if tail:
        import math

        tx, ty = float(tail[0]), float(tail[1])
        angle = math.atan2(ty - cy, tx - cx)
        spread = math.radians(float(bubble.get("tail_spread", 16)))
        base = [
            (cx + rx * math.cos(angle + spread), cy + ry * math.sin(angle + spread)),
            (cx + rx * math.cos(angle - spread), cy + ry * math.sin(angle - spread)),
            (tx, ty),
        ]
        draw.polygon(base, fill=fill)

    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill,
                 outline=outline if outline_w else None,
                 width=outline_w or 1)

    inner_w = int(rx * 1.45)
    lines = _wrap_to_width(str(bubble["text"]), font, inner_w, draw)
    spacing = round(size * 0.34)
    line_h = size + spacing
    total_h = line_h * len(lines) - spacing
    y = cy - total_h / 2
    for line in lines:
        line_w = draw.textlength(line, font=font)
        draw.text((cx - line_w / 2, y), line, font=font, fill=text_fill)
        y += line_h

    rotate = float(bubble.get("rotate", 0.0))
    if rotate:
        layer = layer.rotate(rotate, resample=Image.BICUBIC, center=(cx, cy))
    return layer


_BADGE_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right", "top-center")


def render_badge_layer(canvas_size: tuple[int, int], badge: dict,
                       font_path: str | None) -> Image.Image:
    """The chapter-range stamp (``1-12``) pinned to a corner.

    A corner name rather than coordinates, because the one thing that must
    never happen is the badge drifting under YouTube's duration overlay —
    ``bottom-right`` is accepted but warned about by ``--check``.
    """
    corner = str(badge.get("corner", "top-left")).lower()
    if corner not in _BADGE_CORNERS:
        raise ValueError(f"badge corner must be one of {', '.join(_BADGE_CORNERS)}")
    size = int(badge.get("size", 92))
    font = load_font(size, badge.get("font") or font_path)
    text = str(badge["text"])
    stroke = max(2, round(size * STROKE_FRACTION))

    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    cw, ch = canvas_size
    if corner == "top-center":
        x = (cw - text_w) / 2
        y = MARGIN * 0.5
    else:
        vertical, horizontal = corner.split("-")
        x = MARGIN if horizontal == "left" else cw - text_w - MARGIN
        y = MARGIN * 0.5 if vertical == "top" else ch - text_h - MARGIN
    draw.text((x - box[0], y - box[1]), text, font=font,
              fill=badge.get("fill", YELLOW), stroke_width=stroke,
              stroke_fill=badge.get("stroke", "#000000"))
    return layer


def build_canvas(sources: list[Path], size: tuple[int, int], layout: dict) -> Image.Image:
    """The base image: one panel cover-cropped, or several side by side.

    The split layout is the before/after comparison from the references
    (``WEAK`` | ``STRONG``): each source fills an equal column, with a bar
    between them so the eye reads two states rather than one wide picture.
    """
    kind = str(layout.get("kind", "single")).lower()
    if kind == "single" or len(sources) == 1:
        return cover_canvas(Image.open(sources[0]), size).convert("RGBA")
    if kind != "split":
        raise ValueError("layout.kind must be 'single' or 'split'")

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


def draw_border(draw: ImageDraw.ImageDraw, size: tuple[int, int]) -> None:
    w, h = size
    inset, thickness = 14, 6
    draw.rectangle([inset, inset, w - inset - 1, h - inset - 1],
                   outline="#FFFFFF", width=thickness)


def preset_spec(name: str, texts: list[str], size: tuple[int, int],
                has_badge: bool = False) -> dict:
    """A worked starting spec for one of the three reference layouts.

    Presets exist because writing coordinates from scratch costs an agent two
    or three render-and-look rounds before anything is even roughly placed.
    They are a starting point to adjust, not a template to ship unexamined —
    where the arrow should point depends entirely on the panel.

    *has_badge* shifts the label clear of the top-left corner, since that is
    where the chapter badge lands by default and two things stacked in one
    corner render both unreadable.
    """
    width, height = size
    words = [t for t in texts if t.strip()] or ["HOOK"]
    if name == "label-arrow":
        # Label near the top, arrow angling down into the subject beneath it.
        x = int(width * 0.34) if has_badge else MARGIN + 20
        return {
            "blocks": [{"text": words[0].upper(), "x": x, "y": MARGIN,
                        "size": 104, "rotate": -3, "fill": YELLOW}],
            "arrows": [{"from": [x + 130, MARGIN + 150],
                        "to": [x + 270, MARGIN + 260], "width": 30}],
        }
    if name == "bubble":
        line = words[0] if len(words) == 1 else "\n".join(words[:3])
        return {
            "bubbles": [{"text": line.upper(), "center": [int(width * 0.21), int(height * 0.36)],
                         "rx": 168, "ry": 196, "style": "dark",
                         "tail": [int(width * 0.32), int(height * 0.62)], "size": 56}],
        }
    if name == "split":
        left, right = (words + ["BEFORE", "AFTER"])[:2]
        return {
            "layout": {"kind": "split"},
            "blocks": [
                {"text": left.upper(), "x": MARGIN + 20, "y": height - 150, "size": 96,
                 "fill": YELLOW},
                {"text": right.upper(), "x": int(width * 0.56), "y": height - 150,
                 "size": 96, "fill": YELLOW},
            ],
        }
    raise ValueError(f"unknown preset {name!r}")


def check_composition(spec: dict, blocks: list[dict], bubbles: list[dict],
                      size: tuple[int, int], font_path: str | None) -> list[str]:
    """Mechanical faults only — the ones an agent cannot see in a JSON spec.

    Deliberately narrow. Whether the thumbnail is *good*, whether it matches
    the title, and whether it reads as a sexualized minor are all judgements
    that require looking at the image; a linter that pretended to cover them
    would be worse than none, because it would be trusted.
    """
    width, height = size
    problems: list[str] = []
    probe = ImageDraw.Draw(Image.new("RGB", size))
    # (label, x, y, w, h) for every element that occupies space, so elements
    # can be checked against each other and not only against the canvas.
    boxes: list[tuple[str, float, float, float, float]] = []

    for block in blocks:
        font_size = int(block.get("size", DEFAULT_FONT_SIZE))
        font = load_font(font_size, block.get("font") or font_path)
        text = str(block["text"])
        x, y = int(block["x"]), int(block["y"])
        longest = max((probe.textlength(line, font=font) for line in text.split("\n")),
                      default=0)
        lines = len(text.split("\n"))
        block_h = lines * font_size * 1.18
        label = text.replace("\n", " ")[:24]
        if x + longest > width - 8 or y + block_h > height - 8 or x < 0 or y < 0:
            problems.append(f"text block {label!r} spills off the canvas — move or shrink it")
        if font_size < 44:
            problems.append(f"text block {label!r} is {font_size}px; below ~44px it is "
                            f"unreadable at the 320x180 size most viewers see")
        if _overlaps(x, y, longest, block_h, DURATION_BADGE_BOX):
            problems.append(f"text block {label!r} sits under YouTube's duration badge "
                            f"(bottom-right corner)")
        boxes.append((f"text block {label!r}", x, y, longest, block_h))

    for bubble in bubbles:
        cx, cy = bubble.get("center", (0, 0))
        rx, ry = int(bubble.get("rx", 170)), int(bubble.get("ry", 190))
        label = str(bubble["text"]).replace("\n", " ")[:24]
        if cx - rx < 0 or cy - ry < 0 or cx + rx > width or cy + ry > height:
            problems.append(f"bubble {label!r} extends past the canvas edge")
        if _overlaps(cx - rx, cy - ry, rx * 2, ry * 2, DURATION_BADGE_BOX):
            problems.append(f"bubble {label!r} sits under YouTube's "
                            f"duration badge (bottom-right corner)")
        boxes.append((f"bubble {label!r}", cx - rx, cy - ry, rx * 2, ry * 2))

    badge = spec.get("badge")
    if badge:
        corner = str(badge.get("corner", "top-left")).lower()
        if corner == "bottom-right":
            problems.append("badge corner 'bottom-right' collides with YouTube's "
                            "duration overlay")
        badge_size = int(badge.get("size", 92))
        badge_font = load_font(badge_size, badge.get("font") or font_path)
        badge_w = probe.textlength(str(badge["text"]), font=badge_font)
        badge_h = badge_size * 1.2
        if corner == "top-center":
            bx, by = (width - badge_w) / 2, MARGIN * 0.5
        else:
            vertical, horizontal = corner.split("-")
            bx = MARGIN if horizontal == "left" else width - badge_w - MARGIN
            by = MARGIN * 0.5 if vertical == "top" else height - badge_h - MARGIN
        boxes.append((f"badge {str(badge['text'])!r}", bx, by, badge_w, badge_h))

    # Elements printed on top of each other is the single most common spec
    # mistake — a badge pinned to the same corner as the hook word renders
    # both unreadable, and neither one looks wrong in the JSON.
    for i, (name_a, ax, ay, aw, ah) in enumerate(boxes):
        for name_b, bx, by, bw, bh in boxes[i + 1:]:
            if _overlaps(ax, ay, aw, ah, (bx, by, bx + bw, by + bh)):
                problems.append(f"{name_a} overlaps {name_b} — move one of them")
    return problems


def _overlaps(x: float, y: float, w: float, h: float, box: tuple[int, int, int, int]) -> bool:
    bx1, by1, bx2, by2 = box
    return not (x + w < bx1 or x > bx2 or y + h < by1 or y > by2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{CLI_NAME} thumbnail-compose",
        description="Compose a YouTube thumbnail from approved manga panels: "
                    "base art + stroked hook text + block arrows + speech bubbles "
                    "+ chapter badge (1280x720). No image generation.",
    )
    parser.add_argument("--base", type=Path, action="append", default=[], metavar="PANEL",
                        help="Base panel — an approved crop from the project. "
                             "Repeat it for a split layout.")
    parser.add_argument("--output", type=Path, required=True, help="Output PNG/JPG path.")
    parser.add_argument("--text", action="append", default=[], metavar="WORDS",
                        help="Quick mode: one text block (repeatable, stacked top-left, "
                             "alternating yellow/white). Keep each to 3-5 punchy words. "
                             "With --preset, these fill the preset's slots instead.")
    parser.add_argument("--preset", choices=("label-arrow", "bubble", "split"), default=None,
                        help="Start from a worked spec for one of the reference layouts, "
                             "then adjust: label-arrow (label + block arrow at a character), "
                             "bubble (spoken hook line in a speech bubble), split "
                             "(before/after comparison).")
    parser.add_argument("--badge", default=None, metavar="RANGE",
                        help="Chapter-range stamp, e.g. '1-12'.")
    parser.add_argument("--badge-corner", default="top-left",
                        choices=_BADGE_CORNERS, help="Where the badge sits (default: top-left).")
    parser.add_argument("--spec", type=Path, default=None,
                        help="JSON spec file: layout/blocks/arrows/bubbles/badge/border.")
    parser.add_argument("--spec-json", default=None, metavar="JSON",
                        help="The spec JSON as one CLI argument (wins over --spec).")
    parser.add_argument("--width", type=int, default=DEFAULT_SIZE[0])
    parser.add_argument("--height", type=int, default=DEFAULT_SIZE[1])
    parser.add_argument("--font", default=None, help="Path to a .ttf to use for all blocks.")
    parser.add_argument("--no-border", action="store_true",
                        help="Skip the thin white inset border.")
    parser.add_argument("--check", action="store_true",
                        help="Report mechanical faults (off-canvas text, unreadable sizes, "
                             "collisions with YouTube's duration badge) and exit 3 if any.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit one JSON object on stdout.")
    args = parser.parse_args(argv)

    size = (args.width, args.height)

    spec: dict = {}
    try:
        if args.spec_json is not None:
            spec = json.loads(args.spec_json)
        elif args.spec is not None:
            spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"ERROR: invalid spec JSON: {exc}", file=sys.stderr)
        return 2

    if args.preset:
        preset = preset_spec(args.preset, args.text, size,
                             has_badge=bool(args.badge or spec.get("badge")))
        # An explicit spec always wins over the preset's guess.
        for key, value in preset.items():
            spec.setdefault(key, value)

    sources = [Path(p) for p in (args.base or [])] or \
              [Path(p) for p in spec.get("layout", {}).get("sources", [])]
    if not sources:
        print("ERROR: provide at least one --base panel (or layout.sources in the spec)",
              file=sys.stderr)
        return 2
    missing = [str(p) for p in sources if not p.is_file()]
    if missing:
        print(f"ERROR: base panel not found: {', '.join(missing)}", file=sys.stderr)
        return 1
    if not (args.text or args.preset or args.badge or spec):
        print("ERROR: provide --text, --preset, --badge, --spec, or --spec-json",
              file=sys.stderr)
        return 2

    layout = dict(spec.get("layout", {}))
    if len(sources) > 1:
        layout.setdefault("kind", "split")
    try:
        canvas = build_canvas(sources, size, layout)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    blocks = list(spec.get("blocks", []))
    if args.text and not args.preset:
        y = MARGIN
        for i, text in enumerate(args.text):
            blocks.append({"text": text, "x": MARGIN, "y": y,
                           "size": DEFAULT_FONT_SIZE, "fill": FILL_CYCLE[i % len(FILL_CYCLE)]})
            y += round(DEFAULT_FONT_SIZE * 1.28)

    arrows = list(spec.get("arrows", []))
    if spec.get("arrow"):
        arrows.append(spec["arrow"])
    bubbles = list(spec.get("bubbles", []))
    if spec.get("bubble"):
        bubbles.append(spec["bubble"])

    badge = spec.get("badge")
    if args.badge:
        badge = {"text": args.badge, "corner": args.badge_corner}

    problems = check_composition({**spec, "badge": badge}, blocks, bubbles, size, args.font)

    try:
        for block in blocks:
            canvas.alpha_composite(render_block_layer(size, block, args.font))
        for arrow in arrows:
            canvas.alpha_composite(render_arrow_layer(size, arrow))
        for bubble in bubbles:
            canvas.alpha_composite(render_bubble_layer(size, bubble, args.font))
        if badge:
            canvas.alpha_composite(render_badge_layer(size, badge, args.font))
    except (KeyError, ValueError) as exc:
        print(f"ERROR: invalid spec: {exc}", file=sys.stderr)
        return 2

    canvas = canvas.convert("RGB")
    if spec.get("border", True) and not args.no_border:
        draw_border(ImageDraw.Draw(canvas), size)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    archived = archive_before_overwrite(args.output)
    canvas.save(args.output)

    payload = {
        "ok": not (problems and args.check),
        "outputs": [str(args.output)],
        "size": list(size),
        "sources": [str(p) for p in sources],
        "blocks": len(blocks),
        "arrows": len(arrows),
        "bubbles": len(bubbles),
        "badge": bool(badge),
        "problems": problems,
        "archived": str(archived) if archived else None,
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if archived:
            print(f"[info] previous thumbnail archived: {archived}")
        print(f"[info] thumbnail written: {args.output} ({size[0]}x{size[1]}, "
              f"{len(blocks)} text block(s), {len(bubbles)} bubble(s))")
        for problem in problems:
            print(f"[warn] {problem}")
        print("[info] open it at full size before upload: faces, text overlap, edge "
              "crops, and anything that reads as explicit or minor-coded.")
    emit_result(**payload)
    # 3 = artifact created, review still required — the house contract.
    return 3 if (problems and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
