#!/usr/bin/env python3
"""Build the Android adaptive-icon foreground layer from abct-logo.png.

Android 8+ masks the launcher icon to the launcher's shape, so an adaptive
icon is two layers: a 108dp background and a 108dp foreground, of which only
the centre 72dp is guaranteed visible. Feeding the square logo straight in
gets it cropped by the mask.

abct-logo.png is a glowing disc on a black field. That splits cleanly:
  background -> the artwork's own black, as a flat colour (see pubspec.yaml)
  foreground -> the disc alone, alpha-cut out of the field and scaled to the
                safe zone, which is what this script writes

Run from the repo root after changing the logo, then regenerate:

    python3 scripts/make_adaptive_foreground.py
    dart run flutter_launcher_icons

Requires Pillow and numpy.
"""

from PIL import Image
import numpy as np

SRC = "abct-logo.png"
OUT = "abct-logo-adaptive-foreground.png"
CANVAS = 1024
SAFE = round(CANVAS * 72 / 108)

# Measured against the source: lit pixels reach r=382 from centre, and
# everything past ~370 is already below luminance 10. Fading between these
# radii therefore cannot clip anything the eye can see.
R_FULL, R_ZERO = 372.0, 386.0


def main() -> None:
    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    cx, cy = w / 2, h / 2

    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - cx, yy - cy)
    alpha = np.clip((R_ZERO - r) / (R_ZERO - R_FULL), 0.0, 1.0)

    rgba = np.dstack([np.asarray(im), (alpha * 255).round().astype(np.uint8)])
    logo = Image.fromarray(rgba, "RGBA")

    half = int(np.ceil(R_ZERO))
    logo = logo.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
    logo = logo.resize((SAFE, SAFE), Image.LANCZOS)

    out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    off = (CANVAS - SAFE) // 2
    out.paste(logo, (off, off))
    out.save(OUT)
    print(f"wrote {OUT}: {CANVAS}x{CANVAS}, content {SAFE}px ({SAFE / CANVAS:.1%})")


if __name__ == "__main__":
    main()
