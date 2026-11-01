#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liest die Hoch-/Niedrigwasser der Myanma Port Authority (mpa.gov.mm, Tidal Information).

Die Seite fuehrt je Pegel (Elephant Point, Yangon River) eine Tabelle Datum / vier Paare Zeit+Hoehe.
Die Spalten "Low/High" sind nicht verlaesslich vertauscht; deshalb zaehlt allein die Hoehe. "00:00 0.00"
heisst: kein vierter Scheitel an diesem Tag. Zeiten MMT (UTC+6:30), Quelle: Internet Archive 13.03.2026
(die Seite selbst hat ein unvollstaendiges Zertifikat).

Usage: als Modul -- lesen() -> {pegel: [(unixzeit, hoehe), ...]}
"""
from __future__ import annotations

import datetime as dt
import html
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PFAD = os.path.join(ROOT, 'tide_tables/myanmar_mpa/mpa_tidal_archiv_20260313.html')
MMT = dt.timezone(dt.timedelta(hours=6, minutes=30))
ZEILE = re.compile(r'(\d\d)/(\d\d)/(20\d\d)((?: \d\d:\d\d -?\d+\.\d+){1,4})')


def lesen():
    t = open(PFAD, encoding='utf-8', errors='replace').read()
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', t, flags=re.S)
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
    teile = re.split(r'(Elephant Point|Yangon River) Date Time Low', t)
    aus = {}
    for pegel, text in zip(teile[1::2], teile[2::2]):
        z = aus.setdefault(pegel, {})
        for d, m, j, rest in ZEILE.findall(text):
            for hm, h in re.findall(r'(\d\d:\d\d) (-?\d+\.\d+)', rest):
                if hm == '00:00' and float(h) == 0.0:
                    continue
                try:
                    a = dt.datetime(int(j), int(m), int(d), int(hm[:2]), int(hm[3:]), tzinfo=MMT)
                except ValueError:      # Tippfehler der Quelle wie 11:75
                    continue
                z[a.timestamp()] = float(h)
    return {p: sorted(v.items()) for p, v in aus.items()}


if __name__ == '__main__':
    for p, v in lesen().items():
        lu = [(b[0] - a[0]) / 3600 for a, b in zip(v, v[1:])]
        print(p, len(v), dt.datetime.fromtimestamp(v[0][0], MMT).date(), dt.datetime.fromtimestamp(v[-1][0], MMT).date(),
              'min/max h', min(x[1] for x in v), max(x[1] for x in v), 'Abstand', round(min(lu), 2), round(max(lu), 2),
              'gleiche Richtung', sum(1 for a, b, c in zip(v, v[1:], v[2:]) if (b[1] - a[1]) * (c[1] - b[1]) > 0))
