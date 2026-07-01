#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR-Index NUR der NP208-Scans (Scan_20260701*) im gemeinsamen
Scans_compressed/-Ordner: liest Region-Header (oben) + Folio-Seitenzahl
(unten und oben-aussen) je Seite. Rohbild vertikal gespiegelt -> ImageOps.flip.
Ausgabe: /tmp/np208_index.tsv  (datei-nr \t seite \t header)
"""
import io, re, sys
from pathlib import Path
import fitz, pytesseract
from PIL import Image, ImageOps

DST = Path('/mnt/c/Users/Ihr Benutzerkonto/Pictures/Scans_compressed')


Image.MAX_IMAGE_PIXELS = None


def page_img(p):
    # get_pixmap skaliert das riesige (~620 MP) eingebettete Bild sauber
    # herunter und liefert aufrechte Orientierung (KEIN Flip noetig).
    d = fitz.open(p)
    pix = d[0].get_pixmap(dpi=55, colorspace=fitz.csGRAY)
    im = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    d.close()
    return im


def ocr(im, t0, t1, x0=0.0, x1=1.0):
    w, h = im.size
    c = im.crop((int(w * x0), int(h * t0), int(w * x1), int(h * t1)))
    return pytesseract.image_to_string(c, config='--psm 6').replace('\n', ' ').strip()


def key(p):
    m = re.search(r'\((\d+)\)', p.name)
    return int(m.group(1)) if m else 1   # base = 1


def main():
    files = sorted(DST.glob('Scan_20260701*.pdf'), key=key)
    print(f'{len(files)} NP208-Scans')
    rows = []
    for i, p in enumerate(files, 1):
        try:
            im = page_img(p)
            header = ocr(im, 0.03, 0.065, 0.25, 0.75)   # Region-Titel (oben mitte)
            foot = ocr(im, 0.965, 0.995, 0.35, 0.65)     # Folio-Seitenzahl (unten mitte)
            nums = re.findall(r'\b(2[0-9]{2}|3[0-9]{2})\b', foot)
        except Exception as e:
            header, foot, nums = f'ERR {e}', '', []
        tag = f'({key(p)})' if key(p) != 1 else 'base'
        rows.append(f'{tag}\t{",".join(nums)}\t{header[:70]}\t{foot[:40]}')
        print(f'[{i}/{len(files)}] {tag:5s} nums={nums} | {header[:55]}')
        sys.stdout.flush()
    Path('/tmp/np208_index.tsv').write_text('\n'.join(rows), encoding='utf-8')
    print('-> /tmp/np208_index.tsv')


if __name__ == '__main__':
    main()
