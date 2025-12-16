#!/usr/bin/env python3
"""
Compose a 296x128 1-bit BMP by placing a left-side logo and drawing a text string (e.g., from BME/BMP280).

Example:
  python tools/make_screen_bmp.py --logo logo_1bit.bmp \
    --text "T:23.4C P:1012.8hPa H:45%" --out screen.bmp --dither none

Notes:
- Output is 1-bit monochrome (mode '1') BMP, white background (255), black text (0).
- If your logo is not 1-bit, it will be converted.
- If text draws too small/large, adjust --font-size or try a truetype font with --font.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CANVAS_W, CANVAS_H = 296, 128


def load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path:
        return ImageFont.truetype(font_path, size)
    # Fallback to a simple built-in bitmap font
    return ImageFont.load_default()


def compose_bmp(logo_path: Path, text: str, out_path: Path, font_path: str | None, font_size: int, dither: str) -> None:
    # Start with white 1-bit canvas
    # Use 'L' first to allow anti-aliased text if dithering, then convert to '1' at end
    working_mode = 'L' if dither != 'none' else '1'
    canvas = Image.new(working_mode, (CANVAS_W, CANVAS_H), color=255)

    # Load logo
    logo = Image.open(logo_path)
    # Ensure monochrome
    if working_mode == '1':
        logo = logo.convert('1')
    else:
        # L mode to allow dithering/antialias pipeline later
        logo = logo.convert('L')

    # Paste logo at (0,0); if taller than canvas, crop; if wider than a left region, that's OK
    paste_w = min(logo.width, CANVAS_W)
    paste_h = min(logo.height, CANVAS_H)
    if paste_w != logo.width or paste_h != logo.height:
        logo = logo.crop((0, 0, paste_w, paste_h))
    canvas.paste(logo, (0, 0))

    # Draw text to the right of logo with some padding
    draw = ImageDraw.Draw(canvas)
    font = load_font(font_path, font_size)

    # Compute a decent x start: logo width + margin, but keep inside canvas
    text_x = min(logo.width + 6, CANVAS_W - 1)
    # Baseline y somewhere mid-height; we can wrap if needed
    text_y = 10

    # Simple wrapping if text too long (2 lines max)
    max_text_width = CANVAS_W - text_x - 6
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + ' ' + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        w_px = bbox[2] - bbox[0]
        if w_px <= max_text_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    # Draw lines
    for i, ln in enumerate(lines[:3]):
        draw.text((text_x, text_y + i * (font_size + 4)), ln, font=font, fill=0)

    # Convert to 1-bit with optional dithering
    if canvas.mode != '1':
        if dither == 'fs':
            canvas = canvas.convert('1', dither=Image.FLOYDSTEINBERG)
        else:
            canvas = canvas.convert('1')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format='BMP')
    print(f"Saved {out_path} ({out_path.stat().st_size} bytes), size={canvas.size}, mode={canvas.mode}")


ess = ["fs", "none"]

def main() -> None:
    p = argparse.ArgumentParser(description="Compose a 296x128 1-bit BMP with logo + text")
    p.add_argument("--logo", required=True, help="Path to left-side logo (e.g., logo_1bit.bmp)")
    p.add_argument("--text", required=True, help="Text to render (e.g., sensor reading)")
    p.add_argument("--out", default="screen.bmp", help="Output BMP filename")
    p.add_argument("--font", default=None, help="Optional path to a TTF font")
    p.add_argument("--font-size", type=int, default=16, help="Font size (for TTF; bitmap default ignores size)")
    p.add_argument("--dither", choices=ess, default="none", help="Dither when converting to 1-bit")
    args = p.parse_args()

    compose_bmp(Path(args.logo), args.text, Path(args.out), args.font, args.font_size, args.dither)


if __name__ == "__main__":
    main()
