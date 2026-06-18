#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Montage der oberen + unteren Seitenraender aller 29 NP203-Scans, damit die
gedruckten Seitenzahlen visuell ablesbar sind (OCR unzuverlaessig).
Schreibt /tmp/np203_top.png und /tmp/np203_bot.png (je 29 beschriftete Streifen).
"""
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

SRC = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans')
ROW_W = 1800       # Zielbreite je Streifen
STRIP = 0.05       # Anteil oben/unten


def gray(p):
    d = fitz.open(p)
    pix = d[0].get_pixmap(dpi=72, colorspace=fitz.csGRAY)  # native 5100x7013
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    return im


def strip(im, top: bool):
    w, h = im.size
    c = im.crop((0, 0, w, int(h * STRIP))) if top else im.crop((0, int(h * (1 - STRIP)), w, h))
    return c.resize((ROW_W, int(c.height * ROW_W / c.width)))


def montage(files, top: bool, out: Path):
    strips = []
    for p in files:
        s = strip(gray(p), top).convert('L')
        strips.append((p.stem, s))
    rowh = max(s.height for _, s in strips)
    lblw = 360
    canvas = Image.new('L', (lblw + ROW_W, rowh * len(strips)), 255)
    dr = ImageDraw.Draw(canvas)
    for i, (name, s) in enumerate(strips):
        y = i * rowh
        canvas.paste(s, (lblw, y))
        dr.text((6, y + rowh // 2 - 6), name, fill=0)
        dr.line((0, y, canvas.width, y), fill=0, width=2)
    canvas.save(out)
    print(f'-> {out} ({canvas.width}x{canvas.height})')


def main():
    files = sorted(SRC.glob('Scan_20260618*.pdf'))
    montage(files, True, Path('/tmp/np203_top.png'))
    montage(files, False, Path('/tmp/np203_bot.png'))


if __name__ == '__main__':
    main()
