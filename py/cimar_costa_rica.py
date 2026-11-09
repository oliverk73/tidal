#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Costa Rica: Tidenkalender 2026 des UCR-CIMAR (Modulo de Informacion Oceanografica) lesen und pruefen (9.11.2026).

Quelle: tide_tables/costa_rica/Tabla_Mareas_<Ort>_2026.pdf (LaTeX, Text auslesbar), HW/NW, Ortszeit UTC-6,
Bezug "promedio de las mareas bajas" (>= 20 Jahre). Je Seite drei Monate, je Monat zwei Spalten (1.-16., 17.-31.).
Gelesen ueber pdftotext -bbox: jede Uhrzeit, rechts daneben die Hoehe; Tag = letzte Tageszahl links darueber.

BEFUND 9.11.2026 -- nichts uebernommen:
- Alle acht Pazifik-Tafeln sind Uebertragungen von Puntarenas: feste Zeitdifferenz je HW/NW, fester Hubfaktor,
  Streuung 0 (Culebra/Santa Elena -2 min x1,00, Herradura -6/-1, Golfito -13/+2 x1,03, Quepos -13/-4 x0,91,
  Uvita -25/-20 x1,00, Isla del Coco -25 x0,93). Eigene Information nur in Puntarenas (trifft TICON 3 %, 3 min).
- Unsere Messsaetze schlagen die Uebertragungen: Marina Papagayo, Cuajiniquil, Flamingo 23-27 % kleiner als die
  Culebra/Santa-Elena-Tafel (SINAMOT Nacascolo bestaetigt die Messung, Hub 0,97); Herradura 13 %, Coco 12 %/16 min.
- NOAA "Golfo Elena" und "Bahia Uvita" sind dieselben Puntarenas-Uebertragungen (gegen die Tafel 0,3 cm, 0 min):
  M2 28 % bzw. 12 % zu gross -> FES geeicht (harmonics/help/fes_ersetzen_20261109_costa_rica.csv), NOAA archiviert.
- Limon (Karibik, Mikrotide): Tafel selbst mit vertauschten Zeiten, unbrauchbar.
SINAMOT (UNA, "Mareas <Ort> 2026.pdf", Fuss, Ortszeit): eigene Vorhersagen, Puntarenas/Nacascolo bestaetigen den
Bestand (Kurve 2 %/4 %). Rincon de Osa (kein Satz): Tafelfit M2 1,03@237 gegen Golfito-Messung 1,10@247 und FES im
ganzen Golfo Dulce 1,11@245 -- 8 % kleiner, 20 min frueher, nicht uebernommen.

Usage: venv/bin/python py/cimar_costa_rica.py
"""
import datetime as dt
import glob
import html
import os
import re
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'tide_tables/costa_rica')
MONATE = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre',
          'Noviembre', 'Diciembre']
WORT = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')
UTC_VERSATZ_H = -6


def woerter(pdf, seite):
    out = subprocess.run(['pdftotext', '-bbox', '-f', str(seite), '-l', str(seite), pdf, '-'],
                         capture_output=True, text=True).stdout
    return [(float(a), float(b), float(c), float(d), html.unescape(w)) for a, b, c, d, w in WORT.findall(out)]


def lesen(pdf, jahr=2026):
    """-> (Ereignisse [(datetime UTC, Hoehe m)], Kopf {name, lat, lon})."""
    kopf, ev = {}, []
    seiten = int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout)[1])
    for s in range(1, seiten + 1):
        w = woerter(pdf, s)
        txt = ' '.join(x[4] for x in w)
        m = re.search(r'Latitud\s+(-?[\d.]+)°([NS]),\s+Longitud\s+(-?[\d.]+)°W', txt)
        if m and not kopf:
            la = float(m[1]) * (1 if m[2] == 'N' else -1)
            lo = -abs(float(m[3]))
            kopf = dict(lat=la, lon=lo, name=re.split(r'\s+Latitud', txt)[0].strip())
        koepfe = [(x[0], MONATE.index(x[4]) + 1) for x in w if x[4] in MONATE]
        if not koepfe:
            continue
        zeiten = [x for x in w if re.fullmatch(r'\d\d:\d\d', x[4])]
        hoehen = [x for x in w if re.fullmatch(r'-?\d+\.\d\d', x[4])]
        tage = [x for x in w if re.fullmatch(r'\d\d', x[4]) and 1 <= int(x[4]) <= 31]
        for tx, ty, txe, tye, tw in zeiten:
            hs = [h for h in hoehen if abs(h[1] - ty) < 1.0 and 0 < h[0] - txe < 40]
            if not hs:
                raise ValueError(f'{pdf} S.{s}: keine Hoehe zu {tw} bei x={tx:.0f} y={ty:.0f}')
            hoehe = float(min(hs, key=lambda h: h[0])[4])
            ds = [d for d in tage if 8 < tx - d[2] < 30 and d[1] <= ty + 3.5]
            if not ds:
                raise ValueError(f'{pdf} S.{s}: kein Tag zu {tw} bei x={tx:.0f} y={ty:.0f}')
            tag = int(max(ds, key=lambda d: d[1])[4])
            monat = min(koepfe, key=lambda k: abs(k[0] - (tx + 20)))[1]
            hh, mm = map(int, tw.split(':'))
            t = dt.datetime(jahr, monat, tag, hh, mm, tzinfo=dt.timezone.utc) - dt.timedelta(hours=UTC_VERSATZ_H)
            ev.append((t, hoehe))
    ev.sort()
    return ev, kopf


def pruefen(ev):
    """Plausibilitaet: Abstaende 2-9 h (Tagestide bis 15 h), HW/NW im Wechsel."""
    t = np.array([e[0].timestamp() for e in ev]) / 3600
    h = np.array([e[1] for e in ev])
    d = np.diff(t)
    wechsel = np.sign(np.diff(h))
    nicht = int((wechsel[1:] == wechsel[:-1]).sum())
    return dict(n=len(ev), min_h=round(float(d.min()), 2), max_h=round(float(d.max()), 2), kein_wechsel=nicht,
                tage=len({e[0].date() for e in ev}))


def main(argv):
    for pdf in sorted(glob.glob(os.path.join(QUELLE, 'Tabla_Mareas_*_2026.pdf'))):
        ev, kopf = lesen(pdf)
        print('%-22s %-45s %7.3f %8.3f %s' % (os.path.basename(pdf)[13:-9], kopf.get('name', '')[:45], kopf['lat'],
                                            kopf['lon'], pruefen(ev)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
