from __future__ import annotations

import base64
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from app.config import ROOT

# Reference layout on a 1200px-tall photo (Figma 900×1200).
# REF_LEFT = distance from photo's left edge to the visible logo (beige pill).
REF_PHOTO_H = 1200
REF_LOGO_W = 484.0
REF_LOGO_H = 415.38
REF_TOP = 24.0
# Visible logo (pill) further right — hangs past the right edge of a 900px-wide photo.
REF_LEFT = 650.0
# Pill x inside the SVG artboard — artboard paste x = (REF_LEFT - SVG_PILL_X) * scale
SVG_PILL_X = 87.3281

DEFAULT_LOGO_SVG = ROOT / "static" / "default" / "logo_exp.svg"


def rasterize_logo_svg(svg_path: Path, *, scale: float = 3.0) -> Image.Image:
    """Rasterize the bundled logo SVG artboard (484×415.38) in memory.

    Source of truth is the SVG. Pillow cannot open SVG directly, so we
    rebuild the artboard from SVG elements (beige pill + ODI artwork).
    No permanent logo_exp.png is written.
    """
    raw = svg_path.read_text(encoding="utf-8")

    img_m = re.search(
        r'xlink:href\s*=\s*["\']data:image/png;base64,([^"\']+)["\']',
        raw,
        re.I,
    )
    if not img_m:
        raise RuntimeError("Logo SVG has no embedded PNG artwork")

    artwork = Image.open(
        BytesIO(base64.b64decode(re.sub(r"\s+", "", img_m.group(1))))
    ).convert("RGBA")

    out_w = max(1, int(round(REF_LOGO_W * scale)))
    out_h = max(1, int(round(REF_LOGO_H * scale)))
    canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    s = out_w / REF_LOGO_W

    # Beige pill under the letters (same order as in the SVG).
    pill = re.search(
        r'<rect\s+x="([0-9.]+)"\s+y="([0-9.]+)"\s+width="([0-9.]+)"\s+'
        r'height="([0-9.]+)"\s+rx="([0-9.]+)"\s+fill="#F0EBDE"',
        raw,
        re.I,
    )
    if pill:
        px = int(round(float(pill.group(1)) * s))
        py = int(round(float(pill.group(2)) * s))
        pw = max(1, int(round(float(pill.group(3)) * s)))
        ph = max(1, int(round(float(pill.group(4)) * s)))
        pr = max(0, int(round(float(pill.group(5)) * s)))
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            (px, py, px + pw, py + ph),
            radius=pr,
            fill=(240, 235, 222, 255),
        )
        canvas = Image.alpha_composite(canvas, layer)

    pattern = re.search(
        r'<rect\s+(?:[^>]*\s)?width="([0-9.]+)"\s+height="([0-9.]+)"[^>]*'
        r'fill="url\(#pattern',
        raw,
        re.I,
    )
    pat_w = float(pattern.group(1)) if pattern else REF_LOGO_W
    pat_h = float(pattern.group(2)) if pattern else REF_LOGO_H
    placed = artwork.resize(
        (max(1, int(round(pat_w * s))), max(1, int(round(pat_h * s)))),
        Image.Resampling.LANCZOS,
    )
    canvas.paste(placed, (0, 0), placed)
    return canvas


@lru_cache(maxsize=1)
def default_logo_image() -> Image.Image:
    """Cached high-res raster of the default SVG (in memory only)."""
    if not DEFAULT_LOGO_SVG.exists():
        raise FileNotFoundError(f"Default logo not found: {DEFAULT_LOGO_SVG}")
    return rasterize_logo_svg(DEFAULT_LOGO_SVG, scale=3.0)


def default_logo_path() -> Path:
    """Path to the default SVG source."""
    if not DEFAULT_LOGO_SVG.exists():
        raise FileNotFoundError(f"Default logo not found: {DEFAULT_LOGO_SVG}")
    return DEFAULT_LOGO_SVG


def _paste_with_overflow(
    photo: Image.Image,
    logo: Image.Image,
    x: int,
    y: int,
) -> None:
    """Paste logo at (x, y); parts outside the photo are clipped away."""
    photo_w, photo_h = photo.size
    logo_w, logo_h = logo.size

    src_x0 = max(0, -x)
    src_y0 = max(0, -y)
    dst_x0 = max(0, x)
    dst_y0 = max(0, y)
    src_x1 = min(logo_w, photo_w - x)
    src_y1 = min(logo_h, photo_h - y)
    if src_x1 <= src_x0 or src_y1 <= src_y0:
        return

    cropped = logo.crop((src_x0, src_y0, src_x1, src_y1))
    photo.paste(cropped, (dst_x0, dst_y0), cropped)


def overlay_logo(
    photo_path: Path,
    logo_path: Path,
    out_path: Path,
) -> None:
    """Paste logo onto photo, scaled from photo height vs REF_PHOTO_H.

    - Logo size = (REF_LOGO_W × REF_LOGO_H) * (photo_h / REF_PHOTO_H)
    - Top inset = REF_TOP * scale
    - Left: visible logo (pill) at REF_LEFT * scale
    - Default logo is always the bundled SVG (rasterized in memory)
    """
    with Image.open(photo_path) as photo_img:
        photo = photo_img.convert("RGBA")
        _photo_w, photo_h = photo.size

        scale = photo_h / REF_PHOTO_H
        target_w = max(1, int(round(REF_LOGO_W * scale)))
        target_h = max(1, int(round(REF_LOGO_H * scale)))
        top_px = max(0, int(round(REF_TOP * scale)))
        # Artboard has transparent padding left of the pill — shift so pill is at REF_LEFT.
        left_px = max(0, int(round((REF_LEFT - SVG_PILL_X) * scale)))

        if Path(logo_path).suffix.lower() == ".svg" or Path(logo_path).resolve() == (
            DEFAULT_LOGO_SVG.resolve()
        ):
            logo = default_logo_image()
        else:
            with Image.open(logo_path) as logo_img:
                logo = logo_img.convert("RGBA")

        logo_resized = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # Allow logo to hang past photo edges (cropped to visible overlap).
        x = left_px
        y = top_px
        _paste_with_overflow(photo, logo_resized, x, y)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = photo_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            rgb = photo.convert("RGB")
            rgb.save(out_path, format="JPEG", quality=92, optimize=True)
        elif suffix == ".webp":
            photo.save(out_path, format="WEBP", quality=92, method=4)
        else:
            if out_path.suffix.lower() != ".png":
                out_path = out_path.with_suffix(".png")
            photo.save(out_path, format="PNG", optimize=True)
