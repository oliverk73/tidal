#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zeitpruefung: Uebertragungssaetze (NOAA, ATT, alte Buchsaetze) gegen Pegel der Landesquelle.

Fuer jeden Satz, der nicht aus der Landesquelle stammt (Suedkorea: KHOA), werden die Hoch- und
Niedrigwasserzeiten eines Monats gegen die Landesquellen-Saetze bis 15 km verglichen.
Natuerliches Gefaelle der Gezeitenwelle zieht FES2022 ab (M2-Phasendifferenz zwischen beiden
Positionen). Gemeldet wird nur, wenn der Zeitversatz gegen ALLE Nachbarn >= 20 min ist und FES ihn
nicht erklaert (FES sagt die andere Richtung oder mindestens 20 min weniger). In Buchten liegt FES
oft zu weit daneben; dort meldet die Regel nur, wenn FES nicht einmal die Richtung trifft.

Geeicht 14.10.2026 an Suedkorea: alle 41 Uebertragungssaetze im Bestand erklaert (Baengnyeongdo
+20 = FES +20, Hajodo -26 / FES -23, Chojeon-ri +32 / FES +74 Bucht); archiviert Seogwipo (1997)
+61 min am selben Ort gemeldet.

Usage: venv/bin/python py/zeit_pruefung.py "South Korea"   (Liste auf stdout)
"""
import cmath
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dubletten_kurven as D                                       # noqa: E402

RADIUS_KM = 15
SCHWELLE_MIN = 20
LANDESQUELLE = {'South Korea': ('khoa',), 'Philippines': ('namria',),
                'Indonesia': ('big (badan', 'pushidrosal', 'bmkg', 'uhslc'),
                'Japan': ('uhslc',), 'Vietnam': ('vho navy', 'icoe', 'nchmf', 'uhslc'),
                'Thailand': ('royal thai navy', 'uhslc'), 'Malaysia': ('nmdis', 'uhslc'), 'Singapore': ('nmdis', 'uhslc'),
                'Myanmar': ('survey of india', 'nmdis', 'uhslc'), 'Cambodia': ('vho navy',),
                'China': ('nmdis', 'hko tide', 'cwa tide', 'ioc sea level', 'uhslc')}   # amtliche Pegel/Tafeln und Messreihen
_T = np.arange(0, 30 * 24, 1 / 60)          # 30 Tage, Minutentakt (Stunden)


def _kurve(s):
    y = np.zeros_like(_T)
    for c, z in D.vek(s).items():
        y += abs(z) * np.cos(np.radians(D.SP[c] * _T) - cmath.phase(z))
    return y


def _scheitel(y):
    hw = np.where((y[1:-1] > y[:-2]) & (y[1:-1] >= y[2:]))[0] + 1
    nw = np.where((y[1:-1] < y[:-2]) & (y[1:-1] <= y[2:]))[0] + 1
    return hw, nw


def versatz(a, b):
    """-> (Median HW-Versatz a-b in min, Median NW-Versatz, Hubverhaeltnis a/b - 1)."""
    ya, yb = _kurve(a), _kurve(b)
    ha, na = _scheitel(ya)
    hb, nb = _scheitel(yb)

    def med(xa, xb):
        d = [x - xb[np.argmin(abs(xb - x))] for x in xa]
        d = [v for v in d if abs(v) < 180]
        return float(np.median(d)) if d else float('nan')
    hub = lambda y, h, n: np.mean(y[h[:len(n)]]) - np.mean(y[n[:len(h)]])
    return med(ha, hb), med(na, nb), hub(ya, ha, na) / hub(yb, hb, nb) - 1


_FES = {}


def fes_m2(lat, lon):
    """M2-Phase (Grad, Greenwich) aus FES2022 an der Position, None ohne Modell."""
    try:
        import netCDF4 as nc
        from fes_ersatz_inseln import sample, FES_DIR
    except Exception:
        return None
    if 'ds' not in _FES:
        p = os.path.join(FES_DIR, 'm2_fes2022.nc')
        _FES['ds'] = nc.Dataset(p) if os.path.exists(p) else None
    if _FES['ds'] is None:
        return None
    return sample(_FES['ds'], lat, lon)[1]


def pruefe(land, dateien):
    """-> {(satzname, datei): befundtext} fuer Saetze mit unerklaertem Zeitversatz."""
    kenn = LANDESQUELLE.get(land)
    if not kenn:
        return {}
    S = D.saetze(land, dateien)
    amtlich = lambda s: any(k in s['kopf'].lower() for k in kenn)
    ref = [s for s in S if amtlich(s)]
    out = {}
    for s in S:
        if amtlich(s):
            continue
        nb = [r for r in sorted(ref, key=lambda r: D.km(s, r)) if D.km(s, r) <= RADIUS_KM][:3]
        if not nb:
            continue
        g_s = fes_m2(s['lat'], s['lon'])
        zeilen, unerklaert = [], []
        for r in nb:
            hw, nw, hub = versatz(s, r)
            g_r = fes_m2(r['lat'], r['lon'])
            fes = ((g_s - g_r + 180) % 360 - 180) / D.SP['M2'] * 60 if g_s is not None and g_r is not None else 0.0
            dt = (hw + nw) / 2
            # Ueberschuss, den FES nicht erklaert (gleiche Richtung wird bis zu ihrem Betrag abgezogen)
            rest = abs(dt) - (abs(fes) if fes * dt > 0 else 0.0)
            unerklaert.append(abs(dt) >= SCHWELLE_MIN and rest >= SCHWELLE_MIN)
            zeilen.append('%s %.0f km: HW %+.0f / NW %+.0f min, Hub %+.0f %%, FES %+.0f min' % (
                r['name'].rsplit(',', 1)[0], D.km(s, r), hw, nw, 100 * hub, fes))
        if all(unerklaert):
            out[(s['name'], s['file'])] = 'ZEIT gegen die Landesquelle verschoben: ' + '; '.join(zeilen)
    return out


if __name__ == '__main__':
    import json
    land = sys.argv[1] if len(sys.argv) > 1 else 'South Korea'
    stem = 'harmonics/help/pruefliste_%s_' % land.lower().replace(' ', '_')
    dateien = sys.argv[2:]
    if not dateien:
        import glob
        j = sorted(glob.glob(os.path.join(D.ROOT, stem + '*.json')))[-1]
        dateien = sorted({z['datei'] for z in json.load(open(j))})
    for n, t in pruefe(land, dateien).items():
        print(n[0], '|', t)
