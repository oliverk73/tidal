#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sucht TICON-Saetze mit Zeitfehler -- ueber drei unabhaengige Wege.

Anlass: zweimal lag TICON als Ganzes zeitlich daneben -- die deutschen
Saetze um +40 min (ungeklaert), Hong Kong um -63 min (geerbt aus der
zeitfalschen UHSLC-Reihe 329, siehe noaa-bezugsort-verwechslung).
TICON-4 ist eine Analyse der GESLA-Reihen; hat eine Reihe falsche
Zeitstempel, stehen alle Phasen um dieselbe ZEIT verschoben.

Genau das ist die Signatur, auf die hier geprueft wird: ein Zeitfehler
verschiebt M2, S2, K1 und O1 um dieselbe Anzahl Minuten (also um
verschiedene Winkel). Ein Modell- oder Analysefehler trifft die
Partialtiden verschieden.

Geprueft wird am Zwilling (naechster unabhaengiger Satz bis 2 km, keine
Uebertragung, kein TICON), und FES2022 (Altimetrie) entscheidet, WER von
beiden falsch liegt: ist der Zwilling gegen FES puenktlich und der Versatz
bei allen Partialtiden gleich, sitzt der Zeitfehler im TICON-Satz (Klasse A).
FES allein taugt nicht -- es driftet an manchen Kuesten selbst (San'in bis
+60 min bei K1/O1) und versagt in Fluessen; ohne Zwilling wird nicht geurteilt.

Der Zwilling ist oft aus genau der Tafel gefittet, gegen die gemessen wird,
und gilt dort als blind -- deshalb hat die Zeitregel in
dubletten_aufraeumen.py diese TICON-Saetze nie erwischt.

Geloescht wird hier nichts.

Aufruf: venv/bin/python3 py/ticon_zeitpruefung.py   (braucht netCDF4)
"""
from __future__ import annotations

import cmath
import collections
import csv
import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, SPEED            # noqa: E402
from transfer_zonen import zeitversatz                      # noqa: E402
from pegel_dubletten import vermerke, ABGELEITET            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP = os.path.join(ROOT, 'harmonics/help')
FES = os.path.join(ROOT, 'tide_models/fes2022b/ocean_tide_extrapolated')
TEILE = ('M2', 'S2', 'K1', 'O1')
MIND_AMP = 0.03       # m -- darunter ist die Phase zu unsicher
REGION_KM = 150.0
MIND_NACHBARN = 3
MIND_MIN = 20         # ab hier heisst es Zeitfehler
EINIG_MIN = 15        # so eng muessen die Partialtiden beieinander liegen
ZWILLING_KM = 2.0
MIND_ZW = 25          # Minuten Versatz gegen den Zwilling


def phase(r, c):
    z = r['z'][c]
    return (-math.degrees(cmath.phase(z))) % 360, abs(z)


def fes_werte(recs):
    import netCDF4
    import numpy as np
    out = {id(r): {} for r in recs}
    for c in TEILE:
        ds = netCDF4.Dataset(os.path.join(FES, f'{c.lower()}_fes2022.nc'))
        lats, lons = ds['lat'][:], ds['lon'][:]
        ph = ds['phase'][:].filled(np.nan) if hasattr(ds['phase'][:], 'filled') else ds['phase'][:]
        am = ds['amplitude'][:].filled(np.nan) if hasattr(ds['amplitude'][:], 'filled') else ds['amplitude'][:]
        dla, dlo = lats[1] - lats[0], lons[1] - lons[0]
        for r in recs:
            i = int(round((r['lat'] - lats[0]) / dla))
            j = int(round(((r['lon'] % 360) - lons[0]) / dlo)) % len(lons)
            out[id(r)][c] = (float(ph[i, j]), float(am[i, j]) / 100.0)
        del ph, am
        ds.close()
    return out


def versatz_min(g_satz, g_fes, c):
    return ((g_satz - g_fes + 180) % 360 - 180) / SPEED[c] * 60


def messungen():
    """{(datei, name): [zeit_min, ...]} aus allen Qualitaetstabellen, ohne eigene Reihe."""
    out = collections.defaultdict(list)
    for p in glob.glob(os.path.join(HELP, '*qualitaet*.csv')):
        for r in csv.DictReader(open(p, encoding='utf-8')):
            if 'ticon' not in r.get('datei', '') or r.get('eigen') == '1':
                continue
            try:
                out[(r['datei'], r['satz'])].append(float(r['zeit_min']))
            except (ValueError, KeyError):
                pass
    return out


def main():
    """Zwillingsprobe mit FES-Gegenprobe (Stand 10.09.2026).

    Klasse A -- belegt: Zwilling bis 2 km, Versatz ab MIND_ZW Minuten, der
      Zwilling selbst ist gegen FES puenktlich (Median bis 20 min), und der
      Versatz TICON gegen Zwilling ist bei allen Partialtiden gleich (Streuung
      bis 20 min) -- die Signatur eines Zeitfehlers im TICON-Satz.
    Klasse B -- offen: Versatz ab MIND_ZW, aber FES kann nicht entscheiden
      (Fluss, Lagune, Amphidromie) oder der Zwilling ist selbst nicht
      puenktlich -- dann liegt der Fehler oft beim Zwilling (Mawson, Lagos Bar,
      San Sebastian de La Gomera: TICON sitzt auf FES, der ATT-Satz nicht).
    """
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    komm = vermerke()
    for r in recs:
        r['abgeleitet'] = bool(ABGELEITET.search(komm.get((r['file'], r['line']), '')))
        r['ticon'] = 'ticon' in r['file']
    ticon = [r for r in recs if r['ticon']]
    basis = [r for r in recs if not r['ticon'] and not r['abgeleitet']]
    fes = fes_werte(ticon + basis)

    def roh(r):
        d = {}
        for c in TEILE:
            g, a = phase(r, c)
            gf, af = fes[id(r)][c]
            if a >= MIND_AMP and af >= MIND_AMP and not math.isnan(gf):
                d[c] = versatz_min(g, gf, c)
        return d
    gitter = collections.defaultdict(list)
    for b in basis:
        gitter[(int(b['lat'] // 1), int(b['lon'] // 1))].append(b)
    mess = messungen()
    zeilen = []
    for t in ticon:
        nah = sorted((b for dz in (-1, 0, 1) for dm in (-1, 0, 1)
                      for b in gitter.get((int(t['lat'] // 1) + dz, int(t['lon'] // 1) + dm), ())
                      if km(t, b) <= ZWILLING_KM), key=lambda b: km(t, b))
        if not nah:
            continue
        b = nah[0]
        v, g = zeitversatz(t, b)
        if g < 0.9:
            continue
        v *= 60
        rt, rb = roh(t), roh(b)
        dif = {c: rt[c] - rb[c] for c in rt if c in rb}
        streu = (max(dif.values()) - min(dif.values())) if len(dif) >= 3 else None
        zw_fes = statistics.median(rb.values()) if len(rb) >= 3 else None
        m = mess.get((os.path.basename(t['file']), t['name']))
        klasse = ''
        if abs(v) >= MIND_ZW:
            klasse = 'A' if (streu is not None and streu <= 20 and zw_fes is not None
                             and abs(zw_fes) <= 20
                             and abs(statistics.mean(dif.values()) - v) <= 15) else 'B'
        zeilen.append(dict(
            klasse=klasse, name=t['name'], datei=os.path.basename(t['file']),
            versatz_min=round(v), zwilling=b['name'], zwilling_datei=os.path.basename(b['file']),
            zwilling_km=round(km(t, b), 2), zwilling_gegen_fes_min=None if zw_fes is None else round(zw_fes),
            ticon_gegen_fes=' '.join(f'{c}{x:+.0f}' for c, x in rt.items()),
            je_tide=' '.join(f'{c}{x:+.0f}' for c, x in dif.items()),
            messung_min=None if not m else statistics.median(m)))
    aus = os.path.join(HELP, 'ticon_zeitpruefung.csv')
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(sorted(zeilen, key=lambda z: (z['klasse'] or 'Z', z['versatz_min'])))
    c = collections.Counter(z['klasse'] or '-' for z in zeilen)
    print(f"{len(zeilen)} TICON-Saetze mit Zwilling bis {ZWILLING_KM} km: "
          f"A {c['A']}, B {c['B']}, unauffaellig {c['-']}")
    print(f'-> {aus}')


if __name__ == '__main__':
    main()
