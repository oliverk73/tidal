#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wie gut ist FES2022 -- getrennt nach Kuestentyp? Eichung an echten Messungen.

Anlass 02.10.2026 (Oliver): Wenn FES an einfachen Kuesten gut ist, kann man sich dort
die Einzelpruefung sparen. Bisher war FES nur an zwei Kuesten geeicht (IH: Angola,
Nord-Mocambique) und lag anderswo schon falsch (San'in, Observatory Bay, Awatscha).

Vergleichsstationen: nur MESSUNGEN -- TICON-4 und harmonics_utide_observations mit
confidence >= 7, ohne JMA (Tafeln, nicht Messung) und ohne Rijkswaterstaat
"astronomical tide" (Vorhersage). Doppelte Orte (unter 2 km) zaehlen einmal.

Kuestentyp automatisch aus der Landmaske (global-land-mask, ~1 km):
  offen     Wasseranteil 10 km >= 40 %, 50 km >= 40 %, Kuestenlinie glatt
            (hoechstens 2 Land/Wasser-Wechsel auf dem 15-km-Kreis)
  insel     Inselwelt / Meerenge: >= 6 Wechsel auf dem 15- oder 40-km-Kreis
  binnen    Bucht, Muendung, Lagune: Wasseranteil 10 km < 25 %
  gemischt  der Rest
Dazu der Abstand zur naechsten ECHTEN FES-Wasserzelle (Maske 0; 1 = nur
hochgerechnet).

Fehlermass wie health_check.curve_diff: Effektivwert des Vektorfehlers ueber
M2 S2 K1 O1 N2, relativ zur Tidengroesse (Prozent). Dazu M2-Zeitversatz in Minuten.

Ergebnis: harmonics/help/fes_kuestentyp.csv und eine Tabelle auf stdout.

Aufruf: venv/bin/python py/fes_kuestentyp.py
"""
from __future__ import annotations

import cmath
import csv
import math
import os
import site
import statistics
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, curve_diff, km, MAIN, SPEED   # noqa: E402

# global-land-mask liegt nur in der User-Installation, nicht im venv
sys.path.append(site.getusersitepackages())
from global_land_mask import globe                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FES = os.path.join(ROOT, 'tide_models/fes2022b/ocean_tide_extrapolated')
OUT = os.path.join(ROOT, 'harmonics/help/fes_kuestentyp.csv')
QUELLEN = ('harmonics/ticon/harmonics_ticon4_worldwide.txt',
           'harmonics/utide/harmonics_utide_observations.txt')
NICHT = ('JMA hourly', 'Rijkswaterstaat astronomical')


def kopf(texte, r):
    """Kommentarzeilen des Satzes."""
    L = texte[r['file']]
    i = r['line'] - 1
    b = max(k for k in range(max(0, i - 80), i) if L[k].startswith('# BEGIN HOT'))
    return L[b:i]


def auswahl():
    recs = [r for r in load_records() if r['file'] in QUELLEN and r['lat'] is not None
            and not r['current'] and r['amp'].get('M2')]
    texte = {f: open(os.path.join(ROOT, f), encoding='iso-8859-1').read().split('\n') for f in QUELLEN}
    gut = []
    for r in recs:
        k = kopf(texte, r)
        quelle = next((x[10:].strip() for x in k if x.startswith('# source:')), '')
        conf = next((int(x.split(':')[1]) for x in k if x.startswith('# confidence:')), 0)
        if conf < 7 or any(n in quelle for n in NICHT):
            continue
        r['quelle'], r['conf'] = quelle, conf
        r['land'] = next((x.split(':', 1)[1].strip() for x in k if x.startswith('# country:')), '')
        gut.append(r)
    # Dubletten unter 2 km: die mit der hoeheren confidence bleibt
    gut.sort(key=lambda r: -r['conf'])
    behalten = []
    for r in gut:
        if all(abs(r['lat'] - b['lat']) > 0.03 or km(r, b) > 2 for b in behalten):
            behalten.append(r)
    return behalten


def fes_dazu(recs):
    """FES-Konstanten der naechsten Zelle (extrapoliertes Gitter) und Abstand zu echtem Wasser."""
    d = nc.Dataset(os.path.join(FES, 'mask_fes2022B.nc'))
    lats, lons = np.asarray(d['lat'][:]), np.asarray(d['lon'][:])
    maske = np.asarray(d['mask'][:])
    dla, dlo = lats[1] - lats[0], lons[1] - lons[0]
    for r in recs:
        i = int(round((r['lat'] - lats[0]) / dla))
        j = int(round(((r['lon'] % 360) - lons[0]) / dlo)) % len(lons)
        r['ij'] = (i, j)
        r['fes_maske'] = int(maske[i, j])
        best = None
        for rad in range(0, 31):
            fen = maske[max(0, i - rad):i + rad + 1, :]
            jj = [(j + x) % len(lons) for x in range(-rad, rad + 1)]
            fen = fen[:, jj]
            ii, kk = np.nonzero(fen == 0)
            if len(ii):
                for a, b in zip(ii, kk):
                    p = dict(lat=float(lats[max(0, i - rad) + a]), lon=float(lons[jj[b]]))
                    dist = km(r, p)
                    best = dist if best is None else min(best, dist)
                break
        r['fes_wasser_km'] = best if best is not None else 999.0
    # Das extrapolierte Gitter reicht nur ein Stueck ins Land; weiter drinnen
    # (Fluesse, Lagunen) ist es leer. Dann gilt die naechste belegte Zelle.
    d = nc.Dataset(os.path.join(FES, 'm2_fes2022.nc'))
    leer = np.ma.getmaskarray(d['amplitude'][:]) | ~np.isfinite(np.ma.filled(d['amplitude'][:], np.nan))
    d.close()
    for r in recs:
        i, j = r['ij']
        r['fes_ersatz_km'] = 0.0
        if not leer[i, j]:
            continue
        for rad in range(1, 61):
            jj = [(j + x) % len(lons) for x in range(-rad, rad + 1)]
            fen = leer[max(0, i - rad):i + rad + 1, :][:, jj]
            ii, kk = np.nonzero(~fen)
            if len(ii):
                kand = [(km(r, dict(lat=float(lats[max(0, i - rad) + a]), lon=float(lons[jj[b]]))),
                         max(0, i - rad) + a, jj[b]) for a, b in zip(ii, kk)]
                dist, ni, nj = min(kand)
                r['ij'], r['fes_ersatz_km'] = (ni, nj), dist
                break
    for c in MAIN:
        d = nc.Dataset(os.path.join(FES, f'{c.lower()}_fes2022.nc'))
        am, ph = d['amplitude'], d['phase']
        for r in recs:
            i, j = r['ij']
            a, g = float(am[i, j]) / 100.0, float(ph[i, j])
            r.setdefault('fes', {})[c] = (a, g)
        d.close()
    for r in recs:
        z = {c: cmath.rect(r['fes'][c][0], -math.radians(r['fes'][c][1] % 360)) for c in MAIN}
        r['fes_rec'] = dict(z=z, tot=sum(abs(z[c]) for c in MAIN))


def kreis(lat, lon, rad_km, n):
    out = []
    for k in range(n):
        w = 2 * math.pi * k / n
        la = lat + rad_km / 111.2 * math.cos(w)
        lo = lon + rad_km / (111.2 * max(0.05, math.cos(math.radians(lat)))) * math.sin(w)
        out.append(bool(globe.is_land(max(-89.9, min(89.9, la)), ((lo + 180) % 360) - 180)))
    return out


def wasseranteil(lat, lon, rad_km):
    pts = []
    for rr in np.linspace(rad_km / 5, rad_km, 5):
        pts += kreis(lat, lon, rr, 36)
    return 1 - sum(pts) / len(pts)


def wechsel(lat, lon, rad_km):
    k = kreis(lat, lon, rad_km, 90)
    return sum(1 for a, b in zip(k, k[1:] + k[:1]) if a != b)


def typ(r):
    w10, w50 = wasseranteil(r['lat'], r['lon'], 10), wasseranteil(r['lat'], r['lon'], 50)
    t15, t40 = wechsel(r['lat'], r['lon'], 15), wechsel(r['lat'], r['lon'], 40)
    r.update(w10=w10, w50=w50, t15=t15, t40=t40)
    if w10 < 0.25:
        return 'binnen'
    if t15 >= 6 or t40 >= 6:
        return 'insel'
    if w10 >= 0.40 and w50 >= 0.40 and t15 <= 2:
        return 'offen'
    return 'gemischt'


def m2_min(r):
    a, g = r['amp']['M2']
    a *= r['scale']
    fa, fg = r['fes']['M2']
    if a < 0.05 or fa < 0.05:
        return None
    gs = (-math.degrees(cmath.phase(r['z']['M2']))) % 360
    return ((gs - fg + 180) % 360 - 180) / SPEED['M2'] * 60


def zusammenfassung(rows, schluessel, titel):
    print(f'\n{titel}')
    print(f'{"":22} {"n":>5} {"Median":>7} {"P75":>6} {"P90":>6} {"<=10%":>6} {"<=20%":>6}'
          f' {"|dM2| Med":>9} {"<=10min":>7} {"Fehler cm":>9}')
    gruppen = {}
    for r in rows:
        gruppen.setdefault(schluessel(r), []).append(r)
    for g in sorted(gruppen, key=lambda g: (-len(gruppen[g]), g)):
        rs = gruppen[g]
        rel = sorted(r['rel'] for r in rs)
        q = lambda p: rel[min(len(rel) - 1, int(p * len(rel)))]
        dm = [abs(r['dm2']) for r in rs if r['dm2'] is not None]
        print(f'{g[:22]:22} {len(rs):5} {statistics.median(rel):6.1f}% {q(.75):5.1f}% {q(.9):5.1f}%'
              f' {100 * sum(x <= 10 for x in rel) / len(rel):5.0f}% {100 * sum(x <= 20 for x in rel) / len(rel):5.0f}%'
              f' {statistics.median(dm) if dm else float("nan"):8.1f}m'
              f' {100 * sum(x <= 10 for x in dm) / max(1, len(dm)):6.0f}%'
              f' {100 * statistics.median(r["abs"] for r in rs):8.1f}')


def main():
    recs = auswahl()
    print(f'{len(recs)} Messorte (nach Dubletten unter 2 km)', file=sys.stderr)
    fes_dazu(recs)
    for r in recs:
        r['typ'] = typ(r)
        d, rel = curve_diff(r, r['fes_rec'])
        r['abs'], r['rel'], r['dm2'] = d, 100 * rel, m2_min(r)
    rows = sorted(recs, key=lambda r: r['rel'])
    with open(OUT, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['datei', 'name', 'land', 'lat', 'lon', 'typ', 'w10', 'w50', 't15', 't40',
                    'fes_maske', 'fes_wasser_km', 'fes_ersatz_km', 'fehler_cm', 'fehler_prozent', 'm2_min', 'quelle'])
        for r in rows:
            w.writerow([r['file'], r['name'], r['land'], r['lat'], r['lon'], r['typ'],
                        f'{r["w10"]:.2f}', f'{r["w50"]:.2f}', r['t15'], r['t40'], r['fes_maske'],
                        f'{r["fes_wasser_km"]:.1f}', f'{r["fes_ersatz_km"]:.1f}', f'{100 * r["abs"]:.1f}', f'{r["rel"]:.1f}',
                        '' if r['dm2'] is None else f'{r["dm2"]:.0f}', r['quelle'][:60]])
    zusammenfassung(rows, lambda r: r['typ'], 'Nach Kuestentyp (Fehler relativ zur Tidengroesse)')
    zusammenfassung(rows, lambda r: 'FES-Zelle echt' if r['fes_maske'] == 0 else
                    ('hochgerechnet <5 km' if r['fes_wasser_km'] < 5 else 'hochgerechnet >=5 km'),
                    'Nach FES-Zelle am Ort')
    zusammenfassung([r for r in rows if r['typ'] == 'offen'], lambda r: r['land'] or '?',
                    'Offene Kuesten nach Land')
    print(f'\n-> {OUT}')


if __name__ == '__main__':
    main()
