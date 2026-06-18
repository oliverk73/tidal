#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fuer die 29 neuen NP203-Scans (Scan_20260618*): Orientierung (OSD +
Bild-Transformationsmatrix) pruefen und gedruckte Seitenzahl per OCR lesen.
Read-only. Ausgabe: /tmp/np203_pages.tsv  (datei \t osd_rot \t d_sign \t pageno_raw)
"""
import re
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

SRC = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans')
OUT = Path('/tmp/np203_pages.tsv')


def render(p, dpi=150):
    d = fitz.open(p)
    pg = d[0]
    info = pg.get_image_info(xrefs=True)
    dsign = 'd<0' if (info and info[0]['transform'][3] < 0) else (
        'd>0' if info else 'noimg')
    pix = pg.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    return im, dsign


def osd(im):
    try:
        d = pytesseract.image_to_osd(im, output_type=pytesseract.Output.DICT)
        return d.get('rotate', -1)
    except Exception:
        return -1


def page_numbers(im):
    """OCR unteres + oberes Band (volle Breite) -> alle gefundenen 3-stelligen Zahlen."""
    w, h = im.size
    found = []
    for t0, t1 in [(0.955, 1.0), (0.0, 0.045)]:
        c = im.crop((0, int(h * t0), w, int(h * t1)))
        if c.width > 2000:
            c = c.resize((2000, int(c.height * 2000 / c.width)))
        txt = pytesseract.image_to_string(c, config='--psm 6 -c tessedit_char_whitelist=0123456789 ')
        found += re.findall(r'\b(\d{3})\b', txt)
    return found


def main():
    files = sorted(SRC.glob('Scan_20260618*.pdf'))
    rows = ['file\tosd_rot\td_sign\tpagenos']
    for i, p in enumerate(files, 1):
        im, dsign = render(p)
        rot = osd(im)
        nums = page_numbers(im)
        rows.append(f'{p.name}\t{rot}\t{dsign}\t{",".join(nums)}')
        print(f'[{i}/{len(files)}] {p.name}: rot={rot} {dsign} pages={nums}')
    OUT.write_text('\n'.join(rows), encoding='utf-8')
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
