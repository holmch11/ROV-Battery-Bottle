#!/usr/bin/env python3
"""
Convert an image (e.g., logo.bmp) to a 1-bit monochrome BMP suitable for CircuitPython displayio.OnDiskBitmap.

Usage (run from repo root):
  python tools/convert_to_1bit.py --input logo.bmp --output logo_1bit.bmp --dither fs --invert false --threshold 128

Notes:
- Output is a 1-bit, uncompressed BMP (mode '1').
- Dithering 'fs' (Floyd-Steinberg) gives smoother visual results on e-ink.
- Use --invert true if your display expects white background (often yes) and your source appears inverted.
- You can omit --threshold when using dithering; it's used only for no-dither mode.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from PIL import Image


def to_1bit(
    input_path: Path,
    output_path: Path,
    dither: str = "fs",
    invert: bool = False,
    threshold: int = 128,
) -> None:
    img = Image.open(input_path)

    # Convert to grayscale first for consistent results
    gray = img.convert("L")

    if dither.lower() in ("fs", "floyd", "floyd-steinberg"):
        bw = gray.convert("1", dither=Image.FLOYDSTEINBERG)
    elif dither.lower() in ("none", "off", "0"):
        # Manual threshold for no-dither path
        th = max(0, min(255, int(threshold)))
        bw = gray.point(lambda x: 255 if x >= th else 0, mode="1")
    else:
        raise ValueError("Invalid dither option. Use 'fs' or 'none'.")

    if invert:
        # Invert black/white for displays that need white background
        bw = Image.eval(bw, lambda px: 255 - px)

    # Ensure mode '1' before saving as BMP
    if bw.mode != "1":
        bw = bw.convert("1")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bw.save(output_path, format="BMP")

    # Report info
    out_size = output_path.stat().st_size
    print(f"Saved {output_path} ({out_size} bytes), size={bw.size}, mode={bw.mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert image to 1-bit BMP for CircuitPython")
    parser.add_argument("--input", required=True, help="Input image path (e.g., logo.bmp)")
    parser.add_argument("--output", default="logo_1bit.bmp", help="Output image path")
    parser.add_argument("--dither", default="fs", choices=["fs", "none"], help="Dithering method")
    parser.add_argument("--invert", default="false", choices=["true", "false"], help="Invert black/white")
    parser.add_argument("--threshold", type=int, default=128, help="Threshold for no-dither (0-255)")
    args = parser.parse_args()

    invert = args.invert.lower() == "true"

    to_1bit(
        input_path=Path(args.input),
        output_path=Path(args.output),
        dither=args.dither,
        invert=invert,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
