"""mangaeasy.images.ai_pdf — labelled PDF from chapter panels for AI context.

Adds a filename banner ABOVE each panel (never overlapping content) and packs
the result with img2pdf at original panel resolution.
Original panel files are never modified.
"""

from __future__ import annotations
import io
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGB"), mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _stamp_label(img: Image.Image, label: str) -> Image.Image:
    """Return a new image with a dark filename banner added ABOVE the panel.

    Banner height scales with image width so text is always readable at any
    panel resolution.  Panel content is never covered.
    """
    img = _to_rgb(img)
    w, h = img.size

    # Font size: 3 % of image width, clamped to [18, 90] px.
    font_size = max(18, min(90, int(w * 0.030)))
    font = _load_font(font_size)

    _d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bb = _d.textbbox((0, 0), label, font=font)
    text_h = bb[3] - bb[1]

    pad_y = max(6, int(font_size * 0.35))
    pad_x = max(8, int(font_size * 0.50))
    banner_h = text_h + pad_y * 2

    out = Image.new("RGB", (w, banner_h + h), (18, 18, 18))
    draw = ImageDraw.Draw(out)
    draw.rectangle([(0, 0), (w, banner_h)], fill=(28, 30, 36))
    draw.text((pad_x + 1, pad_y + 1), label, font=font, fill=(0, 0, 0))
    draw.text((pad_x, pad_y), label, font=font, fill=(225, 232, 248))
    draw.rectangle([(0, banner_h - 2), (w, banner_h)], fill=(65, 120, 175))
    out.paste(img, (0, banner_h))
    return out


def _to_jpeg_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True, subsampling=0)
    return buf.getvalue()


def panels_to_ai_pdf(
    panels_dir: Path,
    out_path: Path,
    log: Callable[[str], None] = print,
) -> int:
    """Build a labelled PDF from *panels_dir* into *out_path* at original size.

    Does NOT modify any source files.
    Returns the number of pages written.
    """
    try:
        import img2pdf
    except ImportError as exc:
        raise RuntimeError("img2pdf is required — it is listed in project dependencies") from exc

    files = sorted(p for p in panels_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTS)
    if not files:
        raise FileNotFoundError(f"no panel images found in {panels_dir}")

    pages: list[bytes] = []
    for p in files:
        try:
            img = Image.open(p)
            img.load()
        except Exception as exc:
            log(f"[ai-pdf] skip {p.name}: {exc}")
            continue
        stamped = _stamp_label(img, p.name)
        pages.append(_to_jpeg_bytes(stamped))
        img.close()
        log(f"[ai-pdf] labelled {p.name}")

    if not pages:
        raise FileNotFoundError("all panel images failed to load")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(img2pdf.convert(pages))
    log(f"[ai-pdf] ✓ {len(pages)} pages → {out_path.name}")
    return len(pages)
