#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Berichtigt Positionen und Namen in den Table-2-Extrakten der NOAA-Stromtafeln.

pypdf liest die Zeilen teils so, dass die Zehnerstelle der Breite am Namensende
klebt ("Mihara Seto, north of Kone Shima . . . 3" + Breite 4 deg 20' statt 34 deg 20').
Betroffen waren 2026-10-16 rund 430 von 3024 Zeilen (Oliver: fehlende Japan- und
US-Stroeme). pdftotext -layout liest dieselben Zeilen sauber in Spalten; daraus
kommen Breite und Laenge, die Nummer (No.) verbindet beide Lesarten.

Namen: Fuehrungspunkte, angeklebte Ziffern und Endnoten (<7>) werden entfernt.

Usage: venv/bin/python py/noaa_t2_koordinaten.py [--schreiben]
       schreibt harmonics/help/{pcct,acct}_t2_full.json (Sicherung *.vor_koord)
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUCH = {'pcct': 'tide_tables/NOAA/pcct_2020_full_book.pdf', 'acct': 'tide_tables/NOAA/acct_2020_full_book.pdf'}
ZEILE = re.compile(r"^\s{0,8}(\d{1,4})\s+(.+?)\s+(?:(\d+)d\s+)?(\d{1,2})°\s*([\d.]+)’\s+(\d{1,3})°\s*([\d.]+)’")


def layout(pdf):
    txt = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, encoding='utf-8').stdout
    pos = {}
    for z in txt.split('\n'):
        m = ZEILE.match(z)
        if m and 'Daily' not in z:
            pos.setdefault(int(m.group(1)), (int(m.group(4)) + float(m.group(5)) / 60,
                                             int(m.group(6)) + float(m.group(7)) / 60))
    return pos


def name_sauber(n):
    """-> (Name, Messtiefe in ft oder None). Hinter den Fuehrungspunkten steht die Tiefe
    ("Camden Harbor Entrance . . . . 14", "Redwood Point . . . .7 d 3"), teils mit der
    angeklebten Breitenziffer."""
    n = re.sub(r'<\d+>', ' ', n)
    m = re.search(r'(\s*\.\s*){2,}(.*)$', n)
    tiefe = None
    if m:
        z = re.match(r'^(\d+)\s*d?', m.group(2).replace(' ', ''))
        tiefe = int(z.group(1)) if z and 'd' in m.group(2) or (z and len(z.group(1)) >= 2) else None
        n = n[:m.start()]
    return re.sub(r'\s+', ' ', n).strip(' .'), tiefe


def main(argv):
    for v, pdf in BUCH.items():
        pfad = os.path.join(ROOT, 'harmonics/help/%s_t2_full.json' % v)
        J = json.load(open(pfad))
        pos = layout(os.path.join(ROOT, pdf))
        npos = nnam = ohne = 0
        for r in J:
            p = pos.get(r['no'])
            if p is None:
                ohne += 1
            else:
                la = p[0] if r['lat'] >= 0 else -p[0]
                lo = p[1] if r['lon'] >= 0 else -p[1]
                if abs(la - r['lat']) > 0.005 or abs(lo - r['lon']) > 0.005:
                    r['lat'], r['lon'] = round(la, 4), round(lo, 4)
                    npos += 1
            n, tiefe = name_sauber(r['name'])
            if n != r['name']:
                r['name'] = n
                nnam += 1
            if tiefe and not r.get('depth_ft'):
                r['depth_ft'] = tiefe
        print('%s: %d Zeilen, %d Positionen berichtigt, %d Namen gesaeubert, %d ohne Layoutzeile'
              % (v, len(J), npos, nnam, ohne))
        if '--schreiben' in argv:
            if not os.path.exists(pfad + '.vor_koord'):
                shutil.copy(pfad, pfad + '.vor_koord')
            json.dump(J, open(pfad, 'w'), ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main(sys.argv[1:])
