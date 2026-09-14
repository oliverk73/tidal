#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orientierung fuer die NOAA-Saetze ohne Beleg (py/noaa_neu_uebertragen.py: 'offen').

Diese 751 Saetze haben keine Wahrheit unter 3 km, keinen Pegel und keinen
unabhaengigen Nachbarn unter 5 km. Verglichen wird deshalb weiter weg --
mit einem Massstab dafuer, wie stark zwei gute Saetze in diesem Abstand
ohnehin auseinanderliegen (grundrauschen()).

  Nachbarn bis 25 km: alter und neuer Satz gegen jeden der naechsten 6
      unabhaengigen Saetze (Kurvenabstand in % des Hubs). Der neue Satz
      wird genommen, wenn er im Median um mindestens MIND_PUNKTE naeher liegt
      UND bei mindestens 2/3 der Nachbarn naeher ist (bei nur einem Nachbarn:
      unter 10 km und doppelter Abstand).
  Weiter weg (25-100 km): dieselbe Probe gegen die Nachbarn, zusaetzlich
      gegen FES2022 am Ort. Genommen wird nur, wenn beide fuer den neuen
      Satz sprechen. Ohne Nachbarn unter 100 km bleibt der Satz.

Schreibt harmonics/help/noaa_offen_nachbarn.csv; mit --schreiben werden die
Zeilen 'schreiben' ueber py/noaa_neu_uebertragen.anwenden() eingetragen.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import random
import statistics
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noaa_pruefstand as P                                        # noqa: E402
import noaa_neu_uebertragen as NU                                  # noqa: E402
from health_check import load_records                              # noqa: E402

ROOT = P.ROOT
AUS = os.path.join(P.HELP, 'noaa_offen_nachbarn.csv')
FES = os.path.join(ROOT, 'tide_models/fes2022b/ocean_tide_extrapolated')
FES_TEILE = ('M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1', 'M4', 'MS4', 'MN4')
STUFEN = (5, 10, 25, 50, 100)
MIND_PUNKTE = 1.0


def entfernungen(r, la, lo):
    a, b = math.radians(r['lat']), math.radians(r['lon'])
    x = np.sin((la - a) / 2) ** 2 + np.cos(a) * np.cos(la) * np.sin((lo - b) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(np.minimum(x, 1)))


def stufe(d):
    for s in STUFEN:
        if d <= s:
            return s
    return 999


def grundrauschen(unabh, la, lo, n_je=600):
    """Median-Kurvenabstand zweier Klasse-A-Saetze je Abstandsstufe."""
    random.seed(7)
    a_ix = [i for i, r in enumerate(unabh) if P.klasse(r) == 'A']
    werte = collections.defaultdict(list)
    for i in random.sample(a_ix, min(len(a_ix), 4000)):
        d = entfernungen(unabh[i], la, lo)
        for j in np.where((d > 0.5) & (d <= 100))[0][:12]:
            if P.klasse(unabh[j]) != 'A':
                continue
            s = stufe(d[j])
            if len(werte[s]) >= n_je:
                continue
            try:
                werte[s].append(P.messen(P.satz(unabh[i])[1], P.satz(unabh[j])[1])['kurve_pct'])
            except (KeyError, ValueError, IndexError):
                pass
    return {s: (statistics.median(v), np.percentile(v, 75)) for s, v in werte.items() if len(v) >= 30}


def fes_konstanten(punkte):
    """{id: {c: (amp m, G)}} am naechsten gueltigen FES-Gitterpunkt (Umkreis 3 Zellen)."""
    import netCDF4
    out = {id(r): {} for r in punkte}
    for c in FES_TEILE:
        ds = netCDF4.Dataset(os.path.join(FES, f'{c.lower()}_fes2022.nc'))
        lats, lons = ds['lat'][:], ds['lon'][:]
        am = ds['amplitude'][:]; ph = ds['phase'][:]
        am = am.filled(np.nan) if hasattr(am, 'filled') else am
        ph = ph.filled(np.nan) if hasattr(ph, 'filled') else ph
        dla, dlo = lats[1] - lats[0], lons[1] - lons[0]
        for r in punkte:
            i0 = int(round((r['lat'] - lats[0]) / dla)); j0 = int(round(((r['lon'] % 360) - lons[0]) / dlo))
            best = None
            for di in range(-3, 4):
                for dj in range(-3, 4):
                    i, j = i0 + di, (j0 + dj) % len(lons)
                    if 0 <= i < len(lats) and not np.isnan(am[i, j]):
                        if best is None or di * di + dj * dj < best[0]:
                            best = (di * di + dj * dj, float(am[i, j]) / 100.0, float(ph[i, j]))
            if best:
                out[id(r)][c] = (best[1], best[2] % 360.0)
        del am, ph
        ds.close()
    return out


def probe(alt, neu, nachbarn):
    aa, bb = [], []
    for q in nachbarn:
        w = P.satz(q)[1]
        aa.append(P.messen(alt, w)['kurve_pct']); bb.append(P.messen(neu, w)['kurve_pct'])
    anteil = sum(1 for a, b in zip(aa, bb) if b < a) / len(aa)
    return statistics.median(aa), statistics.median(bb), anteil


def pruefen():
    recs = [r for r in load_records() if r['lat'] is not None]
    unabh = [r for r in recs if '/noaa/' not in r['file'] and 'current' not in r['file'].lower()
             and P.klasse(r) is not None]
    la = np.radians([r['lat'] for r in unabh]); lo = np.radians([r['lon'] for r in unabh])
    rauschen = grundrauschen(unabh, la, lo)
    print('Grundrauschen zweier guter Saetze (Median / P75 Kurve %):',
          {s: (round(m, 1), round(p, 1)) for s, (m, p) in sorted(rauschen.items())}, flush=True)
    konst = json.load(open(NU.KONST, encoding='utf-8'))
    liste = [z for z in csv.DictReader(open(NU.AUS, encoding='utf-8')) if z['entscheidung'].startswith('offen')]
    nach_name = {(os.path.basename(r['file']), r['name']): r for r in recs if '/noaa/' in r['file']}
    faelle = []
    for z in liste:
        r = nach_name.get((z['datei'], z['name']))
        c = konst.get(f"{z['datei']}|{z['name']}")
        if r is None or c is None:
            continue
        faelle.append((z, r, {k: tuple(v) for k, v in c.items()}))
    weit = [r for z, r, c in faelle]
    fes = fes_konstanten(weit)
    zeilen = []
    for z, r, neu in faelle:
        alt = P.satz(r)[1]
        d = entfernungen(r, la, lo)
        order = np.argsort(d)
        nah = [unabh[i] for i in order[:6] if d[i] <= 25.0]
        mittel = [unabh[i] for i in order[:6] if 25.0 < d[i] <= 100.0]
        d0 = float(d[order[0]])
        e = dict(datei=z['datei'], name=r['name'], no=z['no'], naechster_km=round(d0, 1),
                 rauschen_pct=round(rauschen.get(stufe(d0), (float('nan'),))[0], 1),
                 nachbarn=0, nachbar_alt_pct='', nachbar_neu_pct='', anteil_neu_besser='',
                 fes_alt_pct='', fes_neu_pct='', bezug=z['bezug'], einstellung=z['einstellung'],
                 beleg='', entscheidung='behalten')
        if nah:
            a, b, ant = probe(alt, neu, nah)
            e.update(nachbarn=len(nah), nachbar_alt_pct=round(a, 2), nachbar_neu_pct=round(b, 2),
                     anteil_neu_besser=round(ant, 2))
            if len(nah) >= 2 and a - b >= MIND_PUNKTE and ant >= 2 / 3:
                e['entscheidung'], e['beleg'] = 'schreiben', f'Nachbarn bis 25 km ({len(nah)})'
            elif len(nah) == 1 and d0 <= 10.0 and a - b >= 2 * MIND_PUNKTE:
                e['entscheidung'], e['beleg'] = 'schreiben', 'ein Nachbar unter 10 km'
            else:
                e['beleg'] = 'Nachbarn sprechen nicht klar fuer neu'
        elif mittel:
            a, b, ant = probe(alt, neu, mittel)
            e.update(nachbarn=len(mittel), nachbar_alt_pct=round(a, 2), nachbar_neu_pct=round(b, 2),
                     anteil_neu_besser=round(ant, 2))
            f = fes.get(id(r), {})
            if 'M2' in f and f['M2'][0] > 0.02:
                fa, fb = P.messen(alt, f)['kurve_pct'], P.messen(neu, f)['kurve_pct']
                e.update(fes_alt_pct=round(fa, 2), fes_neu_pct=round(fb, 2))
                if a - b >= MIND_PUNKTE and ant >= 2 / 3 and fa - fb >= MIND_PUNKTE:
                    e['entscheidung'], e['beleg'] = 'schreiben', f'Nachbarn 25-100 km ({len(mittel)}) und FES'
                else:
                    e['beleg'] = 'Nachbarn und FES nicht beide fuer neu'
            else:
                e['beleg'] = 'FES ohne Wert (Land/Fjord)'
        else:
            e['beleg'] = 'kein Nachbar unter 100 km'
        zeilen.append(e)
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader(); w.writerows(zeilen)
    print('->', os.path.relpath(AUS, ROOT), len(zeilen))
    for k, n in collections.Counter((z['entscheidung'], z['beleg']) for z in zeilen).most_common():
        print(f'   {k[0]:10} {k[1]:45} {n:5d}')
    ok = [z for z in zeilen if z['entscheidung'] == 'schreiben']
    if ok:
        print('   geschrieben wuerden: Nachbarn Median %.2f -> %.2f %%' % (
            statistics.median(z['nachbar_alt_pct'] for z in ok), statistics.median(z['nachbar_neu_pct'] for z in ok)))


def anwenden():
    """Traegt die Zeilen 'schreiben' in die NOAA-Dateien ein (ueber noaa_neu_uebertragen.anwenden)."""
    import shutil
    wahl = {(z['datei'], z['name']): z for z in csv.DictReader(open(AUS, encoding='utf-8'))
            if z['entscheidung'] == 'schreiben'}
    alt_aus = NU.AUS
    tmp = os.path.join(P.HELP, 'noaa_offen_schreiben.csv')
    zeilen = []
    for z in csv.DictReader(open(alt_aus, encoding='utf-8')):
        k = (z['datei'], z['name'])
        if k in wahl:
            z['entscheidung'] = 'schreiben'
            z['beleg'] = wahl[k]['beleg']
            zeilen.append(z)
    with open(tmp, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader(); w.writerows(zeilen)
    NU.AUS = tmp
    try:
        NU.anwenden()
    finally:
        NU.AUS = alt_aus
    os.remove(tmp)


if __name__ == '__main__':
    if '--schreiben' in sys.argv:
        anwenden()
    else:
        pruefen()
