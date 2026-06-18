#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erkennt per Tesseract-OSD, welche ATT-Scans kopfstehend (180°) sind.
Read-only: schreibt nur einen Report nach /tmp/scan_rotation.tsv.
Rendert via get_pixmap (gleiche, korrekt-orientierte Methode wie compress/render).
"""
import sys
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

SRC = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans')
OUT = Path('/tmp/scan_rotation.tsv')


def page_img(p: Path):
    d = fitz.open(p)
    pix = d[0].get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    return im


def osd(im):
    if im.width > 1600:
        im = im.resize((1600, int(im.height * 1600 / im.width)))
    try:
        d = pytesseract.image_to_osd(im, output_type=pytesseract.Output.DICT)
        return d.get('rotate', -1), d.get('orientation_conf', 0.0)
    except Exception as e:
        return -1, str(e)


def main():
    files = sorted(SRC.glob('*.pdf'))
    rows = ['file\trotate\tconf']
    flipped = []
    for i, p in enumerate(files, 1):
        try:
            rot, conf = osd(page_img(p))
        except Exception as e:
            rot, conf = -1, str(e)
        rows.append(f'{p.name}\t{rot}\t{conf}')
        mark = ' <== 180' if rot == 180 else ''
        if rot == 180:
            flipped.append(p.name)
        print(f'[{i}/{len(files)}] {p.name}: rotate={rot} conf={conf}{mark}')
    OUT.write_text('\n'.join(rows), encoding='utf-8')
    print(f'\n{len(flipped)} kopfstehend (180°):')
    for n in flipped:
        print(f'  {n}')
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
