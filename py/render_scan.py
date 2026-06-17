#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendert einen komprimierten ATT-Scan korrekt orientiert (Rohbild ist
vertikal gespiegelt -> ImageOps.flip) als PNG nach /tmp, zum Lesen.
Aufruf: python render_scan.py "Scan_20260615 (30)" [oberer_anteil unterer_anteil]
"""
import io
import sys
from pathlib import Path

import fitz
from PIL import Image, ImageOps

DST = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans_compressed')


def page_img(p: Path):
    d = fitz.open(p)
    imgs = d[0].get_images(full=True)
    if imgs:
        im = Image.open(io.BytesIO(d.extract_image(imgs[0][0])['image'])).convert('L')
    else:
        pix = d[0].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
        im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    return ImageOps.flip(im)


def main():
    name = sys.argv[1]
    if not name.endswith('.pdf'):
        name += '.pdf'
    im = page_img(DST / name)
    # optional vertikaler Ausschnitt (Anteile 0..1)
    if len(sys.argv) >= 4:
        t0, t1 = float(sys.argv[2]), float(sys.argv[3])
        w, h = im.size
        im = im.crop((0, int(h * t0), w, int(h * t1)))
    out = Path('/tmp') / (Path(name).stem + '.png')
    im.save(out)
    print(out)


if __name__ == '__main__':
    main()
