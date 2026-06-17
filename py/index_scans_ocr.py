#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Indiziert alle komprimierten ATT-Scans per OCR: Titel-Header (Region) +
Seitenzahl. Rohbild ist vertikal gespiegelt -> ImageOps.flip korrigiert.
Ausgabe: /tmp/scan_index.tsv  (datei \t seite \t titel)
"""
import io
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageOps

DST = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans_compressed')
OUT = Path('/tmp/scan_index.tsv')


def page_img(p: Path):
    d = fitz.open(p)
    imgs = d[0].get_images(full=True)
    if imgs:
        im = Image.open(io.BytesIO(d.extract_image(imgs[0][0])['image'])).convert('L')
    else:
        pix = d[0].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
        im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    return ImageOps.flip(im)  # Rohbild vertikal gespiegelt


def ocr(im, t0, t1):
    w, h = im.size
    c = im.crop((0, int(h * t0), w, int(h * t1)))
    if c.width > 1600:
        c = c.resize((1600, int(c.height * 1600 / c.width)))
    return pytesseract.image_to_string(c, config='--psm 6').replace('\n', ' ').strip()


def main():
    files = sorted(DST.glob('*.pdf'))
    rows = []
    for i, p in enumerate(files, 1):
        try:
            im = page_img(p)
            title = ocr(im, 0.0, 0.055)
            pageno = ocr(im, 0.955, 1.0)
        except Exception as e:
            title, pageno = f'ERR {e}', ''
        rows.append(f'{p.name}\t{pageno}\t{title}')
        print(f'[{i}/{len(files)}] {p.name}: p[{pageno[:12]}] {title[:60]}')
    OUT.write_text('\n'.join(rows), encoding='utf-8')
    print(f'\n-> {OUT}')


if __name__ == '__main__':
    main()
