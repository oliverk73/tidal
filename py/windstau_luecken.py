#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kuestenorte ohne Satz in Meeren, in denen das Wetter den Wasserstand bestimmt (Oliver 8.11.2026).

Bisher fielen solche Orte aus der Lueckensuche (py/luecken_fes_welt.py: Springhub >= 1 m). Mit der
Wetterkurve (py/windstau_cmems.py) werden sie relevant: der Wasserstand schwankt dort um Dezimeter.

Massstab: Copernicus-Tagesmittel des Wasserstands ueber ein Jahr (11/2025-10/2026, ohne Gezeit):
  Ostsee         cmems_mod_bal_phy-ssh_anfc_detided_P1D-m, zos_detided
  Schwarzes Meer cmems_mod_blk_phy-ssh_anfc_2.5km_P1D-m, zos
liegen unter water_levels/cmems_ssh/jahr/. Je Modellzelle: Standardabweichung und 99-%-Quantil des Betrags
der Abweichung vom Jahresmittel. Tagesmittel unterschaetzen kurze Sturmflutspitzen; als Rangfolge taugen sie.

Orte: GeoNames cities5000 (ab 5000 Einwohnern), naechste Modell-Meerzelle <= KUESTE_KM, kein
Gezeitensatz (ohne Stroeme) <= LUECKE_KM.
Ergebnis: harmonics/help/windstau_luecken_<meer>.csv (sortiert nach Schwankung). Schreibt keine Saetze.

Usage: venv/bin/python py/windstau_luecken.py <geonames-ordner>   (cities5000.txt, admin1CodesASCII.txt, countryInfo.txt)
"""
import csv
import math
import os
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402

ROOT = H.ROOT
JAHR = os.path.join(ROOT, 'water_levels/cmems_ssh/jahr')
MEERE = {
    'ostsee': ('zos_bal_P1D_2025-2026.nc', 'zos_detided'),
    'schwarz': ('zos_blk_P1D_2025-2026.nc', 'zos'),
}
KUESTE_KM, LUECKE_KM = 5.0, 20.0


def kennzahlen(datei, var):
    d = nc.Dataset(os.path.join(JAHR, datei))
    la, lo = d['latitude'][:].astype(float), d['longitude'][:].astype(float)
    z = d[var][:]                                                   # (t, [depth,] lat, lon), maskiert an Land
    if z.ndim == 4:
        z = z[:, 0]
    z = np.ma.filled(z.astype(float), np.nan)
    an = z - np.nanmean(z, axis=0)
    std = np.nanstd(an, axis=0)
    p99 = np.nanpercentile(np.abs(an), 99, axis=0)
    gut = np.isfinite(std) & (np.sum(np.isfinite(z), axis=0) > 300)
    return la, lo, std, p99, gut


def main(argv):
    gn = argv[0]
    adm = {}
    for l in open(os.path.join(gn, 'admin1CodesASCII.txt'), encoding='utf-8'):
        p = l.rstrip('\n').split('\t')
        adm[p[0]] = p[1]
    land = {}
    for l in open(os.path.join(gn, 'countryInfo.txt'), encoding='utf-8'):
        if not l.startswith('#'):
            p = l.split('\t')
            land[p[0]] = p[4]
    saetze = [r for r in H.load_records() if not r['current'] and r['lat'] is not None]
    for meer, (datei, var) in MEERE.items():
        la, lo, std, p99, gut = kennzahlen(datei, var)
        LA, LO = np.meshgrid(la, lo, indexing='ij')
        zl, zo, zs, zp = LA[gut], LO[gut], std[gut], p99[gut]
        print('%s: %d Meerzellen, Schwankung (Std) Median %.1f cm, 90 %% %.1f cm' % (
            meer, len(zs), 100 * np.median(zs), 100 * np.percentile(zs, 90)))
        orte = []
        for l in open(os.path.join(gn, 'cities5000.txt'), encoding='utf-8'):
            p = l.rstrip('\n').split('\t')
            y, x = float(p[4]), float(p[5])
            if not (la.min() - 0.1 < y < la.max() + 0.1 and lo.min() - 0.1 < x < lo.max() + 0.1):
                continue
            d = np.hypot((zl - y) * 111.2, (zo - x) * 111.2 * math.cos(math.radians(y)))
            i = int(np.argmin(d))
            if d[i] > KUESTE_KM:
                continue
            ns = min((H.km({'lat': y, 'lon': x}, r) for r in saetze
                      if abs(r['lat'] - y) < 0.5 and abs(r['lon'] - x) < 1.0), default=999.0)
            if ns <= LUECKE_KM:
                continue
            orte.append(dict(land=land.get(p[8], p[8]), cc=p[8], region=adm.get('%s.%s' % (p[8], p[10]), ''),
                             name=p[1], einwohner=int(p[14] or 0), lat=y, lon=x,
                             meer_lat='%.4f' % zl[i], meer_lon='%.4f' % zo[i], meer_km='%.1f' % d[i],
                             naechster_satz_km='%.0f' % ns, std_cm='%.1f' % (100 * zs[i]),
                             p99_cm='%.0f' % (100 * zp[i]), tz=p[17]))
        orte.sort(key=lambda o: -float(o['std_cm']))
        aus = os.path.join(ROOT, 'harmonics/help/windstau_luecken_%s.csv' % meer)
        with open(aus, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(orte[0]) if orte else ['name'])
            w.writeheader()
            w.writerows(orte)
        print('  %d Orte ohne Satz <= %.0f km -> %s' % (len(orte), LUECKE_KM, os.path.relpath(aus, ROOT)))
        for o in orte:
            print('   %-22s %-18s %-24s %7d  Std %5s cm  99%% %4s cm  Satz %4s km' % (
                o['land'][:22], o['region'][:18], o['name'][:24], o['einwohner'], o['std_cm'], o['p99_cm'],
                o['naechster_satz_km']))


if __name__ == '__main__':
    main(sys.argv[1:])
