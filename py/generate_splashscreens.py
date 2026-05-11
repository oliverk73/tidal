"""Generate apple-touch-startup-image splash screens for the PWA.

iOS Safari is strict: it only displays an apple-touch-startup-image whose
declared dimensions match the device's native resolution exactly. So we
generate one image per relevant iPhone model and attach each with a
device-specific media query.

Run from the repo root:
    python3 py/generate_splashscreens.py

Output goes to static/splash/. The HTML <link> tags to copy into the
template are printed at the end.
"""

import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ICON = os.path.join(ROOT, "static", "icon-512.png")
OUT_DIR  = os.path.join(ROOT, "static", "splash")
BG_COLOR = (255, 255, 255)  # matches manifest.background_color
ICON_FRACTION = 0.32        # icon occupies ~32% of the shorter side

# (width, height, device-width-pt, device-height-pt, device-pixel-ratio)
# Covers iPhone SE/8 through iPhone 16 Pro Max (2024/2025 lineup).
# Source: https://docs.pwabuilder.com/#/builder/ios?id=splash-screens
DEVICES = [
    # Plain                 px-w   px-h   pt-w   pt-h   dpr  orient
    ("iPhone SE/8/7/6s",      750, 1334, 375, 667, 2, "portrait"),
    ("iPhone XR/11",          828, 1792, 414, 896, 2, "portrait"),
    ("iPhone X/XS/11Pro/12mini",1125,2436, 375, 812, 3, "portrait"),
    ("iPhone 12/13/14",      1170, 2532, 390, 844, 3, "portrait"),
    ("iPhone 14 Plus/13 Pro Max",1284,2778, 428, 926, 3, "portrait"),
    ("iPhone 14 Pro",        1179, 2556, 393, 852, 3, "portrait"),
    ("iPhone 14 Pro Max/15 Pro Max",1290,2796, 430, 932, 3, "portrait"),
    ("iPhone 15/16 Pro",     1206, 2622, 402, 874, 3, "portrait"),
    ("iPhone 16 Pro Max",    1320, 2868, 440, 956, 3, "portrait"),
]


def make_splash(out_path, w, h, icon):
    img = Image.new("RGB", (w, h), BG_COLOR)
    short = min(w, h)
    icon_size = int(short * ICON_FRACTION)
    icon_resized = icon.resize((icon_size, icon_size), Image.LANCZOS)
    # Centre the icon
    paste_x = (w - icon_size) // 2
    paste_y = (h - icon_size) // 2
    # Use alpha channel if present
    if icon_resized.mode == "RGBA":
        img.paste(icon_resized, (paste_x, paste_y), icon_resized)
    else:
        img.paste(icon_resized, (paste_x, paste_y))
    img.save(out_path, "PNG", optimize=True)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    icon = Image.open(SRC_ICON).convert("RGBA")
    links = []
    for name, w, h, pw, ph, dpr, orient in DEVICES:
        fname = f"splash-{w}x{h}.png"
        out_path = os.path.join(OUT_DIR, fname)
        make_splash(out_path, w, h, icon)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"  → {fname} ({size_kb:.0f} KB)  — {name}")
        media = (f"(device-width: {pw}px) and (device-height: {ph}px) "
                 f"and (-webkit-device-pixel-ratio: {dpr}) "
                 f"and (orientation: {orient})")
        links.append(
            f'<link rel="apple-touch-startup-image" '
            f'href="/static/splash/{fname}" media="{media}"/>'
        )

    print("\n--- HTML <link> tags to embed in <head>: ---\n")
    for ln in links:
        print(ln)


if __name__ == "__main__":
    main()
