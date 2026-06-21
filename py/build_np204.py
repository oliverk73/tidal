#!/usr/bin/env python3
# -*- coding: iso-8859-1 -*-
"""NP204 (ATT Vol.4 Pazifik) — MASTER-Builder.

Führt alle Sekundärhafen-Konstanten aus den drei Regions-Datenmodulen
(build_np204_{pacific,russia,asia}.py) in EINE deployte Datei zusammen:
  harmonics_att_np204_secondary.txt   (alle Sekundärhäfen)

ATT-Datei-Konvention (wie NP207): Standard Ports und Secondary Ports getrennt.
Für NP204 wurden AUSSCHLIESSLICH Sekundärhäfen gebaut — die NP204-Standardhäfen
(Kwajalein/Naha/Wusong/Vladivostok/Petropavlovsk/Incheon/Yokohama …) liegen bereits
aus gemessenen Quellen im Bestand und werden NICHT dupliziert. Daher gibt es keine
harmonics_att_np204.txt (Standard) — sie wäre leer.

Die Regions-Skripte bleiben als Daten-/Debug-Module (schreiben nach harmonics/help/
np204/ als Scratch). Phasen ATT-Lokalzone -> Meridian = -(Zone); N2/K2 inferiert.
"""
import os, re, math, importlib, sys

HARM = os.path.expanduser('~/harmonics')
OUT = f'{HARM}/att/harmonics_att_np204_secondary.txt'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
P = importlib.import_module('build_np204_pacific')
R = importlib.import_module('build_np204_russia')
A = importlib.import_module('build_np204_asia')
HEADER, ORDER = P.HEADER, P.ORDER


def norm(entries):
    """Vereinheitlicht die Tupel-Formate: pacific/asia haben mer an Pos 6 (str) +
    country; russia hat ew (int) an Pos 6 + Land=Russia."""
    out = []
    for e in entries:
        if isinstance(e[6], str):                 # pacific/asia
            att, name, ld, lm, od, om, mer, tz, country, z0, M2, S2, K1, O1 = e
            lon = od + om / 60.0
        else:                                     # russia (ew=1/-1)
            att, name, ld, lm, od, om, ew, mer, tz, z0, M2, S2, K1, O1 = e
            lon = ew * (od + om / 60.0); country = 'Russia'
        out.append((att, name, ld + lm / 60.0, lon, mer, tz, country, z0, M2, S2, K1, O1))
    return out


ALL = norm(P.S) + norm(R.S) + norm(A.S)


def record(att, name, lat, lon, mer, tz, country, z0, M2, S2, K1, O1):
    gM2, gS2 = M2[1], S2[1]; hM2, hS2 = M2[0], S2[0]
    con = {'M2': M2, 'S2': S2, 'K1': K1, 'O1': O1,
           'N2': (round(0.19 * hM2, 4), (gM2 - 0.536 * (gS2 - gM2)) % 360),
           'K2': (round(0.27 * hS2, 4), gS2 % 360)}
    micro = hM2 < 0.25
    note = ('NP204 Part III Harmonic Constants; Phasen ATT-Lokalzone (Meridian '
            f'{mer}); N2/K2 inferiert' + ('; mikrotidal' if micro else ''))
    o = ['# BEGIN HOT COMMENTS', f'# country: {country}',
         '# source: ADMIRALTY Tide Tables Vol.4 (NP204), Part III Harmonic Constants',
         f'# att_number: {att}', f'# note: {note}', '# coord_source: NP204 Part II',
         '# date_imported: 20260620', '# datum: Chart Datum (Z0 = mean level above CD)',
         f'# confidence: {2 if micro else 3}', '# !units: meters',
         f'# !longitude: {lon:.4f}', f'# !latitude: {lat:.4f}',
         f'{name}, {country}', f'{mer} :{tz}', f'{z0:.4f} meters']
    for c in ORDER:
        if c in con:
            amp, g = con[c]; o.append(f'{c:<16}{amp:.4f}  {g % 360:.2f}')
        else:
            o.append('x 0 0')
    return '\n'.join(o)


def main():
    seen = {}
    recs = []
    for e in ALL:
        att = e[0]
        if att in seen:
            raise SystemExit(f'Doppelte att_number {att} ({e[1]} vs {seen[att]})')
        seen[att] = e[1]
        recs.append(record(*e))
    open(OUT, 'w', encoding='iso-8859-1').write('\n'.join(HEADER) + '\n' + '\n'.join(recs) + '\n')
    from collections import Counter
    reg = Counter()
    for _, _, lat, lon, *_ in ALL:
        reg['pac' if lon > 130 and 0 < lat < 12 else ('rus' if lat > 42 and (lon > 130 or lon < -160) else 'asia')] += 1
    print(f'Gebaut: {len(recs)} Sekundärhäfen -> {OUT}')
    print(f'  (Pazifik {len(P.S)} + Russland {len(R.S)} + Asien {len(A.S)})')


if __name__ == '__main__':
    main()
