#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATT-Nebenorte (Part II) gegen FES, gruppiert nach Bezugshafen (Oliver 26.10.2026).

Anlass Jamaika: alle 8 NP202-Nebenorte (Transfer von Cristobal, Panama) lagen systematisch neben FES, und
FES traf dort den Messpegel Port Royal auf 2-4 Grad. Gesucht werden weitere solche Gruppen.

Gewertet wird ein Nebenort nur, wo FES lokal bestaetigt ist: mindestens 2 Mess-/Amtssaetze bis REF_KM mit
FES-Fehler-Median < GUT (ohne Saetze, deren Kopf FES nennt). Auffaellig = FES-Fehler des Nebenorts > AUFFAELLIG.
Gruppe = gleicher Bezugshafen ("Transfer von X"); gemeldet ab 2 auffaelligen Orten.
Fehlermass wie health_check.curve_diff ueber M2 S2 N2 K1 O1 relativ zur Tidengroesse; dazu M2-/K1-Versatz.

Usage: venv/bin/python py/att_neben_gruppen.py   -> harmonics/help/att_neben_gruppen.csv
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import xtide_modell as X                                           # noqa: E402
from fes_ersatz_inseln import sample, FES_DIR, ROOT                # noqa: E402
from luecken_fes_welt import REF_DATEI, K, SP                      # noqa: E402

REF_KM, GUT, AUFFAELLIG = 150.0, 6.0, 15.0
AUS = os.path.join(ROOT, 'harmonics/help/att_neben_gruppen.csv')


def main(argv):
    F = {k: nc.Dataset(os.path.join(FES_DIR, '%s_fes2022.nc' % k.lower())) for k in K}
    texte = {}

    def kopf(r):
        if r['file'] not in texte:
            texte[r['file']] = open(r['file'], encoding='iso-8859-1').read().split('\n')
        T = texte[r['file']]
        i = T.index(r['name'])
        a = i
        while a > 0 and T[a - 1].startswith('#'):
            a -= 1
        return '\n'.join(T[a:i])

    def fehler(r):
        _z, w, e, mer = X.satz_lesen(r['file'], r['name'])
        f_ = 0.3048 if e.startswith('f') else 1.0
        v = {k: cmath.rect(w[k][0] * f_, math.radians(X.greenwich(w[k][1], SP[k], mer))) for k in K if k in w and w[k][0] > 0}
        fv = {}
        for k in K:
            a, g = sample(F[k], r['lat'], r['lon'])
            if a:
                fv[k] = cmath.rect(a, math.radians(g))
        cs = [k for k in K if k in v and k in fv]
        if 'M2' not in cs or 'K1' not in cs:
            return None
        tot = sum(abs(v[k]) for k in cs)
        if tot < 0.15:
            return None
        pct = 100 * math.sqrt(sum(abs(v[k] - fv[k]) ** 2 for k in cs) / 2) / tot
        dt = {k: (math.degrees(cmath.phase(v[k] / fv[k])) / SP[k] * 60) for k in ('M2', 'K1')}
        return pct, dt['M2'], dt['K1'], abs(v['M2']) / abs(fv['M2'])

    recs = [r for r in H.load_records() if r['lat'] is not None and not r['current']]
    refs = []
    for r in recs:
        b = os.path.basename(r['file'])
        if 'fes2022' in b or not REF_DATEI.search(b) or 'secondary' in b or 'FES' in kopf(r):
            continue
        f = fehler(r)
        if f:
            refs.append((r['lat'], r['lon'], f[0]))
    rla = np.radians([x[0] for x in refs]); rlo = np.radians([x[1] for x in refs]); rerr = np.array([x[2] for x in refs])
    zeilen = []
    for r in recs:
        if 'att_np' not in r['file'] or 'secondary' not in r['file']:
            continue
        m = re.search(r'[Tt]ransfer (?:von|from) (.+?) \(att', kopf(r))
        bezug = m.group(1) if m else '?'
        f = fehler(r)
        if not f:
            continue
        a, b = math.radians(r['lat']), math.radians(r['lon'])
        x = np.sin((rla - a) / 2) ** 2 + np.cos(a) * np.cos(rla) * np.sin((rlo - b) / 2) ** 2
        e = rerr[6371 * 2 * np.arcsin(np.sqrt(x)) <= REF_KM]
        bestaetigt = len(e) >= 2 and np.median(e) < GUT
        zeilen.append(dict(datei=os.path.basename(r['file']), name=r['name'], lat=r['lat'], lon=r['lon'], bezug=bezug,
                           fes_fehler_pct='%.1f' % f[0], m2_min='%.0f' % f[1], k1_min='%.0f' % f[2], m2_faktor='%.2f' % f[3],
                           fes_lokal='%d/%.1f' % (len(e), float(np.median(e)) if len(e) else -1),
                           auffaellig='ja' if bestaetigt and f[0] > AUFFAELLIG else ('nein' if bestaetigt else 'FES unbestaetigt')))
    with open(AUS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    g = collections.defaultdict(list)
    for z in zeilen:
        g[(z['datei'], z['bezug'])].append(z)
    print('%d Nebenorte, %d mit bestaetigtem FES, davon %d auffaellig' % (
        len(zeilen), sum(z['auffaellig'] != 'FES unbestaetigt' for z in zeilen), sum(z['auffaellig'] == 'ja' for z in zeilen)))
    for (d, b), L in sorted(g.items(), key=lambda x: -sum(z['auffaellig'] == 'ja' for z in x[1])):
        ja = [z for z in L if z['auffaellig'] == 'ja']
        nein = [z for z in L if z['auffaellig'] == 'nein']
        if len(ja) < 2:
            continue
        print('  %-28s Bezug %-30s %2d auffaellig / %2d geprueft / %2d gesamt  M2 %+4.0f min  K1 %+4.0f min  Fehler %4.1f %%' % (
            d[13:41], b[:30], len(ja), len(ja) + len(nein), len(L), st.median(float(z['m2_min']) for z in ja),
            st.median(float(z['k1_min']) for z in ja), st.median(float(z['fes_fehler_pct']) for z in ja)))
    print('->', os.path.relpath(AUS, ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
