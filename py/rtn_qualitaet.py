#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Thailand-Saetze gegen die gedruckten RTN-Gezeitentafeln.

Die Tafeln des Royal Thai Navy Hydrographic Department (tide_tables/thailand)
drucken fuer jede Station stuendliche Wasserstaende in Metern. Das ist eine
unabhaengige Referenz: jeder Datensatz im Bestand laesst sich dagegen
nachrechnen, statt seine Quelle zu bewerten.

Der konstante Pegelversatz wird herausgerechnet -- die Bezugsniveaus sind
verschieden (RTN gegen MSL, unsere Saetze teils gegen Chart Datum).

Usage: python3 py/rtn_qualitaet.py [--monat "July 2026"] [--km 5] [--csv <datei>]
"""
from __future__ import annotations

import csv
import math
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km                            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDFS = os.path.join(ROOT, 'tide_tables/thailand')
TCD = '/usr/share/xtide'
# UTC-Fenster fuer einen Monat in Ortszeit (ICT = UTC+7)
FENSTER = {'July 2026': ('2026-06-30 17:00', '2026-07-31 16:00', 744)}


def pdftext(pfad, *args):
    return subprocess.run(['pdftotext', *args, pfad, '-'],
                          capture_output=True, text=True).stdout


def station(pfad):
    """-> (Name, Provinz, lat, lon) aus dem Tafelkopf."""
    t = pdftext(pfad)
    # Das Gradzeichen ist je nach Tafel ein thailaendisches Zeichen oder
    # fehlt ganz. Es darf keine Ziffern verschlucken -- mit \S{0,3} wurde
    # aus 13 Grad 27' 01" ein 13 Grad 7' 01" (Fehler von 37 km).
    lm = re.search(r'Lat\)\s*(\d+)\s*[^\d\s]{0,3}\s*(\d+)\'\s*(\d+)"', t)
    gm = re.search(r'Long\)\s*(\d+)\s*[^\d\s]{0,3}\s*(\d+)\'\s*(\d+)"', t)
    if not (lm and gm):
        return None
    # Der englische Name steht unmittelbar vor der Lat-Zeile.
    kopf = t[:lm.start()].rstrip().split('\n')
    name = prov = ''
    for zeile in reversed(kopf[-6:]):
        m = re.match(r"\s*([A-Z][A-Za-z'\-\. ]{2,40})\s*\(([A-Z][a-zA-Z ]{2,30})\)\s*$", zeile)
        if m:
            name, prov = m.group(1).strip(), m.group(2).strip()
            break
    lat = int(lm.group(1)) + int(lm.group(2)) / 60 + int(lm.group(3)) / 3600
    lon = int(gm.group(1)) + int(gm.group(2)) / 60 + int(gm.group(3)) / 3600
    return name, prov, lat, lon


def reihe(pfad, monat):
    """Stuendliche Hoehen des Monats aus der Tafel."""
    t = pdftext(pfad)
    teile = t.split('\f')
    for seite in teile:
        if monat not in seite:
            continue
        werte = []
        for zeile in seite.split('\n'):
            v = re.findall(r'-?\d+\.\d', zeile)
            if len(v) == 24:
                werte += [float(q) for q in v]
        if werte:
            return werte
    return []


def vorhersage(tcd, name, von, bis):
    env = dict(os.environ, HFILE_PATH=os.path.join(TCD, tcd))
    out = subprocess.run(['tide', '-l', name, '-b', von, '-e', bis, '-m', 'r',
                          '-s', '01:00', '-z', '-u', 'm', '-f', 'c'],
                         env=env, capture_output=True, text=True).stdout
    return [float(l.rsplit(',', 1)[1]) for l in out.split('\n')
            if re.search(r',\d{9,},-?\d', l)]


def guete(ref, y):
    n = min(len(ref), len(y))
    if n < 600:
        return None
    a, b = ref[:n], y[:n]
    off = statistics.mean(a) - statistics.mean(b)
    d = [a[i] - (b[i] + off) for i in range(n)]
    ma, mb = statistics.mean(a), statistics.mean(b)
    nen = math.sqrt(sum((q - ma) ** 2 for q in a) * sum((q - mb) ** 2 for q in b))
    r = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / nen if nen else 0.0
    return dict(n=n, off=off, rms=math.sqrt(sum(q * q for q in d) / n),
                max=max(abs(q) for q in d), r=r)


def main():
    monat = 'July 2026'
    if '--monat' in sys.argv:
        monat = sys.argv[sys.argv.index('--monat') + 1]
    umkreis = 5.0
    if '--km' in sys.argv:
        umkreis = float(sys.argv[sys.argv.index('--km') + 1])
    ausgabe = None
    if '--csv' in sys.argv:
        ausgabe = sys.argv[sys.argv.index('--csv') + 1]
    von, bis, _ = FENSTER[monat]
    zeilen_csv = []
    recs = [x for x in load_records()
            if x['lat'] is not None and x['lon'] is not None and not x['current']]
    print(f'Referenzmonat {monat}, Umkreis {umkreis:.0f} km\n')
    for fn in sorted(os.listdir(PDFS)):
        if not fn.endswith('.pdf'):
            continue
        p = os.path.join(PDFS, fn)
        st = station(p)
        if not st:
            print(f'{fn}: Kopf nicht lesbar')
            continue
        name, prov, lat, lon = st
        ref = reihe(p, monat)
        if not ref:
            print(f'{fn}: {name} -- Monatstafel {monat} nicht gefunden')
            continue
        ziel = {'lat': lat, 'lon': lon}
        nah = sorted(((km(ziel, x), x) for x in recs if km(ziel, x) <= umkreis),
                     key=lambda t: t[0])
        print(f'== {name} ({prov})  {lat:.5f}/{lon:.5f}  {len(ref)} Stundenwerte, '
              f'{len(nah)} Saetze im Umkreis')
        if not nah:
            print('     kein Satz im Bestand\n')
            continue
        zeilen = []
        for d, x in nah:
            tcd = os.path.basename(x['file'])[:-4] + '.tcd'
            g = guete(ref, vorhersage(tcd, x['name'], von, bis))
            zeilen.append((g['rms'] if g else 9.99, d, x, g))
        for rms, d, x, g in sorted(zeilen):
            if g:
                zeilen_csv.append(dict(
                    station=name, provinz=prov, lat=f'{lat:.5f}', lon=f'{lon:.5f}',
                    satz=x['name'], datei=os.path.basename(x['file']),
                    abstand_m=f'{d*1000:.0f}', rms_m=f'{g["rms"]:.4f}',
                    max_m=f'{g["max"]:.3f}', r=f'{g["r"]:.4f}'))
            if not g:
                print(f'     {x["name"][:40]:40} -- keine Vorhersage')
                continue
            print(f'     RMS {g["rms"]:.4f}  max {g["max"]:.3f}  r {g["r"]:.4f}  '
                  f'{d*1000:5.0f} m  {x["name"][:34]:34} {os.path.basename(x["file"])[:26]}')
        print()

    if ausgabe:
        with open(ausgabe, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(zeilen_csv[0]))
            w.writeheader()
            w.writerows(zeilen_csv)
        print(f'{len(zeilen_csv)} Messungen nach {ausgabe}')


if __name__ == '__main__':
    main()
