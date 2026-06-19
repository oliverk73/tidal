#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fuehrt die 15 NP207-Scans (Scan_20260616 39-44 = Part III Standard Ports,
Scan_20260619* = Part II Secondary Ports) nach gedruckter Seitenzahl sortiert
in 2 komprimierte PDFs zusammen:
  - NP207_StandardPorts_160-165.pdf  (Part III Harmonic Constants)
  - NP207_SecondaryPorts_150-158.pdf (Part II Secondary Ports)
Graustufe + JPEG, nicht-destruktiv.

Seitenzuordnung (PAGE_MAP) OCR + visuell verifiziert 2026-06-19:
160/165 (Eck-PNG gelesen), 162/163 (OCR sauber), 150-158 (OCR sauber),
156 = Scan_20260619 (9) (nachgescannt, visuell '156', BRAZIL; FRENCH GUIANA).
"""
import io
from pathlib import Path

import fitz
from PIL import Image

SRC = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans')
DST = SRC.parent / 'Scans_compressed'
QUALITY = 80

PAGE_MAP = {
    # Part III Standard Ports (Harmonic Constants) 160-165
    'Scan_20260616 (39)': 160, 'Scan_20260616 (40)': 161, 'Scan_20260616 (41)': 162,
    'Scan_20260616 (42)': 163, 'Scan_20260616 (43)': 164, 'Scan_20260616 (44)': 165,
    # Part II Secondary Ports (Differences) 150-158
    'Scan_20260619': 150, 'Scan_20260619 (2)': 151, 'Scan_20260619 (3)': 152,
    'Scan_20260619 (4)': 153, 'Scan_20260619 (5)': 154, 'Scan_20260619 (6)': 155,
    'Scan_20260619 (9)': 156, 'Scan_20260619 (7)': 157, 'Scan_20260619 (8)': 158,
}

STANDARD = range(160, 166)   # 160..165 (Part III)
SECONDARY = range(150, 159)  # 150..158 (Part II)


def page_jpeg(p: Path, q=QUALITY):
    d = fitz.open(p)
    pix = d[0].get_pixmap(dpi=72, colorspace=fitz.csGRAY)  # native Pixel
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=q, optimize=True)
    return buf.getvalue(), pix.width, pix.height


def build(pages, out: Path):
    dout = fitz.open()
    for pageno, src in sorted(pages):
        jpg, w, h = page_jpeg(src)
        pg = dout.new_page(width=w, height=h)
        pg.insert_image(pg.rect, stream=jpg)
        print(f'  S.{pageno}: {src.name} -> {len(jpg)//1024} KB')
    dout.save(out, deflate=True, garbage=4)
    dout.close()
    print(f'-> {out} ({out.stat().st_size//1024} KB, {len(pages)} Seiten)')


def main():
    DST.mkdir(exist_ok=True)
    assert len(set(PAGE_MAP.values())) == len(PAGE_MAP), 'doppelte Seitenzahl!'
    std, sec = [], []
    for stem, pageno in PAGE_MAP.items():
        src = SRC / f'{stem}.pdf'
        assert src.exists(), f'fehlt: {src}'
        (std if pageno in STANDARD else sec).append((pageno, src))
    std_have = sorted(p for p, _ in std); sec_have = sorted(p for p, _ in sec)
    print(f'Standard {std_have}  fehlt={sorted(set(STANDARD)-set(std_have))}')
    print(f'Secondary {sec_have}  fehlt={sorted(set(SECONDARY)-set(sec_have))}')
    print('\nStandard Ports:')
    build(std, DST / 'NP207_StandardPorts_160-165.pdf')
    print('Secondary Ports:')
    build(sec, DST / 'NP207_SecondaryPorts_150-158.pdf')


if __name__ == '__main__':
    main()
