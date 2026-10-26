#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weltweite Lueckensuche: Kuestenorte ohne Satz, an denen FES nachweislich gut trifft (Oliver 26.10.2026).

Nach dem Brasilien-Muster (py/fes_neu_geeicht.py): Orte aus GeoNames cities15000 (ab 15000 Einwohnern),
  * an der Kueste: Meer (global_land_mask) innerhalb KUESTE_KM,
  * Luecke: kein Gezeitensatz (ohne Stroeme) innerhalb LUECKE_KM,
  * nennenswerte Tide: FES-Springhub 2(M2+S2) am naechsten Meerpunkt >= MIN_HUB m,
  * FES lokal gut: Mess-/Amtssaetze (utide_observations, ticon, tidetables, ATT-Standardhaefen) innerhalb
    REF_KM; FES-Fehler je Satz wie health_check.curve_diff ueber M2 S2 N2 K1 O1 relativ zur Tidengroesse.
    Urteil gut = mindestens 2 Referenzen, Median < GUT und keine ueber SCHLECHT; einzeln = 1 Referenz < GUT;
    sonst unsicher/schlecht.
Ergebnis: harmonics/help/luecken_fes_welt.csv und Uebersicht je Land. Schreibt keine Saetze.

Usage: venv/bin/python py/luecken_fes_welt.py <pfad/zu/geonames>   (cities15000.txt, admin1CodesASCII.txt, countryInfo.txt)
"""
import cmath
import collections
import csv
import math
import os
import re
import statistics as st
import sys

import netCDF4 as nc
import numpy as np
from global_land_mask import globe

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR, ROOT                # noqa: E402

KUESTE_KM, LUECKE_KM, MIN_HUB, REF_KM, GUT, SCHLECHT = 5.0, 20.0, 1.0, 150.0, 6.0, 15.0
K = ['M2', 'S2', 'N2', 'K1', 'O1']
SP = {'M2': 28.9841042, 'S2': 30.0, 'N2': 28.4397295, 'K1': 15.0410686, 'O1': 13.9430356}
REF_DATEI = re.compile(r'utide_observations|ticon|utide_tidetables|att_np20\d\.txt|puertos|big_srgi|khoa')
AUS = os.path.join(ROOT, 'harmonics/help/luecken_fes_welt.csv')


def meer(la, lo):
    return not globe.is_land(max(-89.9, min(89.9, la)), ((lo + 180) % 360) - 180)


def meerpunkt(la, lo):
    """naechster Meerpunkt bis KUESTE_KM (0,5-km-Schritte, 16 Richtungen) -> (lat, lon) oder None"""
    if meer(la, lo):
        return la, lo
    for d in np.arange(0.5, KUESTE_KM + 0.01, 0.5):
        for az in range(0, 360, 22):
            p = (la + d / 111.2 * math.cos(math.radians(az)), lo + d / (111.2 * max(0.1, math.cos(math.radians(la)))) * math.sin(math.radians(az)))
            if meer(*p):
                return p
    return None


def main(argv):
    gn = argv[0]
    adm = {}
    for l in open(os.path.join(gn, 'admin1CodesASCII.txt'), encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        adm[f[0]] = f[1]
    land = {}
    for l in open(os.path.join(gn, 'countryInfo.txt'), encoding='utf-8'):
        if not l.startswith('#'):
            f = l.split('\t')
            land[f[0]] = f[4]
    F = {k: nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in K}

    def fes(la, lo):
        out = {}
        for k in K:
            a, g = sample(F[k], la, lo)
            if a:
                out[k] = cmath.rect(a, math.radians(g))
        return out

    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    lat = np.radians([r['lat'] for r in recs]); lon = np.radians([r['lon'] for r in recs])

    def naechster_km(la, lo):
        a, b = math.radians(la), math.radians(lo)
        x = np.sin((lat - a) / 2) ** 2 + np.cos(a) * np.cos(lat) * np.sin((lon - b) / 2) ** 2
        return float(6371 * 2 * np.arcsin(np.sqrt(x.min())))

    # Referenzen: FES-Fehler je Mess-/Amtssatz. Saetze, deren Kopf FES nennt (Peru-DHN 10.10.2026 durch FES ersetzt,
    # FES-Ersatz-Saetze), messen FES an sich selbst -> raus.
    texte, refs = {}, []
    for r in recs:
        if 'fes2022' in r['file'] or not REF_DATEI.search(os.path.basename(r['file'])) or 'secondary' in r['file']:
            continue
        if r['file'] not in texte:
            texte[r['file']] = open(r['file'], encoding='iso-8859-1').read().split('\n')
        T = texte[r['file']]
        i = T.index(r['name'])
        a = i
        while a > 0 and T[a - 1].startswith('#'):
            a -= 1
        if 'FES' in '\n'.join(T[a:i]):
            continue
        try:
            _z, w, e, mer = X.satz_lesen(r['file'], r['name'])
        except Exception:                                            # noqa: BLE001
            continue
        f_ = 0.3048 if e.startswith('f') else 1.0
        v = {k: cmath.rect(w[k][0] * f_, math.radians(X.greenwich(w[k][1], SP[k], mer))) for k in K if k in w and w[k][0] > 0}
        fv = fes(r['lat'], r['lon'])
        cs = [k for k in K if k in v and k in fv]
        if 'M2' not in cs or 'K1' not in cs:
            continue
        tot = sum(abs(v[k]) for k in cs)
        if tot < 0.15:
            continue
        refs.append((r['lat'], r['lon'], 100 * math.sqrt(sum(abs(v[k] - fv[k]) ** 2 for k in cs) / 2) / tot))
    rla = np.radians([x[0] for x in refs]); rlo = np.radians([x[1] for x in refs]); rerr = np.array([x[2] for x in refs])
    print('%d Referenzsaetze, FES-Fehler Median %.1f %%' % (len(refs), float(np.median(rerr))), flush=True)

    zeilen = []
    for l in open(os.path.join(gn, 'cities15000.txt'), encoding='utf-8'):
        f = l.rstrip('\n').split('\t')
        name, la, lo, cc, a1, pop, tz = f[1], float(f[4]), float(f[5]), f[8], f[10], int(f[14] or 0), f[17]
        if pop < 15000 or abs(la) > 70:
            continue
        mp = meerpunkt(la, lo)
        if not mp:
            continue
        d = naechster_km(la, lo)
        if d <= LUECKE_KM:
            continue
        fv = fes(*mp)
        if 'M2' not in fv:
            continue
        hub = 2 * (abs(fv['M2']) + abs(fv.get('S2', 0)))
        if hub < MIN_HUB:
            continue
        a, b = math.radians(mp[0]), math.radians(mp[1])
        x = np.sin((rla - a) / 2) ** 2 + np.cos(a) * np.cos(rla) * np.sin((rlo - b) / 2) ** 2
        dk = 6371 * 2 * np.arcsin(np.sqrt(x))
        e = rerr[dk <= REF_KM]
        if len(e) >= 2 and np.median(e) < GUT and e.max() < SCHLECHT:
            urteil = 'gut'
        elif len(e) == 1 and e[0] < GUT:
            urteil = 'einzeln'
        elif len(e) == 0:
            urteil = 'ohne Referenz'
        elif np.median(e) < GUT:
            urteil = 'gemischt'
        else:
            urteil = 'schlecht'
        zeilen.append(dict(land=land.get(cc, cc), cc=cc, region=adm.get('%s.%s' % (cc, a1), ''), name=name, einwohner=pop,
                           lat='%.4f' % la, lon='%.4f' % lo, meer_lat='%.4f' % mp[0], meer_lon='%.4f' % mp[1],
                           naechster_satz_km='%.0f' % d, springhub_m='%.1f' % hub, refs=len(e),
                           fes_median_pct='%.1f' % float(np.median(e)) if len(e) else '', fes_max_pct='%.1f' % float(e.max()) if len(e) else '',
                           urteil=urteil, tz=tz))
    zeilen.sort(key=lambda z: (z['land'], z['region'], -z['einwohner']))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    c = collections.Counter(z['urteil'] for z in zeilen)
    print('%d Luecken-Orte: %s' % (len(zeilen), dict(c)))
    pl = collections.defaultdict(collections.Counter)
    for z in zeilen:
        pl[z['land']][z['urteil']] += 1
    for k, v in sorted(pl.items(), key=lambda x: -x[1]['gut']):
        if v['gut'] or v['einzeln']:
            print('  %-28s gut %3d  einzeln %3d  gemischt %3d  schlecht %3d  ohne Ref %3d' % (k[:28], v['gut'], v['einzeln'], v['gemischt'], v['schlecht'], v['ohne Referenz']))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
