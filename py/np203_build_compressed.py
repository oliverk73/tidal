#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fuehrt die 29 neuen NP203-Scans (Scan_20260618*) nach gedruckter Seitenzahl
sortiert in 2 komprimierte PDFs zusammen:
  - NP203_2015_StandardPorts_240-253.pdf  (Part III Harmonic Constants)
  - NP203_2015_SecondaryPorts_222-236.pdf (Part II Secondary Ports)
Graustufe + JPEG (volle 600-dpi-Aufloesung), nicht-destruktiv.

Seitenzuordnung kommt aus PAGE_MAP (datei -> gedruckte Seitenzahl), das nach der
verifizierten OCR/visuellen Pruefung hier eingetragen wird.
"""
import io
from pathlib import Path

import fitz
from PIL import Image

SRC = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans')
DST = SRC.parent / 'Scans_compressed'
QUALITY = 80

# datei-stem -> gedruckte Seitenzahl (OCR + visuell verifiziert 2026-06-18)
PAGE_MAP = {
    'Scan_20260618 (13)': 222, 'Scan_20260618 (14)': 223, 'Scan_20260618 (15)': 224,
    'Scan_20260618 (16)': 225, 'Scan_20260618 (17)': 226, 'Scan_20260618 (18)': 227,
    'Scan_20260618 (19)': 228, 'Scan_20260618 (20)': 229, 'Scan_20260618 (21)': 230,
    'Scan_20260618 (22)': 231, 'Scan_20260618 (23)': 232, 'Scan_20260618 (24)': 233,
    'Scan_20260618 (25)': 234, 'Scan_20260618 (26)': 235, 'Scan_20260618 (27)': 236,
    'Scan_20260618 (28)': 237, 'Scan_20260618 (29)': 238,
    'Scan_20260618': 240, 'Scan_20260618 (2)': 241, 'Scan_20260618 (3)': 242,
    'Scan_20260618 (4)': 243, 'Scan_20260618 (5)': 244, 'Scan_20260618 (6)': 245,
    'Scan_20260618 (7)': 246, 'Scan_20260618 (8)': 247, 'Scan_20260618 (9)': 248,
    'Scan_20260618 (10)': 249, 'Scan_20260618 (11)': 252, 'Scan_20260618 (12)': 253,
}

# Part III Standardhafen-Konstanten beginnen S.240; alles davor = Part II Secondary.
SECONDARY = range(222, 240)  # 222..239 (Part II)
STANDARD = range(240, 254)   # 240..253 (Part III)
WANT_STD = set(range(240, 254))   # angefragt
WANT_SEC = set(range(222, 237))   # angefragt 222..236


def page_jpeg(p: Path, q=QUALITY):
    d = fitz.open(p)
    # dpi=72 => 1:1 native Pixel (Seitenrect == Bildpixel); Graustufe
    pix = d[0].get_pixmap(dpi=72, colorspace=fitz.csGRAY)
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=q, optimize=True)
    return buf.getvalue(), pix.width, pix.height


def build(pages, out: Path):
    """pages: Liste (pageno, src_path) -> nach pageno sortiert in out schreiben."""
    dout = fitz.open()
    for pageno, src in sorted(pages):
        jpg, w, h = page_jpeg(src)
        pg = dout.new_page(width=w, height=h)
        pg.insert_image(pg.rect, stream=jpg)
        print(f'  S.{pageno}: {src.name} -> {len(jpg)//1024} KB')
    dout.save(out, deflate=True, garbage=4)
    dout.close()
    print(f'-> {out} ({out.stat().st_size//1024//1024} MB, {len(pages)} Seiten)')


def main():
    DST.mkdir(exist_ok=True)
    assert PAGE_MAP, 'PAGE_MAP leer!'
    assert len(set(PAGE_MAP.values())) == len(PAGE_MAP), 'doppelte Seitenzahl!'
    std, sec, unknown = [], [], []
    for stem, pageno in PAGE_MAP.items():
        src = SRC / f'{stem}.pdf'
        if pageno in STANDARD:
            std.append((pageno, src))
        elif pageno in SECONDARY:
            sec.append((pageno, src))
        else:
            unknown.append((stem, pageno))
    std_have = {p for p, _ in std}; sec_have = {p for p, _ in sec}
    print(f'Standard (240-253): {sorted(std_have)}')
    print(f'  FEHLT (angefragt): {sorted(WANT_STD - std_have)}')
    print(f'Secondary (222-239): {sorted(sec_have)}')
    print(f'  FEHLT (angefragt 222-236): {sorted(WANT_SEC - sec_have)}')
    if unknown:
        print(f'UNZUGEORDNET: {unknown}')
    print('\nStandard Ports:')
    a, b = min(std_have), max(std_have)
    build(std, DST / f'NP203_2015_StandardPorts_{a}-{b}.pdf')
    print('Secondary Ports:')
    a, b = min(sec_have), max(sec_have)
    build(sec, DST / f'NP203_2015_SecondaryPorts_{a}-{b}.pdf')


if __name__ == '__main__':
    main()
