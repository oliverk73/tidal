#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Komprimiert die ATT-Scan-PDFs (je ~16 MB, 300-DPI-RGB-PNG pro Seite)
verlustarm fuer die Lesbarkeit: Graustufe + JPEG q78 bei VOLLER Aufloesung.
-> ~95 % kleiner, alle Tabellenziffern bleiben lesbar.

Nicht-destruktiv: schreibt nach <Scans>/../Scans_compressed/, Originale bleiben.
"""
from __future__ import annotations
import io
import os
import sys
from pathlib import Path

import fitz
from PIL import Image

SRC = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans')
DST = SRC.parent / 'Scans_compressed'
QUALITY = 78


def compress_pdf(src: Path, dst: Path) -> tuple[int, int]:
    din = fitz.open(src)
    dout = fitz.open()
    for page in din:
        imgs = page.get_images(full=True)
        if len(imgs) == 1:
            # Standardfall: ein Vollseiten-Bild -> direkt re-encoden
            raw = din.extract_image(imgs[0][0])['image']
            im = Image.open(io.BytesIO(raw))
            if im.mode != 'L':
                im = im.convert('L')
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=QUALITY, optimize=True)
            pg = dout.new_page(width=im.width * 72 / 300,
                               height=im.height * 72 / 300)
            pg.insert_image(pg.rect, stream=buf.getvalue())
        else:
            # Fallback: Seite als Ganzes bei 200 DPI rendern
            pix = page.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            buf = io.BytesIO()
            Image.frombytes('L', (pix.width, pix.height), pix.samples).save(
                buf, 'JPEG', quality=QUALITY, optimize=True)
            pg = dout.new_page(width=pix.width * 72 / 200,
                               height=pix.height * 72 / 200)
            pg.insert_image(pg.rect, stream=buf.getvalue())
    dout.save(dst, deflate=True, garbage=4)
    dout.close(); din.close()
    return src.stat().st_size, dst.stat().st_size


def main():
    DST.mkdir(exist_ok=True)
    pdfs = sorted(SRC.glob('*.pdf'))
    print(f'{len(pdfs)} PDFs -> {DST}')
    tot_o = tot_n = 0
    fails = []
    for i, src in enumerate(pdfs, 1):
        dst = DST / src.name
        try:
            o, n = compress_pdf(src, dst)
        except Exception as e:  # pro Datei robust
            fails.append((src.name, str(e)))
            print(f'[{i}/{len(pdfs)}] FEHLER {src.name}: {e}')
            continue
        tot_o += o; tot_n += n
        if i % 20 == 0 or i == len(pdfs):
            print(f'[{i}/{len(pdfs)}] {src.name}: {o//1024}->{n//1024}KB')
    print(f'\nGesamt: {tot_o//1024//1024} MB -> {tot_n//1024//1024} MB '
          f'({100*tot_n//max(tot_o,1)} %)')
    if fails:
        print(f'{len(fails)} Fehler:')
        for nm, e in fails:
            print(f'  {nm}: {e}')


if __name__ == '__main__':
    main()
