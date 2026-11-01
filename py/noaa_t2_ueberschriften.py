#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die kursiven Zwischenueberschriften aus Table 2 der NOAA-Stromtafeln (1.11.2026).

"Oyster Bay" steht im Buch kleiner und links, die Eintraege darunter sind eingerueckt; im Import und
in der CO-OPS-API fehlt die Ueberschrift ("Harbor, west of Soper Point"). Erkannt wird sie an der
kleineren Schrift (Hoehe ~6,5 statt ~7,9 pt) ohne Laufnummer. Sie gilt, solange die Eintraege eingerueckt sind.

Usage: python3 py/noaa_t2_ueberschriften.py -> harmonics/help/noaa_t2_ueberschriften.json {buch: {no: ueberschrift}}
"""
from __future__ import annotations

import collections
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCH = {'acct': 'tide_tables/NOAA/acct_2020_full_book.pdf', 'pcct': 'tide_tables/NOAA/pcct_2020_full_book.pdf'}
WORT = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


def zeilen(pdf, seite):
    t = subprocess.run(['pdftotext', '-f', str(seite), '-l', str(seite), '-bbox', pdf, '-'], capture_output=True, text=True).stdout
    w = sorted((float(b), float(a), float(d) - float(b), s) for a, b, c, d, s in WORT.findall(t))
    z = []
    for y, x, h, s in w:
        if z and abs(z[-1][0] - y) < 2.5 and abs(z[-1][2] - h) < 0.6:
            z[-1][1].append((x, s))
        else:
            z.append([y, [(x, s)], h])
    return [(y, sorted(ws), h) for y, ws, h in z]


def main():
    aus = {}
    for buch, pfad in BUCH.items():
        T = json.load(open(os.path.join(ROOT, f'harmonics/help/{buch}_t2_full.json'), encoding='utf-8'))
        seiten = sorted({x['pdfpage'] for x in T if x.get('pdfpage')})
        haupt = {}
        for s in seiten:
            kopf = None
            for _y, ws, h in zeilen(os.path.join(ROOT, pfad), s):
                ws = [(x, t) for x, t in ws if x < 215]
                if not ws:
                    continue
                if re.fullmatch(r'\d{1,4}', ws[0][1]) and len(ws) > 1:
                    no = int(ws[0][1])
                    einger = ws[1][0] - GRUND
                    if kopf and einger > 3:
                        haupt[no] = kopf
                    else:
                        kopf = None
                elif h < 7.0 and 70 < ws[0][0] < 82 and re.match(r'[A-Z]', ws[0][1]) and 'do.' not in ws[0][1]:
                    k = ' '.join(t for _x, t in ws if not set(t) <= set('. '))
                    if len(k) > 3 and not k.endswith('mile') and k.upper() != k:
                        kopf = k
        aus[buch] = haupt
        print(buch, len(T), len(haupt), collections.Counter(haupt.values()).most_common(10))
    json.dump(aus, open(os.path.join(ROOT, 'harmonics/help/noaa_t2_ueberschriften.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)


GRUND = 77.5
if __name__ == '__main__':
    main()
