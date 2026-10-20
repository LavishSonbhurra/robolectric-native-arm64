#!/usr/bin/env python3
"""Writes the small decode-test images into app/src/test/resources/images.

The files are committed, so this only needs to run again if the set changes. Every pixel is
computed from its coordinates (no randomness), so the output is reproducible with the same
Pillow version. Needs Pillow with WebP support.

Usage: scripts/make-assets.py [output dir]
"""
import math
import os
import sys

from PIL import Image

W, H = 96, 64


def photo_like():
    img = Image.new("RGBA", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            r = int(255 * x / (W - 1))
            g = int(255 * y / (H - 1))
            b = int(127 + 127 * math.sin(x / 6.0) * math.cos(y / 5.0))
            # A disc with a soft edge and a transparent corner, so alpha matters.
            d = math.hypot(x - 60, y - 30)
            if d < 18:
                r, g, b = 250, 240, 40
            elif d < 21:
                t = (d - 18) / 3
                r = int(250 * (1 - t) + r * t)
                g = int(240 * (1 - t) + g * t)
                b = int(40 * (1 - t) + b * t)
            a = 255 if x + y > 20 else int(255 * (x + y) / 20)
            # Fine stripes stress chroma subsampling and filtering.
            if 8 <= y < 20 and (x // 2) % 2 == 0:
                r, g, b = 20, 20, 160
            px[x, y] = (r, g, b, a)
    return img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "app", "src", "test", "resources", "images")
    os.makedirs(out, exist_ok=True)
    rgba = photo_like()
    rgb = rgba.convert("RGB")
    rgba.save(os.path.join(out, "photo-rgba.png"), optimize=False)
    rgb.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).save(os.path.join(out, "photo-palette.png"))
    rgb.convert("L").save(os.path.join(out, "photo-gray.png"))
    rgb.save(os.path.join(out, "photo-q90-420.jpg"), quality=90, subsampling=2)
    rgb.save(os.path.join(out, "photo-q75-444-progressive.jpg"), quality=75, subsampling=0, progressive=True)
    rgba.save(os.path.join(out, "photo-lossy.webp"), quality=80, method=4)
    rgba.save(os.path.join(out, "photo-lossless.webp"), lossless=True)
    # Large enough for inSampleSize and BitmapRegionDecoder.
    rgb.resize((W * 4, H * 4), Image.Resampling.NEAREST).save(os.path.join(out, "photo-large.jpg"), quality=92)
    for name in sorted(os.listdir(out)):
        print(name, os.path.getsize(os.path.join(out, name)))


if __name__ == "__main__":
    main()
