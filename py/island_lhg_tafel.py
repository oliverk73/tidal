#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest Tafla I der Sjavarfallatoflur 2026 (Landhelgisgaesla Islands).

Fuenf Hafen je vier Seiten (je drei Monate, 2x sechs Spalten) mit allen
Hoch- und Niedrigwassern 2026, Zeiten GMT, Hoehen ueber Seekartennull in
0,1 m. Der Textlayer ist sauber; die Spalten lassen sich aber nur ueber
die Wortpositionen (pdftotext -bbox) zuordnen.

Usage: als Modul -- tafel(hafen) -> [(unixzeit, hoehe)]; alle HAEFEN
"""
from __future__ import annotations

import calendar
import datetime as dt
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'tide_tables/iceland_sjolag/lhg_sjavarfallatoflur_2026.pdf')
HAEFEN = {'Reykjavík': 7, 'Ísafjörður': 11, 'Siglufjörður': 15, 'Djúpivogur': 19, 'Þorlákshöfn': 23}
MONAT = {'Janúar': 1, 'Febrúar': 2, 'Mars': 3, 'Apríl': 4, 'Maí': 5, 'Júní': 6,
         'Júlí': 7, 'Ágúst': 8, 'September': 9, 'Október': 10, 'Nóvember': 11, 'Desember': 12}
WORT = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


def woerter(seite):
    t = subprocess.run(['pdftotext', '-f', str(seite), '-l', str(seite), '-bbox', PDF, '-'],
                       capture_output=True, text=True, check=True).stdout
    return [(float(a), float(b), float(c), float(d), w) for a, b, c, d, w in WORT.findall(t)]


def seite_lesen(seite):
    """-> [(monat, tag, hhmm, hoehe)] einer Tafelseite."""
    w = woerter(seite)
    monate = sorted([(x0, MONAT[t]) for x0, _y0, _x1, _y1, t in w if t in MONAT])
    tage = [(x0, y0, y1, int(t)) for x0, y0, _x1, y1, t in w
            if re.fullmatch(r'\d{1,2}', t) and 1 <= int(t) <= 31 and y1 - y0 > 18]
    hoehen = [(x0, y0, t) for x0, y0, _x1, _y1, t in w if re.fullmatch(r'-?\d,\d', t)]
    out = []
    for x0, y0, _x1, _y1, t in w:
        if y0 < 100 or not re.fullmatch(r'\d{4}', t) or int(t[:2]) > 23 or int(t[2:]) > 59:
            continue
        kand = [(hx, h) for hx, hy, h in hoehen if abs(hy - y0) < 1.5 and 25 < hx - x0 < 40]
        if len(kand) != 1:
            raise ValueError(f'Seite {seite}: {t} bei y={y0}: {kand}')
        h = float(kand[0][1].replace(',', '.'))
        # Tag: naechste Tageszahl links davon, deren Zeile die Zeit enthaelt
        links = [d for d in tage if 5 < x0 - d[0] < 32 and d[1] - 3 <= y0 < d[1] + 40]
        if not links:
            raise ValueError(f'Seite {seite}: kein Tag zu {t} bei {x0:.0f}/{y0:.0f}')
        tag = max(links, key=lambda d: d[1])[3]
        # Monat: drei Spaltenpaare je Seite
        mon = monate[0 if x0 < 212 else 1 if x0 < 375 else 2][1]
        out.append((mon, tag, t, h))
    return out


def tafel(hafen):
    start = HAEFEN[hafen]
    zeilen = []
    for s in range(start, start + 4):
        zeilen += seite_lesen(s)
    out = []
    for mon, tag, hm, h in zeilen:
        if tag > calendar.monthrange(2026, mon)[1]:
            raise ValueError((hafen, mon, tag, hm))
        z = dt.datetime(2026, mon, tag, int(hm[:2]), int(hm[2:]), tzinfo=dt.timezone.utc)
        out.append((z.timestamp(), h))
    return sorted(out)


if __name__ == '__main__':
    for hafen in HAEFEN:
        t = tafel(hafen)
        lu = [round((b[0] - a[0]) / 3600, 2) for a, b in zip(t, t[1:])]
        wech = sum(1 for a, b, c in zip(t, t[1:], t[2:]) if (b[1] - a[1]) * (c[1] - b[1]) > 0)
        print(hafen, len(t), 'Abstand h', min(lu), max(lu), 'ohne Wechsel', wech,
              'Hoehe', min(x[1] for x in t), max(x[1] for x in t))
